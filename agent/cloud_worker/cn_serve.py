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

That seam now has its real counterpart: ``fleet_intake`` polls the server-side
turn queue (``turn_claim``) and yields turns, and ``make_turn_handler`` wraps
the same per-item core with heartbeating and a ``turn_done`` report. Neither
changes the loop — which is the point of having written the loop against an
async iterable.
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


class Shutdown:
    """Set when the pod is asked to stop.

    Kubernetes sends SIGTERM and then waits `terminationGracePeriodSeconds`
    before SIGKILL. Without handling it the pod is killed mid-turn and the
    customer waits for the server-side reaper to notice a stale heartbeat —
    ~120s of silence for something that could have been clean.

    Draining means two different things and both matter: stop CLAIMING at once
    (so no new work is taken hostage), and finish what is already in flight.
    """

    __slots__ = ("_event",)

    def __init__(self) -> None:
        self._event = asyncio.Event()

    def requested(self) -> bool:
        return self._event.is_set()

    def request(self) -> None:
        self._event.set()

    async def wait(self) -> None:
        await self._event.wait()


class Capacity:
    """How many turns this pod may hold at once.

    Shared deliberately between ``serve`` and ``fleet_intake``: the loop marks a
    slot taken when it starts a turn and frees it when the turn ends, and the
    intake refuses to CLAIM while full. Without that second half a pod at
    capacity keeps taking turns off the queue and sitting on them — hoarding
    work other pods could be running, and heartbeating turns it has not started.

    The number must match what ``vehicle_register`` advertises as
    ``max_concurrent_tasks``; a pod that claims more than it can run tells the
    placement side something untrue.
    """

    __slots__ = ("limit", "in_use", "_slot_freed")

    def __init__(self, limit: int = 1) -> None:
        self.limit = max(1, int(limit or 1))
        self.in_use = 0
        # Set whenever a slot frees. serve() waits on this; fleet_intake only
        # peeks with free(), because it must keep looping to heartbeat.
        self._slot_freed = asyncio.Event()
        self._slot_freed.set()

    def free(self) -> bool:
        return self.in_use < self.limit

    async def acquire(self) -> None:
        """Block until a slot is free, then take it.

        serve() enforces the bound HERE rather than trusting the intake to do
        it. The first version only tracked usage and let the intake gate
        claiming, which meant any intake that did not know about capacity —
        stdin_intake, or a test feeding a plain list — ran every item at once.
        A bound the owner does not enforce is not a bound.
        """
        while not self.free():
            self._slot_freed.clear()
            await self._slot_freed.wait()
        self.take()

    def take(self) -> None:
        self.in_use += 1

    def give(self) -> None:
        self.in_use = max(0, self.in_use - 1)
        self._slot_freed.set()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Capacity({self.in_use}/{self.limit})"


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
# Fleet intake — the turn queue
#
# The server hands out work through ``turn_claim``: one queued turn whose
# ``requires[]`` this pod's ``capabilities[]`` satisfy, or nothing. "Nothing" is
# the normal steady state, so an idle pod backs off instead of hammering the
# control plane, and resets the moment it gets work.
# ---------------------------------------------------------------------------

DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_IDLE_BACKOFF_MAX = 15.0
DEFAULT_VEHICLE_HEARTBEAT = 60.0
DEFAULT_TURN_HEARTBEAT = 30.0


async def fleet_intake(
    fleet,
    *,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    idle_backoff_max: float = DEFAULT_IDLE_BACKOFF_MAX,
    vehicle_heartbeat_interval: float = DEFAULT_VEHICLE_HEARTBEAT,
    max_turns: Optional[int] = None,
    capacity: Optional[Capacity] = None,
    shutdown: Optional[Shutdown] = None,
) -> AsyncIterator[str]:
    """Yield claimed turns as JSON strings, forever.

    Errors claiming are logged and retried, never raised: a control plane blip
    must not take a pod out of the fleet, and the server's own reaper requeues
    anything this pod dropped.
    """
    claimed = 0
    delay = poll_interval
    last_vehicle_beat = 0.0

    while max_turns is None or claimed < max_turns:
        # Draining: stop taking new work immediately. Anything already claimed
        # is finished by serve(); anything still queued stays queued for another
        # pod, which is strictly better than claiming it and dying holding it.
        if shutdown is not None and shutdown.requested():
            logger.info("[cn_serve] shutdown requested; no longer claiming")
            return

        now = time.time()
        if now - last_vehicle_beat >= vehicle_heartbeat_interval:
            last_vehicle_beat = now
            try:
                await fleet.heartbeat_vehicle()
            except Exception as exc:
                logger.warning(f"[cn_serve] vehicle heartbeat failed (non-fatal): {exc}")

        # Full: do not claim. Keep looping anyway — the vehicle heartbeat above
        # is what keeps this pod in the roster, and skipping it while busy would
        # get a perfectly healthy pod reaped as dead.
        if capacity is not None and not capacity.free():
            await asyncio.sleep(poll_interval)
            continue

        try:
            turn = await fleet.claim_turn()
        except Exception as exc:
            logger.warning(f"[cn_serve] turn_claim failed, backing off: {exc}")
            turn = None

        if turn is None:
            await asyncio.sleep(delay)
            delay = min(delay * 2, idle_backoff_max)
            continue

        delay = poll_interval
        claimed += 1
        logger.info(
            f"[cn_serve] claimed turn {turn.get('id')} "
            f"conversation={turn.get('conversationId')} attempt={turn.get('attempt')}"
        )
        yield json.dumps(turn, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Turn -> work item
# ---------------------------------------------------------------------------

class TurnMappingError(ValueError):
    """A claimed turn cannot be mapped to something this worker can run."""


def turn_to_worker_message(turn: dict) -> str:
    """Translate a claimed turn into the message ``run_single_cn`` parses.

    The gap this has to bridge: a turn names an *owner, conversation, agent and
    input text*, while the worker loads work by *task id*. Nothing on the turn
    row carries one, so the task is resolved in this order, and a turn that
    resolves to neither is a permanent failure, not a retry:

    1. ``turn.input`` parsed as a JSON object carrying ``task_id`` — the
       structured form an enqueuer can use to name the work exactly;
    2. ``ECAN_TASK_ID`` — a pod pinned to one task, which is the single-tenant
       serving shape.

    ``run_id`` is the turn id, deliberately: a redelivered turn then overwrites
    its own run state instead of opening a second one. The turn id is the
    server's idempotency key and this client never mints its own.
    """
    if not isinstance(turn, dict):
        raise TurnMappingError(f"turn must be an object, got {type(turn).__name__}")

    turn_id = str(turn.get("id") or "").strip()
    if not turn_id:
        raise TurnMappingError("turn has no id")

    raw_input = turn.get("input")
    structured: dict = {}
    text = ""
    if isinstance(raw_input, dict):
        structured = raw_input
    elif isinstance(raw_input, str) and raw_input.strip():
        try:
            parsed = json.loads(raw_input)
            structured = parsed if isinstance(parsed, dict) else {}
        except Exception:
            structured = {}
        if not structured:
            text = raw_input

    text = text or str(structured.get("text") or structured.get("latest_message") or "")

    owner = str(
        turn.get("owner")
        or structured.get("owner_id")
        or structured.get("owner")
        or os.environ.get("ECAN_TASK_OWNER")
        or ""
    ).strip()
    # Resolution order, most specific first:
    #   1. the turn's own task — the server resolves it from the routed agent at
    #      enqueue (agent_task_rels) and stores it on the row, so the turn names
    #      its own work;
    #   2. a task_id embedded in a structured input, for callers that name it;
    #   3. ECAN_TASK_ID — a pod pinned to ONE task, which is the single-tenant
    #      shape and the reason this pod could previously only serve one task no
    #      matter which agent a turn was routed to.
    #
    # 3 stays as a fallback because `agent_task_rels` is empty in production
    # today; once agents have tasks linked, 1 wins and the env var can go.
    task_id = str(
        turn.get("taskId")
        or turn.get("task_id")
        or structured.get("task_id")
        or structured.get("taskId")
        or os.environ.get("ECAN_TASK_ID")
        or ""
    ).strip()

    if not owner:
        raise TurnMappingError(f"turn {turn_id} has no owner and ECAN_TASK_OWNER is unset")
    if not task_id:
        raise TurnMappingError(
            f"turn {turn_id} names no task: put task_id in the turn input JSON, "
            f"or pin this pod to one with ECAN_TASK_ID"
        )

    conversation_id = str(turn.get("conversationId") or turn.get("conversation_id") or "")
    agent_id = str(turn.get("agentId") or turn.get("agent_id") or "")

    options = dict(structured.get("options") or {})
    options.update({
        "run_id": turn_id,
        "turn_id": turn_id,
        "conversation_id": conversation_id,
        "agent_id": agent_id,
    })

    test_inputs = structured.get("testInputs") or structured.get("test_inputs")
    options["testInputs"] = dict(test_inputs) if isinstance(test_inputs, dict) else {
        "text": text,
        "conversation_id": conversation_id,
    }

    # Phase 2.2, on the path where it is actually knowable: the turn names its
    # conversation, so the thread key needs no payload sniffing. Still behind
    # ECAN_CONVERSATION_THREADS — off, this is a per-turn thread exactly as
    # before.
    from agent.conversation_threads import conversation_threads_enabled, thread_id_for

    if conversation_threads_enabled() and conversation_id:
        options["thread_id"] = thread_id_for(agent_id, conversation_id)

    return json.dumps(
        {"owner_id": owner, "task_id": task_id, "options": options}, ensure_ascii=False
    )


# ---------------------------------------------------------------------------
# Turn handler — heartbeat while running, report when done
# ---------------------------------------------------------------------------

async def _heartbeat_turn(fleet, turn_id: str, interval: float) -> None:
    """Keep one claimed turn alive until cancelled.

    A turn that legitimately runs longer than the server's stale window has to
    heartbeat *during* the run — after it is too late, the reaper has already
    requeued it and a second pod is answering the same customer.
    """
    while True:
        await asyncio.sleep(interval)
        try:
            alive = await fleet.heartbeat_turns([turn_id])
            if turn_id not in alive:
                logger.warning(
                    f"[cn_serve] turn {turn_id} is no longer ours (reaped or reassigned); "
                    f"still running it locally"
                )
        except Exception as exc:
            logger.warning(f"[cn_serve] turn heartbeat failed (non-fatal): {exc}")


def _json_safe_result(result: Any) -> dict:
    """A turn result the server can store as jsonb.

    The skill's return value is whatever the skill produced; anything that will
    not serialise is reported as its text rather than failing the report, since
    losing the outcome of a completed turn is worse than losing its shape.
    """
    if isinstance(result, dict):
        try:
            json.dumps(result, ensure_ascii=False)
            return result
        except Exception:
            pass
    if result is None:
        return {}
    return {"text": str(result)[:4000]}


def make_turn_handler(
    fleet,
    *,
    core: Optional[Callable[[str], Awaitable[Any]]] = None,
    heartbeat_interval: float = DEFAULT_TURN_HEARTBEAT,
) -> Callable[[str], Awaitable[None]]:
    """Wrap the per-item core with turn heartbeating and a ``turn_done`` report.

    Returned callable is a ``serve()`` handler: it takes the item the intake
    yielded and raises on failure, so the loop's per-item isolation and its
    failure counter keep working unchanged.
    """
    if core is None:
        from agent.cloud_worker.cn_worker_main import run_single_cn
        core = run_single_cn

    async def handle(item: str) -> None:
        from agent.ec_skills.usage_window import snapshot

        turn = json.loads(item) if isinstance(item, str) else dict(item)
        turn_id = str(turn.get("id") or "")

        try:
            message = turn_to_worker_message(turn)
        except TurnMappingError as exc:
            # Permanent: a second attempt maps to the same nothing. Reporting it
            # as retryable would burn every attempt and read as a flaky worker.
            logger.error(f"[cn_serve] turn {turn_id} unmappable: {exc}")
            await _report(fleet, turn_id, status="failed", error=str(exc), retry=False)
            raise

        before = snapshot()
        beat = asyncio.create_task(_heartbeat_turn(fleet, turn_id, heartbeat_interval))
        try:
            result = await core(message)
        except Exception as exc:
            await _report(
                fleet, turn_id, status="failed", error=str(exc),
                usage=snapshot() - before,
            )
            raise
        else:
            await _report(
                fleet, turn_id, status="done", result=_json_safe_result(result),
                usage=snapshot() - before,
            )
        finally:
            beat.cancel()

    return handle


async def _report(fleet, turn_id: str, *, status: str, result: Optional[dict] = None,
                  error: str = "", usage: Any = None, retry: Optional[bool] = None) -> None:
    """Report an outcome. Never raises — the run already happened.

    A failed report is a real loss (the server will reap and requeue the turn,
    and the customer may be answered twice), so it is logged loudly; but raising
    here would replace one problem with a dead pod.
    """
    try:
        await fleet.finish_turn(
            turn_id,
            status=status,
            result=result,
            error=error,
            cost_usd=getattr(usage, "cost_usd", 0.0) or 0.0,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            retry=retry,
        )
        if usage is not None:
            logger.info(
                f"[cn_serve] turn {turn_id} reported {status}: "
                f"{getattr(usage, 'input_tokens', 0)}in/{getattr(usage, 'output_tokens', 0)}out "
                f"${getattr(usage, 'cost_usd', 0.0):.4f}"
            )
    except Exception as exc:
        logger.error(
            f"[cn_serve] FAILED to report turn {turn_id} as {status}: {exc}. "
            f"The server will treat it as abandoned and requeue it."
        )


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
    capacity: Optional[Capacity] = None,
    shutdown: Optional[Shutdown] = None,
) -> ServeStats:
    """Serve work items until the intake is exhausted or STOP arrives.

    ``handler`` defaults to the one-shot execution core, so serving and
    single-shot run exactly the same code per item.

    Up to ``capacity.limit`` turns run concurrently. This is not an
    optimisation detail — it decides what the fleet costs. A turn is mostly
    spent awaiting an LLM, so a pod that runs them one at a time is idle for
    almost all of its billed life, and serving N concurrent conversations needs
    N pods. At 256 peak that is 256 pods against roughly 8.

    Concurrency is bounded rather than unbounded because each in-flight turn
    holds a checkpointer connection and an LLM call; the bound is the same
    number the pod advertises to the scheduler.
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
    slots = capacity if capacity is not None else Capacity(1)
    inflight: set = set()
    logger.info(f"[cn_serve] serving; waiting for work (concurrency={slots.limit})")

    async def _run_one(item: Any, item_id: str) -> None:
        try:
            await handler(item if isinstance(item, str) else json.dumps(item))
            stats.completed += 1
            logger.info(f"[cn_serve] item {item_id} completed "
                        f"({stats.completed}/{stats.accepted})")
        except Exception as exc:
            # Per-item isolation: a bad item must not take the pod down.
            stats.failed += 1
            logger.error(f"[cn_serve] item {item_id} FAILED: {exc}", exc_info=True)
        finally:
            slots.give()

    try:
        async for item in intake:
            if item is STOP:
                logger.info("[cn_serve] STOP received; draining")
                break
            if shutdown is not None and shutdown.requested():
                logger.info("[cn_serve] shutdown requested; draining")
                break

            # Blocks while full. fleet_intake also declines to claim when
            # full, which keeps unstartable work off this pod; this is the
            # guard that holds regardless of which intake is wired in.
            await slots.acquire()
            # Re-check AFTER acquiring: waiting for a slot can take as long as
            # the longest running turn, and SIGTERM may well arrive during that
            # wait. Checking only before the wait let a turn start on a pod that
            # had already been told to stop.
            if shutdown is not None and shutdown.requested():
                slots.give()
                logger.info("[cn_serve] shutdown requested while waiting for a slot; draining")
                break
            stats.accepted += 1
            item_id = _describe(item)
            task = asyncio.create_task(_run_one(item, item_id))
            inflight.add(task)
            task.add_done_callback(inflight.discard)

            if max_items is not None and stats.accepted >= max_items:
                logger.info(f"[cn_serve] reached max_items={max_items}; stopping")
                break
    finally:
        if inflight:
            logger.info(f"[cn_serve] draining {len(inflight)} in-flight turn(s)")
            await asyncio.gather(*inflight, return_exceptions=True)
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
