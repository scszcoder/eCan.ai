"""CN worker serving mode (Path 1.5, Phase 5).

``cn_worker_main`` is one-shot: load a task, run it, exit. A pod that serves a
fleet has to do the other thing — stay up, take work item after work item, and
keep nothing in memory that a restart would lose::

    accept work -> resume thread -> run one iteration -> persist -> release

The execution core (``run_single_cn`` -> ``_run_skill_once``) is reused
unchanged; what is new is the loop around it, which is what this module owns.

Three properties this has to hold, all of them Path 1.5 rather than plumbing:

* **Durable state.** A serving pod whose checkpointer is in-memory cannot
  survive the restart it exists to survive, so ``serve`` refuses to start on
  one unless explicitly allowed. Phase 0.2 makes that check possible.
* **Headless context.** No MainWindow exists here, so a service locator is
  installed up front (Phase 1.3) and gaps are loud rather than ``None``.
* **Per-item isolation.** One bad work item must not take the pod down with it;
  every item is caught, reported, and the loop continues.

The transport is deliberately NOT invented here. ``serve`` consumes any async
iterable of message strings; ``stdin_intake`` is a working default (newline
-delimited JSON, which a sidecar can feed) and the injection point for whatever
the CN control plane settles on — HTTP, WS, or a queue.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Optional

from utils.logger_helper import logger_helper as logger

# Sentinel a transport can push to ask the loop to drain and stop.
STOP = object()


@dataclass
class ServeStats:
    accepted: int = 0
    completed: int = 0
    failed: int = 0
    started_at: float = field(default_factory=time.time)

    def as_dict(self) -> dict:
        return {
            "accepted": self.accepted,
            "completed": self.completed,
            "failed": self.failed,
            "uptime_s": round(time.time() - self.started_at, 2),
        }


# ---------------------------------------------------------------------------
# Preconditions
# ---------------------------------------------------------------------------

class ServePreconditionFailed(RuntimeError):
    """The pod is not configured to serve safely."""


def require_durable_checkpointer(allow_ephemeral: bool = False) -> None:
    """A serving pod must be able to survive its own restart.

    With an in-memory saver every conversation in flight dies with the process,
    which is the exact failure durable residency exists to prevent. Set
    ECAN_SERVE_ALLOW_EPHEMERAL=1 (or pass allow_ephemeral) for a local smoke
    test where that is understood and fine.
    """
    from agent.checkpointing import is_durable, ENV_KIND

    if is_durable():
        return

    if allow_ephemeral or (os.environ.get("ECAN_SERVE_ALLOW_EPHEMERAL") or "").strip().lower() in ("1", "true", "yes", "on"):
        logger.warning(
            "[cn_serve] Serving with an EPHEMERAL checkpointer: conversations "
            "in flight will not survive a restart. Development only."
        )
        return

    raise ServePreconditionFailed(
        f"Serving mode needs a durable checkpointer; {ENV_KIND} is unset or "
        f"'memory'. Set {ENV_KIND}=postgres with ECAN_CHECKPOINTER_DSN, or set "
        f"ECAN_SERVE_ALLOW_EPHEMERAL=1 to accept losing in-flight conversations."
    )


def build_cn_headless_context(client: Any = None):
    """A headless service locator carrying what the CN worker actually has.

    Honest about its limits: the worker can supply identity and endpoint today,
    not the full ~15-service surface. Installed non-strict so a gap raises when
    a skill reaches for it — naming the service — instead of blocking startup
    on services this pod may never need.
    """
    from headless_context import HeadlessAppContext

    services: dict = {}
    if client is not None:
        owner = getattr(client, "owner", None) or os.environ.get("ECAN_TASK_OWNER") or ""
        if owner:
            services["user"] = owner
        endpoint = getattr(client, "endpoint", None)
        if endpoint:
            services["getWanApiEndpoint"] = endpoint
        token = getattr(client, "access_token", None)
        if token:
            services["get_auth_token"] = token

    return HeadlessAppContext(browser_capable=False, services=services)


# ---------------------------------------------------------------------------
# Intake
# ---------------------------------------------------------------------------

async def stdin_intake() -> AsyncIterator[str]:
    """Newline-delimited JSON on stdin — one work item per line.

    A real transport (a sidecar can pipe into it) and the seam for whatever the
    control plane ends up using. A blank line is ignored; EOF ends the loop.
    """
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:                      # EOF
            return
        line = line.strip()
        if not line:
            continue
        yield line


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------

async def serve(
    intake: AsyncIterator[Any],
    *,
    handler: Optional[Callable[[str], Awaitable[None]]] = None,
    install_context: bool = True,
    allow_ephemeral: bool = False,
    max_items: Optional[int] = None,
) -> ServeStats:
    """Serve work items until the intake is exhausted or STOP arrives.

    ``handler`` defaults to the one-shot execution core, so serving and
    single-shot run exactly the same code per item.
    """
    require_durable_checkpointer(allow_ephemeral=allow_ephemeral)

    if handler is None:
        from agent.cloud_worker.cn_worker_main import run_single_cn
        handler = run_single_cn

    ctx = None
    if install_context:
        from headless_context import install_headless_context
        ctx = build_cn_headless_context()
        install_headless_context(ctx, strict=False)
        missing = sorted(ctx.missing_expected())
        if missing:
            logger.warning(
                f"[cn_serve] Headless context is partial; these raise on use: {missing}"
            )

    stats = ServeStats()
    logger.info("[cn_serve] serving; waiting for work")

    try:
        async for item in intake:
            if item is STOP:
                logger.info("[cn_serve] STOP received; draining")
                break

            stats.accepted += 1
            item_id = _describe(item)
            try:
                await handler(item if isinstance(item, str) else json.dumps(item))
                stats.completed += 1
                logger.info(f"[cn_serve] item {item_id} completed "
                            f"({stats.completed}/{stats.accepted})")
            except Exception as exc:
                # Per-item isolation: a bad item must not take the pod down.
                stats.failed += 1
                logger.error(f"[cn_serve] item {item_id} FAILED: {exc}", exc_info=True)

            if max_items is not None and stats.accepted >= max_items:
                logger.info(f"[cn_serve] reached max_items={max_items}; stopping")
                break
    finally:
        if install_context:
            from headless_context import uninstall_headless_context
            uninstall_headless_context()
        logger.info(f"[cn_serve] stopped: {stats.as_dict()}")

    return stats


def _describe(item: Any) -> str:
    """A short, log-safe id for a work item."""
    try:
        data = json.loads(item) if isinstance(item, str) else item
        if isinstance(data, dict):
            return str(data.get("task_id") or data.get("run_id") or "?")
    except Exception:
        pass
    return "?"
