"""Worker supervisor — one process per isolation domain, launched by the app.

The app the operator starts is one app: one icon, one login, one database, one
update. Underneath, work that must not share memory runs in its own child
process, and the *app* launches those, not the operator.

Why processes and not scoped state
----------------------------------
Measured in the live-chat bundle 2026-09-23: 138 module-level mutable globals,
71 of them keyed by customer. Two domains sharing a process means any one of
those 71 can hand domain A's conversation to domain B — a fluent, confident,
wrong answer, with no exception and no error line. A process boundary makes
that impossible by construction, and keeps doing so for every global somebody
adds later without reading this.

The unit is an isolation KEY, not a "store"
-------------------------------------------
This module never learns what the key means. It is an opaque string: tasks
carrying the same one share a process and share it with nothing else. The
business layer supplies the value (an e-commerce deployment uses its store id),
which is the same split that keeps the runner-bridge registry keyed by site and
agent grouping keyed by declared sender.

**A task with no isolation key runs in-process, exactly as today.** Nothing
declares one yet, so this module changes no behaviour until something does.

Spawning is deliberately not built in
-------------------------------------
How a worker is launched differs between a dev checkout and a frozen build (the
packaged exe cannot be re-run as an interpreter; it needs the ECAN_RUN_SCRIPT
path the Fast Deploy handler already uses). Rather than guess that now and let
the guess rot, the supervisor takes a ``spawner`` — a callable returning the
argv and env for a key. Tests inject a trivial one; the real one arrives when
the first task is actually routed.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

# Task-variable that names a task's isolation domain. A first-class variable
# rather than something derived, so an operator can deliberately co-locate two
# small domains in one worker, or split one that turns out to be noisy.
ISOLATION_KEY_VAR = "isolation_key"

# Restart policy. A worker that dies repeatedly in quick succession is broken,
# not unlucky: restarting it forever would hide the fault behind a flapping
# process, so the supervisor gives up and says so.
_BACKOFF_BASE_S = 1.0
_BACKOFF_MAX_S = 60.0
_MAX_RAPID_RESTARTS = 5
_RAPID_WINDOW_S = 120.0

# How long a worker gets to finish what it is holding before being terminated.
# A live-chat worker may be mid-delivery; killing it loses the customer's reply.
DEFAULT_DRAIN_TIMEOUT_S = 20.0


def isolation_key_for_task(task: Any) -> str:
    """The isolation key a task declares, or ``""`` for "run in-process".

    Read from the task's own variables, so it travels with the task through
    the same path ``store_id`` and ``front_desk_agent_id`` already use.
    """
    try:
        metadata = getattr(task, "metadata", None)
        if not isinstance(metadata, dict):
            return ""
        task_vars = metadata.get("task_vars")
        if not isinstance(task_vars, dict):
            return ""
        return str(task_vars.get(ISOLATION_KEY_VAR) or "").strip()
    except Exception:
        return ""


@dataclass
class WorkerSpec:
    """How to launch one worker.

    ``log_path`` receives the child's stdout and stderr. It is worth setting:
    a worker that dies before its own logging is up leaves its traceback
    nowhere else, and that is exactly the crash-loop the supervisor has to be
    able to explain.
    """
    argv: List[str]
    env: Dict[str, str] = field(default_factory=dict)
    cwd: str = ""
    log_path: str = ""


@dataclass
class WorkerStatus:
    key: str
    pid: int = 0
    running: bool = False
    started_at: float = 0.0
    restarts: int = 0
    last_exit_code: Optional[int] = None
    gave_up: bool = False
    detail: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key, "pid": self.pid, "running": self.running,
            "started_at": self.started_at, "restarts": self.restarts,
            "last_exit_code": self.last_exit_code, "gave_up": self.gave_up,
            "detail": self.detail,
        }


class _Worker:
    """One child process and the bookkeeping to keep it alive."""

    def __init__(self, key: str, spec: WorkerSpec):
        self.key = key
        self.spec = spec
        self.proc: Optional[subprocess.Popen] = None
        self.started_at = 0.0
        self.restarts = 0
        self.last_exit_code: Optional[int] = None
        self.gave_up = False
        self.detail = ""
        # Failures, not starts: a worker that cannot even spawn must count
        # toward giving up the same as one that starts and dies.
        self._recent_failures: List[float] = []
        self._retry_not_before = 0.0
        self._stopping = False
        # Guards against counting one death several times — tick() runs on an
        # interval and would otherwise inflate the restart count (and the
        # backoff) every pass while the worker sits dead waiting to retry.
        self._exit_noted = False
        self._log_fh = None

    def _close_log(self) -> None:
        try:
            if self._log_fh is not None:
                self._log_fh.close()
        except Exception:
            pass
        self._log_fh = None

    # ── lifecycle ────────────────────────────────────────────────────
    def start(self) -> bool:
        env = dict(os.environ)
        env.update(self.spec.env)
        creationflags = 0
        if sys.platform == "win32":
            # Without this a console window flashes on every spawn, which for
            # eight workers at launch is eight flashes on the operator's screen.
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        # stdout/stderr MUST be set explicitly, not inherited. Redirecting any
        # one of the three standard handles on Windows makes CreateProcess use
        # STARTF_USESTDHANDLES, and then all three have to be valid handles --
        # so inheriting stdout/stderr from a parent that has none (a packaged
        # GUI app with no console, or a test runner that captured them) fails
        # the spawn with "[WinError 6] The handle is invalid". Found by the
        # supervisor's own tests under pytest's fd capture; it would have hit
        # the packaged app the same way.
        self._log_fh = None
        if self.spec.log_path:
            try:
                os.makedirs(os.path.dirname(self.spec.log_path) or ".", exist_ok=True)
                self._log_fh = open(self.spec.log_path, "ab", buffering=0)
            except Exception as exc:
                logger.warning(
                    f"[WorkerSupervisor] could not open worker log "
                    f"{self.spec.log_path!r} ({exc}); output will be discarded")
                self._log_fh = None
        out = self._log_fh if self._log_fh is not None else subprocess.DEVNULL
        try:
            self.proc = subprocess.Popen(
                self.spec.argv,
                env=env,
                cwd=self.spec.cwd or None,
                # stdin is the shutdown channel: closing it means "no more
                # work, drain and exit". It is also how the existing worker
                # entry already receives work (--intake stdin), so one pipe
                # serves both without a second mechanism.
                stdin=subprocess.PIPE,
                stdout=out,
                stderr=out,
                creationflags=creationflags,
            )
        except Exception as exc:
            self.proc = None
            self._close_log()
            self.detail = f"spawn failed: {exc}"
            logger.error(f"[WorkerSupervisor] could not start worker {self.key!r}: {exc}")
            return False
        self.started_at = time.time()
        self.detail = ""
        logger.info(
            f"[WorkerSupervisor] worker {self.key!r} started pid={self.proc.pid} "
            f"(restarts={self.restarts})"
        )
        return True

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def stop(self, drain_timeout: float = DEFAULT_DRAIN_TIMEOUT_S) -> None:
        """Ask the worker to finish, then insist, then compel.

        Closing stdin is the graceful signal, and it is the only one that works
        the same on Windows as elsewhere — ``terminate()`` on Windows is
        TerminateProcess, which gives the child no chance to flush a reply it
        is mid-way through delivering.
        """
        self._stopping = True
        if self.proc is None:
            return
        try:
            if self.proc.stdin and not self.proc.stdin.closed:
                self.proc.stdin.close()
        except Exception:
            pass
        deadline = time.time() + max(0.0, drain_timeout)
        while time.time() < deadline:
            if self.proc.poll() is not None:
                logger.info(f"[WorkerSupervisor] worker {self.key!r} drained and exited")
                self._close_log()
                return
            time.sleep(0.1)
        logger.warning(
            f"[WorkerSupervisor] worker {self.key!r} did not exit within "
            f"{drain_timeout:.0f}s — terminating"
        )
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
            return
        except Exception:
            pass
        try:
            self.proc.kill()
            logger.error(f"[WorkerSupervisor] worker {self.key!r} had to be killed")
        except Exception:
            pass
        finally:
            self._close_log()

    # ── health ───────────────────────────────────────────────────────
    def note_exit(self) -> None:
        """Record an unexpected exit and decide whether to keep trying."""
        self.last_exit_code = self.proc.poll() if self.proc else None
        self.restarts += 1
        now = time.time()
        self._recent_failures.append(now)
        self._recent_failures = [t for t in self._recent_failures
                                 if now - t <= _RAPID_WINDOW_S]
        if len(self._recent_failures) >= _MAX_RAPID_RESTARTS:
            self.gave_up = True
            self.detail = (
                f"failed {len(self._recent_failures)} times within "
                f"{_RAPID_WINDOW_S:.0f}s (last code {self.last_exit_code})"
            )
            logger.error(
                f"[WorkerSupervisor] giving up on worker {self.key!r}: {self.detail}. "
                f"It will not be restarted again until something asks for it explicitly."
            )
            return
        delay = min(_BACKOFF_MAX_S, _BACKOFF_BASE_S * (2 ** max(0, self.restarts - 1)))
        self._retry_not_before = time.time() + delay
        logger.warning(
            f"[WorkerSupervisor] worker {self.key!r} exited (code "
            f"{self.last_exit_code}); restarting in {delay:.0f}s"
        )

    def may_retry_now(self) -> bool:
        return not self.gave_up and time.time() >= self._retry_not_before

    def status(self) -> WorkerStatus:
        return WorkerStatus(
            key=self.key,
            pid=(self.proc.pid if self.proc else 0),
            running=self.is_running(),
            started_at=self.started_at,
            restarts=self.restarts,
            last_exit_code=self.last_exit_code,
            gave_up=self.gave_up,
            detail=self.detail,
        )


class WorkerSupervisor:
    """Owns one child process per isolation key."""

    def __init__(self, spawner: Callable[[str], WorkerSpec]):
        self._spawner = spawner
        self._workers: Dict[str, _Worker] = {}
        self._lock = threading.RLock()
        self._monitor: Optional[threading.Thread] = None
        self._stop_monitor = threading.Event()

    # ── the API the launch path uses ─────────────────────────────────
    def ensure_worker(self, key: str) -> Optional[WorkerStatus]:
        """Start the worker for ``key`` if it is not already up.

        Returns its status, or ``None`` for a blank key — which means "this
        task is not isolated, run it in-process" and is the default for
        everything today.
        """
        key = str(key or "").strip()
        if not key:
            return None
        with self._lock:
            worker = self._workers.get(key)
            if worker is None:
                try:
                    spec = self._spawner(key)
                except Exception as exc:
                    logger.error(
                        f"[WorkerSupervisor] no launch spec for worker {key!r}: {exc}")
                    return None
                worker = _Worker(key, spec)
                self._workers[key] = worker
            if worker.gave_up:
                # An explicit ask clears the give-up latch: the operator (or a
                # retry) is saying "try again", which is different from the
                # supervisor restarting a flapping worker on its own.
                worker.gave_up = False
                worker.restarts = 0
                worker._recent_failures.clear()
                worker._retry_not_before = 0.0
                worker._exit_noted = False
            if not worker.is_running():
                worker.start()
            return worker.status()

    def worker_status(self, key: str) -> Optional[WorkerStatus]:
        with self._lock:
            worker = self._workers.get(str(key or "").strip())
            return worker.status() if worker else None

    def status(self) -> List[Dict[str, Any]]:
        """Every worker, for the Agents page and for diagnostics."""
        with self._lock:
            return [w.status().as_dict() for w in self._workers.values()]

    def stop_worker(self, key: str,
                    drain_timeout: float = DEFAULT_DRAIN_TIMEOUT_S) -> None:
        with self._lock:
            worker = self._workers.pop(str(key or "").strip(), None)
        if worker is not None:
            worker.stop(drain_timeout)

    def stop_all(self, drain_timeout: float = DEFAULT_DRAIN_TIMEOUT_S) -> None:
        """Drain every worker. Called on app shutdown, before the app exits.

        Workers are drained in parallel: eight of them serially at a 20s
        timeout each is a three-minute quit, which an operator will resolve
        with Task Manager, losing exactly the replies the drain exists to save.
        """
        self._stop_monitor.set()
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        if not workers:
            return
        threads = [threading.Thread(target=w.stop, args=(drain_timeout,), daemon=True)
                   for w in workers]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=drain_timeout + 10)
        logger.info(f"[WorkerSupervisor] drained {len(workers)} worker(s)")

    # ── health monitoring ────────────────────────────────────────────
    def tick(self) -> None:
        """One health pass: restart what died, respecting backoff.

        Separate from the monitor thread so tests drive it deterministically
        rather than sleeping and hoping.
        """
        with self._lock:
            workers = list(self._workers.values())
        for worker in workers:
            if worker._stopping or worker.is_running():
                continue
            if not worker.started_at:
                continue  # never started; ensure_worker owns the first start
            if not worker._exit_noted:
                worker.note_exit()
                worker._exit_noted = True
            if worker.may_retry_now():
                # Cleared whether or not the start succeeds: a failed spawn is
                # another failure and must be counted on the next pass, or the
                # supervisor would retry a broken command in a tight loop.
                worker.start()
                worker._exit_noted = False

    def start_monitor(self, interval_s: float = 2.0) -> None:
        """Run :meth:`tick` on a daemon thread until shutdown."""
        if self._monitor is not None and self._monitor.is_alive():
            return
        self._stop_monitor.clear()

        def _loop():
            while not self._stop_monitor.wait(interval_s):
                try:
                    self.tick()
                except Exception as exc:
                    logger.warning(f"[WorkerSupervisor] health tick failed: {exc}")

        self._monitor = threading.Thread(
            target=_loop, name="WorkerSupervisor", daemon=True)
        self._monitor.start()

    def stop_monitor(self) -> None:
        self._stop_monitor.set()


# ── process-wide instance ────────────────────────────────────────────
_SUPERVISOR: Optional[WorkerSupervisor] = None
_SUPERVISOR_LOCK = threading.Lock()


def _no_spawner(key: str) -> WorkerSpec:
    raise NotImplementedError(
        f"no worker launch spec is configured, so isolation key {key!r} cannot be "
        f"given its own process. Nothing routes work to a worker yet; when that "
        f"lands it installs a spawner via set_supervisor()."
    )


def supervisor() -> WorkerSupervisor:
    """The process-wide supervisor, created on first use."""
    global _SUPERVISOR
    with _SUPERVISOR_LOCK:
        if _SUPERVISOR is None:
            _SUPERVISOR = WorkerSupervisor(_no_spawner)
        return _SUPERVISOR


def set_supervisor(sup: Optional[WorkerSupervisor]) -> None:
    """Install a supervisor (the real spawner, or a test double)."""
    global _SUPERVISOR
    with _SUPERVISOR_LOCK:
        _SUPERVISOR = sup
