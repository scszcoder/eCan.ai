"""
Subprocess runtime lane.

Lets a hook author ship an executable in **any language** (Node, Go, Rust,
.NET, a shell script) and have the dispatcher drive it via JSON-lines over
stdin/stdout.  Good for re-using legacy business logic without porting it
to Python.

Authoring contract
==================

The subprocess reads ONE JSON object per line from stdin and writes ONE
JSON object per line to stdout.  Every request JSON looks like::

    {
      "trace_id": "...",
      "span_id":  "...",
      "step":     <int>,
      "manifest": {... HookManifest ...},
      "config":   {...},
      "payload":  <any>
    }

The response JSON must look like::

    {
      "decision": "continue" | "replace" | "bypass" | ...,
      "payload":  <any, optional>,
      "reason":   "<optional string>",
      "handoff_agent": "<optional string>"
    }

Manifest entry (YAML)::

    - name: legacy_score
      runtime: subprocess
      entrypoint: ["node", "hook.js"]      # argv, first element is exe
      stage: on_event_normalized
      tier: 1
      priority: 30
      permissions: {tools: []}
      budget: {timeout_ms: 1200}

Lifecycle
=========

The lane uses a lazy, per-hook persistent process:

* First dispatch spawns the process.
* Subsequent dispatches reuse the same stdio pair.
* Timeouts kill + respawn (counted against the circuit breaker).
* Agent shutdown kills every lane process via ``shutdown()``.

Failure behaviour
=================

* Fail-open (``Decision.CONTINUE``) on missing executable, spawn errors,
  JSON parse errors, and timeouts.
* Crashed processes are respawned on the next request; the dispatcher's
  circuit breaker will stop asking if the hook misbehaves repeatedly.

Security
========

Subprocess lane hooks cannot be Tier-0.  The runtime does NOT sandbox the
child process — it inherits the agent's file-system and network privileges.
Operators deploying an untrusted bundle should run the whole agent in a
container or deny-list the bundle at the loader.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import sys
from pathlib import Path
from typing import Any

from ...hook_api import (
    BypassAction,
    Decision,
    HookContext,
    HookManifest,
    HookResult,
)
from .js_lane import _parse_js_decision  # reused: identical response shape

logger = logging.getLogger(__name__)


def _normalize_argv(entrypoint: Any, bundle_dir: Path | None) -> list[str]:
    """Turn ``entrypoint`` into an argv list, resolving relative file
    paths against the bundle dir when provided."""
    if isinstance(entrypoint, str):
        argv = shlex.split(entrypoint)
    elif isinstance(entrypoint, (list, tuple)):
        argv = [str(x) for x in entrypoint]
    else:
        raise TypeError(
            f"subprocess entrypoint must be str or list, got {type(entrypoint).__name__}"
        )
    if not argv:
        raise ValueError("subprocess entrypoint is empty")

    # argv[0] is the executable; argv[1:] are arguments.  If argv[1] is a
    # relative path that exists inside the bundle dir, rewrite it so the
    # child runs regardless of the agent's cwd.
    if bundle_dir is not None and len(argv) >= 2:
        candidate = bundle_dir / argv[1]
        if candidate.is_file():
            argv[1] = str(candidate)
    return argv


# ---------------------------------------------------------------------------
# Lane hook.
# ---------------------------------------------------------------------------
class SubprocessLaneHook:
    """Shim hook that forwards each call to a child process over JSON lines."""

    manifest: HookManifest

    def __init__(
        self,
        *,
        argv: list[str],
        manifest: HookManifest | None = None,
        config: dict | None = None,
        bundle_dir: Path | None = None,
    ):
        self._argv = list(argv)
        self._bundle_dir = bundle_dir
        self.config = dict(config or {})
        if manifest is not None:
            self.manifest = manifest
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()

    @classmethod
    def from_manifest(
        cls,
        manifest: HookManifest,
        bundle_dir: Path | None,
        config: dict | None = None,
    ) -> "SubprocessLaneHook":
        argv = _normalize_argv(manifest.entrypoint, bundle_dir)
        return cls(argv=argv, manifest=manifest, config=config, bundle_dir=bundle_dir)

    # ------------------------------------------------------------- lifecycle
    async def _ensure_proc(self) -> asyncio.subprocess.Process:
        if self._proc is not None and self._proc.returncode is None:
            return self._proc
        logger.info(
            f"[subproc_lane:{getattr(self.manifest, 'name', '?')}] spawning {self._argv}"
        )
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *self._argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._bundle_dir) if self._bundle_dir else None,
            )
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"subprocess executable not found: {self._argv[0]!r} ({e})"
            ) from e
        return self._proc

    async def shutdown(self) -> None:
        """Kill the child process if still running.  Idempotent."""
        if self._proc is None or self._proc.returncode is not None:
            return
        try:
            self._proc.kill()
            await self._proc.wait()
        except Exception:
            pass
        self._proc = None

    # ------------------------------------------------------------- run
    async def run(self, ctx: HookContext, payload: Any) -> HookResult:
        # Build the request envelope.
        try:
            request_obj = {
                "trace_id": getattr(ctx, "trace_id", ""),
                "span_id": getattr(ctx, "span_id", ""),
                "step": int(getattr(ctx, "step", 0) or 0),
                "manifest": (
                    self.manifest.model_dump() if self.manifest is not None else {}
                ),
                "config": dict(getattr(ctx, "config", {}) or {}),
                "payload": payload,
            }
            request_line = json.dumps(request_obj, default=str, ensure_ascii=False) + "\n"
        except Exception as e:
            return HookResult.cont(reason=f"subproc:request_encode:{type(e).__name__}")

        timeout_ms = 500
        if self.manifest is not None:
            timeout_ms = int(getattr(self.manifest.budget, "timeout_ms", 500))

        async with self._lock:
            try:
                proc = await self._ensure_proc()
            except FileNotFoundError as e:
                logger.error(f"[subproc_lane] {e}")
                return HookResult.cont(reason="subproc:executable_missing")
            except Exception as e:
                logger.error(f"[subproc_lane] spawn failed: {e!r}")
                return HookResult.cont(reason="subproc:spawn_failed")

            try:
                proc.stdin.write(request_line.encode("utf-8"))  # type: ignore[union-attr]
                await proc.stdin.drain()  # type: ignore[union-attr]
                raw_line = await asyncio.wait_for(
                    proc.stdout.readline(),  # type: ignore[union-attr]
                    timeout=timeout_ms / 1000.0,
                )
            except asyncio.TimeoutError:
                # Respawn on next call — the process may be wedged.
                await self.shutdown()
                return HookResult.cont(reason="subproc:timeout")
            except Exception as e:
                await self.shutdown()
                return HookResult.cont(reason=f"subproc:io_error:{type(e).__name__}")

            if not raw_line:
                # Child closed stdout → it exited or crashed.
                await self.shutdown()
                return HookResult.cont(reason="subproc:empty_response")

            try:
                decoded = raw_line.decode("utf-8", errors="replace").strip()
                raw_obj = json.loads(decoded) if decoded else None
            except Exception:
                return HookResult.cont(reason="subproc:response_not_json")

            # Reuse the JS lane's parser — response shape is identical.
            return _parse_js_decision(raw_obj)


__all__ = [
    "SubprocessLaneHook",
    "_normalize_argv",
]
