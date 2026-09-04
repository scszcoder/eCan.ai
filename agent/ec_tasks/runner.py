"""
Task Runner - Core task management and execution loop.

This module provides the main TaskRunner class that manages:
- Task registration and lifecycle
- Execution loops for different trigger types
- Event routing
- Task persistence
"""

import asyncio
import concurrent.futures
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import traceback
import uuid
from pathlib import Path
from queue import Queue, Empty
from typing import Any, Dict, Generic, List, Optional, Set, Tuple, TypeVar, TYPE_CHECKING

# Module-level task tracking to prevent "Task was destroyed" warnings
# when event loop closes with orphaned fire-and-forget tasks.
_tracked_cleanup_tasks: Set[asyncio.Task] = set()

from a2a.types import TaskState, Message, TextPart, MessageSendParams, TaskStatus as A2ATaskStatus
from agent.ec_skills.llm_utils.llm_utils import send_response_back
from agent.ec_skills.prep_skills_run import prep_skills_run, apply_task_vars
from langgraph.types import Command

# Import thread registry for leak diagnosis (lazy to avoid circular imports)
def _get_thread_registry():
    from agent.ec_tasks.timer_service import _register_thread, _unregister_thread, _dump_thread_registry
    return _register_thread, _unregister_thread, _dump_thread_registry

from .resume import build_general_resume_payload, normalize_event, _safe_get
from pydantic import TypeAdapter

from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from utils.log_scope import scope as _log_scope, wrap_context as _wrap_log_context

from .models import ManagedTask, PriorityType
from .scheduler import find_tasks_ready_to_run
from .message_sender import ChatMessageSender, MessageType
from .dev_runner import DevRunner
from .executor import TaskExecutor, _create_message
from .terminal_status_utils import task_is_blocked
from .ser_consts import TASK_SERIALIZATION_EXCLUDE
from .timer_service import get_timer_service, TimerService
from utils.sleep_inhibitor import get_sleep_inhibitor

if TYPE_CHECKING:
    from agent.ec_agent import EC_Agent
    from agent.ec_skill import EC_Skill
    from a2a.types import Task

Context = TypeVar('Context')

# Timeouts and polling intervals
DEV_EVENT_TIMEOUT_SEC = int(os.getenv("DEV_EVENT_TIMEOUT_SEC", "300"))
DEV_EVENT_POLL_INTERVAL_SEC = float(os.getenv("DEV_EVENT_POLL_INTERVAL_SEC", "0.5"))
# Per-skill override: pass "_runtime_event_timeout" in task state dict.
# Falls back to this global default (also configurable via env var).
DEFAULT_RUNTIME_EVENT_TIMEOUT_SEC = int(os.getenv("RUN_EVENT_TIMEOUT_SEC", "600"))
try:
    RUNNING_TASK_BLOCKED_CLEAR_SEC = float(os.getenv("RUNNING_TASK_BLOCKED_CLEAR_SEC", "300"))
except (TypeError, ValueError):
    RUNNING_TASK_BLOCKED_CLEAR_SEC = 300.0

# ── Queue event-type tagging & priority dequeue (Change 1a) ──
# HOT-PATH optimization: when both chat_message and browser_event are queued
# for the same task, chat_message must win. It carries the response_text from
# the Q&A agent; if a stale browser_event resumes the pend_event first, the
# chat_message sits unprocessed and the 15s response-time budget is blown.
# We tag event_type on the raw request at enqueue, then scan the queue on
# dequeue to promote chat_message ahead of browser_event.
_EVT_TYPE_ATTR = "__ec_queue_event_type__"
# Enqueue-timestamp tag.  Stamped alongside ``_EVT_TYPE_ATTR`` by
# :func:`_tag_queue_event_type`.  Read by :func:`_queue_event_age_s` for the
# stale-event TTL filter in :func:`_priority_dequeue` (incident: front-desk
# wakes after 2.5h idle, dequeues a stale chat_message reply, tries to
# deliver to a chat that the live-chat site has since closed).
_LIVE_CHAT_EVENT_ENQUEUE_TS_ATTR = "__ec_queue_enqueue_ts__"
# Stale-event TTL for chat_message / a2a / channel_message: anything older
# than this when popped from the queue is silently dropped (with a WARNING
# log) instead of being delivered.  30 min is well above realistic Q&A turn
# times (worst-case observed ~40s) but short enough that a returning-after-
# lunch customer never sees a stale reply attempted against a now-closed
# live chat.  Tunable via env for ops triage.
try:
    _LIVE_CHAT_EVENT_STALE_TTL_S = max(60.0, float(os.getenv("ECAN_STALE_QUEUE_EVENT_TTL_S", "1800")))
except (TypeError, ValueError):
    _LIVE_CHAT_EVENT_STALE_TTL_S = 1800.0
_STALE_EVENT_FILTERED_TYPES = {"chat_message", "a2a", "channel_message"}
_PRIORITY_LOW_EVENT_TYPES = {"browser_event"}
_PRIORITY_HIGH_EVENT_TYPES = {"chat_message", "human_chat", "a2a", "channel_message"}
_DIRECT_LIVE_CHAT_DELIVERY_LOCK = threading.Lock()


def _live_chat_bridge():
    """Return the active live-chat bundle's runner bridge, or None.

    2026-08-01: the runner used to lazy-import the site bundle's
    modules directly at ~45 call sites.  Those sites now resolve every
    site-specific capability (trace ledger, delivery durability, tab
    pool, typing lock, DOM helpers, tunables, ...) through the ONE
    bridge object the active bundle registers at package import (see
    ``live_chat_dispatch.register_runner_bridge`` and
    the active bundle's ``runner_bridge.py``).  A None bridge
    (no live-chat bundle loaded in this process) must degrade each
    call site to the same fallback its old failed-import path took.
    """
    try:
        from agent.ec_skills import live_chat_dispatch
        return live_chat_dispatch.runner_bridge()
    except Exception:
        return None


def _live_chat_env(name: str) -> "str | None":
    """Read a live-chat tunable env var by its platform-neutral name.

    Falls back to any legacy site-branded alias of the same knob (e.g.
    a bundle's historical ``DIRECT_<SITE>_JOB_TIMEOUT_S`` spelling of
    ``DIRECT_LIVE_CHAT_JOB_TIMEOUT_S``) so existing ops run-scripts
    keep working while platform code stays site-agnostic.
    """
    val = os.getenv(name)
    if val is not None:
        return val
    m = re.match(r"^(DIRECT|ECAN)_LIVE_CHAT_([A-Z0-9_]+)$", name)
    if not m:
        return None
    alias_pat = re.compile(rf"^{m.group(1)}_[A-Z0-9]+_{re.escape(m.group(2))}$")
    for key, value in os.environ.items():
        if key != name and alias_pat.match(key):
            return value
    return None


# Dedicated background worker for live-chat direct delivery.
#
# This must not be bound to a skill-run event loop. Q&A/browser skills are
# executed on transient loops; when the originating skill finishes, that loop
# can stop while replies are still queued.  Keep one daemon loop alive for the
# process so "direct_job_queued" is always followed by a worker attempt.
_DIRECT_LIVE_CHAT_ASYNC_WORKER: Optional[Tuple[Any, Any, Any, Any]] = None
_DIRECT_LIVE_CHAT_ASYNC_WORKER_LOCK = threading.Lock()


async def _module_direct_delivery_worker(_queue: Any) -> None:
    """Concurrent direct-delivery worker (module-level twin of the lazy nested
    worker). Pulls jobs off *_queue* and dispatches each as an independent task.
    Mirrors the in-method ``_async_direct_delivery_worker`` exactly; kept separate
    so :func:`_ensure_direct_delivery_worker` can warm the SAME global worker from
    the cold-start placeholder path without touching the reply-delivery code."""
    import asyncio as _asyncio
    _in_flight: set = set()
    while True:
        _job = await _queue.get()
        try:
            _task = _asyncio.create_task(_job())
            _in_flight.add(_task)
            _task.add_done_callback(_in_flight.discard)
        except Exception as _worker_err:
            logger.error(f"[DIRECT-DELIVERY] Async worker dispatch failed: {_worker_err}")
        finally:
            try:
                _queue.task_done()
            except Exception:
                pass


def _ensure_direct_delivery_worker() -> Optional[Tuple[Any, Any, Any, Any]]:
    """Start the background direct-delivery worker thread+loop if not already alive,
    and return its (loop, queue, task, thread) entry (or None on failure).

    Idempotent + thread-safe via the shared ``_DIRECT_LIVE_CHAT_ASYNC_WORKER`` global
    and its lock, so it composes safely with the lazy start in
    ``_submit_loop_direct_delivery`` (whichever runs first wins). Exists so the
    COLD-START 过渡句 can be delivered: the worker was previously created only on the
    first REPLY delivery, but a placeholder fires ~20s earlier — with no worker it
    returned ``submitted=False`` and no placeholder appeared (the 2026-06-19 cold-start
    1-vs-1 had the worker start at 08:17:15 but placeholders fire at 08:16:45)."""
    global _DIRECT_LIVE_CHAT_ASYNC_WORKER
    import asyncio as _asyncio
    import threading as _threading
    with _DIRECT_LIVE_CHAT_ASYNC_WORKER_LOCK:
        _entry = _DIRECT_LIVE_CHAT_ASYNC_WORKER
        _wl = _entry[0] if _entry is not None else None
        _wt = _entry[2] if _entry is not None else None
        _wth = _entry[3] if _entry is not None and len(_entry) > 3 else None
        _dead = (
            _entry is None
            or getattr(_wl, "is_closed", lambda: True)()
            or not getattr(_wl, "is_running", lambda: False)()
            or getattr(_wt, "done", lambda: True)()
            or (_wth is not None and not getattr(_wth, "is_alive", lambda: False)())
        )
        if not _dead:
            return _entry
        _ready = _threading.Event()
        _holder = {}

        def _worker_thread_main() -> None:
            _loop = _asyncio.new_event_loop()
            _asyncio.set_event_loop(_loop)
            _queue = _asyncio.Queue()
            _task = _loop.create_task(_module_direct_delivery_worker(_queue))
            _holder.update({"loop": _loop, "queue": _queue, "task": _task})
            _ready.set()
            try:
                _loop.run_forever()
            finally:
                try:
                    _task.cancel()
                    _loop.run_until_complete(
                        _asyncio.gather(_task, return_exceptions=True)
                    )
                except Exception:
                    pass
                try:
                    _loop.close()
                except Exception:
                    pass

        try:
            _thread = _threading.Thread(
                target=_worker_thread_main, name="LiveChatDirectDelivery", daemon=True,
            )
            _thread.start()
            if not _ready.wait(timeout=2.0):
                logger.warning("[DIRECT-DELIVERY] eager worker did not start in 2s")
                return None
            _DIRECT_LIVE_CHAT_ASYNC_WORKER = (
                _holder["loop"], _holder["queue"], _holder["task"], _thread,
            )
            logger.info(
                f"[DIRECT-DELIVERY] Started background async delivery worker "
                f"(eager) loop_id={id(_holder['loop'])}"
            )
            return _DIRECT_LIVE_CHAT_ASYNC_WORKER
        except Exception as _e:
            logger.warning(f"[DIRECT-DELIVERY] eager worker start failed: {_e}")
            return None
try:
    # 2026-05-19 reverted 90 → 35 s along with the depth=1 revert above.
    # The L1 bump (90 s) was only useful when depth=10 was creating CDP
    # contention that slowed individual sends past 30 s.  With depth=1
    # restored, CDP contention drops back to baseline and 35 s is the
    # right cap (the original v0.9.79 value).
    _DIRECT_LIVE_CHAT_JOB_TIMEOUT_S = float((_live_chat_env("DIRECT_LIVE_CHAT_JOB_TIMEOUT_S") or "35.0"))
except (TypeError, ValueError):
    _DIRECT_LIVE_CHAT_JOB_TIMEOUT_S = 35.0
try:
    _DIRECT_LIVE_CHAT_MAX_RETRIES = max(0, int((_live_chat_env("DIRECT_LIVE_CHAT_MAX_RETRIES") or "0")))
except (TypeError, ValueError):
    _DIRECT_LIVE_CHAT_MAX_RETRIES = 0
try:
    _DIRECT_LIVE_CHAT_RETRY_DELAY_S = max(
        0.0, float((_live_chat_env("DIRECT_LIVE_CHAT_RETRY_DELAY_S") or "0.75"))
    )
except (TypeError, ValueError):
    _DIRECT_LIVE_CHAT_RETRY_DELAY_S = 0.75
try:
    _DIRECT_LIVE_CHAT_TASK_IDLE_WAIT_S = max(
        0.0, float((_live_chat_env("DIRECT_LIVE_CHAT_TASK_IDLE_WAIT_S") or "0.0"))
    )
except (TypeError, ValueError):
    _DIRECT_LIVE_CHAT_TASK_IDLE_WAIT_S = 0.0
try:
    _DIRECT_LIVE_CHAT_FOCUS_RETRIES = max(
        0, int((_live_chat_env("DIRECT_LIVE_CHAT_FOCUS_RETRIES") or "2"))
    )
except (TypeError, ValueError):
    _DIRECT_LIVE_CHAT_FOCUS_RETRIES = 2
try:
    _DIRECT_LIVE_CHAT_FOCUS_RETRY_DELAY_S = max(
        0.0, float((_live_chat_env("DIRECT_LIVE_CHAT_FOCUS_RETRY_DELAY_S") or "0.5"))
    )
except (TypeError, ValueError):
    _DIRECT_LIVE_CHAT_FOCUS_RETRY_DELAY_S = 0.5
try:
    _DIRECT_LIVE_CHAT_REQUEUE_LIMIT = max(
        0, int((_live_chat_env("DIRECT_LIVE_CHAT_REQUEUE_LIMIT") or "1"))
    )
except (TypeError, ValueError):
    _DIRECT_LIVE_CHAT_REQUEUE_LIMIT = 1
try:
    _DIRECT_LIVE_CHAT_REQUEUE_DELAY_S = max(
        0.0, float((_live_chat_env("DIRECT_LIVE_CHAT_REQUEUE_DELAY_S") or "0.75"))
    )
except (TypeError, ValueError):
    _DIRECT_LIVE_CHAT_REQUEUE_DELAY_S = 0.75
try:
    _DIRECT_LIVE_CHAT_CDP_COOLDOWN_REQUEUE_LIMIT = max(
        0, int((_live_chat_env("DIRECT_LIVE_CHAT_CDP_COOLDOWN_REQUEUE_LIMIT") or "0"))
    )
except (TypeError, ValueError):
    _DIRECT_LIVE_CHAT_CDP_COOLDOWN_REQUEUE_LIMIT = 0
try:
    _DIRECT_LIVE_CHAT_CDP_COOLDOWN_RETRY_BUFFER_S = max(
        0.0, float((_live_chat_env("DIRECT_LIVE_CHAT_CDP_COOLDOWN_RETRY_BUFFER_S") or "0.25"))
    )
except (TypeError, ValueError):
    _DIRECT_LIVE_CHAT_CDP_COOLDOWN_RETRY_BUFFER_S = 0.25
try:
    _DIRECT_LIVE_CHAT_CDP_TIMEOUT_DELAY_CAP_S = max(
        0.0, float((_live_chat_env("DIRECT_LIVE_CHAT_CDP_TIMEOUT_DELAY_CAP_S") or "20.0"))
    )
except (TypeError, ValueError):
    _DIRECT_LIVE_CHAT_CDP_TIMEOUT_DELAY_CAP_S = 20.0
try:
    # 2026-05-19: depth=1 chosen as the fast-path equilibrium.
    #
    # History:
    # • depth=1: fast first-response (~20s).  Pre-fix bypass path
    #   silently dropped ~1 reply per flood, but those drops were
    #   addressed by fixing the two real bugs (drift-recovery
    #   dead-end + sidebar-only PreDispatch starvation), not by
    #   masking with larger queues.
    # • depth=2: tried 2026-05-19, traded 1 drop for 2 different
    #   drops (longer typing-lock hold worsened starvation + drift).
    # • depth=10: zero drops but ~25-30s first response from constant
    #   queue contention serializing through one typing-lock.
    _DIRECT_LIVE_CHAT_MAX_ASYNC_QUEUE_DEPTH = max(
        0, int((_live_chat_env("DIRECT_LIVE_CHAT_MAX_ASYNC_QUEUE_DEPTH") or "1"))
    )
except (TypeError, ValueError):
    _DIRECT_LIVE_CHAT_MAX_ASYNC_QUEUE_DEPTH = 1
# 2026-05-19 Fix B: restore v0.9.79's bypass-on-backpressure behavior
# behind a tunable, default ON.
#
# v0.9.79 returned False from `_submit_loop_direct_delivery` when the
# direct-delivery queue depth exceeded `_DIRECT_LIVE_CHAT_MAX_ASYNC_QUEUE_DEPTH`,
# which let the caller fall back to the per-task queue path (HOT-PATH-B
# in the regular task runner).  The two queues had two parallel consumer
# threads, each serializing through the typing-lock — same total
# throughput, but with the bypass acting as a safety valve that prevented
# a single queue from accumulating unbounded backpressure under flood.
#
# Commit 1d18e4714 "fix stuck." (2026-05-11) removed the `return False`,
# making every reply queue into the direct-delivery worker regardless of
# depth.  Under 8+ customer flood, that queue piled up and the per-task
# queue path went unused, contributing to the 100-300 s tail latencies
# observed in the customer's 2026-05-19 21:00 run.
#
# This consults the active bundle's tunables (via the runner bridge)
# so the default + naming line up with the other 2026-05-19 fixes.
# Resolved lazily at each check — the bridge isn't registered yet when
# this module is imported, and the bundle's env spelling of the knob
# lives on the business side of the boundary.
def _direct_live_chat_bypass_on_backpressure() -> bool:
    try:
        bridge = _live_chat_bridge()
        if bridge is not None:
            return bool(bridge.bypass_on_backpressure())
    except Exception:
        pass
    return True
try:
    _DIRECT_LIVE_CHAT_BROWSER_SESSION_WAIT_S = max(
        0.0, float((_live_chat_env("DIRECT_LIVE_CHAT_BROWSER_SESSION_WAIT_S") or "5.0"))
    )
except (TypeError, ValueError):
    _DIRECT_LIVE_CHAT_BROWSER_SESSION_WAIT_S = 5.0
try:
    # 2026-05-11 (flood-test fix): 1 → 2.  A single send-tool CDP
    # timeout used to open the circuit and bypass HOT-PATH-B direct
    # delivery for *every* customer for 20s — turning one slow renderer
    # frame into a fleet-wide stall.  Require two consecutive failures
    # before assuming the renderer is genuinely wedged.
    _DIRECT_LIVE_CHAT_CDP_TIMEOUT_CIRCUIT_THRESHOLD = max(
        0, int((_live_chat_env("DIRECT_LIVE_CHAT_CDP_TIMEOUT_CIRCUIT_THRESHOLD") or "2"))
    )
except (TypeError, ValueError):
    _DIRECT_LIVE_CHAT_CDP_TIMEOUT_CIRCUIT_THRESHOLD = 2
try:
    # 2026-05-11 (flood-test fix): 20.0 → 6.0.  20s of "no direct delivery
    # for anyone" is far too punitive during a 20-customer flood — it
    # forces every reply through the slow front-desk agent fallback path.
    # 6s is enough to let a transient renderer hiccup clear without
    # head-of-line-blocking the whole delivery queue.
    _DIRECT_LIVE_CHAT_CDP_TIMEOUT_CIRCUIT_COOLDOWN_S = max(
        0.0, float((_live_chat_env("DIRECT_LIVE_CHAT_CDP_TIMEOUT_CIRCUIT_COOLDOWN_S") or "6.0"))
    )
except (TypeError, ValueError):
    _DIRECT_LIVE_CHAT_CDP_TIMEOUT_CIRCUIT_COOLDOWN_S = 6.0
_DIRECT_LIVE_CHAT_CDP_TIMEOUT_CIRCUIT_QUEUE_BYPASS = str(
    (_live_chat_env("DIRECT_LIVE_CHAT_CDP_TIMEOUT_CIRCUIT_QUEUE_BYPASS") or "0")
).strip().lower() in {"1", "true", "yes", "on"}
_DIRECT_LIVE_CHAT_CDP_TIMEOUT_CIRCUIT_LOCK = threading.Lock()
_DIRECT_LIVE_CHAT_CDP_TIMEOUT_FAILURES = 0
_DIRECT_LIVE_CHAT_CDP_TIMEOUT_OPEN_UNTIL = 0.0
try:
    _LIVE_CHAT_SHUTDOWN_DRAIN_TIMEOUT_S = max(
        0.0, float((_live_chat_env("ECAN_LIVE_CHAT_SHUTDOWN_DRAIN_TIMEOUT_S") or "15.0"))
    )
except (TypeError, ValueError):
    _LIVE_CHAT_SHUTDOWN_DRAIN_TIMEOUT_S = 15.0
try:
    _LIVE_CHAT_SHUTDOWN_FALLBACK_WAIT_S = max(
        0.0, float((_live_chat_env("ECAN_LIVE_CHAT_SHUTDOWN_FALLBACK_WAIT_S") or "3.0"))
    )
except (TypeError, ValueError):
    _LIVE_CHAT_SHUTDOWN_FALLBACK_WAIT_S = 3.0
_LIVE_CHAT_SHUTDOWN_EVENT = threading.Event()
_LIVE_CHAT_SHUTDOWN_LOCK = threading.RLock()
_LIVE_CHAT_SHUTDOWN_STARTED_AT = 0.0
_LIVE_CHAT_SHUTDOWN_REASON = ""
_LIVE_CHAT_SHUTDOWN_DRAIN_FINALIZED = threading.Event()

# 2026-05-25 mt044E: process-wide BoundedSemaphore that caps how many
# direct-delivery typing operations can be running concurrently.  Created
# lazily on first acquire so the size honors a live tunable read at startup
# rather than import time.  The size comes from the active bundle's
# typing-concurrency tunable; a non-positive value disables the cap.
_MT044E_TYPING_SEM: "asyncio.BoundedSemaphore | None" = None
_MT044E_TYPING_SEM_SIZE: int = 0

_DIRECT_LIVE_CHAT_TRACKED_JOBS: Dict[str, dict] = {}
_DIRECT_LIVE_CHAT_TRACKED_JOBS_LOCK = threading.RLock()


def _mt044e_get_typing_semaphore():
    """Lazily build the BoundedSemaphore for direct-delivery typing concurrency.

    Returns None when the tunable is non-positive (cap disabled).  The semaphore
    is bound to the asyncio event loop that first calls this; calls from a
    different loop fall back to None so the typing path still proceeds (the
    semaphore is a soft-cap, not a correctness gate).
    """
    global _MT044E_TYPING_SEM, _MT044E_TYPING_SEM_SIZE
    try:
        size = _live_chat_bridge().typing_concurrency()
    except Exception:
        size = 3
    if size is None or size <= 0:
        return None
    if _MT044E_TYPING_SEM is None or _MT044E_TYPING_SEM_SIZE != size:
        try:
            _MT044E_TYPING_SEM = asyncio.BoundedSemaphore(size)
            _MT044E_TYPING_SEM_SIZE = size
        except Exception:
            return None
    return _MT044E_TYPING_SEM


# ws118: cap how many per-turn QA skill executions run CONCURRENTLY in the skill
# thread pool, so the shared CDP client's loop thread isn't CPU/GIL-starved under
# high concurrency — the 1-vs-9 HANDOFF-STARVED freeze (a customer-facing 卡死
# where the main asyncio loop stayed healthy but the live-chat WS-send evals
# "NEVER ran" because the shared CDP loop didn't get its turn). The persistent
# front-desk MONITOR is EXCLUDED (it must keep detecting). threading (not
# asyncio) because _execute runs in a ThreadPoolExecutor. Soft cap: a long
# acquire timeout is a deadlock backstop after which the turn proceeds anyway.
# Env ECAN_LIVE_CHAT_QA_MAX_CONCURRENCY (default 5; 0 disables).
_WS118_QA_SEM: "threading.Semaphore | None" = None
_WS118_QA_SEM_SIZE: int = 0
_WS118_QA_SEM_LOCK = threading.Lock()


def _ws118_qa_cap() -> int:
    try:
        return int((_live_chat_env("ECAN_LIVE_CHAT_QA_MAX_CONCURRENCY") or "5") or 5)
    except (TypeError, ValueError):
        return 5


def _ws118_get_qa_semaphore():
    """Process-wide threading.Semaphore capping concurrent QA-turn executions.
    Returns None when the cap is disabled (<=0)."""
    global _WS118_QA_SEM, _WS118_QA_SEM_SIZE
    size = _ws118_qa_cap()
    if size <= 0:
        return None
    with _WS118_QA_SEM_LOCK:
        if _WS118_QA_SEM is None or _WS118_QA_SEM_SIZE != size:
            _WS118_QA_SEM = threading.Semaphore(size)
            _WS118_QA_SEM_SIZE = size
        return _WS118_QA_SEM
_DIRECT_LIVE_CHAT_RETRYABLE_REASONS = {
    "tab_focus_failed",
    "tab_focus_timeout",
    "typing_lock_busy",
    "post_open_verify_failed",
    "pre_send_reverify_failed",
    # 2026-05-20: unverified send outcomes (JS couldn't confirm bubble in
    # expected customer's chat).  Worth one retry — under heavy multi-tab
    # load a fresh open_session + re-type often succeeds.
    "send_unverified_no_bubble",
    "send_unverified_mis_delivered",
}


def _is_direct_live_chat_retryable_reason(reason: str) -> bool:
    """Generic retryable reasons plus any site-specific reason codes the
    active bundle contributes (e.g. its send tool's ``tool_failed:*``)."""
    if reason in _DIRECT_LIVE_CHAT_RETRYABLE_REASONS:
        return True
    try:
        bridge = _live_chat_bridge()
        if bridge is not None:
            return reason in bridge.retryable_send_reasons
    except Exception:
        pass
    return False


def _direct_live_chat_cdp_timeout_circuit_remaining() -> float:
    now = time.monotonic()
    with _DIRECT_LIVE_CHAT_CDP_TIMEOUT_CIRCUIT_LOCK:
        remaining = _DIRECT_LIVE_CHAT_CDP_TIMEOUT_OPEN_UNTIL - now
    return remaining if remaining > 0.0 else 0.0


def _live_chat_cdp_health_cooldown_remaining() -> float:
    try:
        bridge = _live_chat_bridge()
        if bridge is not None:
            return max(0.0, float(bridge.cdp_health_cooldown_remaining()))
    except Exception:
        pass
    return 0.0


def _record_direct_live_chat_cdp_timeout_failure() -> tuple[int, float]:
    global _DIRECT_LIVE_CHAT_CDP_TIMEOUT_FAILURES
    global _DIRECT_LIVE_CHAT_CDP_TIMEOUT_OPEN_UNTIL
    if (
        _DIRECT_LIVE_CHAT_CDP_TIMEOUT_CIRCUIT_THRESHOLD <= 0
        or _DIRECT_LIVE_CHAT_CDP_TIMEOUT_CIRCUIT_COOLDOWN_S <= 0.0
    ):
        return 0, 0.0
    now = time.monotonic()
    with _DIRECT_LIVE_CHAT_CDP_TIMEOUT_CIRCUIT_LOCK:
        if _DIRECT_LIVE_CHAT_CDP_TIMEOUT_OPEN_UNTIL > now:
            return (
                _DIRECT_LIVE_CHAT_CDP_TIMEOUT_FAILURES,
                _DIRECT_LIVE_CHAT_CDP_TIMEOUT_OPEN_UNTIL - now,
            )
        _DIRECT_LIVE_CHAT_CDP_TIMEOUT_FAILURES += 1
        if _DIRECT_LIVE_CHAT_CDP_TIMEOUT_FAILURES >= _DIRECT_LIVE_CHAT_CDP_TIMEOUT_CIRCUIT_THRESHOLD:
            _DIRECT_LIVE_CHAT_CDP_TIMEOUT_OPEN_UNTIL = (
                now + _DIRECT_LIVE_CHAT_CDP_TIMEOUT_CIRCUIT_COOLDOWN_S
            )
        remaining = _DIRECT_LIVE_CHAT_CDP_TIMEOUT_OPEN_UNTIL - now
        return _DIRECT_LIVE_CHAT_CDP_TIMEOUT_FAILURES, remaining if remaining > 0.0 else 0.0


def _record_direct_live_chat_cdp_timeout_success() -> None:
    global _DIRECT_LIVE_CHAT_CDP_TIMEOUT_FAILURES
    global _DIRECT_LIVE_CHAT_CDP_TIMEOUT_OPEN_UNTIL
    with _DIRECT_LIVE_CHAT_CDP_TIMEOUT_CIRCUIT_LOCK:
        _DIRECT_LIVE_CHAT_CDP_TIMEOUT_FAILURES = 0
        _DIRECT_LIVE_CHAT_CDP_TIMEOUT_OPEN_UNTIL = 0.0


def _direct_live_chat_cdp_delay_with_cap(delay_s: float) -> float:
    if _DIRECT_LIVE_CHAT_CDP_TIMEOUT_DELAY_CAP_S <= 0.0:
        return max(0.0, delay_s)
    return min(max(0.0, delay_s), _DIRECT_LIVE_CHAT_CDP_TIMEOUT_DELAY_CAP_S)


def _direct_live_chat_cdp_cooldown_retry_delay(error_text: str) -> float:
    text = str(error_text or "")
    if "cdp_timeout_cooldown_active" not in text:
        return 0.0
    match = re.search(
        r"cdp_timeout_cooldown_active\s+([0-9]+(?:\.[0-9]+)?)s?",
        text,
    )
    remaining = _DIRECT_LIVE_CHAT_REQUEUE_DELAY_S
    if match:
        try:
            remaining = float(match.group(1))
        except (TypeError, ValueError):
            remaining = _DIRECT_LIVE_CHAT_REQUEUE_DELAY_S
    return _direct_live_chat_cdp_delay_with_cap(
        remaining + _DIRECT_LIVE_CHAT_CDP_COOLDOWN_RETRY_BUFFER_S
    )


def _begin_live_chat_shutdown(reason: str = "shutdown") -> None:
    global _LIVE_CHAT_SHUTDOWN_STARTED_AT
    global _LIVE_CHAT_SHUTDOWN_REASON
    with _LIVE_CHAT_SHUTDOWN_LOCK:
        if not _LIVE_CHAT_SHUTDOWN_EVENT.is_set():
            _LIVE_CHAT_SHUTDOWN_STARTED_AT = time.monotonic()
            _LIVE_CHAT_SHUTDOWN_REASON = str(reason or "shutdown")
            _LIVE_CHAT_SHUTDOWN_DRAIN_FINALIZED.clear()
            _LIVE_CHAT_SHUTDOWN_EVENT.set()
            logger.warning(
                f"[LIVE-CHAT-SHUTDOWN] begin reason={_LIVE_CHAT_SHUTDOWN_REASON!r}"
            )


def _reset_live_chat_shutdown_state_for_tests() -> None:
    global _LIVE_CHAT_SHUTDOWN_STARTED_AT
    global _LIVE_CHAT_SHUTDOWN_REASON
    with _LIVE_CHAT_SHUTDOWN_LOCK:
        _LIVE_CHAT_SHUTDOWN_EVENT.clear()
        _LIVE_CHAT_SHUTDOWN_DRAIN_FINALIZED.clear()
        _LIVE_CHAT_SHUTDOWN_STARTED_AT = 0.0
        _LIVE_CHAT_SHUTDOWN_REASON = ""
    with _DIRECT_LIVE_CHAT_TRACKED_JOBS_LOCK:
        _DIRECT_LIVE_CHAT_TRACKED_JOBS.clear()


def _is_live_chat_shutdown_active() -> bool:
    return _LIVE_CHAT_SHUTDOWN_EVENT.is_set()


def _is_live_chat_shutdown_drain_finalized() -> bool:
    return _LIVE_CHAT_SHUTDOWN_DRAIN_FINALIZED.is_set()


def is_app_shutdown_active() -> bool:
    return _is_live_chat_shutdown_active()


def is_app_shutdown_drain_finalized() -> bool:
    return _is_live_chat_shutdown_drain_finalized()


def _tag_queue_event_type(request: Any, event_type: str) -> None:
    """Stamp event_type + enqueue timestamp onto the request so the dequeue
    side can classify and age-filter it.

    The timestamp piggybacks here (rather than getting its own helper) so
    every code path that tags an event_type also stamps a ts — guarantees
    the stale-event TTL in :func:`_priority_dequeue` can age-check every
    queued item without nullable-timestamp bookkeeping.
    """
    try:
        import time as _ttq_t
        _ts = _ttq_t.time()
        if isinstance(request, dict):
            request[_EVT_TYPE_ATTR] = event_type
            request.setdefault(_LIVE_CHAT_EVENT_ENQUEUE_TS_ATTR, _ts)
        else:
            try:
                setattr(request, _EVT_TYPE_ATTR, event_type)
                if not hasattr(request, _LIVE_CHAT_EVENT_ENQUEUE_TS_ATTR):
                    setattr(request, _LIVE_CHAT_EVENT_ENQUEUE_TS_ATTR, _ts)
            except Exception:
                pass
    except Exception:
        pass


def _queue_event_age_s(msg: Any) -> float:
    """Return seconds since the message was enqueued, or 0.0 if untagged."""
    try:
        import time as _qa_t
        if isinstance(msg, dict):
            ts = msg.get(_LIVE_CHAT_EVENT_ENQUEUE_TS_ATTR)
        else:
            ts = getattr(msg, _LIVE_CHAT_EVENT_ENQUEUE_TS_ATTR, None)
        if ts is None:
            return 0.0
        return max(0.0, _qa_t.time() - float(ts))
    except Exception:
        return 0.0


def _classify_queue_event(msg: Any) -> str:
    """Return the event_type tag we attached, or '' if unknown."""
    try:
        if isinstance(msg, dict):
            return str(msg.get(_EVT_TYPE_ATTR, "") or "")
        return str(getattr(msg, _EVT_TYPE_ATTR, "") or "")
    except Exception:
        return ""


def _browser_event_label(msg: Any) -> str:
    """Return the browser_event label/sub_type for queue coalescing."""
    try:
        if isinstance(msg, dict):
            return str(msg.get("sub_type") or _safe_get(msg, "context.sub_type") or "")
    except Exception:
        pass
    return ""


def _browser_event_snapshot_body(msg: Any) -> dict:
    """Return snapshot-style browser_event body, or {} for raw CDP events.

    Config-driven DOM monitors emit a full current snapshot under
    ``params.body``.  A newer snapshot supersedes older queued snapshots
    for the same label, so these are safe to coalesce.
    """
    if not isinstance(msg, dict):
        return {}
    if _classify_queue_event(msg) not in ("", "browser_event") and msg.get("type") != "browser_event":
        return {}
    body = msg.get("body")
    if not isinstance(body, dict):
        params = msg.get("params") or {}
        raw_body = params.get("body") if isinstance(params, dict) else None
        if isinstance(raw_body, dict):
            body = raw_body
        elif isinstance(raw_body, str) and raw_body.strip().startswith("{"):
            try:
                body = json.loads(raw_body)
            except Exception:
                body = {}
    if not isinstance(body, dict):
        return {}
    if isinstance(body.get("items"), list):
        return body
    return {}


def _coalesce_queued_browser_events(q: Queue, new_msg: Any) -> int:
    """Drop older snapshot browser_events for the same label before enqueue.

    This keeps real-time DOM monitors from building a stale backlog while a
    task is working.  Chat messages and raw/non-snapshot browser events are
    left untouched.
    """
    if _classify_queue_event(new_msg) != "browser_event":
        return 0
    label = _browser_event_label(new_msg)
    if not label or not _browser_event_snapshot_body(new_msg):
        return 0
    dropped = 0
    try:
        with q.mutex:
            kept = []
            for old_msg in list(q.queue):
                if (
                    _classify_queue_event(old_msg) == "browser_event"
                    and _browser_event_label(old_msg) == label
                    and _browser_event_snapshot_body(old_msg)
                ):
                    dropped += 1
                    continue
                kept.append(old_msg)
            if dropped:
                q.queue.clear()
                q.queue.extend(kept)
                try:
                    q.unfinished_tasks = max(0, q.unfinished_tasks - dropped)
                    if q.unfinished_tasks == 0:
                        q.all_tasks_done.notify_all()
                except Exception:
                    pass
    except Exception as exc:
        logger.debug(f"[QUEUE] browser_event coalescing failed (non-fatal): {exc}")
        return 0
    return dropped


def _drop_duplicate_queued_messages(q: Queue, new_msg: Any, event_type: str) -> int:
    """Drop duplicate chat_message/task_request from queue if same content already exists.

    This prevents message flooding when a task is busy working - instead of stacking
    multiple identical messages, we only keep the latest one.
    """
    if event_type not in ("chat_message", "task_request", "a2a"):
        return 0

    # Extract message fingerprint for deduplication
    new_fingerprint = _get_message_fingerprint(new_msg, event_type)
    if not new_fingerprint:
        return 0

    dropped = 0
    try:
        with q.mutex:
            kept = []
            for old_msg in list(q.queue):
                old_type = _classify_queue_event(old_msg)
                if old_type == event_type and _get_message_fingerprint(old_msg, event_type) == new_fingerprint:
                    dropped += 1
                    continue
                kept.append(old_msg)
            if dropped:
                q.queue.clear()
                q.queue.extend(kept)
                try:
                    q.unfinished_tasks = max(0, q.unfinished_tasks - dropped)
                    if q.unfinished_tasks == 0:
                        q.all_tasks_done.notify_all()
                except Exception:
                    pass
    except Exception as exc:
        logger.debug(f"[QUEUE] message deduplication failed (non-fatal): {exc}")
        return 0
    return dropped


def _get_message_fingerprint(msg: Any, event_type: str) -> str:
    """Extract a fingerprint from a message for deduplication.

    For chat_message: uses content hash
    For task_request/a2a: uses task name + input preview
    Returns None if no fingerprint can be extracted.
    """
    import hashlib

    try:
        if event_type == "chat_message":
            # Extract text content
            content = ""
            if isinstance(msg, dict):
                # Try common content paths
                for path in [
                    ("data", "content", "text"),
                    ("data", "text"),
                    ("content", "text"),
                    ("text",),
                ]:
                    try:
                        obj = msg
                        for key in path:
                            if isinstance(obj, dict):
                                obj = obj.get(key)
                            else:
                                obj = None
                                break
                        if obj and isinstance(obj, str) and len(obj) > 0:
                            content = obj
                            break
                    except Exception:
                        continue

            if content:
                return hashlib.md5(content.encode()).hexdigest()[:16]

        elif event_type in ("task_request", "a2a"):
            # Extract task name and key input
            task_name = ""
            input_preview = ""
            if isinstance(msg, dict):
                task_name = msg.get("task", "") or msg.get("task_name", "")
                data = msg.get("data", {}) or msg
                if isinstance(data, dict):
                    input_preview = str(data.get("input", ""))[:100]

            if task_name:
                combined = f"{task_name}|{input_preview}"
                return hashlib.md5(combined.encode()).hexdigest()[:16]

    except Exception:
        pass
    return None


def _describe_queue_msg(msg: Any) -> str:
    """Return a short human-readable summary of a queued request for diagnostics.

    Format: 'evt=<event_type> chat=<chatId> from=<senderId> preview=<first 60 chars>'.
    Best-effort, never raises. Used by [QUEUE-TRACE] logs.

    Handles multiple request shapes:
      - A2A executor dict: {"params": {"message": {"parts":[{"text":...}], "metadata":{...}}, "metadata":{...}}}
      - event_monitor dict: {"sub_type": "新消息", "data": {...}, "context": {...}}
      - legacy SendTaskRequest Pydantic / dict with params.parts[...]
    """
    def _get(obj, key, default=None):
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _scan_for_text(parts_list):
        try:
            for p in parts_list or []:
                # Part may be dict or Pydantic
                root = _get(p, "root", None)
                txt = _get(root, "text", None) if root is not None else None
                if not txt:
                    txt = _get(p, "text", None)
                if txt:
                    return str(txt)[:60]
        except Exception:
            return ""
        return ""

    try:
        evt = _classify_queue_event(msg) or "?"
        chat_id = ""
        sender_id = ""
        sub_type = ""
        preview = ""
        # --- event_monitor browser_event dict shape ---
        if isinstance(msg, dict) and msg.get("sub_type") is not None:
            sub_type = str(msg.get("sub_type") or "")
            ctx = msg.get("context") or {}
            chat_id = str(ctx.get("chatId", "") or "")
            body = _browser_event_snapshot_body(msg)
            items = body.get("items") if isinstance(body, dict) else None
            if isinstance(items, list) and items:
                bits = []
                for item in items[:2]:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("customer_name") or item.get("name") or "").strip()
                    last = str(item.get("last_message") or "").strip()
                    if name or last:
                        bits.append(f"{name}|{last}"[:60])
                if bits:
                    preview = " ; ".join(bits)[:60]
        # --- A2A executor dict shape ---
        params = _get(msg, "params", None)
        if params is not None:
            outer_meta = _get(params, "metadata", None) or {}
            message = _get(params, "message", None)
            msg_meta = _get(message, "metadata", None) or {}
            parts = _get(message, "parts", None) or _get(params, "parts", None) or []
            chat_id = chat_id or str(_get(outer_meta, "chatId", "") or _get(msg_meta, "chatId", "") or "")
            sender_id = str(
                _get(outer_meta, "senderId", "")
                or _get(msg_meta, "senderId", "")
                or _get(msg_meta, "sender_id", "")
                or ""
            )
            if not preview:
                preview = _scan_for_text(parts)
        # --- fallback: look at top-level parts or human_text ---
        if isinstance(msg, dict) and not preview:
            data = msg.get("data") or {}
            preview = str(data.get("human_text") or data.get("text") or "")[:60]
        extra = f" sub={sub_type}" if sub_type else ""
        return f"evt={evt}{extra} chat={chat_id or '-'} from={sender_id or '-'} preview={preview!r}"
    except Exception as _e:
        return f"evt=?(describe_error={_e})"


def _snapshot_queue(q: Queue, limit: int = 10) -> str:
    """Return a compact snapshot of the first `limit` queued items (thread-safe)."""
    try:
        with q.mutex:
            items = list(q.queue)
        depth = len(items)
        head = items[:limit]
        summaries = [f"#{i}:{_describe_queue_msg(m)}" for i, m in enumerate(head)]
        more = f" (+{depth - len(head)} more)" if depth > len(head) else ""
        return f"depth={depth} [{' | '.join(summaries)}]{more}"
    except Exception as _e:
        return f"snapshot_error={_e}"


def _task_execution_future_running(task: Any) -> bool:
    """Return True while a task's current skill execution future is still active."""
    try:
        future = getattr(task, "future", None)
        if future is None:
            return False
        done = getattr(future, "done", None)
        if callable(done):
            return not bool(done())
        return False
    except Exception:
        # If the Future object is in an odd state, prefer preserving queued
        # messages over starting a second execution that can overwrite state.
        return True


def _queue_msg_text(msg: Any) -> str:
    """Best-effort text extraction for queue/A2A messages without side effects."""
    try:
        if isinstance(msg, dict):
            for key in ("human_text", "text", "content"):
                value = msg.get(key)
                if isinstance(value, str) and value:
                    return value
            data = msg.get("data")
            if isinstance(data, dict):
                value = data.get("human_text") or data.get("text")
                if isinstance(value, str) and value:
                    return value
            params = msg.get("params")
            if isinstance(params, dict):
                value = params.get("content")
                if isinstance(value, str) and value:
                    return value
                message = params.get("message")
                if isinstance(message, dict):
                    parts = message.get("parts")
                    if isinstance(parts, list) and parts:
                        first = parts[0]
                        if isinstance(first, dict):
                            root = first.get("root")
                            if isinstance(root, dict) and isinstance(root.get("text"), str):
                                return root["text"]
                            if isinstance(first.get("text"), str):
                                return first["text"]

        params = getattr(msg, "params", None)
        message = getattr(params, "message", None) if params is not None else None
        if message is None:
            message = getattr(msg, "message", None)
        parts = getattr(message, "parts", None)
        if isinstance(parts, list) and parts:
            first = parts[0]
            text = getattr(first, "text", None)
            if isinstance(text, str) and text:
                return text
            root = getattr(first, "root", None)
            text = getattr(root, "text", None)
            if isinstance(text, str) and text:
                return text
            if isinstance(first, dict):
                root = first.get("root")
                if isinstance(root, dict) and isinstance(root.get("text"), str):
                    return root["text"]
                if isinstance(first.get("text"), str):
                    return first["text"]
    except Exception:
        return ""
    return ""


def _live_chat_payload_from_queue_msg(msg: Any) -> dict[str, Any]:
    """Extract the structured live-chat customer payload from a queued message."""
    try:
        if isinstance(msg, dict) and (
            msg.get("customer_id") or msg.get("customer_name")
        ):
            return dict(msg)
        text = _queue_msg_text(msg)
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except Exception:
            return {}
        if not isinstance(parsed, dict):
            return {}
        if not (
            parsed.get("customer_id")
            or parsed.get("customer_name")
            or parsed.get("response_text")
        ):
            return {}
        return parsed
    except Exception:
        return {}


def _live_chat_response_payload_from_queue_msg(msg: Any) -> dict[str, Any]:
    payload = _live_chat_payload_from_queue_msg(msg)
    if not isinstance(payload, dict):
        return {}
    if not str(payload.get("response_text") or "").strip():
        return {}
    if not str(payload.get("customer_name") or payload.get("customer_id") or "").strip():
        return {}
    return payload


def _is_live_chat_response_payload(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and bool(str(payload.get("response_text") or "").strip())
        and bool(str(payload.get("customer_name") or payload.get("customer_id") or "").strip())
    )


def _log_live_chat_delivery_aborted_shutdown(
    payload: dict[str, Any],
    *,
    reason: str,
    **fields: Any,
) -> None:
    if not payload:
        return
    try:
        _live_chat_bridge().delivery_durability.clear_pending_delivery(payload)
    except Exception:
        pass
    try:
        _ledger_payload = _live_chat_bridge().trace_ledger.log_payload
        _ledger_payload(
            "delivery_aborted_shutdown",
            payload,
            level=logging.WARNING,
            reason=reason,
            shutdown_reason=_LIVE_CHAT_SHUTDOWN_REASON,
            **fields,
        )
    except Exception:
        pass


def _track_direct_live_chat_job(job_id: str, payload: dict[str, Any], status: str) -> None:
    if not job_id:
        return
    with _DIRECT_LIVE_CHAT_TRACKED_JOBS_LOCK:
        row = _DIRECT_LIVE_CHAT_TRACKED_JOBS.get(job_id, {})
        row.update(
            {
                "payload": dict(payload or {}),
                "status": status,
                "updated_at": time.monotonic(),
            }
        )
        row.setdefault("created_at", time.monotonic())
        _DIRECT_LIVE_CHAT_TRACKED_JOBS[job_id] = row


def _untrack_direct_live_chat_job(job_id: str) -> None:
    if not job_id:
        return
    with _DIRECT_LIVE_CHAT_TRACKED_JOBS_LOCK:
        _DIRECT_LIVE_CHAT_TRACKED_JOBS.pop(job_id, None)


def _direct_live_chat_tracked_jobs_snapshot() -> list[dict[str, Any]]:
    with _DIRECT_LIVE_CHAT_TRACKED_JOBS_LOCK:
        return [dict(row) for row in _DIRECT_LIVE_CHAT_TRACKED_JOBS.values()]


# Phase 3.5 (2026-05-21): placeholder-timer entry point.
#
# The placeholder sweeper (started from dom_assets._start_placeholder_sweeper)
# calls this helper when a customer's reply timer expires.  We schedule a
# synthetic typing job on the SAME background worker loop the real
# direct-delivery uses, so placeholders inherit pool-tab routing.
#
# Returns True if scheduled, False if the worker isn't up or the browser
# session isn't reachable.  Failures are non-fatal — the timer entry was
# already consumed from the registry (see placeholder_timer.claim_expired)
# and the next deadline tick will try again.
def _enqueue_direct_placeholder(
    customer_key: str,
    source_msg_id: str,
    text: str,
    browser_session: Any,
    *,
    armed_at: float = 0.0,
) -> bool:
    """Schedule a placeholder send onto the direct-delivery worker loop.

    ``armed_at`` (mt050P, 2026-05-28): the timer entry's arm time,
    forwarded from the sweeper so the pre-type ``is_real_reply_recent``
    checks honour newer-turn semantics.  Default 0.0 keeps pre-mt050P
    callers working (their checks fall back to the prior behaviour
    where any recent reply suppresses the placeholder).

    mt051C (2026-05-28): the actual placeholder typing coroutine moved
    to the site bundle (``hooks/external/<site>/direct_delivery.py``).
    This runner-side function is now a thin shim: it validates inputs,
    resolves the worker loop, and fires
    ``Stage.ON_LIVE_CHAT_PLACEHOLDER_NEEDED`` via ``live_chat_dispatch``.
    Whichever live-chat bundle is loaded owns the implementation and
    registers its handler at import time.  ``runner.py`` imports no
    site-specific modules in this path.
    """
    if not customer_key or not text or browser_session is None:
        return False
    global _DIRECT_LIVE_CHAT_ASYNC_WORKER
    with _DIRECT_LIVE_CHAT_ASYNC_WORKER_LOCK:
        entry = _DIRECT_LIVE_CHAT_ASYNC_WORKER
    if entry is None:
        # lever-1 (2026-06-19): the direct-delivery worker was created lazily only on
        # the first REPLY, but a 过渡句 fires ~20s earlier — so at cold start there was
        # no worker and the placeholder returned submitted=False (no 过渡句 at all, the
        # exact 1-vs-1 cold-start symptom). Start it on-demand here so the cold-start
        # placeholder is deliverable. Idempotent with the reply path's lazy start.
        # Kill switch: ECAN_LIVE_CHAT_EAGER_DELIVERY_WORKER=0.
        if (_live_chat_env("ECAN_LIVE_CHAT_EAGER_DELIVERY_WORKER") or "1") != "0":
            entry = _ensure_direct_delivery_worker()
        if entry is None:
            logger.debug(
                f"[placeholder_timer] no direct-delivery worker yet; "
                f"skipping placeholder for cust={customer_key!r}"
            )
            return False
        with _DIRECT_LIVE_CHAT_ASYNC_WORKER_LOCK:
            entry = _DIRECT_LIVE_CHAT_ASYNC_WORKER or entry
    worker_loop = entry[0]
    if worker_loop is None or getattr(worker_loop, "is_closed", lambda: True)():
        return False

    from agent.ec_skills import live_chat_dispatch
    from agent.ec_skills.browser_use_extension.hook_api import (
        LiveChatPlaceholderRequest,
    )
    if not live_chat_dispatch.has_placeholder_handler():
        logger.debug(
            f"[placeholder_timer] no live-chat placeholder handler "
            f"registered; skipping placeholder for cust={customer_key!r}"
        )
        return False
    req = LiveChatPlaceholderRequest(
        session_id=customer_key,
        turn_id=source_msg_id,
        text=text,
        armed_at=armed_at,
        site_context={"browser_session": browser_session},
    )
    return live_chat_dispatch.dispatch_placeholder(req, worker_loop=worker_loop)


def _queue_response_payloads(q: Any) -> list[dict[str, Any]]:
    try:
        with q.mutex:
            items = list(q.queue)
    except Exception:
        return []
    payloads: list[dict[str, Any]] = []
    for item in items:
        payload = _live_chat_response_payload_from_queue_msg(item)
        if payload:
            payloads.append(payload)
    return payloads


def _has_queued_live_chat_response_payload(task: Any) -> bool:
    """Return True if *task*'s queue currently contains a live-chat *response*
    payload (i.e. a Q&A-agent reply destined for the front-desk).

    Restored 2026-05-12 after the dev merge dropped the definition while
    leaving the call site in the runner's dequeue-while-busy block — that
    NameError was crashing the queue pump on every chat_message and
    blocking all deliveries.  Semantics are unchanged from
    ``9299db8eb`` / ``33eeb9ae4``: thin wrapper over
    :func:`_queue_response_payloads`.  Distinct from dev's
    ``_is_live_chat_response_payload`` (single-payload shape check) — this
    one inspects the *queue contents* and is what gates the
    ``input_required`` + ``future_running`` "let the live-chat response
    through" exception in the dequeue-skip condition.
    """
    try:
        q = getattr(task, "queue", None)
        return bool(q is not None and _queue_response_payloads(q))
    except Exception:
        return False


def _queue_live_chat_payloads(q: Any) -> list[dict[str, Any]]:
    try:
        with q.mutex:
            items = list(q.queue)
    except Exception:
        return []
    payloads: list[dict[str, Any]] = []
    for item in items:
        payload = _live_chat_payload_from_queue_msg(item)
        if payload:
            payloads.append(payload)
    return payloads


def _remove_queued_live_chat_work(q: Any) -> list[dict[str, Any]]:
    try:
        removed: list[dict[str, Any]] = []
        with q.mutex:
            kept: list[Any] = []
            for item in list(q.queue):
                payload = _live_chat_payload_from_queue_msg(item)
                if payload and not _is_live_chat_response_payload(payload):
                    removed.append(payload)
                else:
                    kept.append(item)
            if removed:
                q.queue.clear()
                q.queue.extend(kept)
                try:
                    q.unfinished_tasks = max(0, int(q.unfinished_tasks) - len(removed))
                except Exception:
                    pass
                try:
                    q.not_full.notify_all()
                except Exception:
                    pass
        return removed
    except Exception:
        return []


def _collect_response_payload_candidates(value: Any) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    candidates: list[Any] = [value]
    try:
        if isinstance(value, str) and value.strip().startswith("{"):
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                candidates.append(parsed)
    except Exception:
        pass
    for candidate in candidates:
        payload = _live_chat_response_payload_from_queue_msg(candidate)
        if payload:
            payloads.append(payload)
    return payloads


def _collect_live_chat_payload_candidates(value: Any) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    candidates: list[Any] = [value]
    try:
        if isinstance(value, str) and value.strip().startswith("{"):
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                candidates.append(parsed)
    except Exception:
        pass
    for candidate in candidates:
        payload = _live_chat_payload_from_queue_msg(candidate)
        if payload:
            payloads.append(payload)
    return payloads


def _task_state_payload_candidates(state: dict[str, Any]) -> list[Any]:
    candidates: list[Any] = []
    for key in ("input", "current_invocation_input", "human_text"):
        candidates.append(state.get(key))
    attrs = state.get("attributes")
    if isinstance(attrs, dict):
        for key in ("current_invocation_input", "human_text"):
            candidates.append(attrs.get(key))
        params = attrs.get("params")
        if isinstance(params, dict):
            candidates.append({"params": params})
    prompt_refs = state.get("prompt_refs")
    if isinstance(prompt_refs, dict):
        candidates.append(prompt_refs.get("events"))
    events = state.get("events")
    if isinstance(events, list) and events:
        candidates.append(events[-1])
    messages = state.get("messages")
    if isinstance(messages, list) and len(messages) > 4:
        candidates.append(messages[4])
    result = state.get("result")
    if isinstance(result, dict):
        candidates.append(result)
        llm_result = result.get("llm_result")
        if isinstance(llm_result, dict):
            candidates.append(llm_result)
    return candidates


def _task_state_response_payloads(task: Any) -> list[dict[str, Any]]:
    state = getattr(task, "state", None)
    if not isinstance(state, dict):
        return []
    candidates = _task_state_payload_candidates(state)

    payloads: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        for payload in _collect_response_payload_candidates(candidate):
            key = (
                str(payload.get("customer_name") or payload.get("customer_id") or ""),
                str(payload.get("source_customer_msg_id") or ""),
                str(payload.get("response_text") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            payloads.append(payload)
    return payloads


def _task_state_live_chat_payloads(task: Any) -> list[dict[str, Any]]:
    state = getattr(task, "state", None)
    if not isinstance(state, dict):
        return []
    candidates = _task_state_payload_candidates(state)

    payloads: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for candidate in candidates:
        for payload in _collect_live_chat_payload_candidates(candidate):
            key = (
                str(payload.get("customer_name") or payload.get("customer_id") or ""),
                str(payload.get("source_customer_msg_id") or payload.get("latest_message_msg_id") or ""),
                str(payload.get("response_text") or ""),
                str(payload.get("latest_message") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            payloads.append(payload)
    return payloads


def _task_live_chat_delivery_pending(task: Any) -> tuple[bool, dict[str, Any]]:
    q = getattr(task, "queue", None)
    queue_response_payloads = _queue_response_payloads(q) if q is not None else []
    queue_live_chat_payloads = _queue_live_chat_payloads(q) if q is not None else []
    state_response_payloads = _task_state_response_payloads(task)
    state_live_chat_payloads = _task_state_live_chat_payloads(task)
    response_payloads = queue_response_payloads + state_response_payloads
    future_running = _task_execution_future_running(task)
    task_name = str(getattr(task, "name", "") or "")
    state = getattr(getattr(task, "status", None), "state", None)
    queue_depth = -1
    try:
        queue_depth = q.qsize() if q is not None else 0
    except Exception:
        queue_depth = -1
    pending = (
        bool(queue_response_payloads)
        or (future_running and bool(state_response_payloads))
        or (future_running and bool(state_live_chat_payloads))
    )
    return pending, {
        "task_name": task_name,
        "task_id": str(getattr(task, "id", "") or ""),
        "task_state": str(state or ""),
        "future_running": future_running,
        "queue_depth": queue_depth,
        "response_payloads": response_payloads,
        "live_chat_payloads": state_live_chat_payloads,
        "queue_live_chat_payloads": queue_live_chat_payloads,
        "queue_response_count": len(queue_response_payloads),
        "queue_live_chat_count": len(queue_live_chat_payloads),
        "state_response_count": len(state_response_payloads),
        "state_live_chat_payload_count": len(state_live_chat_payloads),
    }


def _wait_for_task_live_chat_delivery_idle(task: Any, timeout_s: float) -> bool:
    deadline = time.monotonic() + max(0.0, timeout_s)
    while True:
        pending, _summary = _task_live_chat_delivery_pending(task)
        if not pending:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)


def _log_live_chat_runner_stage(
    stage: str,
    msg: Any,
    *,
    task: Any = None,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Best-effort live-chat trace-ledger logging for runner queue/submit
    transitions."""
    try:
        payload = _live_chat_payload_from_queue_msg(msg)
        if not payload:
            return
        _ledger_payload = _live_chat_bridge().trace_ledger.log_payload

        extra = dict(fields)
        if task is not None:
            extra.setdefault("target_task", getattr(task, "name", ""))
            extra.setdefault("task_id", getattr(task, "id", ""))
            try:
                extra.setdefault(
                    "task_state",
                    str(getattr(getattr(task, "status", None), "state", "")),
                )
            except Exception:
                pass
        _ledger_payload(stage, payload, level=level, **extra)
    except Exception:
        return


def _priority_dequeue(q: Queue, timeout: float) -> Any:
    """Dequeue one item with a three-tier priority order.

    Priority tiers (highest → lowest):

    1. **TOP** — ``chat_message`` carrying a Q&A reply
       (``response_text`` + ``customer_name``).  These are deliveries
       that the front-desk needs to type into the live chat *right now*; the
       customer has been waiting since the Q&A bot finished.

    2. **HIGH** — other ``chat_message`` / ``a2a`` / ``human_chat`` /
       ``channel_message`` events (customer arrivals to dispatch).

    3. **LOW** — ``browser_event`` (DOM monitor snapshots).

    Blocks up to `timeout` on the initial get (same semantics as q.get).
    After the first get returns anything below TOP, peek the rest of
    the queue and swap if a higher-priority item is waiting.  The
    demoted item stays in the queue for the next iteration.

    Why a TOP tier (Fix 19, 2026-05-13): the 21:39 flood showed
    35-145 s gaps between a Q&A reply arriving in the front-desk
    queue and HOT-PATH-B actually firing — the queue was stuffed
    with new-customer ``chat_message`` arrivals (also HIGH tier) so
    the existing HIGH-vs-LOW promotion never fired and replies were
    served strict-FIFO behind arrivals.  Promoting replies cuts
    the wait dramatically because typing a queued answer (~5 s)
    is much cheaper than dispatching a fresh customer (~10-15 s
    LLM call + Q&A round trip).

    Stale-event filtering (added 2026-05-13, see ``_LIVE_CHAT_EVENT_STALE_TTL_S``):
    if the popped item is a ``chat_message``/``a2a``/``channel_message``
    older than the TTL, drop it (the chat it would deliver to is almost
    certainly closed) and recurse to pop the next item, up to the same
    ``timeout`` budget.  Untagged events (no enqueue_ts) are never
    age-filtered.
    """
    import time as _pd_t
    deadline = _pd_t.monotonic() + max(0.0, float(timeout))
    while True:
        remaining = max(0.0, deadline - _pd_t.monotonic())
        # Always allow at least the original timeout for the first iter;
        # subsequent iters use whatever budget is left.
        msg = q.get(timeout=remaining if remaining > 0 else timeout)
        evt = _classify_queue_event(msg)
        # Stale-event TTL guard.  Only filter event types that represent
        # outbound deliveries (chat_message etc.) — never drop browser_event
        # (snapshot coalescing already handles those) or shutdown / control
        # events.  Untagged events (age=0.0) are kept.
        if evt in _STALE_EVENT_FILTERED_TYPES:
            age_s = _queue_event_age_s(msg)
            if age_s > _LIVE_CHAT_EVENT_STALE_TTL_S:
                try:
                    logger.warning(
                        f"[QUEUE-TRACE] dropping stale {evt} (age={int(age_s)}s > "
                        f"TTL={int(_LIVE_CHAT_EVENT_STALE_TTL_S)}s): "
                        f"{_describe_queue_msg(msg)} | "
                        f"remaining={_snapshot_queue(q, limit=10)}"
                    )
                except Exception:
                    pass
                # Mark task done so the queue.join() bookkeeping stays
                # balanced — we consumed the slot, we just discarded the body.
                try:
                    q.task_done()
                except Exception:
                    pass
                # If we still have budget, pop the next one; otherwise raise
                # Empty so the caller's normal "queue empty" branch runs.
                if _pd_t.monotonic() >= deadline:
                    from queue import Empty as _QEmpty
                    raise _QEmpty
                continue
        # [QUEUE-TRACE] Record every pop so we can reconstruct the full consumption
        # order post-mortem. The remaining snapshot reveals what was left behind.
        try:
            logger.info(
                f"[QUEUE-TRACE] dequeue popped: {_describe_queue_msg(msg)} | "
                f"remaining={_snapshot_queue(q, limit=10)}"
            )
        except Exception:
            pass
        # Fix 19: short-circuit when the popped msg is already TOP-tier
        # (a Q&A reply delivery) — nothing in the queue can beat it.
        if _is_live_chat_response_payload(_live_chat_payload_from_queue_msg(msg)):
            return msg
        # If the popped msg is HIGH-tier (non-reply chat_message), still
        # check the queue for a reply that should jump ahead of it.
        # Browser_events (LOW tier) fall through to the same scan.
        is_low = evt in _PRIORITY_LOW_EVENT_TYPES
        is_high = evt in _PRIORITY_HIGH_EVENT_TYPES
        if not (is_low or is_high):
            # Unknown / untagged: return as-is, no promotion attempted.
            return msg
        break  # fall through to priority-promotion scan below
    try:
        with q.mutex:
            # First pass: look for a TOP-tier reply payload.
            for i, peek_msg in enumerate(q.queue):
                if _is_live_chat_response_payload(_live_chat_payload_from_queue_msg(peek_msg)):
                    peek_evt = _classify_queue_event(peek_msg)
                    if peek_evt in _STALE_EVENT_FILTERED_TYPES and \
                            _queue_event_age_s(peek_msg) > _LIVE_CHAT_EVENT_STALE_TTL_S:
                        continue
                    q.queue[i] = msg
                    logger.info(
                        f"[QUEUE] Priority promotion (TOP): promoted Q&A reply ahead of "
                        f"'{evt}' (queue_depth={len(q.queue)}); promoted_msg="
                        f"{_describe_queue_msg(peek_msg)} demoted_msg={_describe_queue_msg(msg)}"
                    )
                    return peek_msg
            # Second pass (only if the popped item is browser_event): look for a HIGH-tier.
            if is_low:
                for i, peek_msg in enumerate(q.queue):
                    peek_evt = _classify_queue_event(peek_msg)
                    if peek_evt in _PRIORITY_HIGH_EVENT_TYPES:
                        # Skip stale candidates so promotion doesn't surface a
                        # message older than the TTL.  We don't drop it from the
                        # queue here (we'd need to touch task_done bookkeeping
                        # while holding q.mutex, and the simpler model is "the
                        # next dequeue iteration will catch it").
                        if peek_evt in _STALE_EVENT_FILTERED_TYPES and \
                                _queue_event_age_s(peek_msg) > _LIVE_CHAT_EVENT_STALE_TTL_S:
                            continue
                        q.queue[i] = msg
                        logger.info(
                            f"[QUEUE] Priority promotion: promoted '{peek_evt}' ahead of "
                            f"'{evt}' (queue_depth={len(q.queue)}); promoted_msg="
                            f"{_describe_queue_msg(peek_msg)} demoted_msg={_describe_queue_msg(msg)}"
                        )
                        return peek_msg
    except Exception as _prio_err:
        logger.debug(f"[QUEUE] Priority scan failed (non-fatal): {_prio_err}")
    return msg


def _release_dispatch_locks_on_skill_failure(response: Any) -> None:
    """Release live-chat dispatch dedup + inflight locks when a Q&A worker
    skill fails.

    Liveness incident 2026-04-27 (eCan.log around 03:41:33): a Q&A
    worker handling customer ``cejs``'s "退货包邮吗?" message failed at
    its ``check_loop_*_condition`` step.  ``runner._on_skill_complete``
    correctly marked the task ``failed`` and emitted ``task_failed``,
    but performed **zero cleanup of dispatch state**.  Because

    * ``_dispatched_identity_keys`` (site bundle actionable_items, no TTL)
      was stamped on dispatch *success* and is invalidated only by
      DOM-diff pruning when the customer's sidebar ``last_message``
      changes, and
    * the customer is *waiting for a reply* and won't send anything
      new,

    the customer's message stayed permanently dedup-blocked — every
    monitor tick logged ``[filter] identity_key dedup: …
    already_dispatched, age=…`` growing forever, and the front-desk
    monitor silently skipped re-dispatch until the 1-hour safety GC
    or until the customer eventually gave up and re-asked.  Same
    failure mode held customer ``sc``'s "有12岁女生款吗?" hostage in
    parallel.

    The 30s inflight lock has the same failure mode (released on
    ``send_chat`` *transport* failure, never on worker-side failure).

    This helper is best-effort: on any error or non-live-chat skill
    shape it silently no-ops so other callers are unaffected.
    """
    if not isinstance(response, dict):
        return
    try:
        # Q&A worker contract: input payload is JSON
        # ``{customer_id, customer_name, latest_message}``.  Walk the
        # ``response['step']`` envelope to find the most recent
        # dict-shaped step with such an ``input``.
        payload: dict | None = None
        step = response.get("step")
        if isinstance(step, dict):
            for _v in step.values():
                if not isinstance(_v, dict):
                    continue
                _inp = _v.get("input")
                if isinstance(_inp, dict):
                    payload = _inp
                    break
                if isinstance(_inp, str) and _inp.strip().startswith("{"):
                    try:
                        _parsed = json.loads(_inp)
                    except (ValueError, TypeError):
                        continue
                    if isinstance(_parsed, dict):
                        payload = _parsed
                        break
        if not isinstance(payload, dict):
            roots: list[Any] = [response.get("step")]
            cp = response.get("cp")
            cp_values = getattr(cp, "values", None)
            if isinstance(cp_values, dict):
                roots.append(cp_values)
            stack: list[Any] = [root for root in roots if root is not None]
            seen: set[int] = set()
            inspected = 0
            while stack and inspected < 300:
                obj = stack.pop()
                oid = id(obj)
                if oid in seen:
                    continue
                seen.add(oid)
                inspected += 1
                if isinstance(obj, dict):
                    llm_result = obj.get("llm_result")
                    if isinstance(llm_result, dict):
                        payload = llm_result
                        break
                    stack.extend(
                        val for val in obj.values() if isinstance(val, (dict, list, tuple))
                    )
                elif isinstance(obj, (list, tuple)):
                    stack.extend(
                        val for val in obj if isinstance(val, (dict, list, tuple))
                    )
        if not isinstance(payload, dict):
            return
        cust_id = str(
            payload.get("customer_id") or payload.get("customerId") or ""
        ).strip()
        cust_name = str(
            payload.get("customer_name") or payload.get("customerName") or ""
        ).strip()
        latest_msg = str(
            payload.get("latest_message")
            or payload.get("source_latest_message")
            or ""
        ).strip()
        if not (cust_id or cust_name) or not latest_msg:
            return  # Not a Q&A inbound payload — nothing to release.

        # The identity_key format is ``<customer_name>|<last_message>``
        # (see ``actionable_items.py``); fastpath stamping prefers
        # ``customer_name`` but ``customer_id`` may be used when name
        # is absent, so try both.
        ident_candidates: list[str] = []
        for _prefix in (cust_name, cust_id):
            if _prefix:
                _id = f"{_prefix}|{latest_msg}"
                if _id not in ident_candidates:
                    ident_candidates.append(_id)

        # 1. Identity-key dedup (site-bundle-specific; best-effort via
        #    the runner bridge).
        try:
            _ai_identity_keys = _live_chat_bridge().actionable_items._dispatched_identity_keys
            _now = time.time()
            for _id in ident_candidates:
                _stamped_at = _ai_identity_keys.pop(_id, None)
                if _stamped_at is not None:
                    logger.info(
                        f"[COMPLETE] Released identity_key dedup on skill "
                        f"failure: {_id!r} "
                        f"(was stamped {_now - _stamped_at:.1f}s ago)"
                    )
        except AttributeError:
            pass  # No live-chat bundle — no identity-key table to clear.
        except Exception as _e:
            logger.debug(
                f"[COMPLETE] identity_key release failed (non-fatal): {_e}"
            )

        # 2. Inflight lock (keyed by *normalized* customer name/id).
        try:
            from agent.ec_skills.build_node import (
                _clear_dispatch_inflight,
                _normalize_dispatch_identity_key,
            )
            _seen: set[str] = set()
            for _key_raw in (cust_name, cust_id):
                if not _key_raw:
                    continue
                _key = _normalize_dispatch_identity_key(_key_raw)
                if not _key or _key in _seen:
                    continue
                _seen.add(_key)
                _clear_dispatch_inflight(_key)
                logger.info(
                    f"[COMPLETE] Released inflight lock on skill failure: "
                    f"customer_key={_key!r}"
                )
        except ImportError:
            pass
        except Exception as _e:
            logger.debug(
                f"[COMPLETE] inflight release failed (non-fatal): {_e}"
            )
    except Exception as _outer:
        logger.debug(
            f"[COMPLETE] _release_dispatch_locks_on_skill_failure: {_outer}"
        )


def _cleanup_live_chat_delivery_state(customer_name: str, customer_id: str = "") -> None:
    """Release front-desk dispatch state after a live-chat reply is delivered.

    Direct delivery bypasses the browser-node HOT-PATH-B hook, so it must do
    the same cleanup itself: clear the cross-scope inflight lock and evict the
    stale ``assigned_sessions`` entry.  Otherwise a later customer turn can be
    suppressed as "same message already assigned" even after we already sent
    the answer.
    """
    raw_candidates: list[str] = []
    for raw in (customer_name, customer_id):
        text = str(raw or "").strip()
        if text and text not in raw_candidates:
            raw_candidates.append(text)
    if not raw_candidates:
        return

    try:
        from agent.ec_skills import build_node as _build_node
    except Exception as exc:
        logger.debug(
            f"[DIRECT-DELIVERY] live-chat cleanup skipped: build_node unavailable: {exc}"
        )
        return

    try:
        normalize = getattr(_build_node, "_normalize_dispatch_identity_key")
    except Exception:
        normalize = lambda x: str(x or "").strip()  # type: ignore[assignment]

    normalized: set[str] = set()
    for raw in raw_candidates:
        try:
            key = str(normalize(raw) or "").strip()
        except Exception:
            key = raw
        if key:
            normalized.add(key)

    try:
        clear_inflight = getattr(_build_node, "_clear_dispatch_inflight", None)
        if callable(clear_inflight):
            for key in sorted(normalized):
                clear_inflight(key)
                logger.info(
                    f"[DIRECT-DELIVERY] Cleared dispatch_inflight for "
                    f"customer_key={key!r}"
                )
    except Exception as exc:
        logger.debug(
            f"[DIRECT-DELIVERY] dispatch_inflight cleanup failed: {exc}"
        )

    try:
        ds_by_agent = getattr(_build_node, "_dispatch_state_by_agent", {})
        if not isinstance(ds_by_agent, dict):
            return
        evicted = 0
        for state in list(ds_by_agent.values()):
            if not isinstance(state, dict):
                continue
            assigned = state.get("assigned_sessions")
            if not isinstance(assigned, dict):
                continue
            for sid in list(assigned.keys()):
                sid_text = str(sid or "").strip()
                try:
                    sid_key = str(normalize(sid_text) or "").strip()
                except Exception:
                    sid_key = sid_text
                if sid_text in raw_candidates or (sid_key and sid_key in normalized):
                    assigned.pop(sid, None)
                    evicted += 1
        if evicted:
            logger.info(
                f"[DIRECT-DELIVERY] Evicted {evicted} assigned_sessions "
                f"record(s) for customers={raw_candidates!r}"
            )
    except Exception as exc:
        logger.debug(
            f"[DIRECT-DELIVERY] assigned_sessions cleanup failed: {exc}"
        )


class TaskRunnerRegistry:
    """Global registry for TaskRunner instances to allow coordinated shutdown."""
    _runners: List["TaskRunner"] = []
    
    @classmethod
    def register(cls, runner: "TaskRunner"):
        try:
            if runner not in cls._runners:
                cls._runners.append(runner)
        except Exception:
            pass
    
    @classmethod
    def unregister(cls, runner: "TaskRunner"):
        try:
            if runner in cls._runners:
                cls._runners.remove(runner)
        except Exception:
            pass
    
    @classmethod
    def stop_all(cls):
        for r in list(cls._runners):
            try:
                r.stop()
            except Exception:
                pass

    @classmethod
    def prepare_live_chat_shutdown(
        cls,
        timeout_s: float | None = None,
        reason: str = "app_shutdown",
    ) -> bool:
        _begin_live_chat_shutdown(reason)
        cls._abort_queued_live_chat_work_for_shutdown()
        return cls.drain_live_chat_delivery(
            _LIVE_CHAT_SHUTDOWN_DRAIN_TIMEOUT_S if timeout_s is None else timeout_s
        )

    @classmethod
    def drain_live_chat_delivery(cls, timeout_s: float) -> bool:
        deadline = time.monotonic() + max(0.0, timeout_s)
        last_log = 0.0
        idle_since: float | None = None
        idle_grace_s = 0.5
        logger.warning(
            f"[LIVE-CHAT-SHUTDOWN] drain start timeout={max(0.0, timeout_s):.1f}s"
        )
        while True:
            pending = cls._collect_pending_live_chat_delivery()
            direct_pending = cls._direct_worker_unfinished_count()
            now = time.monotonic()
            if not pending and direct_pending <= 0:
                if idle_since is None:
                    idle_since = now
                if now - idle_since >= idle_grace_s or now >= deadline:
                    _LIVE_CHAT_SHUTDOWN_DRAIN_FINALIZED.set()
                    logger.warning("[LIVE-CHAT-SHUTDOWN] drain complete")
                    return True
            else:
                idle_since = None
            if now >= deadline:
                logger.warning(
                    f"[LIVE-CHAT-SHUTDOWN] drain timeout pending_tasks={len(pending)} "
                    f"direct_pending={direct_pending}"
                )
                cls._log_pending_live_chat_shutdown_aborts(pending, direct_pending)
                _LIVE_CHAT_SHUTDOWN_DRAIN_FINALIZED.set()
                return False
            if now - last_log >= 1.0:
                logger.warning(
                    f"[LIVE-CHAT-SHUTDOWN] waiting pending_tasks={len(pending)} "
                    f"direct_pending={direct_pending}"
                )
                last_log = now
            time.sleep(min(0.25, max(0.0, deadline - now)))

    @classmethod
    def _direct_worker_unfinished_count(cls) -> int:
        try:
            entry = _DIRECT_LIVE_CHAT_ASYNC_WORKER
            if entry is None:
                queue_count = 0
            else:
                queue = entry[1]
                queue_count = 0
                try:
                    queue_count = max(queue_count, int(queue.qsize()))
                except Exception:
                    pass
                try:
                    queue_count = max(queue_count, int(getattr(queue, "_unfinished_tasks", 0) or 0))
                except Exception:
                    pass
            return max(queue_count, len(_direct_live_chat_tracked_jobs_snapshot()))
        except Exception:
            return len(_direct_live_chat_tracked_jobs_snapshot())

    @classmethod
    def _iter_unique_tasks(cls) -> list[Any]:
        tasks: list[Any] = []
        seen: set[int] = set()
        for runner in list(cls._runners):
            task_sources: list[Any] = []
            try:
                task_sources.extend(list(getattr(getattr(runner, "agent", None), "tasks", []) or []))
            except Exception:
                pass
            try:
                local_tasks = getattr(runner, "tasks", {}) or {}
                if isinstance(local_tasks, dict):
                    task_sources.extend(list(local_tasks.values()))
            except Exception:
                pass
            for task in task_sources:
                if task is None:
                    continue
                task_key = id(task)
                if task_key in seen:
                    continue
                seen.add(task_key)
                tasks.append(task)
        return tasks

    @classmethod
    def _abort_queued_live_chat_work_for_shutdown(cls) -> int:
        aborted = 0
        for task in cls._iter_unique_tasks():
            q = getattr(task, "queue", None)
            if q is None:
                continue
            removed = _remove_queued_live_chat_work(q)
            if not removed:
                continue
            aborted += len(removed)
            for payload in removed:
                _log_live_chat_delivery_aborted_shutdown(
                    payload,
                    reason="queued_live_chat_task_aborted_shutdown",
                    target_task=str(getattr(task, "name", "") or ""),
                    task_id=str(getattr(task, "id", "") or ""),
                    task_state=str(getattr(getattr(task, "status", None), "state", "") or ""),
                    queue_depth=getattr(q, "qsize", lambda: -1)(),
                )
        if aborted:
            logger.warning(f"[LIVE-CHAT-SHUTDOWN] aborted queued live-chat task(s): {aborted}")
        return aborted

    @classmethod
    def _collect_pending_live_chat_delivery(cls) -> list[dict[str, Any]]:
        pending: list[dict[str, Any]] = []
        for task in cls._iter_unique_tasks():
            is_pending, summary = _task_live_chat_delivery_pending(task)
            if is_pending:
                pending.append(summary)
        return pending

    @classmethod
    def _log_pending_live_chat_shutdown_aborts(
        cls,
        pending: list[dict[str, Any]],
        direct_pending: int,
    ) -> None:
        for row in _direct_live_chat_tracked_jobs_snapshot():
            payload = row.get("payload") if isinstance(row, dict) else {}
            if isinstance(payload, dict) and payload:
                _log_live_chat_delivery_aborted_shutdown(
                    payload,
                    reason="direct_job_pending_at_shutdown",
                    direct_status=str(row.get("status") or ""),
                    direct_age_s=round(
                        time.monotonic() - float(row.get("created_at") or time.monotonic()),
                        3,
                    ),
                )
        for summary in pending:
            payloads = summary.get("response_payloads") or []
            if payloads:
                for payload in payloads:
                    _log_live_chat_delivery_aborted_shutdown(
                        payload,
                        reason="task_queue_pending_at_shutdown",
                        target_task=summary.get("task_name") or "",
                        task_id=summary.get("task_id") or "",
                        task_state=summary.get("task_state") or "",
                        queue_depth=summary.get("queue_depth"),
                        future_running=summary.get("future_running"),
                    )
                continue
            payloads = summary.get("live_chat_payloads") or []
            if payloads:
                for payload in payloads:
                    _log_live_chat_delivery_aborted_shutdown(
                        payload,
                        reason="inflight_live_chat_task_at_shutdown",
                        target_task=summary.get("task_name") or "",
                        task_id=summary.get("task_id") or "",
                        task_state=summary.get("task_state") or "",
                        queue_depth=summary.get("queue_depth"),
                        future_running=summary.get("future_running"),
                    )
                continue
            logger.warning(
                f"[LIVE-CHAT-SHUTDOWN] pending live-chat task without queued response "
                f"at shutdown: {summary}"
            )
        if direct_pending > 0 and not _direct_live_chat_tracked_jobs_snapshot():
            logger.warning(
                f"[LIVE-CHAT-SHUTDOWN] direct worker still had {direct_pending} "
                "unfinished item(s) at shutdown"
            )


class TaskRunner(Generic[Context]):
    """
    Main task runner that manages task execution.
    
    Responsibilities:
    - Task registration and lifecycle management
    - Execution loop for different trigger types
    - Event routing to appropriate tasks
    - Task persistence (save/load)
    """
    
    def __init__(self, agent: "EC_Agent"):
        """
        Initialize the task runner.
        
        Args:
            agent: The agent that owns this runner.
        """
        self.agent = agent
        self.tasks: Dict[str, ManagedTask] = {}
        
        # Skill execution thread pool
        _max_workers = int(os.environ.get("ECAN_SKILL_WORKERS", "8"))
        self._skill_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=_max_workers,
            thread_name_prefix="SkillExec",
        )
        logger.info(f"[TaskRunner] SkillExecutor: max_workers={_max_workers}")
        
        # Per-task state for concurrent execution
        self._task_states: Dict[str, dict] = {}
        self._task_execution_lock = threading.RLock()
        
        # Dev runner for debugging
        self.dev_runner = DevRunner()
        
        # Running tasks list
        self.running_tasks: List[asyncio.Task] = []
        
        # Persistence directory
        self.save_dir = os.path.join(agent.mainwin.my_ecb_data_homepath, "task_saves")
        os.makedirs(self.save_dir, exist_ok=True)
        
        # Global event routing config (agent-level, not per-skill)
        self._global_event_routing: Dict[str, dict] = self._load_global_event_routing()
        
        # Stop event for shutdown
        self._stop_event = threading.Event()
        
        # Message sender
        self._message_sender: Optional[ChatMessageSender] = None
        
        # Active hybrid cloud subscriptions keyed by run_id
        # Each entry: {"passive_service": PassiveCommandService, "status_cancel": asyncio.Task, "task_id": str}
        self._active_subscriptions: Dict[str, dict] = {}
        
        # Register with global registry
        TaskRunnerRegistry.register(self)
    
    # ==================== Properties ====================
    
    @property
    def bp_manager(self):
        """Backward compatibility: access breakpoint manager via dev_runner."""
        return self.dev_runner.bp_manager
    
    @property
    def _dev_task(self):
        """Backward compatibility: access dev task via dev_runner."""
        return self.dev_runner.current_task
    
    @_dev_task.setter
    def _dev_task(self, value):
        """Backward compatibility: set dev task via dev_runner."""
        if value is None:
            self.dev_runner.clear_dev_task()
        else:
            self.dev_runner.set_dev_task(value)
    
    # ==================== Message Sender ====================
    
    def _get_message_sender(self) -> ChatMessageSender:
        """Get or create message sender."""
        if self._message_sender is None:
            self._message_sender = ChatMessageSender(self.agent)
        return self._message_sender
    
    def sendChatMessageToGUI(self, sender_agent, chatId, msg):
        """Send a text message to GUI. Backward compatible."""
        logger.debug(f"sendChatMessageToGUI: {msg}")
        sender = ChatMessageSender(sender_agent)
        sender.send_text(chatId, msg)
    
    def sendChatFormToGUI(self, sender_agent, chatId, chatData):
        """Send a form message to GUI. Backward compatible."""
        logger.debug(f"sendChatFormToGUI: {chatData}")
        sender = ChatMessageSender(sender_agent)
        sender.send_form(chatId, chatData)
    
    def sendChatNotificationToGUI(self, sender_agent, chatId, chatData):
        """Send a notification to GUI. Backward compatible."""
        logger.debug(f"sendChatNotificationToGUI: {chatData}")
        sender = ChatMessageSender(sender_agent)
        sender.send_notification(chatId, chatData)
    
    # ==================== Dev Run Controls (Delegated) ====================
    
    def set_bps_dev_skill(self, bps: Optional[List[str]]) -> dict:
        """Set breakpoints for dev skill run."""
        return self.dev_runner.set_breakpoints(bps)
    
    def clear_bps_dev_skill(self, bps: Optional[List[str]] = None) -> dict:
        """Clear breakpoints."""
        return self.dev_runner.clear_breakpoints(bps)
    
    def launch_dev_run(self, init_state: dict, dev_task: ManagedTask) -> dict:
        """Launch a dev run via the unified execution loop."""
        try:
            # Truncate screenshot data for logging
            try:
                from agent.ec_skills.browser_use_extension.passive_utils import truncate_screenshot_for_logging
                log_init_state = truncate_screenshot_for_logging(init_state)
            except Exception:
                log_init_state = str(init_state)[:500] + "..."
            logger.debug(f"[TaskRunner][launch_dev_run] init_state: {log_init_state}")
            dev_init_state = init_state or {}
            try:
                if isinstance(dev_init_state.get("messages"), list) and not dev_init_state["messages"]:
                    dev_init_state = dict(dev_init_state)
                    dev_init_state.pop("messages", None)
            except Exception:
                pass

            final_state = self._prepare_dev_state(dev_task, msg=None, dev_init_state=dev_init_state)
        except Exception as e:
            logger.error(get_traceback(e, "ErrorPrepareDevStateForDevRun"))
            final_state = init_state or {}

        launch_result = self.dev_runner.launch_dev_run(final_state, dev_task)
        if not launch_result.get("success"):
            return launch_result

        # Reset per-task state tracking for dev runs before entering loop
        self._task_states[dev_task.id] = {
            "justStarted": True,
            "dev_auto_started": False,
            "pending_since": None,
            # Allow per-task timeout override (set by skill config); falls back to global default
            "_runtime_event_timeout": DEFAULT_RUNTIME_EVENT_TIMEOUT_SEC,
        }

        # Kick off the unified runner in dev mode with prepared state
        self.launch_unified_run(
            task2run=dev_task,
            trigger_type="dev",
            dev_init_state=final_state,
            dev_single_run=True,
        )

        return {"success": True}
    
    def resume_dev_run(self) -> dict:
        """Resume a paused dev run."""
        return self.dev_runner.resume_dev_run()
    
    def pause_dev_run(self) -> dict:
        """Pause the current dev run."""
        return self.dev_runner.pause_dev_run()
    
    def step_dev_run(self) -> dict:
        """Single-step the dev run."""
        return self.dev_runner.step_dev_run()
    
    def cancel_dev_run(self) -> dict:
        """Cancel the current dev run."""
        return self.dev_runner.cancel_dev_run()
    
    def _get_serializable_state(self, task, config) -> dict:
        """Get serializable state from task."""
        return self.dev_runner.get_serializable_state(config)
    
    # ==================== Lifecycle Management ====================
    
    def stop(self):
        """Signal all loops to exit and notify running tasks to shut down."""
        try:
            self._stop_event.set()
            
            # Get agent name safely
            agent_name = self._get_agent_name()
            logger.info(f"[TaskRunner] Stop event set for agent {agent_name}")
            
            # Stop all ManagedTask instances
            self._stop_managed_tasks()
            
            # Notify agent tasks' queues
            self._notify_task_queues_shutdown()
            
            # Shutdown SkillExecutor thread pool to prevent thread leaks
            try:
                if hasattr(self, '_skill_executor') and self._skill_executor:
                    self._skill_executor.shutdown(wait=False, cancel_futures=True)
                    logger.info(f"[TaskRunner] SkillExecutor shutdown for agent {agent_name}")
            except Exception as executor_shutdown_err:
                logger.debug(f"[TaskRunner] Error shutting down SkillExecutor: {executor_shutdown_err}")
            
            # Cleanup browser event monitors
            try:
                import asyncio
                from agent.ec_skills.browser_use_extension.event_monitor import cleanup_all_monitors
                # Run async cleanup in a new event loop if needed
                try:
                    loop = asyncio.get_running_loop()
                    # If we're in an async context, create a task with tracking
                    cleanup_task = asyncio.create_task(cleanup_all_monitors())
                    _tracked_cleanup_tasks.add(cleanup_task)
                    cleanup_task.add_done_callback(_tracked_cleanup_tasks.discard)
                except RuntimeError:
                    # No running loop, use run_until_complete
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(cleanup_all_monitors())
                    loop.close()
            except Exception as e:
                logger.debug(f"[TaskRunner] Error cleaning up event monitors: {e}")
            
        except Exception as e:
            logger.debug(f"[TaskRunner] Error in stop method: {e}")
    
    def _get_agent_name(self) -> str:
        """Safely get agent name."""
        agent_card = getattr(self.agent, 'card', None)
        if agent_card:
            if hasattr(agent_card, 'name'):
                return agent_card.name
            elif isinstance(agent_card, dict):
                return agent_card.get('name', 'unknown')
        return 'unknown'
    
    def _stop_managed_tasks(self):
        """Stop all managed tasks."""
        from .pending_events import cancel_task_async_operations
        
        try:
            for task_id, managed_task in self.tasks.items():
                try:
                    if managed_task:
                        # Cancel pending async operations first
                        cancel_task_async_operations(managed_task)
                        managed_task.cancel()
                        managed_task.exit()
                        logger.debug(f"[TaskRunner] Stopped managed task: {task_id}")
                except Exception as e:
                    logger.debug(f"[TaskRunner] Error stopping managed task {task_id}: {e}")
        except Exception as e:
            logger.debug(f"[TaskRunner] Error stopping managed tasks: {e}")
    
    def _notify_task_queues_shutdown(self):
        """Notify running task queues to shut down."""
        try:
            for t in getattr(self.agent, "tasks", []) or []:
                try:
                    if not t:
                        continue
                    st = getattr(getattr(t, "status", None), "state", None)
                    if st in (TaskState.submitted, TaskState.working):
                        q = getattr(t, "queue", None)
                        if q is not None:
                            try:
                                q.put_nowait({"__shutdown__": True})
                            except Exception:
                                try:
                                    q.put({"__shutdown__": True})
                                except Exception:
                                    pass
                except Exception:
                    pass
        except Exception:
            pass
    
    def close(self):
        """Close the runner and unregister."""
        self.stop()
        TaskRunnerRegistry.unregister(self)
    
    def assign_agent(self, agent: "EC_Agent"):
        """Assign a new agent to this runner."""
        self.agent = agent
    
    # ==================== Task Management ====================
    
    async def create_task(
        self,
        skill: "EC_Skill",
        state: dict,
        session_id: Optional[str] = None,
        resume_from: Optional[str] = None,
        trigger: Optional[str] = None
    ) -> str:
        """
        Create a new managed task.
        
        Args:
            skill: The skill to execute.
            state: Initial state for the task.
            session_id: Optional session ID.
            resume_from: Optional resume point.
            trigger: Optional trigger type.
            
        Returns:
            The task ID.
        """
        task_id = str(uuid.uuid4())
        
        # Validate skill
        if skill is None:
            logger.error("[SKILL_MISSING] Attempting to create task with skill=None!")
            raise ValueError("Cannot create task with None skill")
        
        logger.info(f"[TASK_CREATE] Creating task {task_id} with skill: {skill.name if hasattr(skill, 'name') else 'UNKNOWN'}")
        
        if not hasattr(skill, 'runnable') or skill.runnable is None:
            logger.warning(f"[SKILL_WARNING] Skill has runnable=None at task creation")
        
        task = ManagedTask(
            id=task_id,
            sessionId=session_id,
            skill=skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger=trigger,
            name=skill.name if hasattr(skill, 'name') else 'unnamed_task',
            description=""
        )
        
        self.tasks[task_id] = task
        return task_id
    
    async def run_task(self, task_id: str):
        """Run a task by ID."""
        tbr_task = next((task for task in self.agent.tasks if task and task.id == task_id), None)
        if tbr_task:
            if tbr_task.status.state not in (TaskState.working, TaskState.input_required):
                logger.info(f"Starting task: {tbr_task.status.state}")
                executor = TaskExecutor(tbr_task)
                await executor.astream_run()
            else:
                logger.warning("Task already running or waiting for input")
    
    async def run_all_tasks(self):
        """Run all tasks with proper cleanup."""
        import inspect
        
        self.running_tasks = []
        
        for t in self.agent.tasks:
            if t and callable(t.task):
                try:
                    coro = t.task()
                    if inspect.isawaitable(coro):
                        self.running_tasks.append(coro)
                except TypeError as e:
                    logger.error(f"Task requires arguments: {e}")
            elif inspect.isawaitable(t.task):
                self.running_tasks.append(t.task)
        
        if not self.running_tasks:
            logger.warning("No running tasks")
            return
        
        logger.info(f"Running {len(self.running_tasks)} tasks")
        
        try:
            results = await asyncio.gather(*self.running_tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Task {i} failed: {result}")
        except Exception as e:
            logger.error(f"run_all_tasks failed: {e}")
        finally:
            self.running_tasks.clear()
    
    async def pause_task(self, task_id: str):
        """Pause a task."""
        task = self.tasks[task_id]
        task.pause()
        task.status.state = TaskState.input_required
    
    async def resume_task(self, task_id: str):
        """Resume a paused task."""
        task = self.tasks[task_id]
        task.resume()
        task.status.state = TaskState.working
    
    async def cancel_task(self, task_id: str, timeout: float = 5.0):
        """Cancel a task and clean up resources."""
        if task_id not in self.tasks:
            raise KeyError(f"Task {task_id} not found")
        
        task = self.tasks[task_id]
        
        # Check terminal state
        terminal_states = (TaskState.completed, TaskState.failed, TaskState.canceled)
        if task.status.state in terminal_states:
            return
        
        try:
            # Cancel pending async operations and their timers
            from .pending_events import cancel_task_async_operations
            cancel_task_async_operations(task)

            # Unified stop entrypoint (cancellation_event + future + force-stop callbacks + asyncio task)
            if hasattr(task, 'stop') and callable(task.stop):
                task.stop(reason="runner_cancel", force=True)
            else:
                # Backward compatibility fallback
                if task.task:
                    task.task.cancel()

            # Wait briefly for asyncio task to settle after cancellation
            if task.task:
                try:
                    await asyncio.wait_for(task.task, timeout=timeout)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
            
            # Cleanup
            if hasattr(task, 'cleanup') and callable(task.cleanup):
                task.cleanup()
            
            # Clear queue
            if hasattr(task, 'queue') and task.queue:
                while not task.queue.empty():
                    try:
                        task.queue.get_nowait()
                    except Empty:
                        break
            
            # Update status AFTER all cleanup is done — setting it early causes the
            # Guard in _submit_task_execution to misidentify the task as terminal
            # and clear cancellation_event, which can prematurely wake the old
            # execution loop if it is still blocked on cancellation_event.wait().
            task.status.state = TaskState.canceled
            task.status.message = "Task cancelled by user"
            logger.info(f"[cancel_task] Status set to canceled for {task_id} (after cleanup)")
            
            logger.info(f"Task {task_id} cancelled successfully")
            
        except Exception as e:
            logger.error(f"Failed to cancel task {task_id}: {e}")
            raise
    
    async def schedule_task(self, task_id: str, delay: int) -> asyncio.Task:
        """Schedule a task to run after a delay."""
        async def _delayed_run():
            try:
                await asyncio.sleep(delay)
                if task_id in self.tasks:
                    task = self.tasks[task_id]
                    if task.status.state != TaskState.canceled:
                        await self.run_task(task_id)
            except asyncio.CancelledError:
                logger.info(f"Scheduled task {task_id} cancelled")
                raise
        
        return asyncio.create_task(_delayed_run())
    
    # ==================== Task Persistence ====================
    
    def save_task(self, task_id: str):
        """Save task to disk with atomic write."""
        if task_id not in self.tasks:
            raise KeyError(f"Task {task_id} not found")
        
        task = self.tasks[task_id]
        save_dir = Path(self.save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        
        target_file = save_dir / f"{task_id}.json"
        temp_file = None
        
        try:
            with tempfile.NamedTemporaryFile(
                mode='w',
                dir=save_dir,
                prefix=f"{task_id}_",
                suffix=".json.tmp",
                delete=False,
                encoding='utf-8'
            ) as f:
                temp_file = f.name
                # Exclude non-serializable fields (Event, Future, Queue, etc.)
                json_data = task.model_dump_json(
                    indent=2,
                    exclude=TASK_SERIALIZATION_EXCLUDE
                )
                f.write(json_data)
                f.flush()
                os.fsync(f.fileno())
            
            shutil.move(temp_file, target_file)
            logger.debug(f"Task {task_id} saved to {target_file}")
            
        except Exception as e:
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)
            raise IOError(f"Failed to save task {task_id}: {e}")
    
    def load_task(self, task_id: str, skill: "EC_Skill") -> ManagedTask:
        """Load task from disk."""
        file_path = Path(self.save_dir) / f"{task_id}.json"
        
        if not file_path.exists():
            raise FileNotFoundError(f"Task file not found: {task_id}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            raw = f.read()
        
        if not raw.strip():
            raise ValueError(f"Task file is empty: {task_id}")
        
        from a2a.types import Task
        base_task = TypeAdapter(Task).validate_json(raw)
        task = ManagedTask(**base_task.model_dump(), skill=skill)
        
        self.tasks[task_id] = task
        return task
    
    # ==================== Event Routing ====================
    
    def _load_global_event_routing(self) -> Dict[str, dict]:
        """Load global event routing config from agent_files/event_routing.json.
        
        Falls back to the bundled default file if no user-level override exists.
        Returns the 'event_routing' dict from the JSON file.
        """
        # 1. User-level override: <data_home>/event_routing.json
        user_path = os.path.join(self.agent.mainwin.my_ecb_data_homepath, "event_routing.json")
        # 2. Bundled default: agent/agent_files/event_routing.json
        default_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agent_files", "event_routing.json")
        
        for path in (user_path, default_path):
            try:
                if os.path.isfile(path):
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    routing = data.get("event_routing", {})
                    if isinstance(routing, dict) and routing:
                        logger.info(f"[EventRouting] Loaded global event routing from {path} ({len(routing)} rules)")
                        return routing
            except Exception as e:
                logger.warning(f"[EventRouting] Failed to load {path}: {e}")
        
        logger.warning("[EventRouting] No global event_routing.json found, using empty routing")
        return {}
    
    def _save_global_event_routing(self, routing: Dict[str, dict]) -> bool:
        """Save global event routing config to user data directory."""
        user_path = os.path.join(self.agent.mainwin.my_ecb_data_homepath, "event_routing.json")
        try:
            data = {"event_routing": routing}
            os.makedirs(os.path.dirname(user_path), exist_ok=True)
            with open(user_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self._global_event_routing = routing
            logger.info(f"[EventRouting] Saved global event routing to {user_path}")
            return True
        except Exception as e:
            logger.error(f"[EventRouting] Failed to save event routing: {e}")
            return False
    
    def reload_event_routing(self) -> None:
        """Reload global event routing config from disk."""
        self._global_event_routing = self._load_global_event_routing()
    
    def _extract_event_types_from_skill(self, skill, task=None) -> List[Dict[str, Any]]:
        """Extract all event types and their match_fields from a skill's pend_event nodes.

        Inspects the skill's diagram (flowgram) for pend_event_node type nodes
        and collects their eventType, pendingSources, matchFields, timerName, and browserEventLabel.

        SHARED_SKILL_MULTI_TASK_PLAN: shared skills stay agent-agnostic, so the
        pend_event agentIds / matchFields values may carry ``{{var}}``
        placeholders (e.g. ``{{front_desk_agent_id}}``) instead of concrete
        agent ids. When ``task`` is given, placeholders are resolved here —
        at task-launch time, after deployment has created the agents — from
        ``task.metadata["task_vars"]``. A placeholder that can't be resolved
        DROPS that filter (catch-all + WARNING) rather than installing a
        literal ``{{...}}`` string that would silently blackhole every event.

        Returns:
            List of dicts, each with:
              - event_type (str): The event type string
              - match_fields (list): Array of {event_path, task_path} from the node config
              - timer_name (str|None): Timer name if event_type is 'timer'
              - browser_event_label (str|None): Label if event_type is 'browser_event'
        """
        results: List[Dict[str, Any]] = []
        task_vars: Dict[str, Any] = {}
        _md = getattr(task, "metadata", None) if task is not None else None
        if isinstance(_md, dict) and isinstance(_md.get("task_vars"), dict):
            task_vars = _md["task_vars"]
        _task_label = (getattr(task, "name", "") or getattr(task, "id", "") or "?") if task is not None else "?"

        def _resolve_task_var_tokens(value, field_label: str):
            """Substitute {{var}} tokens from task_vars; returns "" when any token is unresolvable."""
            if not isinstance(value, str) or "{{" not in value:
                return value
            unresolved: List[str] = []

            def _sub(m):
                name = m.group(1)
                v = task_vars.get(name)
                if v is not None and str(v).strip():
                    return str(v).strip()
                unresolved.append(name)
                return m.group(0)

            resolved = re.sub(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}", _sub, value)
            if unresolved:
                logger.warning(
                    f"[EventRouting][task_vars] task '{_task_label}': pend_event {field_label} "
                    f"placeholder(s) {unresolved} not found in task_vars "
                    f"(available: {sorted(task_vars.keys())}) — dropping this sender filter "
                    f"(catch-all) so events are not blackholed"
                )
                return ""
            logger.info(
                f"[EventRouting][task_vars] task '{_task_label}': pend_event {field_label} "
                f"'{value}' -> '{resolved}'"
            )
            return resolved
        try:
            diagram = getattr(skill, "diagram", None)
            if not isinstance(diagram, dict):
                return results
            
            # Get nodes from workFlow or top-level
            wf = diagram.get("workFlow") or diagram
            nodes = wf.get("nodes") or diagram.get("nodes") or []
            
            def _collect_all_nodes(node_list: list) -> list:
                """Recursively collect all nodes, including those nested in blocks (loop, conditional)."""
                all_nodes = []
                for node in node_list:
                    if not isinstance(node, dict):
                        continue
                    all_nodes.append(node)
                    # Recurse into blocks (loop nodes, conditional nodes, etc.)
                    blocks = node.get("blocks") or []
                    if isinstance(blocks, list):
                        all_nodes.extend(_collect_all_nodes(blocks))
                return all_nodes
            
            all_nodes = _collect_all_nodes(nodes)
            
            for node in all_nodes:
                if not isinstance(node, dict):
                    continue
                ntype = node.get("type") or ""
                if ntype != "pend_event_node":
                    continue
                
                node_data = node.get("data") or node
                inputs = node_data.get("inputsValues") or {}
                
                # Extract match_fields from the node (shared across all event types in this node)
                mf_raw = (inputs.get("matchFields") or {}).get("content") or []
                match_fields = []
                if isinstance(mf_raw, list):
                    for mf in mf_raw:
                        if isinstance(mf, dict):
                            ep = (mf.get("event_path") or "").strip()
                            tp = (mf.get("task_path") or "").strip()
                            literal = mf.get("literal")
                            # Resolve {{var}} placeholders in literals (the skill
                            # editor materializes the agentIds field into a
                            # context.senderId literal here). Unresolvable →
                            # drop just this filter entry.
                            if isinstance(literal, str) and "{{" in literal:
                                literal = _resolve_task_var_tokens(literal, f"matchFields[{ep}].literal")
                                if not literal:
                                    continue
                                # A var may hold a comma-separated id list; the
                                # matcher treats list literals as membership.
                                if "," in literal:
                                    literal = [seg.strip() for seg in literal.split(",") if seg.strip()]
                            elif isinstance(literal, list):
                                _resolved_items = [
                                    _resolve_task_var_tokens(x, f"matchFields[{ep}].literal")
                                    if isinstance(x, str) else x
                                    for x in literal
                                ]
                                if any(isinstance(x, str) and not x for x in _resolved_items):
                                    continue
                                literal = _resolved_items
                            if ep:  # event_path is required; task_path can be blank
                                entry = {"event_path": ep, "task_path": tp}
                                if literal not in (None, ""):
                                    entry["literal"] = literal
                                match_fields.append(entry)

                def _augment_match_fields(event_type: str, fields: list, agent_ids_value: str):
                    augmented = list(fields or [])
                    # NOTE: a2a_task_result and a2a_response are A2A task result events
                    # that should also receive senderId filtering for proper routing
                    supported = {
                        "chat_message", "human_chat", "task_request", "a2a",
                        "channel_message", "a2a_task_result", "a2a_response"
                    }
                    if event_type not in supported:
                        return augmented
                    raw_ids = [seg.strip() for seg in str(agent_ids_value or "").split(",") if seg.strip()]
                    if raw_ids:
                        literal_value = raw_ids if len(raw_ids) > 1 else raw_ids[0]
                        augmented.append({"event_path": "context.senderId", "literal": literal_value})
                    return augmented

                main_agent_ids = ((inputs.get("agentIds") or {}).get("content") or "").strip()
                main_agent_ids = _resolve_task_var_tokens(main_agent_ids, "agentIds")
                
                # Extract timerName from main event config
                main_timer_name = ((inputs.get("timerName") or {}).get("content") or "").strip()
                # Extract browserEventLabel from main event config
                main_browser_label = ((inputs.get("browserEventLabel") or {}).get("content") or "").strip()
                
                # Main event type
                main_et = (inputs.get("eventType") or {}).get("content")
                if isinstance(main_et, str) and main_et.strip():
                    entry = {"event_type": main_et.strip(), "match_fields": _augment_match_fields(main_et.strip(), match_fields, main_agent_ids)}
                    if main_et.strip() == "timer" and main_timer_name:
                        entry["timer_name"] = main_timer_name
                    if main_et.strip() == "browser_event" and main_browser_label:
                        entry["browser_event_label"] = main_browser_label
                    results.append(entry)
                
                # Additional pending sources
                pending_raw = (inputs.get("pendingSources") or {}).get("content") or []
                if isinstance(pending_raw, list):
                    for src in pending_raw:
                        if isinstance(src, str) and src.strip():
                            # FIX: Apply _augment_match_fields to add senderId filtering for string sources
                            # This ensures pendingSources strings receive the same senderId filter as the main event
                            augmented_fields = _augment_match_fields(src.strip(), match_fields, main_agent_ids)
                            results.append({"event_type": src.strip(), "match_fields": augmented_fields})
                        elif isinstance(src, dict):
                            st = (src.get("type") or "").strip()
                            if st:
                                src_agent_ids = (src.get("agentIds") or "").strip()
                                src_agent_ids = _resolve_task_var_tokens(src_agent_ids, "pendingSources.agentIds")
                                entry = {"event_type": st, "match_fields": _augment_match_fields(st, match_fields, src_agent_ids)}
                                # Extract timerName from pending source item
                                src_timer = (src.get("timerName") or "").strip()
                                if st == "timer" and src_timer:
                                    entry["timer_name"] = src_timer
                                # Extract browserEventLabel from pending source item
                                src_label = (src.get("browserEventLabel") or "").strip()
                                if st == "browser_event" and src_label:
                                    entry["browser_event_label"] = src_label
                                results.append(entry)
        except Exception as e:
            logger.debug(f"[EventRouting] Error extracting event types from skill: {e}")
        
        # Deduplicate by (event_type, timer_name, browser_event_label) while preserving order
        seen = set()
        unique = []
        for entry in results:
            key = (entry["event_type"], entry.get("timer_name", ""), entry.get("browser_event_label", ""))
            if key not in seen:
                seen.add(key)
                unique.append(entry)
        return unique
    
    def _amend_event_routing_for_task(self, task: ManagedTask) -> None:
        """Amend global event routing with entries for a task's pending event nodes.
        
        Called at task launch time. Inspects the task's skill for pend_event nodes,
        extracts the event types and match_fields they expect, and adds routing
        entries to the global config.
        
        If the node has match_fields configured, uses match_fields-based routing.
        For timer events with a timer_name, auto-generates a match_fields rule
        that matches on the timer_name field in the event.
        Otherwise falls back to routing_key: command.run_id for dynamic matching.
        
        Task-specific rules take precedence over generic global defaults. If a
        generic rule already exists for an event type, task-specific rules are
        layered ahead of it instead of being skipped.
        """
        skill = getattr(task, "skill", None)
        if not skill:
            logger.debug(f"[EventRouting] Task '{task.name}' has no skill, skipping routing amendment")
            return
        
        try:
            event_entries = self._extract_event_types_from_skill(skill, task)
            if not event_entries:
                logger.debug(f"[EventRouting] No pend_event nodes found in skill for task '{task.name}'")
                return
            
            amended = False
            for entry in event_entries:
                et = entry["event_type"]
                node_match_fields = entry.get("match_fields") or []
                timer_name = entry.get("timer_name") or ""
                browser_event_label = entry.get("browser_event_label") or ""
                task_session_id = self._get_task_session_id(task)
                
                # For timer events with a name, use a composite routing key
                # so multiple tasks can listen for different timer names.
                # Same pattern for browser_event with a label.
                if timer_name:
                    routing_key_name = f"{et}:{timer_name}"
                elif browser_event_label:
                    routing_key_name = f"{et}:{browser_event_label}"
                else:
                    routing_key_name = et

                # Session-less chat tasks (no session_id) DO get a routing rule — they act as
                # catch-all handlers that accept messages for any session not already owned by a
                # session-specific task. The router's session-filter logic (in _resolve_event_routing)
                # prefers session-specific tasks and only falls back to session-less ones when no
                # session match exists. The pend_event node's own agentIds / match_fields do the
                # final filtering after the message lands in the task queue.
                # NOTE: browser_event tasks have always followed this pattern (never skipped for
                # session-less). chat_message now follows the same principle.

                # NOTE: browser_event routing is NOT skipped when sessionId is absent.
                # Unlike chat messages, browser events (e.g. conversation_became_active
                # on the control page) are often sessionless by design and must still
                # reach the task's pend_event node.
                
                rule: Dict[str, Any] = {
                    "task_selector": f"id:{task.id}",
                    "queue": "",
                    "_auto_added_by_task": task.id,
                    "_auto_added_by_skill": getattr(skill, "name", ""),
                }
                
                if et == "timer" and timer_name:
                    # Auto-generate match_fields for timer events:
                    # match event.timer_name == configured timer_name (literal)
                    timer_match = list(node_match_fields) if node_match_fields else []
                    timer_match.append({
                        "event_path": "context.timer_name",
                        "literal": timer_name,
                    })
                    rule["match_fields"] = timer_match
                    rule["match_mode"] = "all"
                    logger.info(
                        f"[EventRouting] Added timer routing rule: event 'timer' "
                        f"(name='{timer_name}') -> task '{task.name}'"
                    )
                elif et == "browser_event" and browser_event_label:
                    # Auto-generate match_fields for browser events:
                    # match browser-event label regardless of whether the normalized event
                    # keeps sub_type at top level or under context/data. The composite-key
                    # lookup already supports all of these shapes; the rule matcher needs
                    # to do the same.
                    # Do not inherit generic pend_event match_fields here. In practice those
                    # often contain chat-assignment constraints such as context.senderId, which
                    # do not exist on emitted browser events and cause routing to miss.
                    be_match = [
                        {
                            "event_path": "sub_type",
                            "literal": browser_event_label,
                        },
                        {
                            "event_path": "context.sub_type",
                            "literal": browser_event_label,
                        },
                        {
                            "event_path": "data.sub_type",
                            "literal": browser_event_label,
                        },
                    ]
                    rule["match_fields"] = be_match
                    rule["match_mode"] = "any"
                    logger.info(
                        f"[EventRouting] Added browser_event routing rule: event 'browser_event' "
                        f"(label='{browser_event_label}') -> task '{task.name}'"
                    )
                elif et in {"chat_message", "human_chat", "channel_message"} and task_session_id:
                    chat_match = list(node_match_fields) if node_match_fields else []
                    chat_match.append({
                        "event_path": "context.chatId",
                        "task_path": "sessionId",
                    })
                    rule["match_fields"] = chat_match
                    rule["match_mode"] = "all"
                    logger.info(
                        f"[EventRouting] Added session-aware chat routing rule: event '{et}' "
                        f"(chatId -> sessionId='{task_session_id}') -> task '{task.name}'"
                    )
                elif et in {"chat_message", "human_chat", "channel_message"} and not task_session_id:
                    # Session-less chat tasks act as catch-all handlers. The router's
                    # session-filter logic prefers session-specific tasks and only falls
                    # back to session-less ones when no session match exists.
                    if node_match_fields:
                        rule["match_fields"] = list(node_match_fields)
                        rule["match_mode"] = "all"
                    logger.info(
                        f"[EventRouting] Added session-less chat routing rule: event '{et}' "
                        f"-> task '{task.name}' (catch-all, {len(node_match_fields)} match fields)"
                    )
                elif node_match_fields:
                    # Use match_fields from the node config for declarative matching
                    rule["match_fields"] = node_match_fields
                    rule["match_mode"] = "all"
                    logger.info(
                        f"[EventRouting] Added match_fields routing rule: event '{et}' -> "
                        f"task '{task.name}' ({len(node_match_fields)} fields)"
                    )
                else:
                    # Fallback: match by run_id
                    rule["routing_key"] = "command.run_id"
                    logger.info(
                        f"[EventRouting] Added routing_key rule: event '{et}' -> task '{task.name}' (id={task.id})"
                    )
                
                existing_rule = self._global_event_routing.get(routing_key_name)
                if isinstance(existing_rule, dict):
                    existing_chain = existing_rule.get("_rule_chain")
                    if isinstance(existing_chain, list):
                        rule_chain = [r for r in existing_chain if isinstance(r, dict)]
                    else:
                        rule_chain = [existing_rule]

                    filtered_chain: List[Dict[str, Any]] = []
                    for candidate_rule in rule_chain:
                        if candidate_rule.get("_auto_added_by_task") == task.id:
                            logger.debug(
                                f"[EventRouting] Replacing existing auto-added rule for "
                                f"'{routing_key_name}' (task={task.id})"
                            )
                            continue
                        filtered_chain.append(candidate_rule)

                    auto_rules = [r for r in filtered_chain if r.get("_auto_added_by_task")]
                    fallback_rules = [r for r in filtered_chain if not r.get("_auto_added_by_task")]

                    # For browser_event rules, session-specific chatter tasks
                    # must be tried before static tasks.  Static tasks have no
                    # customer context and consume the event without acting on it.
                    if routing_key_name.startswith("browser_event:"):
                        chatter_auto = [
                            r for r in auto_rules
                            if str(r.get("_auto_added_by_task", "")).startswith("auto-chatter-")
                        ]
                        static_auto = [
                            r for r in auto_rules
                            if not str(r.get("_auto_added_by_task", "")).startswith("auto-chatter-")
                        ]
                        if str(rule.get("_auto_added_by_task", "")).startswith("auto-chatter-"):
                            new_chain = chatter_auto + [rule] + static_auto + fallback_rules
                        else:
                            new_chain = chatter_auto + static_auto + [rule] + fallback_rules
                    else:
                        new_chain = auto_rules + [rule] + fallback_rules

                    self._global_event_routing[routing_key_name] = {
                        "_rule_chain": new_chain
                    }
                    logger.debug(
                        f"[EventRouting] Layered task-specific rule for '{routing_key_name}' "
                        f"ahead of {len(fallback_rules)} fallback rule(s)"
                    )
                else:
                    self._global_event_routing[routing_key_name] = rule
                try:
                    debug_entry = self._global_event_routing.get(routing_key_name)
                    logger.info(
                        f"[EventRouting] routing_key='{routing_key_name}' entry="
                        f"{json.dumps(debug_entry, default=str)[:1200]}"
                    )
                except Exception:
                    pass
                amended = True
            
            if amended:
                logger.info(
                    f"[EventRouting] Amended global routing with {len(event_entries)} event types "
                    f"from skill '{getattr(skill, 'name', '')}' for task '{task.name}'"
                )
        except Exception as e:
            logger.warning(f"[EventRouting] Failed to amend routing for task '{task.name}': {e}")
    
    def _extract_nested_value(self, data: Any, key_path: str) -> Any:
        """
        Extract a value from nested dict/object using dot notation.
        E.g., "command.run_id" extracts data["command"]["run_id"] or data.command.run_id
        """
        try:
            parts = key_path.split(".")
            current = data
            for part in parts:
                if isinstance(current, dict):
                    current = current.get(part)
                elif hasattr(current, part):
                    current = getattr(current, part)
                elif hasattr(current, "model_dump"):
                    current = current.model_dump().get(part)
                else:
                    return None
                if current is None:
                    return None
            return current
        except Exception:
            return None

    def _extract_task_value(self, task: ManagedTask, key_path: str) -> Any:
        """Extract a value from a ManagedTask using dot notation.
        
        Supports paths like:
          - "id", "name", "run_id"           → direct task fields
          - "state.account_id"               → task.state dict
          - "state.cloud_run_id"             → task.state dict
          - "skill.id", "skill.name"         → task.skill fields
        """
        try:
            parts = key_path.split(".")
            first = parts[0]
            
            # Resolve the root object
            if first == "state":
                current = task.state or {}
                parts = parts[1:]
            elif first == "skill":
                current = getattr(task, "skill", None)
                if current is None:
                    return None
                parts = parts[1:]
            else:
                current = task
            
            # Walk the remaining path
            for part in parts:
                if isinstance(current, dict):
                    current = current.get(part)
                elif hasattr(current, part):
                    current = getattr(current, part)
                elif hasattr(current, "model_dump"):
                    current = current.model_dump().get(part)
                else:
                    return None
                if current is None:
                    return None
            return current
        except Exception:
            return None

    def _get_task_session_id(self, task: ManagedTask) -> str:
        """Best-effort extract a stable session id from a task."""
        try:
            for attr in ("sessionId", "session_id"):
                value = getattr(task, attr, None)
                if isinstance(value, str) and value.strip():
                    return value.strip()

            metadata = getattr(task, "metadata", None) or {}
            if isinstance(metadata, dict):
                ownership_scope = metadata.get("ownership_scope") or {}
                if isinstance(ownership_scope, dict):
                    for key in ("session_id", "sessionId"):
                        value = ownership_scope.get(key)
                        if isinstance(value, str) and value.strip():
                            return value.strip()

            state = getattr(task, "state", None) or {}
            if isinstance(state, dict):
                for key in ("session_id", "sessionId", "chat_id", "chatId"):
                    value = state.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()

            task_name = (getattr(task, "name", "") or "").strip()
            if task_name.startswith("chat:") and ":" in task_name:
                suffix = task_name.rsplit(":", 1)[-1].strip()
                if suffix.startswith("cust_"):
                    return suffix
        except Exception:
            pass
        return ""
    
    @staticmethod
    def _apply_match_transform(value: Any, transform: str) -> Any:
        """Apply a transform to a value before comparison.
        
        Supported transforms:
          - "lowercase" / "lower"   → str.lower()
          - "uppercase" / "upper"   → str.upper()
          - "strip"                 → str.strip()
          - "to_string" / "str"     → str()
          - "to_int" / "int"        → int()
          - "prefix:X"              → remove prefix X from string
          - "suffix:X"              → remove suffix X from string
        """
        if value is None or not transform:
            return value
        try:
            t = transform.strip().lower()
            sv = str(value) if not isinstance(value, str) else value
            
            if t in ("lowercase", "lower"):
                return sv.lower()
            elif t in ("uppercase", "upper"):
                return sv.upper()
            elif t == "strip":
                return sv.strip()
            elif t in ("to_string", "str"):
                return str(value)
            elif t in ("to_int", "int"):
                return int(value)
            elif t.startswith("prefix:"):
                prefix = transform.split(":", 1)[1]
                return sv[len(prefix):] if sv.startswith(prefix) else sv
            elif t.startswith("suffix:"):
                suffix = transform.split(":", 1)[1]
                return sv[:-len(suffix)] if sv.endswith(suffix) else sv
            else:
                return value
        except Exception:
            return value
    
    def _evaluate_match_fields(self, match_fields: list, match_mode: str,
                               request: Any, task: ManagedTask) -> bool:
        """Evaluate match_fields rules against a request and task.
        
        Args:
            match_fields: List of {event_path, task_path, transform?, literal?} dicts.
                If 'literal' is present, compare event value against the static string
                (ignores task_path). Otherwise compare event value vs task value.
            match_mode: "all" (every pair must match) or "any" (at least one).
            request: The incoming event/request object.
            task: The candidate ManagedTask.
            
        Returns:
            True if the task matches according to match_mode.
        """
        if not match_fields:
            return False
        
        results = []
        for mf in match_fields:
            if not isinstance(mf, dict):
                continue
            event_path = mf.get("event_path") or ""
            task_path = mf.get("task_path") or ""
            literal = mf.get("literal")
            transform = mf.get("transform") or ""
            
            if not event_path:
                continue
            # Need either task_path or literal to compare against
            if not task_path and literal is None:
                continue
            
            event_val = self._extract_nested_value(request, event_path)
            
            if literal is not None:
                # Compare event value against a static literal string
                if transform:
                    event_val = self._apply_match_transform(event_val, transform)
                if isinstance(literal, (list, tuple, set)):
                    candidates = [self._apply_match_transform(v, transform) if transform else v for v in literal]
                    matched = (event_val is not None and str(event_val) in {str(v) for v in candidates})
                else:
                    matched = (event_val is not None and str(event_val) == str(literal))
                results.append(matched)
                logger.debug(
                    f"[ROUTING] match_field: event.{event_path}={event_val} vs literal='{literal}' "
                    f"→ {'✅' if matched else '❌'}"
                )
            else:
                task_val = self._extract_task_value(task, task_path)
                
                # Apply transform to both sides
                if transform:
                    event_val = self._apply_match_transform(event_val, transform)
                    task_val = self._apply_match_transform(task_val, transform)
                
                matched = (event_val is not None and task_val is not None
                           and str(event_val) == str(task_val))
                results.append(matched)
                logger.debug(
                    f"[ROUTING] match_field: event.{event_path}={event_val} vs task.{task_path}={task_val} "
                    f"→ {'✅' if matched else '❌'}"
                )
        
        if not results:
            return False
        
        if match_mode == "any":
            return any(results)
        return all(results)  # default: "all"
    
    def _resolve_event_routing(self, event_type: str, request: Any, source: str = "") -> Optional[Tuple[ManagedTask, dict]]:
        """
        Route an event to a task using the global agent-level event routing config.

        Supports ordered rule candidates per event type so task-specific rules can
        coexist with generic fallback rules from `event_routing.json`.
        """
        try:
            event = normalize_event(event_type, request, src=source)
            etype = event.get("type") or event_type
        except Exception:
            event = None
            etype = event_type

        logger.debug(f"[ROUTING] normalized event: {etype}")
        alias_candidates = [etype]
        if etype == "chat_message":
            alias_candidates.append("human_chat")
        elif etype == "human_chat":
            alias_candidates.append("chat_message")
        elif etype == "task_request":
            alias_candidates.append("a2a")
        elif etype == "a2a":
            alias_candidates.append("task_request")

        try:
            rule = None
            candidate_rules: List[Dict[str, Any]] = []
            resolved_etype = etype

            def _extract_rules(rule_value: Any) -> List[Dict[str, Any]]:
                if not isinstance(rule_value, dict):
                    return []
                chain = rule_value.get("_rule_chain")
                if isinstance(chain, list):
                    return [r for r in chain if isinstance(r, dict)]
                return [rule_value]

            for candidate in alias_candidates:
                extracted = _extract_rules(self._global_event_routing.get(candidate))
                if extracted:
                    candidate_rules = extracted
                    rule = extracted[0]
                    resolved_etype = candidate
                    if candidate != etype:
                        logger.debug(f"[ROUTING] Resolved event alias '{etype}' via rule '{candidate}'")
                    break

            if not candidate_rules and etype == "timer":
                timer_name = None
                if isinstance(event, dict):
                    timer_name = (
                        event.get("timer_name")
                        or (event.get("context") or {}).get("timer_name")
                        or (event.get("data") or {}).get("timer_name")
                    )
                if not timer_name and isinstance(request, dict):
                    timer_name = request.get("timer_name")
                if timer_name:
                    composite_key = f"{etype}:{timer_name}"
                    candidate_rules = _extract_rules(self._global_event_routing.get(composite_key))
                    if candidate_rules:
                        rule = candidate_rules[0]
                        logger.debug(f"[ROUTING] Resolved timer via composite key '{composite_key}'")

            if not candidate_rules and etype == "browser_event":
                sub_type = None
                if isinstance(event, dict):
                    sub_type = (
                        event.get("sub_type")
                        or (event.get("context") or {}).get("sub_type")
                        or (event.get("data") or {}).get("sub_type")
                    )
                if not sub_type and isinstance(request, dict):
                    sub_type = request.get("sub_type")
                if sub_type:
                    composite_key = f"{etype}:{sub_type}"
                    candidate_rules = _extract_rules(self._global_event_routing.get(composite_key))
                    if candidate_rules:
                        rule = candidate_rules[0]
                        logger.debug(f"[ROUTING] Resolved browser_event via composite key '{composite_key}'")

            if not isinstance(rule, dict):
                logger.debug(f"[ROUTING] No global routing rule for event type '{etype}'")
                return None

            tasks_list = getattr(self.agent, "tasks", []) or []
            event_session_id = ""
            if etype in {"chat_message", "human_chat", "channel_message"}:
                try:
                    event_session_id = self._extract_session_key_from_request(etype, request, source)
                except Exception:
                    event_session_id = ""
            logger.info(f"[ROUTING] Routing event '{etype}' (rule='{resolved_etype}') - {len(tasks_list)} tasks available")
            if etype == "browser_event":
                try:
                    task_debug = [
                        {
                            "id": getattr(t, "id", ""),
                            "name": getattr(t, "name", ""),
                            "sessionId": self._get_task_session_id(t),
                            "skill": getattr(getattr(t, "skill", None), "name", ""),
                        }
                        for t in tasks_list if t
                    ]
                    logger.info(f"[ROUTING] browser_event tasks_list={json.dumps(task_debug, ensure_ascii=True)}")
                except Exception:
                    pass

            for idx, candidate_rule in enumerate(candidate_rules, start=1):
                selector = candidate_rule.get("task_selector") or ""
                if selector:
                    candidates = [t for t in tasks_list if t and self._evaluate_selector(selector, t)]
                    if not candidates:
                        logger.debug(
                            f"[ROUTING] Rule candidate {idx}/{len(candidate_rules)} for '{etype}' matched no task_selector '{selector}'"
                        )
                        if etype == "browser_event":
                            try:
                                logger.info(
                                    f"[ROUTING] browser_event selector_miss selector='{selector}' "
                                    f"available_task_ids={[getattr(t, 'id', '') for t in tasks_list if t]}"
                                )
                            except Exception:
                                pass
                        continue
                else:
                    candidates = [t for t in tasks_list if t]

                if event_session_id and etype in {"chat_message", "human_chat", "channel_message"}:
                    session_candidates = [
                        t for t in candidates
                        if self._get_task_session_id(t) == event_session_id
                    ]
                    if session_candidates:
                        # Prefer session-specific tasks (exact match).
                        candidates = session_candidates
                    else:
                        # No session-specific task owns this session yet.
                        # Fall back to session-less tasks (no session_id set) — they act as
                        # catch-all handlers and do their own filtering via pend_event agentIds /
                        # match_fields. This mirrors how browser_event tasks work: session-less
                        # does not mean "unreachable", it means "accepts any session".
                        sessionless_candidates = [
                            t for t in candidates
                            if not self._get_task_session_id(t)
                        ]
                        if sessionless_candidates:
                            candidates = sessionless_candidates
                            logger.debug(
                                f"[ROUTING] Rule candidate {idx}/{len(candidate_rules)} for '{etype}': "
                                f"no session-specific task for session='{event_session_id}', "
                                f"falling back to {len(sessionless_candidates)} session-less candidate(s)"
                            )
                        else:
                            logger.debug(
                                f"[ROUTING] Rule candidate {idx}/{len(candidate_rules)} for '{etype}' "
                                f"has no match for session='{event_session_id}' and no session-less fallback"
                            )
                            continue

                match_fields = candidate_rule.get("match_fields")
                if isinstance(match_fields, list) and match_fields:
                    match_mode = candidate_rule.get("match_mode", "all")
                    event_data = event if isinstance(event, dict) else request
                    for t in candidates:
                        if self._evaluate_match_fields(match_fields, match_mode, event_data, t):
                            skill_obj = getattr(t, "skill", None)
                            skill_name = getattr(skill_obj, "name", skill_obj) if skill_obj else ""
                            skill_id = getattr(skill_obj, "id", "") if skill_obj else ""
                            logger.info(
                                f"[ROUTING] Matched task via match_fields: {t.name}, id={t.id}, skill={skill_name}, skill_id={skill_id}"
                            )
                            return (t, candidate_rule)
                    logger.debug(
                        f"[ROUTING] Rule candidate {idx}/{len(candidate_rules)} did not match via match_fields for event '{etype}'"
                    )

                routing_key = candidate_rule.get("routing_key")
                if routing_key:
                    key_value = None
                    if isinstance(event, dict):
                        key_value = self._extract_nested_value(event, routing_key)
                    if key_value is None:
                        key_value = self._extract_nested_value(request, routing_key)
                    if key_value:
                        logger.debug(f"[ROUTING] routing_key '{routing_key}' = '{key_value}'")
                        for t in candidates:
                            if "run_id" in routing_key:
                                if str(t.id) == str(key_value):
                                    skill_obj = getattr(t, "skill", None)
                                    skill_name = getattr(skill_obj, "name", skill_obj) if skill_obj else ""
                                    skill_id = getattr(skill_obj, "id", "") if skill_obj else ""
                                    logger.info(
                                        f"[ROUTING] Matched task by run_id: {t.name}, id={t.id}, skill={skill_name}, skill_id={skill_id}"
                                    )
                                    return (t, candidate_rule)
                                cloud_run_id = (t.state or {}).get("cloud_run_id")
                                if cloud_run_id and str(cloud_run_id) == str(key_value):
                                    skill_obj = getattr(t, "skill", None)
                                    skill_name = getattr(skill_obj, "name", skill_obj) if skill_obj else ""
                                    skill_id = getattr(skill_obj, "id", "") if skill_obj else ""
                                    logger.info(
                                        f"[ROUTING] Matched task by cloud_run_id: {t.name}, id={t.id}, skill={skill_name}, skill_id={skill_id}"
                                    )
                                    return (t, candidate_rule)
                            if "skill_id" in routing_key:
                                skill = getattr(t, "skill", None)
                                if skill and str(getattr(skill, "id", "")) == str(key_value):
                                    skill_name = getattr(skill, "name", skill)
                                    skill_id = getattr(skill, "id", "")
                                    logger.info(
                                        f"[ROUTING] Matched task by skill_id: {t.name}, id={t.id}, skill={skill_name}, skill_id={skill_id}"
                                    )
                                    return (t, candidate_rule)
                    logger.debug(
                        f"[ROUTING] Rule candidate {idx}/{len(candidate_rules)} did not match routing_key '{routing_key}' for event '{etype}'"
                    )

                if selector and not match_fields and not routing_key and candidates:
                    t = candidates[0]
                    logger.info(f"[ROUTING] Matched task via selector '{selector}': {t.name}, id={t.id}")
                    return (t, candidate_rule)

                if not match_fields and not routing_key and not selector:
                    logger.debug(
                        f"[ROUTING] Rule candidate {idx}/{len(candidate_rules)} for event '{etype}' has no matching strategy"
                    )

        except Exception as e:
            logger.error(get_traceback(e, "ErrorResolveEventRouting"))

        return None

    def _evaluate_selector(self, selector: str, task: ManagedTask) -> bool:
        """Evaluate a task selector against a task."""
        try:
            if selector.startswith("id:"):
                task_id = selector.split(":", 1)[1].strip()
                return (task.id or "").strip() == task_id
            elif selector.startswith("name:"):
                name = selector.split(":", 1)[1].strip().lower()
                task_name = (task.name or "").strip().lower()
                skill_name = (getattr(task.skill, "name", "") or "").strip().lower()
                return task_name == name or skill_name == name
            elif selector.startswith("name_contains:"):
                needle = selector.split(":", 1)[1].strip().lower()
                return needle in (task.name or "").lower()
            else:
                return True  # No selector = match
        except Exception:
            return False
    
    # ==================== Task Finding ====================
    
    def _event_aliases_for_routing(self, event_type: str) -> set[str]:
        etype = str(event_type or "").strip()
        aliases = {etype} if etype else set()
        if etype == "chat_message":
            aliases.add("human_chat")
        elif etype == "human_chat":
            aliases.add("chat_message")
        elif etype == "task_request":
            aliases.add("a2a")
        elif etype == "a2a":
            aliases.add("task_request")
        return aliases

    def _task_declares_event_handler(
        self,
        task: ManagedTask,
        event_type: str,
        request: Any = None,
        source: str = "",
    ) -> bool:
        try:
            skill = getattr(task, "skill", None)
            if not skill or getattr(skill, "runnable", None) is None:
                return False
            aliases = self._event_aliases_for_routing(event_type)
            if not aliases:
                return False
            entries = self._extract_event_types_from_skill(skill, task)
            if not entries:
                return False
            event_data = None
            for entry in entries:
                if str(entry.get("event_type") or "").strip() not in aliases:
                    continue
                match_fields = entry.get("match_fields")
                if isinstance(match_fields, list) and match_fields and request is not None:
                    if event_data is None:
                        try:
                            event_data = normalize_event(event_type, request, src=source)
                        except Exception:
                            event_data = request
                    if not self._evaluate_match_fields(
                        match_fields,
                        str(entry.get("match_mode") or "all"),
                        event_data,
                        task,
                    ):
                        continue
                return True
        except Exception as exc:
            logger.debug(
                f"[chatter_task] event-handler detection skipped for "
                f"task={getattr(task, 'name', '?')!r}: {exc}"
            )
        return False

    def _is_chatter_task(
        self,
        task: ManagedTask,
        request: Any = None,
        event_type: str = "chat_message",
        source: str = "",
    ) -> bool:
        try:
            task_name = (getattr(task, "name", "") or "").lower()
            skill_name = (getattr(getattr(task, "skill", None), "name", "") or "").lower()
            if "chat" in task_name or "chat" in skill_name:
                return True
            trigger = getattr(task, "trigger", []) or []
            if isinstance(trigger, str):
                trigger = [trigger]
            if "message" in {str(t).lower() for t in trigger}:
                return True
            return self._task_declares_event_handler(task, event_type, request, source)
        except Exception:
            return False

    def find_chatter_tasks(
        self,
        request: Any = None,
        event_type: str = "chat_message",
        source: str = "",
    ) -> Optional[ManagedTask]:
        """Find a chat task (task name contains 'chat')."""
        found = [
            task
            for task in self.agent.tasks
            if self._is_chatter_task(task, request, event_type, source)
        ]
        if found:
            logger.debug(f"[find_chatter_tasks] Found: {found[0].id}")
            return found[0]
        logger.error("NO chatter tasks found!")
        return None

    def _extract_session_key_from_request(self, event_type: str, request: Any, source: str = "") -> str:
        """Best-effort extract a stable session key from an incoming chat/request event."""
        try:
            from .resume import normalize_event

            event = normalize_event(event_type, request, src=source)
            ctx = event.get("context", {}) if isinstance(event, dict) else {}
            for key in ("chatId", "sessionId"):
                value = ctx.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

            data = event.get("data", {}) if isinstance(event, dict) else {}
            human_text = data.get("human_text")
            if isinstance(human_text, str) and human_text.strip().startswith("{"):
                try:
                    payload = json.loads(human_text)
                except Exception:
                    payload = None
                if isinstance(payload, dict):
                    for key in ("session_id", "sessionId", "customer_id", "customerId"):
                        value = payload.get(key)
                        if isinstance(value, str) and value.strip():
                            return value.strip()
        except Exception as e:
            logger.debug(f"[chatter_task] session key extraction skipped: {e}")
        return ""

    def _find_chatter_task_by_session(
        self,
        session_id: str,
        request: Any = None,
        event_type: str = "chat_message",
        source: str = "",
    ) -> Optional[ManagedTask]:
        if not session_id:
            return None
        for task in getattr(self.agent, "tasks", []) or []:
            if self._get_task_session_id(task) != session_id:
                continue
            if self._is_chatter_task(task, request, event_type, source):
                logger.debug(f"[find_chatter_task_by_session] Found: {task.id} for session_id={session_id}")
                return task
        return None

    def _find_sessionless_chatter_task(
        self,
        request: Any = None,
        event_type: str = "chat_message",
        source: str = "",
    ) -> Optional[ManagedTask]:
        for task in getattr(self.agent, "tasks", []) or []:
            if self._get_task_session_id(task):
                continue
            if self._is_chatter_task(task, request, event_type, source):
                logger.debug(f"[find_sessionless_chatter_task] Found: {task.id}")
                return task
        return None

    def _restart_task_execution(self, task: ManagedTask):
        """Restart execution loop for a completed/failed task.
        
        This is called when a new message arrives for a task that has already
        completed or failed. The task needs to be reset and its execution loop
        restarted to process the new message.
        """
        try:
            mainwin = getattr(self.agent, "mainwin", None)
            thread_pool = getattr(mainwin, "threadPoolExecutor", None) if mainwin else None
            
            if not thread_pool:
                logger.warning(f"[restart_task_execution] No thread pool available for task '{task.name}'")
                return False
                
            if not hasattr(task, "run_id") or not task.run_id:
                logger.warning(f"[restart_task_execution] Task '{task.name}' has no run_id")
                return False
            
            # Check if already running
            active_tasks = getattr(self.agent, "active_tasks", {}) or {}
            if task.run_id in active_tasks:
                future = active_tasks.get(task.run_id)
                if future and not future.done():
                    # Check if the future has an exception (failed execution)
                    try:
                        if future.done() and future.exception() is not None:
                            logger.info(f"[restart_task_execution] Task '{task.name}' has failed execution with exception, forcing restart")
                            # Remove the old future and continue to restart
                            del active_tasks[task.run_id]
                        else:
                            logger.info(f"[restart_task_execution] Task '{task.name}' already has active execution")
                            return True
                    except Exception:
                        # Cannot determine future state, treat as active
                        logger.info(f"[restart_task_execution] Task '{task.name}' already has active execution (state unknown)")
                        return True
            
            # Reset task state
            task_state = getattr(task, "status", None)
            if task_state:
                try:
                    task_state.state = TaskState.submitted
                except Exception:
                    pass
            
            # Clear any previous state
            if task.id in self._task_states:
                self._task_states[task.id] = {'justStarted': True}
            
            # Start new execution loop
            future = thread_pool.submit(self.launch_unified_run, task, ["message"])
            with getattr(self.agent, "task_lock", type("DummyLock", (), {"__enter__": lambda s: None, "__exit__": lambda s, *a: None})()):
                active_tasks[task.run_id] = future
            logger.info(f"[restart_task_execution] Started execution loop for task '{task.name}', run_id={task.run_id}")
            return True
            
        except Exception as e:
            logger.error(f"[restart_task_execution] Failed to restart task '{getattr(task, 'name', '?')}': {e}")
            return False

    def _ensure_task_execution_alive(self, task: "ManagedTask", event_type: str = "") -> None:
        """
        Check whether a task's execution loop is still running; if not, restart it.

        When routing finds an existing chat task, we need to ensure the worker loop is alive
        to consume queued messages. If the task has terminated (completed/failed), restart
        it — the new launch_unified_run cycle will begin a fresh skill execution from start_0
        with a clean state, which is the correct behavior for a new user message.
        """
        if task is None:
            return
        try:
            task_state = getattr(task, "status", None)
            task_status = getattr(task_state, "state", None) if task_state else None
            is_terminal = task_status in ("completed", "failed", "canceled") if task_status else False

            active_tasks = getattr(self.agent, "active_tasks", {}) or {}
            has_active_execution = False
            if task.run_id in active_tasks:
                future = active_tasks.get(task.run_id)
                if future is not None:
                    if not future.done():
                        has_active_execution = True
                    else:
                        # Check if the future has an exception (failed execution)
                        try:
                            if future.exception() is not None:
                                logger.info(f"[ensure_task_execution_alive] Task '{task.name}' has failed future, will restart")
                                # Remove the stale future entry
                                del active_tasks[task.run_id]
                                has_active_execution = False
                        except Exception:
                            # Cannot determine exception state, consider as not running
                            has_active_execution = False

            if is_terminal or not has_active_execution:
                if event_type in _PRIORITY_HIGH_EVENT_TYPES and hasattr(task, "reset_failures"):
                    try:
                        if (
                            hasattr(task, "is_max_failures_reached")
                            and task.is_max_failures_reached()
                        ):
                            logger.info(
                                f"[ensure_task_execution_alive] Resetting failure guard for "
                                f"task '{task.name}' because a real {event_type} message arrived"
                            )
                        task.reset_failures()
                    except Exception as _reset_err:
                        logger.debug(
                            f"[ensure_task_execution_alive] Could not reset failures for "
                            f"task '{getattr(task, 'name', '?')}': {_reset_err}"
                        )
                logger.info(
                    f"[ensure_task_execution_alive] Task '{task.name}' is "
                    f"status={task_status}, active={has_active_execution}; restarting execution loop"
                )
                self._restart_task_execution(task)
            else:
                logger.debug(f"[ensure_task_execution_alive] Task '{task.name}' has active execution")
        except Exception as e:
            logger.error(f"[ensure_task_execution_alive] Failed for task '{getattr(task, 'name', '?')}': {e}")

    def _ensure_chatter_task(self, request: Any = None, event_type: str = "", source: str = "") -> Optional["ManagedTask"]:
        """Ensure the agent has a chatter task for routing human_chat/a2a events.
        
        If an existing completed/failed task is found for the session, it will be
        reset and its execution loop restarted to handle the new message.
        """
        session_id = self._extract_session_key_from_request(event_type, request, source) if request is not None else ""
        if session_id:
            existing = self._find_chatter_task_by_session(
                session_id,
                request=request,
                event_type=event_type,
                source=source,
            )
            if existing:
                # Check if task needs to be restarted (completed/failed task with no active execution)
                task_state = getattr(existing, "status", None)
                task_status = getattr(task_state, "state", None) if task_state else None
                is_terminal = task_status in ("completed", "failed", "canceled") if task_status else False
                
                # Check if task has an active execution loop
                has_active_execution = False
                if hasattr(existing, "run_id") and existing.run_id:
                    active_tasks = getattr(self.agent, "active_tasks", {}) or {}
                    if existing.run_id in active_tasks:
                        future = active_tasks.get(existing.run_id)
                        if future is not None:
                            if not future.done():
                                has_active_execution = True
                            else:
                                # Check if the future has an exception (failed execution)
                                try:
                                    if future.exception() is not None:
                                        logger.info(f"[ensure_chatter_task] Task '{existing.name}' has failed future, will restart")
                                        # Remove the stale future entry
                                        del active_tasks[existing.run_id]
                                        has_active_execution = False
                                except Exception:
                                    # Cannot determine exception state, consider as not running
                                    has_active_execution = False
                
                if is_terminal or not has_active_execution:
                    logger.info(f"[ensure_chatter_task] Found completed task '{existing.name}' for session {session_id}, "
                                f"status={task_status}, will restart execution loop")
                    # Reset task state
                    if task_state:
                        try:
                            task_state.state = TaskState.submitted
                        except Exception:
                            pass
                    # Restart execution loop
                    self._restart_task_execution(existing)
                else:
                    logger.info(f"[ensure_chatter_task] Found active task '{existing.name}' for session {session_id}")
                return existing
            existing = self._find_sessionless_chatter_task(
                request=request,
                event_type=event_type,
                source=source,
            )
            if existing:
                logger.info(
                    f"[ensure_chatter_task] Found session-less chat-capable task "
                    f"'{existing.name}' for session {session_id}"
                )
                return existing
        else:
            existing = self.find_chatter_tasks(
                request=request,
                event_type=event_type,
                source=source,
            )
            if existing:
                return existing

        # Strategy: prefer the skill from a pre-configured chat task (which may reference
        # the full workflow, e.g. gooflish_listing_v3) over a name-matched skill from
        # agent.skills (which may be a simpler chatter like gooflish_listing_chatter).
        chatter_skill = None

        # 1. Check agent's pre-configured tasks for a chat task with a runnable skill
        for t in getattr(self.agent, "tasks", []) or []:
            is_chat_task = self._is_chatter_task(t, request, event_type, source)
            t_skill = getattr(t, "skill", None)
            if is_chat_task and t_skill and getattr(t_skill, "runnable", None) is not None:
                chatter_skill = t_skill
                logger.info(f"[ensure_chatter_task] Using skill '{getattr(t_skill, 'name', '?')}' "
                            f"from pre-configured task '{getattr(t, 'name', '?')}'")
                break

        # 2. Fallback: search agent.skills for a skill with "chat" in the name
        if not chatter_skill:
            skills = getattr(self.agent, "skills", []) or []
            logger.info(f"[ensure_chatter_task] Agent '{getattr(getattr(self.agent, 'card', None), 'name', '?')}' has {len(skills)} skills: {[getattr(sk, 'name', '?') for sk in skills]}")
            chat_candidates = [sk for sk in skills if sk and re.search(r'(?<![a-z])chat', (getattr(sk, "name", "") or "").lower())]
            logger.info(f"[ensure_chatter_task] Found {len(chat_candidates)} chat candidates: {[getattr(sk, 'name', '?') for sk in chat_candidates]}")

            # Simply select the first candidate with a valid runnable
            # Note: Skills should already have runnable compiled during agent initialization.
            # If runnable is None here, it indicates a skill loading problem that should be fixed
            # at the skill loading stage (build_agent_skills.load_skill_from_folder), not here.
            chatter_skill = next((sk for sk in chat_candidates if getattr(sk, "runnable", None) is not None), None)
            if chatter_skill:
                logger.info(f"[ensure_chatter_task] Using name-matched skill '{getattr(chatter_skill, 'name', '?')}' from agent.skills")

        if not chatter_skill:
            logger.error("[ensure_chatter_task] No chat skill found (checked tasks and skills); cannot auto-create chatter task")
            return None

        task_id = f"auto-chatter-{uuid.uuid4()}"
        task = ManagedTask(
            id=task_id,
            context_id=task_id,
            name=(
                f"chat:{getattr(chatter_skill, 'name', 'chatter')}:{session_id}"
                if session_id else
                f"chat:Auto Chatter Task ({getattr(chatter_skill, 'name', 'chatter')})"
            ),
            description="Auto-created chatter task for routing",
            source="code",
            status=A2ATaskStatus(state=TaskState.submitted),
            sessionId=session_id or "",
            skill=chatter_skill,
            metadata={"state": {"top": "ready"}, "ownership_scope": {"session_id": session_id}} if session_id else {"state": {"top": "ready"}},
            state={"top": "ready"},
            resume_from="",
            trigger="message",
            agent_id=getattr(getattr(self.agent, "card", None), "id", "") or "",
        )

        if getattr(self.agent, "tasks", None) is None:
            self.agent.tasks = []
        self.agent.tasks.append(task)
        logger.info(f"[ensure_chatter_task] Auto-created chatter task: {task.name} (session_id={session_id or ''})")

        # Start the execution loop for this new task so it can consume from its queue
        try:
            mainwin = getattr(self.agent, "mainwin", None)
            thread_pool = getattr(mainwin, "threadPoolExecutor", None) if mainwin else None
            if thread_pool and hasattr(task, "run_id") and task.run_id:
                future = thread_pool.submit(self.launch_unified_run, task, ["message"])
                if hasattr(self.agent, "active_tasks") and hasattr(self.agent, "task_lock"):
                    with self.agent.task_lock:
                        self.agent.active_tasks[task.run_id] = future
                logger.info(f"[ensure_chatter_task] Started execution loop for task: {task.name}, run_id={task.run_id}")
            else:
                logger.warning(f"[ensure_chatter_task] Could not start execution loop (no thread pool or run_id)")
        except Exception as e:
            logger.error(f"[ensure_chatter_task] Failed to start execution loop: {e}")

        return task
    
    def find_suitable_tasks(self, msg) -> List[ManagedTask]:
        """Find suitable tasks for a message."""
        found = []
        msg_js = json.loads(msg["message"])
        
        if msg_js['metadata']["mtype"] == "send_task":
            name_filter = (((msg_js.get('metadata') or {}).get('task') or {}).get('name') or '')
            found = [task for task in self.agent.tasks if name_filter.lower() in (task.name or "").lower()]
        elif msg_js['metadata']["mtype"] == "send_chat":
            found = [task for task in self.agent.tasks if "chat" in (task.name or "").lower()]
        
        return found
    
    # ==================== Queue Management ====================
    
    def sync_task_wait_in_line(self, event_type: str, request: Any, source: str = "", async_response: bool = None):
        """
        Queue a task/message for processing.
        
        Args:
            event_type: Type of event.
            request: The request object.
            source: Optional source identifier.
            async_response: If True, response via A2A; if False, via waiter.
        """
        try:
            _sub_type = ""
            if event_type == "browser_event" and isinstance(request, dict):
                _sub_type = request.get("sub_type", "")
            
            # [DEBUG] Add caller stack trace for chat_message to track duplicate issues
            _caller_info = ""
            if event_type == "chat_message":
                import traceback
                _stack = traceback.extract_stack()
                # Skip last 3 frames (this function, wrapper, etc.)
                _caller_frames = _stack[:-3] if len(_stack) > 3 else _stack
                _caller_info = " | caller=" + " -> ".join([
                    f"{f.filename.split('/')[-1]}:{f.lineno}" 
                    for f in _caller_frames[-5:]  # Last 5 frames
                ])
            
            logger.info(f"[QUEUE] sync_task_wait_in_line: event_type={event_type}{f', sub_type={_sub_type}' if _sub_type else ''}, agent={self.agent.card.name}{_caller_info}")
            
            # Handle async callback events (from webhooks/SSE)
            if event_type == "async_callback":
                self._route_async_callback(request)
                return

            if _is_live_chat_shutdown_active():
                _shutdown_live_chat_payload = _live_chat_payload_from_queue_msg(request)
                _shutdown_response_payload = _live_chat_response_payload_from_queue_msg(request)
                if event_type == "browser_event":
                    logger.warning(
                        f"[LIVE-CHAT-SHUTDOWN] suppressing browser_event during shutdown "
                        f"sub_type={_sub_type!r} source={source!r}"
                    )
                    return
                if event_type == "chat_message" and not _shutdown_response_payload:
                    if _shutdown_live_chat_payload:
                        _log_live_chat_delivery_aborted_shutdown(
                            _shutdown_live_chat_payload,
                            reason="new_live_chat_task_suppressed_during_shutdown",
                            source=source,
                        )
                    logger.warning(
                        f"[LIVE-CHAT-SHUTDOWN] suppressing non-reply chat_message "
                        f"during shutdown source={source!r} msg={_describe_queue_msg(request)}"
                    )
                    return
                if (
                    event_type == "chat_message"
                    and _shutdown_response_payload
                    and _is_live_chat_shutdown_drain_finalized()
                ):
                    _log_live_chat_delivery_aborted_shutdown(
                        _shutdown_response_payload,
                        reason="late_response_after_shutdown_drain",
                        source=source,
                    )
                    logger.warning(
                        f"[LIVE-CHAT-SHUTDOWN] dropping late live-chat response after "
                        f"drain finalized source={source!r} msg={_describe_queue_msg(request)}"
                    )
                    return
            
            # Attach async_response to request
            if async_response is not None:
                try:
                    if hasattr(request, 'params') and request.params:
                        if not request.params.metadata:
                            request.params.metadata = {}
                        request.params.metadata["async_response"] = async_response
                except Exception:
                    pass
            
            # Route to target task
            routing_result = self._resolve_event_routing(event_type, request, source)
            if routing_result:
                target_task, rule = routing_result
                try:
                    logger.info(
                        f"[QUEUE] Routed event_type={event_type}"
                        f"{f', sub_type={_sub_type}' if _sub_type else ''} "
                        f"to task={target_task.name} via rule={getattr(rule, 'event_type', '')}/"
                        f"{getattr(rule, 'browser_event_label', '')}"
                    )
                except Exception:
                    pass
                if not hasattr(target_task, "queue") or target_task.queue is None:
                    logger.error(f"[QUEUE] Target task has no queue: {target_task.name}")
                    return

                if event_type == "chat_message":
                    try:
                        from agent.ec_tasks.resume import normalize_event as _ledger_normalize_event
                        _ledger_bridge = _live_chat_bridge().trace_ledger
                        _ledger_payload = _ledger_bridge.log_payload
                        _ledger_parse_json = _ledger_bridge.parse_jsonish_dict

                        _ledger_evt = _ledger_normalize_event(
                            "chat_message", request, src="runner_queue"
                        )
                        _ledger_payload_obj = _ledger_parse_json(
                            (_ledger_evt.get("data") or {}).get("human_text", "")
                        )
                        if _ledger_payload_obj:
                            _ledger_payload(
                                "runner_chat_message_routed",
                                _ledger_payload_obj,
                                runner_agent=getattr(self.agent.card, "name", ""),
                                target_task=target_task.name,
                                source=source,
                            )
                    except Exception:
                        pass

                # ── Direct delivery fast-path ──
                # When a chat_message carrying a structured response arrives for a
                # task whose browser session has the live-chat tools, deliver the reply
                # directly (open_session + send_message) instead of queuing it for
                # the LLM.  This cuts ~30s of queue wait + LLM round-trip.
                if event_type == "chat_message":
                    try:
                        _dd_ok = self._try_direct_live_chat_delivery(target_task, request)
                        if _dd_ok:
                            logger.info(
                                f"[QUEUE] Direct delivery accepted for task={target_task.name}, "
                                f"skipping queue (msg={_describe_queue_msg(request)})"
                            )
                            return
                        else:
                            # [QUEUE-TRACE] Make it clear the direct-delivery shortcut did NOT
                            # fire so we can distinguish this from a missing chat_message later.
                            logger.info(
                                f"[QUEUE-TRACE] direct-delivery skipped (returned False): "
                                f"task={target_task.name} msg={_describe_queue_msg(request)}"
                            )
                    except Exception as _dd_err:
                        logger.info(
                            f"[QUEUE-TRACE] direct-delivery raised (non-fatal, will queue): "
                            f"{_dd_err} msg={_describe_queue_msg(request)}"
                        )

                try:
                    _tag_queue_event_type(request, event_type)
                    if event_type == "browser_event":
                        _dropped = _coalesce_queued_browser_events(target_task.queue, request)
                        if _dropped:
                            logger.info(
                                f"[QUEUE] Coalesced {_dropped} stale browser_event "
                                f"snapshot(s) for task={target_task.name} "
                                f"label={_browser_event_label(request)!r}"
                            )
                    
                    # Queue deduplication for chat_message and task_request
                    if event_type in ("chat_message", "task_request", "a2a"):
                        _dedup_dropped = _drop_duplicate_queued_messages(target_task.queue, request, event_type)
                        if _dedup_dropped:
                            logger.info(
                                f"[QUEUE] Dropped {_dedup_dropped} duplicate {event_type} "
                                f"for task={target_task.name} (queue depth: {target_task.queue.qsize()})"
                            )
                            # Don't enqueue if we dropped a duplicate
                            return
                    
                    target_task.queue.put_nowait(request)
                    # [QUEUE-TRACE] Dump full queue state right after enqueue so we can
                    # tell whether a subsequently-"lost" chat_message ever actually
                    # landed in the task queue. Include task state so we can correlate
                    # with the dequeue-skip-when-working branch below.
                    try:
                        _ts_state = getattr(getattr(target_task, "status", None), "state", None)
                        _queue_depth = target_task.queue.qsize()
                        logger.info(
                            f"[QUEUE] Message queued for task={target_task.name} "
                            f"enqueued={_describe_queue_msg(request)} task_state={_ts_state!r} "
                            f"queue={_snapshot_queue(target_task.queue, limit=10)}"
                        )
                        _log_live_chat_runner_stage(
                            "runner_queue_enqueued",
                            request,
                            task=target_task,
                            event_type=event_type,
                            queue_depth=_queue_depth,
                        )
                    except Exception:
                        logger.info(f"[QUEUE] Message queued for task={target_task.name}")

                    # Ensure the target task's execution loop is alive.
                    # _resolve_event_routing may return a stale task whose loop has already
                    # terminated (e.g. a completed/failed chat task with a backlog of messages).
                    # Without this check the loop silently ignores the queued message forever.
                    self._ensure_task_execution_alive(target_task, event_type)
                    if _is_live_chat_shutdown_active() and event_type == "chat_message":
                        _shutdown_payload = _live_chat_response_payload_from_queue_msg(request)
                        if _shutdown_payload:
                            _drained = _wait_for_task_live_chat_delivery_idle(
                                target_task,
                                _LIVE_CHAT_SHUTDOWN_FALLBACK_WAIT_S,
                            )
                            if not _drained:
                                _log_live_chat_delivery_aborted_shutdown(
                                    _shutdown_payload,
                                    reason="queued_response_pending_during_shutdown",
                                    target_task=target_task.name,
                                    task_id=getattr(target_task, "id", ""),
                                    queue_depth=getattr(target_task.queue, "qsize", lambda: -1)(),
                                    task_state=str(getattr(getattr(target_task, "status", None), "state", "")),
                                )
                except Exception as e:
                    logger.error(f"[QUEUE] Failed to enqueue: {e}")
            else:
                if event_type in {"chat_message", "human_chat", "task_request", "a2a", "channel_message"}:
                    fallback_task = self._ensure_chatter_task(request=request, event_type=event_type, source=source)
                    if fallback_task and getattr(fallback_task, "queue", None) is not None:
                        try:
                            # Mirror the direct-delivery fast-path applied on
                            # the main routing branch above. Q&A reply payloads
                            # from the responder agents arrive here through the
                            # routing-fallback path (no specific task selector
                            # matched on the front-desk agent), so without this
                            # hook every reply sits in the front-desk reception task's
                            # queue and gets processed by the full browser-use
                            # agent loop (~30s/turn) instead of being typed
                            # directly via CDP (~0.3s/turn). Observed in the
                            # 2026-05-14 18:18 run: 18 reply payloads stranded
                            # in queue while the front-desk reception task is
                            # state=working running a browser-use turn.
                            if event_type == "chat_message":
                                try:
                                    _dd_ok = self._try_direct_live_chat_delivery(fallback_task, request)
                                    if _dd_ok:
                                        logger.info(
                                            f"[QUEUE] Direct delivery accepted on fallback for "
                                            f"task={fallback_task.name}, skipping queue "
                                            f"(msg={_describe_queue_msg(request)})"
                                        )
                                        return
                                    logger.info(
                                        f"[QUEUE-TRACE] direct-delivery skipped on fallback "
                                        f"(returned False): task={fallback_task.name} "
                                        f"msg={_describe_queue_msg(request)}"
                                    )
                                except Exception as _dd_err:
                                    logger.info(
                                        f"[QUEUE-TRACE] direct-delivery raised on fallback "
                                        f"(non-fatal, will queue): {_dd_err} "
                                        f"msg={_describe_queue_msg(request)}"
                                    )
                            _tag_queue_event_type(request, event_type)
                            fallback_task.queue.put_nowait(request)
                            logger.info(f"[QUEUE] Message queued for fallback task={fallback_task.name}")
                            try:
                                _log_live_chat_runner_stage(
                                    "runner_queue_enqueued",
                                    request,
                                    task=fallback_task,
                                    event_type=event_type,
                                    queue_depth=fallback_task.queue.qsize(),
                                    routing_fallback=True,
                                )
                            except Exception:
                                pass
                            self._ensure_task_execution_alive(fallback_task, event_type)
                            return
                        except Exception as e:
                            logger.error(f"[QUEUE] Failed to enqueue to fallback chatter task: {e}")
                    elif fallback_task is None:
                        # No task configured for this agent — notify the user
                        try:
                            event = normalize_event(event_type, request, src=source)
                            chat_id = (
                                (event.get("context") or {}).get("chatId")
                                or (event.get("data") or {}).get("chatId")
                            )
                            agent_name = getattr(getattr(self.agent, "card", None), "name", "Agent") or "Agent"
                            if chat_id:
                                try:
                                    from utils.i18n_helper import detect_language
                                    _lang = detect_language(default_lang="zh-CN", supported_languages=["zh-CN", "en-US"])
                                except Exception:
                                    _lang = "zh-CN"
                                _no_task_msgs = {
                                    "zh-CN": (
                                        f"⚠️ 当前 Agent「{agent_name}」尚未配置可接收消息的 Task。"
                                        f"请在 Agent 设置中添加一个名称包含 \"chat\"、触发方式为 \"message\" 的 Task，并关联对应的 Skill。"
                                    ),
                                    "en-US": (
                                        f"⚠️ Agent \"{agent_name}\" has no Task configured to receive messages. "
                                        f"Please add a Task whose name contains \"chat\", trigger is \"message\", "
                                        f"and associate it with the appropriate Skill in Agent settings."
                                    ),
                                }
                                sender = self._get_message_sender()
                                sender.send_text(chat_id, _no_task_msgs.get(_lang, _no_task_msgs["zh-CN"]))
                        except Exception as e:
                            logger.error(f"[QUEUE] Failed to send no-task notification: {e}")
                if event_type == "browser_event":
                    logger.warning(f"[QUEUE] No target task found for browser_event (sub_type={_sub_type}). Check pend_event browserEventLabel matches monitor label.")
                else:
                    logger.debug(f"[QUEUE] No target task for event: {event_type}")
                
        except Exception as e:
            logger.error(get_traceback(e, "ErrorWaitInLine"))
    
    def _try_direct_live_chat_delivery(self, target_task: "ManagedTask", request: Any) -> bool:
        """
        Attempt to deliver a chat_message response directly via the live-chat tools,
        bypassing the LLM queue.  Returns True if the reply was sent successfully.

        This is the "direct delivery" fast-path: when a responder agent sends
        a structured {response_text, customer_name} payload back to the front
        desk, we call the site's open-session + send-message tools on the cached
        browser session immediately, cutting ~30s of queue + LLM latency.
        """
        import asyncio as _asyncio
        import json as _json

        # 1. Extract response_text and customer_name from the request payload.
        #
        # We try normalize_event first (canonical extractor), then fall back
        # to _queue_msg_text — the latter also walks the a2a-sdk
        # `Part(root=TextPart(text=...))` shape and dict-with-attributes
        # variants, so if upstream message wrapping changes again we still
        # find the JSON instead of silently bailing. The previous code only
        # used normalize_event and the dev merge introduced a shape
        # (Part wrapping TextPart) that normalize_event missed, killing the
        # direct-delivery fast path for every chat_message.
        _human_text = ""
        try:
            from agent.ec_tasks.resume import normalize_event
            _evt = normalize_event("chat_message", request, src="direct_delivery")
            _human_text = (_evt.get("data") or {}).get("human_text", "") or ""
        except Exception:
            pass
        if not _human_text:
            try:
                _human_text = _queue_msg_text(request) or ""
            except Exception:
                _human_text = ""
        if not _human_text:
            logger.info(
                f"[DIRECT-DELIVERY] Skipping: empty human_text after extraction "
                f"task={target_task.name} msg={_describe_queue_msg(request)}"
            )
            return False

        try:
            _parsed = _json.loads(_human_text)
        except (ValueError, TypeError):
            # mt053J-C (2026-05-30): defense-in-depth — try a lenient parse
            # that allows raw control chars (json.loads strict=False) before
            # giving up.  mt053J-C also normalizes at the send_chat tool
            # source, but a stray malformed envelope from any other path
            # (e.g. an older binary, an A2A intermediary) should still
            # recover here.  If lenient parse also fails, fall through to
            # the mt053J-A/B recovery below.
            try:
                _parsed = _json.loads(_human_text, strict=False)
            except (ValueError, TypeError):
                _parsed = None
        if _parsed is None:
            # mt053J-A (2026-05-30): when json.loads fails on a chat_message
            # payload (typically the QA bot's send_chat produced unescaped
            # raw control chars inside response_text — see Part C
            # investigation), the fallback path is queue→HOT-PATH-B, which
            # ALSO can't extract the payload and short-circuits as
            # first_invocation_skip, silently dropping the reply.  Live
            # trace 2026-05-30 19:56:58 肽斯特: parse failed, 7.5-min
            # freeze, customer's question never answered.  Mark
            # drift-recovery-pending so HOT-PATH-B's existing override
            # (front_desk.py:290-333) forces chat_message rule match and
            # retries typed delivery via state.input fallback — same
            # workaround the direct_backpressure_bypass path already uses.
            try:
                import re as _mt053ja_re
                _mt053ja_cust_m = _mt053ja_re.search(
                    r'"customer_(?:name|id)"\s*:\s*"([^"]{1,40})"', _human_text
                )
                _mt053ja_cust = _mt053ja_cust_m.group(1) if _mt053ja_cust_m else ""
                if _mt053ja_cust:
                    _mt053ja_mark = _live_chat_bridge().drift_recovery.mark_drift_recovery_pending
                    _mt053ja_src_msg_m = _mt053ja_re.search(
                        r'"source_customer_msg_id"\s*:\s*"([^"]{1,80})"', _human_text
                    )
                    _mt053ja_resp_m = _mt053ja_re.search(
                        r'"response_text"\s*:\s*"(.*?)"\s*[,}]', _human_text
                    )
                    _mt053ja_mark(
                        _mt053ja_cust,
                        source_msg_id=(_mt053ja_src_msg_m.group(1) if _mt053ja_src_msg_m else ""),
                        response_text=(_mt053ja_resp_m.group(1) if _mt053ja_resp_m else ""),
                    )
                    logger.info(
                        f"[DIRECT-DELIVERY] mt053J-A marked drift-recovery for "
                        f"cust={_mt053ja_cust!r} after JSON parse failure; "
                        f"HOT-PATH-B override will retry typed delivery via "
                        f"state.input fallback (task={target_task.name})"
                    )
                    # mt053J-B (2026-05-30): also clear the dedup ledgers
                    # for this customer.  If HOT-PATH-B's drift-recovery
                    # path ALSO fails to extract a usable payload from the
                    # malformed JSON envelope (e.g. all four payload-source
                    # branches in front_desk.py:138-266 hit the same parse
                    # error), the reply ends up first_invocation_skip-
                    # dropped AND last_dispatched_msg_id stays stamped, so
                    # PreDispatch's msg-id dedup blocks every retry for the
                    # full 30s inflight TTL plus indefinitely after.  By
                    # clearing the ledger preemptively here we let
                    # PreDispatch re-dispatch the customer's still-pending
                    # question — the QA bot regenerates the answer (often
                    # with a different / properly-escaped JSON envelope on
                    # the retry) and direct-delivery succeeds.  Same
                    # recovery shape as mt046A / mt053H2.
                    try:
                        _mt053jb_ds = _live_chat_bridge().dispatch_state
                        _mt053jb_msg_id_cleared = (
                            _mt053jb_ds.last_dispatched_msg_id_by_customer.pop(
                                _mt053ja_cust, None
                            )
                            is not None
                        )
                    except Exception:
                        _mt053jb_msg_id_cleared = False
                    _mt053jb_ident_cleared = 0
                    try:
                        _mt053jb_clear_ident = (
                            _live_chat_bridge().actionable_items
                            .clear_dispatched_identity_keys_for_customer
                        )
                        _mt053jb_ident_cleared = _mt053jb_clear_ident(_mt053ja_cust)
                    except Exception:
                        pass
                    try:
                        from agent.ec_skills.browser_use_extension.event_monitor import (
                            force_reemit_for_customer as _mt053jb_reemit,
                        )
                        _mt053jb_reemit(_mt053ja_cust)
                    except Exception as _mt053jb_reemit_err:
                        logger.debug(
                            f"[DIRECT-DELIVERY] mt053J-B force-reemit failed "
                            f"(non-fatal): {_mt053jb_reemit_err}"
                        )
                    logger.warning(
                        f"[DIRECT-DELIVERY] mt053J-B cleared dedup ledgers "
                        f"for cust={_mt053ja_cust!r} after JSON-parse failure: "
                        f"msg_id_cleared={_mt053jb_msg_id_cleared}, "
                        f"identity_keys_cleared={_mt053jb_ident_cleared} "
                        f"(PreDispatch can re-dispatch the still-pending question)"
                    )
                    # ws155: mt053J-B above cleared msg-id + identity but NOT dispatch_inflight;
                    # the unified primitive clears ALL blockers across all keys (no suppressors).
                    if _mt053ja_cust and (_live_chat_env("ECAN_LIVE_CHAT_UNIFIED_BLOCKER_CLEAR") or "1") != "0":
                        try:
                            _u155 = _mt053jb_ds.clear_dispatch_blockers(
                                _mt053ja_cust, reason="mt053J-B_json_parse_fail"
                            )
                            logger.info(
                                f"[DIRECT-DELIVERY] ws155 unified blocker-clear (mt053J-B) "
                                f"cust={_mt053ja_cust!r}: {_u155}"
                            )
                        except Exception as _u155_err:
                            logger.debug(
                                f"[DIRECT-DELIVERY] ws155 unified-clear failed "
                                f"(non-fatal): {_u155_err}"
                            )
                else:
                    logger.warning(
                        f"[DIRECT-DELIVERY] mt053J-A could not regex-extract "
                        f"customer_id from malformed JSON; reply will be dropped "
                        f"by HOT-PATH-B first_invocation_skip "
                        f"(task={target_task.name})"
                    )
            except Exception as _mt053ja_err:
                logger.debug(
                    f"[DIRECT-DELIVERY] mt053J-A drift-recovery mark failed "
                    f"(non-fatal): {_mt053ja_err}"
                )
            logger.info(
                f"[DIRECT-DELIVERY] Skipping: human_text is not JSON "
                f"task={target_task.name} preview={_human_text[:80]!r}"
            )
            return False
        if not isinstance(_parsed, dict):
            logger.info(
                f"[DIRECT-DELIVERY] Skipping: parsed payload is not a dict "
                f"task={target_task.name} type={type(_parsed).__name__}"
            )
            return False

        _response_text = str(_parsed.get("response_text", "")).strip()
        _customer_name = str(
            _parsed.get("customer_name") or _parsed.get("customer_id") or ""
        ).strip()
        if not _response_text or not _customer_name:
            logger.info(
                "[DIRECT-DELIVERY] Skipping: chat_message is not a live-chat "
                f"response payload task={target_task.name}"
            )
            return False

        if _is_live_chat_shutdown_drain_finalized():
            _log_live_chat_delivery_aborted_shutdown(
                _parsed,
                reason="direct_delivery_after_shutdown_drain",
                target_task=target_task.name,
                task_id=getattr(target_task, "id", ""),
            )
            logger.warning(
                f"[DIRECT-DELIVERY] Rejecting direct delivery after shutdown "
                f"drain customer={_customer_name!r} task={target_task.name}"
            )
            return True

        try:
            _live_chat_ledger_payload = _live_chat_bridge().trace_ledger.log_payload
        except Exception:
            _live_chat_ledger_payload = None

        _source_msg_id = str(_parsed.get("source_customer_msg_id") or "").strip()
        try:
            record_pending_delivery = (
                _live_chat_bridge().delivery_durability.record_pending_delivery
            )
            record_pending_delivery(
                _parsed,
                source="direct_delivery",
                target_task=getattr(target_task, "name", ""),
                task_id=getattr(target_task, "id", ""),
            )
        except Exception:
            pass
        _direct_job_id = f"dd_{int(time.time() * 1000)}_{abs(hash((_customer_name, _source_msg_id, _response_text))) % 100000}"
        _scheduled_retry_attr = "_ecan_direct_cdp_circuit_retry_keys"

        def _ledger(_stage: str, **_fields: Any) -> None:
            if _live_chat_ledger_payload is None:
                return
            try:
                _live_chat_ledger_payload(
                    _stage,
                    _parsed,
                    direct_job_id=_direct_job_id,
                    target_task=getattr(target_task, "name", ""),
                    response_len=len(_response_text),
                    **_fields,
                )
            except Exception:
                pass

        def _wait_shutdown_fallback_terminal(_reason: str) -> None:
            if not _is_live_chat_shutdown_active():
                return
            _drained = _wait_for_task_live_chat_delivery_idle(
                target_task,
                _LIVE_CHAT_SHUTDOWN_FALLBACK_WAIT_S,
            )
            if _drained:
                return
            logger.warning(
                f"[LIVE-CHAT-SHUTDOWN] fallback still pending after "
                f"{_LIVE_CHAT_SHUTDOWN_FALLBACK_WAIT_S:.1f}s "
                f"customer={_customer_name!r} reason={_reason}"
            )
            try:
                _queue_depth = target_task.queue.qsize()
            except Exception:
                _queue_depth = -1
            _ledger(
                "delivery_aborted_shutdown",
                reason=_reason,
                queue_depth=_queue_depth,
                task_state=str(getattr(getattr(target_task, "status", None), "state", "")),
            )

        def _find_cached_live_chat_browser_session() -> tuple[Any, str, str]:
            _cache_sources = []
            try:
                from agent.ec_skills.browser_node import build_helpers as _browser_helpers
                _cache_sources.append(("build_helpers", getattr(_browser_helpers, "cached_browser_sessions", {})))
            except Exception:
                pass
            try:
                from agent.ec_skills import build_node as _build_node
                _cache_sources.append(("build_node", getattr(_build_node, "_cached_browser_sessions", {})))
            except Exception:
                pass
            for _cache_name, _cache in _cache_sources:
                if not isinstance(_cache, dict):
                    continue
                for _key, _sess in list(_cache.items()):
                    if _sess is not None:
                        return _sess, _cache_name, str(_key)
            return None, "", ""

        def _schedule_frontdesk_retry_after_health(
            _stage: str,
            _reason: str,
            _cooldown_remaining: float,
        ) -> bool:
            _delay = max(
                0.0,
                float(_cooldown_remaining) + _DIRECT_LIVE_CHAT_CDP_COOLDOWN_RETRY_BUFFER_S,
            )
            _retry_key = (_customer_name, _source_msg_id, _response_text, _stage)
            _scheduled = getattr(target_task, _scheduled_retry_attr, None)
            if not isinstance(_scheduled, set):
                _scheduled = set()
                try:
                    setattr(target_task, _scheduled_retry_attr, _scheduled)
                except Exception:
                    pass
            if _retry_key in _scheduled:
                _ledger(
                    f"{_stage}_already_scheduled",
                    reason=_reason,
                    cooldown_remaining_s=round(_cooldown_remaining, 3),
                    delay_s=round(_delay, 3),
                )
                return True
            _scheduled.add(_retry_key)
            logger.warning(
                f"[DIRECT-DELIVERY] Delaying front-desk fallback for "
                f"{_delay:.1f}s because live-chat CDP health cooldown is active "
                f"customer={_customer_name!r} reason={_reason}"
            )
            _ledger(
                _stage,
                reason=_reason,
                cooldown_remaining_s=round(_cooldown_remaining, 3),
                delay_s=round(_delay, 3),
            )

            def _queue_later() -> None:
                try:
                    _scheduled.discard(_retry_key)
                except Exception:
                    pass
                try:
                    _tag_queue_event_type(request, "chat_message")
                    target_task.queue.put_nowait(request)
                    logger.warning(
                        f"[DIRECT-DELIVERY] Delayed front-desk fallback queued "
                        f"customer={_customer_name!r} reason={_reason}"
                    )
                    _ledger(f"{_stage}_queued", reason=_reason)
                    self._ensure_task_execution_alive(target_task, "chat_message")
                    _wait_shutdown_fallback_terminal(
                        f"delayed_health_fallback_pending:{_reason}"
                    )
                except Exception as _fallback_err:
                    logger.error(
                        f"[DIRECT-DELIVERY] Delayed health fallback enqueue "
                        f"failed customer={_customer_name!r}: {_fallback_err}"
                    )
                    _ledger(
                        f"{_stage}_enqueue_failed",
                        reason=_reason,
                        error=str(_fallback_err),
                    )

            timer = threading.Timer(_delay, _queue_later)
            timer.daemon = True
            timer.start()
            return True

        _health_remaining = _live_chat_cdp_health_cooldown_remaining()
        if _health_remaining > 0.0:
            return _schedule_frontdesk_retry_after_health(
                "direct_cdp_health_retry_scheduled",
                "cdp_health_cooldown",
                _health_remaining,
            )

        _circuit_remaining = _direct_live_chat_cdp_timeout_circuit_remaining()
        if _circuit_remaining > 0.0:
            if _DIRECT_LIVE_CHAT_CDP_TIMEOUT_CIRCUIT_QUEUE_BYPASS:
                try:
                    _tag_queue_event_type(request, "chat_message")
                    target_task.queue.put_nowait(request)
                    logger.warning(
                        f"[DIRECT-DELIVERY] CDP-timeout circuit is open for "
                        f"{_circuit_remaining:.1f}s; bypassed direct worker "
                        f"and queued front-desk delivery customer={_customer_name!r}"
                    )
                    _ledger(
                        "direct_cdp_timeout_circuit_queue_bypass",
                        cooldown_remaining_s=round(_circuit_remaining, 3),
                    )
                    self._ensure_task_execution_alive(target_task, "chat_message")
                    _wait_shutdown_fallback_terminal(
                        "cdp_timeout_circuit_queue_bypass_pending_during_shutdown"
                    )
                    return True
                except Exception as _queue_bypass_err:
                    logger.error(
                        f"[DIRECT-DELIVERY] CDP-timeout circuit queue bypass "
                        f"failed customer={_customer_name!r}: {_queue_bypass_err}"
                    )
                    _ledger(
                        "direct_cdp_timeout_circuit_queue_bypass_failed",
                        cooldown_remaining_s=round(_circuit_remaining, 3),
                        error=str(_queue_bypass_err),
                    )
            _delay = _direct_live_chat_cdp_delay_with_cap(
                _circuit_remaining + _DIRECT_LIVE_CHAT_CDP_COOLDOWN_RETRY_BUFFER_S
            )
            _retry_key = (_customer_name, _source_msg_id, _response_text)
            _scheduled = getattr(target_task, _scheduled_retry_attr, None)
            if not isinstance(_scheduled, set):
                _scheduled = set()
                try:
                    setattr(target_task, _scheduled_retry_attr, _scheduled)
                except Exception:
                    pass
            logger.warning(
                f"[DIRECT-DELIVERY] Delaying direct delivery because "
                f"CDP-timeout circuit is open for {_circuit_remaining:.1f}s "
                f"customer={_customer_name!r} task={target_task.name}"
            )
            _ledger(
                "direct_cdp_timeout_circuit_retry_scheduled",
                cooldown_remaining_s=round(_circuit_remaining, 3),
                delay_s=round(_delay, 3),
            )
            if _retry_key not in _scheduled:
                _scheduled.add(_retry_key)

                def _queue_retry_fallback(_reason: str) -> None:
                    _fallback_session, _fallback_cache_name, _fallback_cache_key = (
                        _find_cached_live_chat_browser_session()
                    )
                    _allow_missing_session_fallback = _fallback_session is None
                    if (
                        not _DIRECT_LIVE_CHAT_CDP_TIMEOUT_CIRCUIT_QUEUE_BYPASS
                        and not _allow_missing_session_fallback
                    ):
                        logger.warning(
                            f"[DIRECT-DELIVERY] Delayed circuit retry was not "
                            f"accepted; suppressing front-desk fallback while "
                            f"CDP circuit queue bypass is disabled "
                            f"customer={_customer_name!r} reason={_reason}"
                        )
                        _ledger(
                            "direct_cdp_timeout_circuit_retry_fallback_suppressed",
                            reason=_reason,
                        )
                        return
                    try:
                        _tag_queue_event_type(request, "chat_message")
                        target_task.queue.put_nowait(request)
                        logger.warning(
                            f"[DIRECT-DELIVERY] Delayed circuit retry fell back "
                            f"to task queue customer={_customer_name!r} "
                            f"reason={_reason} "
                            f"cache_source={_fallback_cache_name!r} "
                            f"cache_key={_fallback_cache_key!r}"
                        )
                        _ledger(
                            "direct_cdp_timeout_circuit_retry_fallback_queued",
                            reason=_reason,
                            missing_browser_session=_allow_missing_session_fallback,
                        )
                        self._ensure_task_execution_alive(target_task, "chat_message")
                        _wait_shutdown_fallback_terminal(
                            f"delayed_circuit_retry_fallback_pending:{_reason}"
                        )
                    except Exception as _fallback_err:
                        logger.error(
                            f"[DIRECT-DELIVERY] Delayed circuit retry fallback "
                            f"enqueue failed customer={_customer_name!r}: "
                            f"{_fallback_err}"
                        )

                def _retry_after_circuit() -> None:
                    try:
                        _scheduled.discard(_retry_key)
                    except Exception:
                        pass
                    try:
                        if not self._try_direct_live_chat_delivery(target_task, request):
                            _queue_retry_fallback("delayed_direct_retry_not_accepted")
                    except Exception as _retry_err:
                        logger.error(
                            f"[DIRECT-DELIVERY] Delayed circuit retry failed "
                            f"customer={_customer_name!r}: {_retry_err}"
                        )
                        _queue_retry_fallback("delayed_direct_retry_exception")

                timer = threading.Timer(_delay, _retry_after_circuit)
                timer.daemon = True
                timer.start()
            return True

        _ledger("direct_reply_received")

        # Share HOT-PATH-B's replay cache. This avoids duplicate sends if
        # the same Q&A answer re-enters through the normal front-desk queue.
        _live_chat_ds = None
        try:
            _live_chat_ds = _live_chat_bridge().dispatch_state
            # ws003e: long-window guard FIRST — a reply already DELIVERED for this
            # (customer, text) must not be re-sent by a stale retry that re-entered
            # after the short claim cache aged out (live: 19-min-late re-send).
            # ws164: pass the source msg_id so a NEW turn whose answer text
            # collides with an earlier delivered reply is NOT dup-suppressed.
            _delivered_age = _live_chat_ds.was_reply_delivered(
                _customer_name, _response_text, _source_msg_id,
            )
            if _delivered_age:
                logger.info(
                    f"[DIRECT-DELIVERY] Dup-send skip (already delivered) "
                    f"customer={_customer_name!r} age={_delivered_age:.1f}s task={target_task.name}"
                )
                _ledger("direct_delivered_dup_skip", delivered_age_s=_delivered_age)
                return True
            _dedup_age = _live_chat_ds.claim_send_for_turn(
                _customer_name,
                _response_text,
                _source_msg_id,
            )
            if _dedup_age:
                logger.info(
                    f"[DIRECT-DELIVERY] Dedup skip for customer={_customer_name!r} "
                    f"age={_dedup_age:.2f}s task={target_task.name}"
                )
                _ledger("direct_dedup_skip", dedup_age_s=_dedup_age)
                return True
            try:
                _reply_norm = _live_chat_ds.remember_agent_reply(
                    _customer_name,
                    _response_text,
                )
                if _reply_norm:
                    logger.info(
                        f"[DIRECT-DELIVERY] Pre-recorded last_agent_reply "
                        f"customer={_customer_name!r} len={len(_reply_norm)} "
                        "before queued live-chat send"
                    )
                    _ledger(
                        "direct_agent_reply_prerecorded",
                        response_len=len(_reply_norm),
                    )
                # 2026-05-23 mt029: also pre-register in the mt028
                # no-TTL typed-text set so mt017 recognises the typed
                # bubble as ours even if the send-tool await
                # is cancelled mid-flight (e.g. supersede or
                # stale_reply rejection AFTER JS already typed the
                # bubble in DOM).  The text-based ledger above has a
                # 90 s TTL and would age out; mt028 set is no-TTL +
                # capped + LRU.
                try:
                    _live_chat_bridge().human_intervention.record_typed_text(
                        _customer_name, _response_text
                    )
                except Exception:
                    pass
            except Exception as _pre_record_err:
                logger.debug(
                    f"[DIRECT-DELIVERY] pre-record reply failed "
                    f"customer={_customer_name!r}: {_pre_record_err}"
                )
        except Exception:
            _live_chat_ds = None

        # 2. Find a cached browser session with the live-chat tools. The live cache
        # moved to browser_node.build_helpers during the browser-node split;
        # keep the older build_node lookup as a fallback for compatibility.
        _session, _cache_name, _cache_key = _find_cached_live_chat_browser_session()
        if _session is None and _DIRECT_LIVE_CHAT_BROWSER_SESSION_WAIT_S > 0.0:
            _wait_started = time.monotonic()
            _deadline = _wait_started + _DIRECT_LIVE_CHAT_BROWSER_SESSION_WAIT_S
            _ledger(
                "direct_browser_session_wait_start",
                wait_s=round(_DIRECT_LIVE_CHAT_BROWSER_SESSION_WAIT_S, 3),
            )
            while time.monotonic() < _deadline:
                time.sleep(0.1)
                _session, _cache_name, _cache_key = _find_cached_live_chat_browser_session()
                if _session is not None:
                    _waited = time.monotonic() - _wait_started
                    logger.info(
                        f"[DIRECT-DELIVERY] Recovered cached browser session "
                        f"after {_waited:.2f}s source={_cache_name} "
                        f"key={_cache_key!r} customer={_customer_name!r}"
                    )
                    _ledger(
                        "direct_browser_session_wait_recovered",
                        wait_s=round(_waited, 3),
                        cache_source=_cache_name,
                        cache_key=_cache_key,
                    )
                    break
        if _session is not None:
            logger.info(
                f"[DIRECT-DELIVERY] Using cached browser session "
                f"source={_cache_name} key={_cache_key!r} customer={_customer_name!r}"
            )
        if _session is None:
            if _live_chat_ds is not None:
                _live_chat_ds.unclaim_send_for_turn(_customer_name, _response_text, _source_msg_id)
            logger.info(
                f"[DIRECT-DELIVERY] Skipping: no cached browser session "
                f"customer={_customer_name!r} task={target_task.name}"
            )
            _ledger("direct_no_browser_session")
            return False

        # 3. Look up the site's open-session + send-message tools (names
        #    provided by the active bundle's runner bridge)
        try:
            from agent.ec_skills.browser_use_extension.extension_tools_service import (
                custom_controller as _ctrl,
            )
            _actions = _ctrl.registry.registry.actions
        except Exception:
            if _live_chat_ds is not None:
                _live_chat_ds.unclaim_send_for_turn(_customer_name, _response_text, _source_msg_id)
            _ledger("direct_tools_unavailable", reason="controller_registry_error")
            return False

        try:
            _open_tool_name = str(_live_chat_bridge().open_session_tool_name)
            _send_tool_name = str(_live_chat_bridge().send_message_tool_name)
        except Exception:
            _open_tool_name = _send_tool_name = ""
        _send_fail_reason = f"tool_failed:{_send_tool_name or 'send_message'}"
        _open_fn = _actions.get(_open_tool_name) if _open_tool_name else None
        _send_fn = _actions.get(_send_tool_name) if _send_tool_name else None
        if not _open_fn or not _send_fn:
            if _live_chat_ds is not None:
                _live_chat_ds.unclaim_send_for_turn(_customer_name, _response_text, _source_msg_id)
            logger.info(
                f"[DIRECT-DELIVERY] Skipping: live-chat tools unavailable "
                f"open={bool(_open_fn)} send={bool(_send_fn)}"
            )
            _ledger("direct_tools_unavailable", has_open=bool(_open_fn), has_send=bool(_send_fn))
            return False

        # 4. Send directly at queue ingress. Avoid the HOT-PATH-B
        # open-session + separate active-customer reverify chain here: under
        # flood those extra CDP round trips are exactly what jammed the
        # direct-delivery queue. The site's send tool performs the customer
        # open/match and source-turn guard inside one renderer eval.
        #
        # ws024: track whether the typing eval was actually dispatched, so the
        # async-timeout handler can tell "stuck BEFORE typing" (tab-resolve /
        # typing-lock wait → nothing typed → safe to requeue) from "typing IN
        # FLIGHT" (bubble almost certainly landed → requeuing re-types the SAME
        # reply and the customer sees it twice — live trace 童趣科普 10:52:26 +
        # 10:52:58 dup of "退换货运费规则我先帮您确认下…").
        _eval_dispatch_state = {"dispatched": False}

        async def _do_guarded_direct_delivery():
            # The live-chat bundle is required on this path — a missing
            # bridge raises here exactly like the old failed import did.
            _dd_bridge = _live_chat_bridge()
            _hot_path_v2 = _dd_bridge.hot_path_v2
            _typing_lock = _dd_bridge.typing_lock
            _resolve_live_chat_tab_target_id = _dd_bridge.resolve_tab_target_id

            _ledger("direct_guarded_send_start")
            _eval_dispatch_state["dispatched"] = False  # ws024: reset per attempt
            # 2026-05-25 mt044D: outer wait_for around the resolve was 2.0s
            # — too tight when the multi-candidate probe inside the resolve
            # had to acquire the session-wide CDP lock once per candidate.
            # mt044A/B/C should make this rare, but the tunable here keeps
            # the safety net configurable.  Defaults to 8.0s; raise the
            # bundle's probe timeout alongside it.
            try:
                _mt044d_resolve_timeout = _dd_bridge.tab_resolve_timeout_s()
            except Exception:
                _mt044d_resolve_timeout = 8.0
            try:
                # Phase 1 multi-tab plumbing: pass customer_key so Phase 3
                # auto-routes direct-delivery to the typing tab assigned
                # to this customer (when one exists).  Until Phase 2/3 the
                # pool is empty so this still resolves to the monitor tab.
                _live_chat_target_id = await _asyncio.wait_for(
                    _resolve_live_chat_tab_target_id(_session, customer_key=_customer_name),
                    timeout=_mt044d_resolve_timeout,
                )
            except _asyncio.TimeoutError:
                logger.warning(
                    f"[DIRECT-DELIVERY] live-chat tab target resolve timed out "
                    f"customer={_customer_name!r}"
                )
                _ledger("direct_tab_focus_failed", reason="tab_focus_timeout")
                return _hot_path_v2.HotPathOutcomeV2(
                    ok=False,
                    reason="tab_focus_timeout",
                )
            except Exception as _focus_err:
                logger.warning(
                    f"[DIRECT-DELIVERY] live-chat tab target resolve failed "
                    f"customer={_customer_name!r}: {_focus_err}"
                )
                _ledger("direct_tab_focus_failed", reason="tab_focus_failed", error=str(_focus_err))
                return _hot_path_v2.HotPathOutcomeV2(
                    ok=False,
                    reason="tab_focus_failed",
                )
            if not _live_chat_target_id:
                logger.warning(
                    f"[DIRECT-DELIVERY] live-chat tab target not found "
                    f"customer={_customer_name!r}"
                )
                _ledger("direct_tab_focus_failed", reason="tab_focus_false")
                return _hot_path_v2.HotPathOutcomeV2(
                    ok=False,
                    reason="tab_focus_failed",
                )
            _ledger("direct_tab_target_resolved", target_id=str(_live_chat_target_id))

            # Phase 3 multi-tab: try to allocate a typing tab from the
            # pool for this customer.  If a tab is assigned, override the
            # target_id so the send tool types into that tab (in
            # parallel with other customers on other tabs).  If the pool
            # is empty / exhausted (Phase 1/2 default), we fall back to
            # the monitor tab — today's serialized behaviour.
            _pool_tab_assigned = None
            try:
                _direct_tab_pool = _live_chat_bridge().tab_pool
                _pool_tab_assigned = _direct_tab_pool.get_pool().allocate_for_typing(
                    _customer_name
                )
            except Exception as _alloc_err:
                logger.debug(
                    f"[DIRECT-DELIVERY] pool allocate skipped (non-fatal): {_alloc_err}"
                )
            if _pool_tab_assigned is not None:
                _live_chat_target_id = _pool_tab_assigned.target_id
                _ledger(
                    "direct_pool_tab_allocated",
                    target_id=str(_live_chat_target_id),
                    sticky=str(_pool_tab_assigned.focused_customer or ""),
                )
                logger.info(
                    f"[DIRECT-DELIVERY] pool allocated typing tab "
                    f"target=...{_live_chat_target_id[-6:]} for cust={_customer_name!r}"
                )

            _source_text = str(
                _parsed.get("source_latest_message")
                or _parsed.get("latest_message")
                or _parsed.get("latest_message_text")
                or ""
            ).strip()

            _outcome = _hot_path_v2.HotPathOutcomeV2()
            # Phase 3.5 (2026-05-21): when a pool typing-tab was allocated,
            # the pool's ``in_use`` flag provides per-tab exclusion — no
            # other job can pick this tab until we release it.  Skip the
            # GLOBAL ``_typing_lock`` to avoid the cross-customer
            # serialization that blocked PreDispatch's sidebar scrape
            # on the monitor tab in single-tab mode.
            #
            # The bypass-fallback HOT-PATH-B path still uses the global
            # lock (it types on the monitor tab and needs cross-customer
            # exclusion), so the global lock stays around for that path.
            # ws026: is this send WS-eligible (will go off-DOM via the socket)?
            # `ws_enabled("send")` mirrors the send tool's WS gate and
            # `can_send` is True only when this conversation already has a send
            # template — exactly when the WS path will be taken.
            _direct_ws_eligible = False
            if (_live_chat_env("ECAN_LIVE_CHAT_WS_SKIP_TYPING_LOCK") or "1") != "0":
                try:
                    _ws_sess_chk = _live_chat_bridge().ws_session
                    _direct_ws_eligible = bool(
                        _ws_sess_chk.ws_enabled("send")
                        and _ws_sess_chk.can_send(_customer_name)
                    )
                except Exception:
                    _direct_ws_eligible = False
            if _pool_tab_assigned is not None:
                _outcome.typing_acquired = False  # pool's in_use is the lock
                _ledger(
                    "direct_typing_lock_skipped_pool_active",
                    pool_target=_pool_tab_assigned.target_id,
                )
            elif _direct_ws_eligible:
                # ws026: the send will go off-DOM (WS socket inject) — it never
                # types into the shared DOM input, so it needs NO cross-customer
                # typing-lock serialization. Holding the PROCESS-GLOBAL typing
                # lock here is what forced every fast WS reply to WAIT up to 12s
                # behind ANOTHER customer's slow (13-16s) DOM bootstrap send —
                # the 1-to-5 "卡死" freeze. The rare WS→DOM fallback INSIDE
                # the site's send tool acquires the same typing lock itself (and
                # releases it in its own finally), so DOM correctness is intact.
                # Kill-switch: ECAN_LIVE_CHAT_WS_SKIP_TYPING_LOCK=0.
                _outcome.typing_acquired = False
                _ledger(
                    "direct_typing_lock_skipped_ws_eligible",
                    customer=_customer_name,
                )
            else:
                _outcome.typing_acquired = await _hot_path_v2._acquire_typing_lock(
                    _typing_lock,
                    _customer_name,
                    "direct_live_chat_delivery",
                )
                if _customer_name and not _outcome.typing_acquired:
                    _outcome.ok = False
                    _outcome.reason = "typing_lock_busy"
                    _ledger(
                        "direct_typing_lock_failed",
                        holder=str(_typing_lock.holder() or ""),
                    )
                    return _outcome
                _ledger("direct_typing_lock_acquired")

            try:
                _outcome.actions_attempted = 1
                # mt017 human-intervention skip: if a human jumped in and
                # typed a reply for this customer (detected by the thread
                # scrape), drop this Q&A bot reply on the floor.  The
                # customer has already been answered — typing now would
                # mean a duplicate.
                #
                # 2026-05-24 mt036A: scope the check to the SPECIFIC
                # question this bot reply is targeting (_source_msg_id).
                # The blanket per-customer check (is_handled_recent)
                # dropped legitimate bot replies for unrelated newer
                # questions for the full 120 s TTL after any mark fired.
                # Live trace 2026-05-24 11:34:41 packet — bot reply to
                # 能不能包邮 (source_msg_id 9034feca) was dropped
                # because a different agent bubble at 11:34:21 had
                # mark_handled.  Post-mt036A, only the bot reply
                # targeting the SAME question the human answered gets
                # dropped; replies to other questions proceed.
                try:
                    _hi_dd = _live_chat_bridge().human_intervention
                    _hi_target_qid = str(_source_msg_id or "").strip()
                    if _hi_target_qid and _hi_dd.is_question_handled(
                        _customer_name, _hi_target_qid,
                    ):
                        # 2026-05-26 mt048B: don't drop unconditionally —
                        # let the LLM judge decide whether the human ACTUALLY
                        # answered the question or just said something
                        # off-topic.  Pre-mt048B every human bubble suppressed
                        # the bot wholesale, silently losing well-formed
                        # replies when the human only said "let me check" /
                        # "在的" / a clarification request.  Judge returns
                        # answered=False (with the bot reply allowed through)
                        # on any failure / timeout / disabled — favours
                        # visibility over silent loss.
                        _mt048b_question_text = str(
                            _parsed.get("source_latest_message")
                            or _parsed.get("latest_message")
                            or ""
                        ).strip()
                        _mt048b_human_text = _hi_dd.get_handled_question_text(
                            _customer_name, _hi_target_qid,
                        )
                        _mt048b_drop = True  # pre-mt048B default
                        _mt048b_verdict = None
                        try:
                            _mt048b_judge_mod = _live_chat_bridge().relevance_judge
                            if (
                                _mt048b_judge_mod.is_enabled()
                                and _mt048b_question_text
                                and _mt048b_human_text
                            ):
                                # mt054A (2026-05-31): use judge_async so the
                                # LLM HTTP I/O doesn't block the event loop.
                                # Sync judge() submitted to a ThreadPoolExecutor
                                # and called _fut.result(timeout=) which blocks
                                # the calling thread; in async context that's
                                # the event loop.  Customer 1-to-7 trace
                                # 2026-05-31 12:02→12:09: two heartbeat gaps
                                # (76 s + 194 s) proved event loop freezes
                                # consistent with this blocker.  judge_async
                                # uses await llm.ainvoke wrapped in
                                # asyncio.wait_for; same verdict shape and
                                # timeout semantics, no event-loop block.
                                _mt048b_verdict = await _mt048b_judge_mod.judge_async(
                                    _mt048b_question_text, _mt048b_human_text,
                                )
                                _mt048b_threshold = _mt048b_judge_mod.get_min_confidence()
                                # 2026-05-27 mt050D — when the judge
                                # itself crashed (LLM init failure,
                                # invoke timeout, malformed JSON), the
                                # verdict carries a non-empty ``error``
                                # field.  The function returns
                                # ``answered=False`` as a safe default
                                # to avoid raising, but that LOOKS
                                # identical to "judge ran and said no"
                                # in the drop calc.  Live trace
                                # 2026-05-27 12:26:11-16: mt050C's
                                # import bug made every judge call
                                # error → ``answered=False`` →
                                # ``drop=False`` → bot reply allowed
                                # through despite the human typing
                                # exactly the right answer 28 s prior.
                                # The fix here: when ``error`` is set,
                                # treat as judge-failed and fall back
                                # to the pre-mt048B unconditional drop
                                # (mt017's original behaviour).
                                _mt048b_failed = bool(
                                    getattr(_mt048b_verdict, "error", "") or ""
                                )
                                if _mt048b_failed:
                                    # ws005: judge ERRORED (init/invoke/parse) — we can't
                                    # tell if the human actually answered. Default to
                                    # PROCEED (show our reply): a silently-unanswered
                                    # customer question is worse than a redundant
                                    # double-answer. Revert with
                                    # ECAN_LIVE_CHAT_HUMAN_JUDGE_FAIL_DROP=1.
                                    _mt048b_drop = (
                                        (_live_chat_env("ECAN_LIVE_CHAT_HUMAN_JUDGE_FAIL_DROP") or "") == "1"
                                    )
                                else:
                                    _mt048b_drop = bool(
                                        _mt048b_verdict.answered
                                        and _mt048b_verdict.confidence >= _mt048b_threshold
                                    )
                                logger.info(
                                    f"[DIRECT-DELIVERY] mt048B judge result "
                                    f"customer={_customer_name!r} drop={_mt048b_drop} "
                                    f"answered={_mt048b_verdict.answered} "
                                    f"confidence={_mt048b_verdict.confidence:.2f} "
                                    f"threshold={_mt048b_threshold:.2f} "
                                    f"reason={_mt048b_verdict.reason!r} "
                                    f"judge_failed={_mt048b_failed}"
                                )
                        except Exception as _mt048b_err:
                            # ws005: favor showing our reply on judge failure (a missed
                            # answer is worse than a double-answer). Revert with
                            # ECAN_LIVE_CHAT_HUMAN_JUDGE_FAIL_DROP=1.
                            _mt048b_drop = (
                                (_live_chat_env("ECAN_LIVE_CHAT_HUMAN_JUDGE_FAIL_DROP") or "") == "1"
                            )
                            logger.warning(
                                f"[DIRECT-DELIVERY] mt048B judge raised "
                                f"(non-fatal, drop={_mt048b_drop}): {_mt048b_err}"
                            )

                        if _mt048b_drop:
                            logger.info(
                                f"[DIRECT-DELIVERY] human-intervention skip "
                                f"customer={_customer_name!r} target_question="
                                f"...{_hi_target_qid[-8:]} — human reply "
                                f"deemed to answer this question; dropping "
                                f"Q&A reply"
                            )
                            _ledger(
                                "direct_send_skipped_human_handled",
                                executor=f"{_send_tool_name}_self_open",
                                mt048b_answered=(
                                    bool(_mt048b_verdict.answered)
                                    if _mt048b_verdict else None
                                ),
                                mt048b_confidence=(
                                    round(_mt048b_verdict.confidence, 3)
                                    if _mt048b_verdict else None
                                ),
                                mt048b_reason=(
                                    _mt048b_verdict.reason
                                    if _mt048b_verdict else ""
                                ),
                            )
                            # ws005 (Situation 3): roll the human's answer into context
                            # so the NEXT Q&A turn for this customer sees it (PreDispatch
                            # surfaces it as `recent_human_reply`).
                            try:
                                if _mt048b_human_text:
                                    _hi_dd.record_human_reply(_customer_name, _mt048b_human_text)
                            except Exception:
                                pass
                            _outcome.ok = True
                            _outcome.reason = "human_intervention_skip"
                            return _outcome
                        # judge said human did NOT answer — log and fall
                        # through to the normal send path.
                        logger.info(
                            f"[DIRECT-DELIVERY] mt048B allowing bot reply "
                            f"through despite human-handled mark "
                            f"customer={_customer_name!r} "
                            f"target_question=...{_hi_target_qid[-8:]} "
                            f"(human reply did NOT answer the question)"
                        )
                        _ledger(
                            "direct_human_judge_allowed_send",
                            mt048b_answered=(
                                bool(_mt048b_verdict.answered)
                                if _mt048b_verdict else None
                            ),
                            mt048b_confidence=(
                                round(_mt048b_verdict.confidence, 3)
                                if _mt048b_verdict else None
                            ),
                            mt048b_reason=(
                                _mt048b_verdict.reason
                                if _mt048b_verdict else ""
                            ),
                        )
                except Exception as _hi_dd_err:
                    logger.debug(
                        f"[DIRECT-DELIVERY] human-intervention check "
                        f"failed (non-fatal): {_hi_dd_err}"
                    )
                _send_args = {
                    "text": _response_text,
                    "customer_name": _customer_name,
                }
                if _source_msg_id:
                    _send_args["source_customer_msg_id"] = _source_msg_id
                if _source_text:
                    _send_args["source_latest_message"] = _source_text
                _ledger(
                    "direct_send_start",
                    source_latest_preview=_source_text,
                    executor=f"{_send_tool_name}_self_open",
                )
                # 2026-05-21: STAMP "real reply in progress" RIGHT NOW —
                # before the JS eval starts.  Without this, the placeholder
                # timer's claim_expired (running on the sweeper thread)
                # could claim a placeholder entry for THIS customer at the
                # exact moment we're about to type the real reply.  Both
                # would type into the chat within milliseconds of each
                # other (客户14 23:35:39.363 placeholder typed 6ms BEFORE
                # real reply at .369).  Marking the suppression here gives
                # the sweeper a chance to skip the claim, OR — if it
                # already claimed — the second is_real_reply_recent check
                # at the placeholder send aborts before typing.
                try:
                    _ph_timer_pre = _live_chat_bridge().placeholder_timer
                    _ph_timer_pre.mark_real_reply_delivered(_customer_name, _source_msg_id)
                    # Also cancel any in-flight placeholder task for this turn
                    _inflight = _ph_timer_pre._INFLIGHT_PLACEHOLDER_TASKS.get(
                        (_customer_name, _source_msg_id or "")
                    )
                    if _inflight is not None:
                        try:
                            _inflight.cancel()
                            logger.info(
                                f"[placeholder_timer] pre-emptively cancelled "
                                f"in-flight placeholder for cust={_customer_name!r} "
                                f"src_msg={_source_msg_id!r} — real reply about to type"
                            )
                        except Exception:
                            pass
                except Exception as _ph_pre_err:
                    logger.debug(
                        f"[placeholder_timer] pre-real-reply suppress failed "
                        f"(non-fatal): {_ph_pre_err}"
                    )
                _send_params = _send_fn.param_model(**_send_args)

                import inspect as _inspect

                # 2026-05-19: drift-retry loop for direct delivery.
                #
                # HOT-PATH-B (hot_path.py:619+) already wraps
                # the send tool in a drift-retry loop with
                # _is_retryable_send_error / HOT_PATH_DRIFT_RETRY_MAX —
                # but direct delivery here was single-shot.  Under
                # sidebar-reshuffle load, "Active customer drifted
                # between typing and click" fires on the click step
                # because the site reordered the active customer in the
                # ~600 ms gap between the typing input and the send-
                # click CDP eval.  Without retry, the reply is
                # permanently lost (observed for 客户13 at 14:04:39 in
                # the 2026-05-19 local-emulation flood test — single
                # attempt, drift error, no retry, customer never got
                # a reply).
                #
                # Reuse the same tunable so behaviour matches HOT-PATH-B.
                try:
                    _dd_hot_path = _live_chat_bridge().hot_path
                    _dd_is_retryable = _dd_hot_path._is_retryable_send_error
                    _dd_backoff = _dd_hot_path.HOT_PATH_DRIFT_RETRY_BACKOFF_S
                    _dd_drift_max = max(
                        1, _live_chat_bridge().hot_path_drift_retry_max()
                    )
                except Exception:
                    _dd_drift_max = 2
                    _dd_backoff = 0.6
                    def _dd_is_retryable(_e):  # type: ignore[no-redef]
                        s = str(_e or "").lower()
                        return (
                            "active customer drifted" in s
                            or "drift" in s and "click" in s
                        )

                _raw = None
                _attempt = 0
                _send_err_final = ""
                # mt044E: serialize concurrent typing ops behind a tunable
                # BoundedSemaphore so Chrome's main thread doesn't get
                # overwhelmed when many customers reply at once.  None
                # when the cap is disabled (typing-concurrency tunable <= 0).
                _mt044e_sem = _mt044e_get_typing_semaphore()
                # ws024: from here the typing eval is in flight — a timeout past
                # this point means the bubble was (almost certainly) typed, so
                # the async-timeout handler must NOT requeue (that re-types).
                _eval_dispatch_state["dispatched"] = True
                while _attempt < _dd_drift_max:
                    _attempt += 1
                    _sig = _inspect.signature(_send_fn.function)
                    if "browser_session" in _sig.parameters:
                        _raw_call = _send_fn.function(
                            params=_send_params,
                            browser_session=_session,
                        )
                    else:
                        _raw_call = _send_fn.function(params=_send_params)
                    if _inspect.isawaitable(_raw_call):
                        if _mt044e_sem is not None:
                            async with _mt044e_sem:
                                _raw = await _raw_call
                        else:
                            _raw = await _raw_call
                    else:
                        _raw = _raw_call

                    _send_err = str(getattr(_raw, "error", "") or "")
                    _send_err_final = _send_err
                    if not _send_err:
                        break  # success
                    if not _dd_is_retryable(_send_err):
                        break  # non-retryable failure
                    if _attempt < _dd_drift_max:
                        logger.info(
                            f"[DIRECT-DELIVERY] live-chat send drift "
                            f"attempt {_attempt}/{_dd_drift_max} for "
                            f"cust={_customer_name!r} (error={_send_err!r}); "
                            f"backing off {_dd_backoff}s and retrying"
                        )
                        try:
                            await _asyncio.sleep(_dd_backoff)
                        except Exception:
                            pass
                        _outcome.actions_attempted = _attempt + 1
                        continue
                    logger.warning(
                        f"[DIRECT-DELIVERY] live-chat send drift "
                        f"unrecoverable after {_attempt} attempts for "
                        f"cust={_customer_name!r}; last_error={_send_err!r}"
                    )
                    # 2026-05-19 Bug 1 fix: signal HOT-PATH-B to retry.
                    # The pend_event preservation flow (build_node.py:8298)
                    # is brittle here — _stale_input is popped BEFORE the
                    # current event's response_text gets put into
                    # state.input (line 8474), so when direct-delivery
                    # drift exhausts the preservation check sees empty
                    # _stale_input and never marks the recovery signal.
                    # Reproduced live 2026-05-19 19:34 for 客户04/客户13.
                    # Mark directly here so HOT-PATH-B's existing override
                    # (front_desk.py drift-recovery block) consumes the
                    # signal when the failure-ack a2a_response arrives at
                    # front-desk and triggers HOT-PATH-B for this customer.
                    try:
                        mark_drift_recovery_pending = (
                            _live_chat_bridge().drift_recovery.mark_drift_recovery_pending
                        )
                        mark_drift_recovery_pending(
                            _customer_name,
                            source_msg_id=_source_msg_id,
                            response_text=_response_text,
                        )
                    except Exception as _drift_sig_err:
                        logger.warning(
                            f"[DIRECT-DELIVERY] drift-recovery signal mark "
                            f"failed (non-fatal): {_drift_sig_err}"
                        )
                    break

                _err = _send_err_final
                if _err:
                    _outcome.ok = False
                    _outcome.last_tool_error = _err
                    if "stale_reply_source_msg_id" in _err:
                        _outcome.reason = "stale_reply_source_msg_id"
                    elif "source_turn_not_found" in _err:
                        _outcome.reason = "source_turn_not_found"
                    else:
                        # Site-specific error markers (e.g. unverified-send
                        # verdicts from the bundle's send tool) map to
                        # generic reason codes via the bridge.
                        try:
                            _site_reason = _live_chat_bridge().classify_send_error(_err)
                        except Exception:
                            _site_reason = None
                        _outcome.reason = _site_reason or _send_fail_reason
                    logger.warning(
                        f"[DIRECT-DELIVERY] live-chat send failed "
                        f"customer={_customer_name!r} reason={_outcome.reason!r} "
                        f"error={_err!r}"
                    )
                    # Grep-friendly stall/failure marker
                    logger.warning(
                        f"[LIVE-CHAT-CUSTOMER-STATE] cust={_customer_name!r} "
                        f"phase=delivery_failed reason={_outcome.reason!r}"
                    )
                    _ledger(
                        "direct_send_failed",
                        reason=_outcome.reason,
                        error=_err,
                        executor=f"{_send_tool_name}_self_open",
                    )
                    return _outcome

                _outcome.ok = True
                _outcome.reason = "all_ok"
                _ledger(
                    "direct_send_success",
                    executor=f"{_send_tool_name}_self_open",
                )
                # Grep-friendly success marker — every truly answered
                # customer emits exactly one of these per turn.
                logger.info(
                    f"[LIVE-CHAT-CUSTOMER-STATE] cust={_customer_name!r} "
                    f"phase=answered_strong source_msg_id={_source_msg_id!r}"
                )
                # Placeholder cancel — PER-TURN (2026-05-20 v2 revert).
                # cancel_any_for_customer was too aggressive: an older
                # in-flight turn's reply landing would kill the LATEST
                # turn's placeholder timer, leaving the customer with no
                # acknowledgment while the Q&A bot processed the latest
                # question (3+ minutes observed for 客户02/06/20 港澳台
                # etc.).  Per-turn cancel keeps each turn's lifecycle
                # independent: this reply's turn closes, others continue.
                # cancel() also stamps _REAL_REPLY_AT[(cust, src_msg_id)]
                # so any in-flight (already-claimed) placeholder for THIS
                # turn is suppressed at submit time.
                try:
                    _ph_timer = _live_chat_bridge().placeholder_timer
                    _ph_timer.cancel(_customer_name, _source_msg_id)
                except Exception:
                    pass
                return _outcome
            except Exception as _send_err:
                _outcome.ok = False
                _outcome.reason = f"exception:{_send_err}"
                _outcome.last_tool_error = str(_send_err)
                logger.warning(
                    f"[DIRECT-DELIVERY] direct live-chat send exception "
                    f"customer={_customer_name!r}: {_send_err}"
                )
                _ledger(
                    "direct_send_exception",
                    error=str(_send_err),
                    executor=f"{_send_tool_name}_self_open",
                )
                return _outcome
            finally:
                if _outcome.typing_acquired and _customer_name:
                    try:
                        _typing_lock.release(_customer_name)
                    except Exception:
                        pass
                # Phase 3 multi-tab: release the typing tab back to the
                # pool.  Sticky retention follows ``_outcome.ok`` — a
                # successful send keeps the customer→tab mapping (next
                # reply for this customer reuses the same tab, skipping
                # the open-session round-trip); a failure clears the sticky so the
                # next attempt picks a different tab.
                if _pool_tab_assigned is not None:
                    try:
                        _direct_tab_pool_release = _live_chat_bridge().tab_pool
                        _direct_tab_pool_release.get_pool().release(
                            _pool_tab_assigned.target_id,
                            succeeded=bool(_outcome.ok),
                            customer_key=str(_customer_name or ""),
                        )
                    except Exception:
                        pass

        def _direct_failure_is_retryable(_reason: str) -> bool:
            if not _reason:
                return False
            return _is_direct_live_chat_retryable_reason(_reason)

        def _direct_failure_is_focus_retryable(_reason: str) -> bool:
            return _reason in {"tab_focus_failed", "tab_focus_timeout"}

        async def _wait_for_frontdesk_browser_idle(_attempt: int) -> bool:
            if _DIRECT_LIVE_CHAT_TASK_IDLE_WAIT_S <= 0:
                return True
            _deadline = time.monotonic() + _DIRECT_LIVE_CHAT_TASK_IDLE_WAIT_S
            _logged = False
            while True:
                _state = getattr(getattr(target_task, "status", None), "state", None)
                if _state != TaskState.working:
                    return True
                if not _logged:
                    logger.info(
                        f"[DIRECT-DELIVERY] Waiting for front-desk browser task "
                        f"to go idle before guarded send customer={_customer_name!r} "
                        f"attempt={_attempt + 1} state={_state!r}"
                    )
                    _logged = True
                if time.monotonic() >= _deadline:
                    logger.warning(
                        f"[DIRECT-DELIVERY] Front-desk browser task still working "
                        f"after {_DIRECT_LIVE_CHAT_TASK_IDLE_WAIT_S:.1f}s; deferring "
                        f"direct send customer={_customer_name!r} "
                        f"attempt={_attempt + 1}"
                    )
                    return False
                await _asyncio.sleep(0.25)

        def _handle_direct_outcome(_outcome: Any, *, release_on_failure: bool = True) -> bool:
            _ok = bool(getattr(_outcome, "ok", False))
            _reason = str(getattr(_outcome, "reason", "") or "")
            logger.info(
                f"[DIRECT-DELIVERY] outcome ok={_ok} reason={_reason!r} "
                f"customer={_customer_name!r} actions={getattr(_outcome, 'actions_attempted', 0)}"
            )
            _ledger(
                "direct_outcome",
                ok=_ok,
                reason=_reason,
                actions=getattr(_outcome, "actions_attempted", 0),
            )
            if _ok:
                try:
                    clear_pending_delivery = _live_chat_bridge().delivery_durability.clear_pending_delivery
                    clear_pending_delivery(_parsed)
                except Exception:
                    pass
                _record_direct_live_chat_cdp_timeout_success()
                if _live_chat_ds is not None:
                    _live_chat_ds.mark_sent_for_turn(_customer_name, _response_text, _source_msg_id)
                    try:
                        # ws003e: long-window delivered ledger so a stale retry can't
                        # re-send this answer after the claim cache ages out.
                        # ws164: record which customer msg this answered.
                        _live_chat_ds.mark_reply_delivered(
                            _customer_name, _response_text, _source_msg_id,
                        )
                    except Exception:
                        pass
                    try:
                        _live_chat_ds.remember_agent_reply(_customer_name, _response_text)
                    except Exception:
                        pass
                _cleanup_live_chat_delivery_state(
                    _customer_name,
                    str(_parsed.get("customer_id") or ""),
                )
                logger.info(
                    f"[DIRECT-DELIVERY] Reply sent to {_customer_name} "
                    f"(bypassed front-desk queue), task={target_task.name}"
                )
                _ledger("direct_sent_and_cleaned")
                return True
            if _reason == "stale_reply_source_msg_id":
                try:
                    clear_pending_delivery = _live_chat_bridge().delivery_durability.clear_pending_delivery
                    clear_pending_delivery(_parsed)
                except Exception:
                    pass
                logger.info(
                    f"[DIRECT-DELIVERY] Dropping stale reply for {_customer_name}; "
                    "newer customer bubble is visible; preserving dispatch state"
                )
                # 2026-05-26 mt046A: clear the two dedup ledgers that PreDispatch
                # and the actionable filter consult.  Without this, the customer
                # is permanently filtered as ``already_dispatched`` even though
                # the reply never landed.  Live trace 2026-05-26 10:14-10:16 for
                # 陆地飞鱼: source-guard correctly aborted, but identity_key dedup
                # (actionable_items) + msg-id dedup (PreDispatch thread-scrape)
                # stayed stamped, so every subsequent EventMonitor tick dropped
                # the customer on the floor.  Same shape as the HOT-PATH-B
                # 2026-05-13 fix in front_desk.py (which only handled HOT-PATH-B
                # crosstalk failures, not direct-delivery stale-drops).
                _mt046a_msg_id_cleared = False
                if _live_chat_ds is not None and _customer_name:
                    try:
                        _mt046a_msg_id_cleared = (
                            _live_chat_ds.last_dispatched_msg_id_by_customer.pop(
                                _customer_name, None
                            )
                            is not None
                        )
                    except Exception:
                        pass
                _mt046a_ident_cleared = 0
                if _customer_name:
                    try:
                        _mt046a_clear_ident = (
                            _live_chat_bridge().actionable_items
                            .clear_dispatched_identity_keys_for_customer
                        )
                        _mt046a_ident_cleared = _mt046a_clear_ident(_customer_name)
                    except Exception:
                        pass
                # 2026-05-27 mt050H — clearing the dedup ledgers isn't
                # enough on its own.  EventMonitor's diff detector only
                # emits dom_observed when a sidebar row's identity_key
                # changes (add / remove / reorder / top_changed).  If
                # the customer's row text is unchanged after stale-drop
                # (common: stale_reply landed but customer hasn't typed
                # anything new), diff stays at added=0 and no event
                # ever fires.  Live trace 2026-05-27 J14N9 was stuck
                # 5+ min after stale-drop because of exactly this.
                # Tell EventMonitor to force-treat this customer as
                # freshly added on its next tick.
                if _customer_name:
                    try:
                        from agent.ec_skills.browser_use_extension.event_monitor import (
                            force_reemit_for_customer as _mt050h_reemit,
                        )
                        _mt050h_reemit(_customer_name)
                    except Exception as _mt050h_err:
                        logger.debug(
                            f"[DIRECT-DELIVERY] mt050H reemit hook failed "
                            f"(non-fatal): {_mt050h_err}"
                        )
                # ws154: also clear the dispatch_inflight marker that ws126's backstop dedup
                # checks. mt046A above clears the msg-id + identity dedups but NOT this, so after
                # a stale-drop the WS-hot-path inflight (set for the OLD message) survives and
                # ws126 SKIPS the re-dispatch of the customer's NEWER message as "already
                # dispatching" until it closes (live 2026-07-08 18:45:31-42 packet: inflight_age
                # 14.5→25s, '你们家衣服现在有优惠吗' never dispatched → conversation closed
                # unanswered). Clear all identity keys (name / card:<talk> / <talk>) — the same
                # keys ws126 probes and ws142 clears on the front_desk stale path.
                _mt046a_inflight_cleared = 0
                if _customer_name and (_live_chat_env("ECAN_LIVE_CHAT_STALE_CLEAR_DISPATCH_INFLIGHT") or "1") != "0":
                    try:
                        from agent.ec_skills.build_node import (
                            _clear_dispatch_inflight as _mt046a_clear_if,
                        )
                        _mt046a_if_keys = [_customer_name]
                        try:
                            _mt046a_t4n = _live_chat_bridge().ws_session.talk_for_name
                            _mt046a_talk = str(_mt046a_t4n(_customer_name) or "").strip()
                            if _mt046a_talk:
                                _mt046a_if_keys += [f"card:{_mt046a_talk}", _mt046a_talk]
                        except Exception:
                            pass
                        for _mt046a_ifk in _mt046a_if_keys:
                            try:
                                _mt046a_clear_if(_mt046a_ifk)
                                _mt046a_inflight_cleared += 1
                            except Exception:
                                pass
                    except Exception:
                        pass
                logger.info(
                    f"[DIRECT-DELIVERY] mt046A cleared dedup ledgers for "
                    f"cust={_customer_name!r} so PreDispatch can re-dispatch: "
                    f"msg_id_cleared={_mt046a_msg_id_cleared}, "
                    f"identity_keys_cleared={_mt046a_ident_cleared}, "
                    f"inflight_cleared={_mt046a_inflight_cleared} "
                    f"(mt050H: queued forced re-emit)"
                )
                _ledger(
                    "direct_stale_dropped",
                    mt046a_msg_id_cleared=_mt046a_msg_id_cleared,
                    mt046a_identity_keys_cleared=_mt046a_ident_cleared,
                )
                return True
            _err_text = str(getattr(_outcome, "last_tool_error", "") or "")
            if (
                _reason == _send_fail_reason
                and "CDP Runtime.evaluate timed out" in _err_text
            ):
                _failures, _remaining = _record_direct_live_chat_cdp_timeout_failure()
                if _remaining > 0.0:
                    logger.warning(
                        f"[DIRECT-DELIVERY] Opened CDP-timeout circuit after "
                        f"{_failures} direct failure(s); bypassing direct "
                        f"delivery for {_remaining:.1f}s"
                    )
                    _ledger(
                        "direct_cdp_timeout_circuit_opened",
                        failures=_failures,
                        cooldown_remaining_s=round(_remaining, 3),
                    )
            # mt053H2 (2026-05-30): when retries are exhausted on a
            # ``Session not found`` / ``target_not_found`` send failure, the
            # chat session for this customer is no longer visible to the site's
            # JS so further deliveries will keep failing the same way.  The
            # only viable recovery is for PreDispatch to re-dispatch via a
            # fresh open-session call — but ``last_dispatched_msg_id``
            # is still stamped from the original dispatch, so PreDispatch's
            # msg-id dedup short-circuits every retry.  Clear the same
            # ledgers mt046A clears on stale-drop so the customer's question
            # can re-enter the dispatch path.  Live trace 2026-05-30 13:09→
            # 13:32 packet: 18+ Session-not-found failures, never recovered,
            # the site auto-closed the session at 13:32.
            if (
                release_on_failure
                and _reason == _send_fail_reason
                and (
                    "Session not found" in _err_text
                    or "target_not_found" in _err_text
                )
            ):
                _mt053h2_msg_id_cleared = False
                if _live_chat_ds is not None and _customer_name:
                    try:
                        _mt053h2_msg_id_cleared = (
                            _live_chat_ds.last_dispatched_msg_id_by_customer.pop(
                                _customer_name, None
                            )
                            is not None
                        )
                    except Exception:
                        pass
                _mt053h2_ident_cleared = 0
                if _customer_name:
                    try:
                        _mt053h2_clear_ident = (
                            _live_chat_bridge().actionable_items
                            .clear_dispatched_identity_keys_for_customer
                        )
                        _mt053h2_ident_cleared = _mt053h2_clear_ident(_customer_name)
                    except Exception:
                        pass
                if _customer_name:
                    try:
                        from agent.ec_skills.browser_use_extension.event_monitor import (
                            force_reemit_for_customer as _mt053h2_reemit,
                        )
                        _mt053h2_reemit(_customer_name)
                    except Exception as _mt053h2_reemit_err:
                        logger.debug(
                            f"[DIRECT-DELIVERY] mt053H2 reemit hook failed "
                            f"(non-fatal): {_mt053h2_reemit_err}"
                        )
                logger.warning(
                    f"[DIRECT-DELIVERY] mt053H2 cleared dedup ledgers for "
                    f"cust={_customer_name!r} after Session-not-found exhausted "
                    f"retries: msg_id_cleared={_mt053h2_msg_id_cleared}, "
                    f"identity_keys_cleared={_mt053h2_ident_cleared} "
                    f"(forced re-emit; PreDispatch can re-open the chat session)"
                )
                # ws155: mt053H2 above cleared msg-id + identity but NOT dispatch_inflight, so a
                # surviving inflight (up to 30s TTL) blocked ws126's backstop re-dispatch. The
                # unified primitive clears ALL blockers across all keys (no suppressors). Gated.
                if _customer_name and (_live_chat_env("ECAN_LIVE_CHAT_UNIFIED_BLOCKER_CLEAR") or "1") != "0":
                    try:
                        _u155 = _live_chat_ds.clear_dispatch_blockers(
                            _customer_name, reason="mt053H2_session_not_found"
                        )
                        logger.info(
                            f"[DIRECT-DELIVERY] ws155 unified blocker-clear (mt053H2) "
                            f"cust={_customer_name!r}: {_u155}"
                        )
                    except Exception as _u155_err:
                        logger.debug(
                            f"[DIRECT-DELIVERY] ws155 unified-clear failed "
                            f"(non-fatal): {_u155_err}"
                        )
                _ledger(
                    "direct_session_not_found_dropped",
                    mt053h2_msg_id_cleared=_mt053h2_msg_id_cleared,
                    mt053h2_identity_keys_cleared=_mt053h2_ident_cleared,
                )
            if release_on_failure and _live_chat_ds is not None:
                _live_chat_ds.unclaim_send_for_turn(_customer_name, _response_text, _source_msg_id)
            return False

        def _schedule_fallback_drain_kick() -> None:
            # ws168 (4): a fallback queued to the front-desk task is only consumed
            # when the task's run loop next polls its queue — a task parked on a
            # pend_event interrupt (or serving other customers) doesn't poll, so
            # the reply sat buried until the SAME customer's next event woke it
            # (live 2026-07-11 'packet': queued 09:59:59, delivered 10:10:03).
            # Kick the queue: after each delay, if the request is STILL queued,
            # pull it and push it through _submit_task_execution, whose guard
            # ladder resumes a parked task and safely re-queues when the task is
            # genuinely working. Dict-only: the guard treats a non-dict msg as
            # no-real-message and would drop it on the working path.
            # Reversible: ECAN_LIVE_CHAT_FALLBACK_DRAIN_KICK=0.
            if (_live_chat_env("ECAN_LIVE_CHAT_FALLBACK_DRAIN_KICK") or "1") == "0":
                return
            if not isinstance(request, dict):
                return
            try:
                _kick_raw = (_live_chat_env("ECAN_LIVE_CHAT_FALLBACK_DRAIN_KICK_S") or "8,20,45") or "8,20,45"
                _kick_delays = [float(x) for x in _kick_raw.split(",") if x.strip()]
            except (TypeError, ValueError):
                _kick_delays = [8.0, 20.0, 45.0]

            def _kick(_attempt: int) -> None:
                try:
                    _q = getattr(target_task, "queue", None)
                    if _q is None:
                        return
                    _found = False
                    with _q.mutex:
                        for _qi_idx, _qi in enumerate(_q.queue):
                            if _qi is request:
                                del _q.queue[_qi_idx]
                                _found = True
                                break
                    if not _found:
                        return  # consumed by the normal path — done
                    request.setdefault("__trigger_source__", "message")
                    logger.warning(
                        f"[DIRECT-DELIVERY] ws168 fallback drain kick #{_attempt} "
                        f"customer={_customer_name!r} — queued fallback still "
                        f"unconsumed (task parked/busy); force-submitting"
                    )
                    _ledger("direct_fallback_drain_kick", attempt=_attempt)
                    self._submit_task_execution(target_task, request, "message", None)
                except Exception as _kick_err:
                    logger.error(
                        f"[DIRECT-DELIVERY] ws168 drain kick failed "
                        f"customer={_customer_name!r}: {_kick_err}"
                    )

            import threading as _kick_threading
            for _kick_i, _kick_d in enumerate(_kick_delays, start=1):
                _kick_t = _kick_threading.Timer(_kick_d, _kick, args=(_kick_i,))
                _kick_t.daemon = True
                _kick_t.start()

        def _enqueue_direct_fallback(_reason: str) -> None:
            _health_remaining_inner = _live_chat_cdp_health_cooldown_remaining()
            if _health_remaining_inner > 0.0:
                _schedule_frontdesk_retry_after_health(
                    "direct_fallback_delayed_for_cdp_health",
                    _reason,
                    _health_remaining_inner,
                )
                return
            # ws169: bound the retry chain. With card timeouts now failing honestly
            # (ws161 card echo-confirm) a doomed delivery — e.g. a synthetic card
            # whose sidebar row never renders — would otherwise cycle
            # requeue -> fallback -> drain-kick -> requeue indefinitely, each cycle
            # holding the global typing lock ~10s (the ws127 storm shape). The
            # counter rides on the request dict, so it survives kick re-submits.
            if isinstance(request, dict):
                _fb_n = int(request.get("_ecan_direct_fallback_attempts") or 0) + 1
                request["_ecan_direct_fallback_attempts"] = _fb_n
                try:
                    _fb_max = int(
                        (_live_chat_env("ECAN_LIVE_CHAT_FALLBACK_MAX_CYCLES") or "3") or 3
                    )
                except (TypeError, ValueError):
                    _fb_max = 3
                if _fb_n > _fb_max:
                    logger.error(
                        f"[DIRECT-DELIVERY] ws169 delivery ABANDONED after "
                        f"{_fb_n - 1} fallback cycles customer={_customer_name!r} "
                        f"reason={_reason} — reply NOT delivered (ws108 backstop / "
                        f"customer re-ask is the remaining recovery)"
                    )
                    _ledger(
                        "direct_fallback_abandoned",
                        reason=_reason,
                        cycles=_fb_n - 1,
                    )
                    # ws170: a card:<talk> reply abandoned here is structurally
                    # undeliverable (no row by that name yet) — park it so the
                    # front-desk backstop flushes it once the talk resolves to
                    # a real name (nickname arrives with the customer's first
                    # TEXT frame).
                    try:
                        _ws170_park = _live_chat_bridge().undeliverable.park
                        _ws170_park(
                            _customer_name, _response_text, _source_msg_id,
                            reason=f"fallback_abandoned:{_reason}",
                        )
                    except Exception:
                        pass
                    if _live_chat_ds is not None:
                        try:
                            _live_chat_ds.unclaim_send_for_turn(
                                _customer_name, _response_text, _source_msg_id
                            )
                        except Exception:
                            pass
                    return
            try:
                _tag_queue_event_type(request, "chat_message")
                target_task.queue.put_nowait(request)
                logger.info(
                    f"[DIRECT-DELIVERY] Background fallback queued for "
                    f"customer={_customer_name!r} reason={_reason} "
                    f"queue={_snapshot_queue(target_task.queue, limit=10)}"
                )
                _ledger("direct_fallback_queued", reason=_reason)
                self._ensure_task_execution_alive(target_task, "chat_message")
                _schedule_fallback_drain_kick()
                _wait_shutdown_fallback_terminal("direct_fallback_pending_during_shutdown")
            except Exception as _fallback_err:
                logger.error(
                    f"[DIRECT-DELIVERY] Background fallback enqueue failed "
                    f"customer={_customer_name!r}: {_fallback_err}"
                )

        _direct_requeue_state = {"count": 0, "cdp_cooldown_count": 0}

        def _should_requeue_direct(_reason: str, _error: str = "") -> bool:
            if _reason in {"tab_focus_failed", "tab_focus_timeout", "typing_lock_busy"}:
                return True
            if _reason == _send_fail_reason:
                if not _error:
                    return True
                if "cdp_timeout_cooldown_active" in _error:
                    return True
                # A CDP Runtime.evaluate timeout means the browser renderer did
                # not answer the send script within the hard eval timeout. In
                # flood tests, immediate requeues of this exact failure never
                # recovered, but they consumed the single direct-delivery worker
                # for another 6s per attempt and blocked fresh replies behind
                # doomed retries. Let the normal front-desk fallback path take
                # over instead of head-of-line blocking the direct queue.
                if (
                    "CDP Runtime.evaluate timed out" in _error
                ):
                    _ledger(
                        "direct_requeue_suppressed",
                        reason=_reason,
                        error=_error,
                        policy="browser_eval_timeout_no_direct_requeue",
                    )
                    return False
                # ws127: fail-fast an UNRESOLVABLE product-card identity on
                # Session-not-found. A ``card:<talk>`` identity has no sidebar row by
                # that literal name, so requeuing just re-storms the GLOBAL typing lock
                # and fails the same way — each retry holds the lock ~10s and defers
                # EVERY other customer's turn behind it (live 1-vs-3: one card's 3 retries
                # froze all 3 customers). Real-name customers are untouched (full transient
                # recovery preserved); only the doomed synthetic card identity is dropped.
                # The uid->name bridge (ws127) resolves most cards before this point; this
                # catches the residual true-cold-start card with no named frame ever seen.
                # Reversible: ECAN_LIVE_CHAT_CARD_SNF_FAILFAST=0.
                if (
                    (_live_chat_env("ECAN_LIVE_CHAT_CARD_SNF_FAILFAST") or "1") != "0"
                    and str(_customer_name or "").startswith("card:")
                    and ("Session not found" in _error or "target_not_found" in _error)
                ):
                    _ledger(
                        "direct_requeue_suppressed",
                        reason=_reason,
                        error=_error,
                        policy="ws127_unresolvable_card_no_requeue",
                    )
                    # ws170: the failfast (correctly) refuses to storm the
                    # typing lock for an unresolvable card — but the reply
                    # used to die with it. Park it for name-resolution flush.
                    try:
                        _ws170_park_snf = _live_chat_bridge().undeliverable.park
                        _ws170_park_snf(
                            _customer_name, _response_text, _source_msg_id,
                            reason="ws127_card_snf_failfast",
                        )
                    except Exception:
                        pass
                    return False
                transient_markers = (
                    "Input box not found",
                    "Session not found",
                    "Active customer mismatch",
                    "Send did not clear input",
                    "No valid agent focus",
                    "target may have detached",
                )
                return any(marker in _error for marker in transient_markers)
            return False

        def _schedule_direct_requeue(
            _queue: Any,
            _reason: str,
            *,
            _error: str = "",
        ) -> bool:
            if _queue is None:
                return False
            _cooldown_delay = _direct_live_chat_cdp_cooldown_retry_delay(_error)
            _is_cdp_cooldown = _cooldown_delay > 0.0
            if _is_cdp_cooldown:
                if (
                    _direct_requeue_state["cdp_cooldown_count"]
                    >= _DIRECT_LIVE_CHAT_CDP_COOLDOWN_REQUEUE_LIMIT
                ):
                    return False
                _direct_requeue_state["cdp_cooldown_count"] += 1
                _count = _direct_requeue_state["cdp_cooldown_count"]
                _limit = _DIRECT_LIVE_CHAT_CDP_COOLDOWN_REQUEUE_LIMIT
                _delay = _cooldown_delay
            else:
                if _direct_requeue_state["count"] >= _DIRECT_LIVE_CHAT_REQUEUE_LIMIT:
                    return False
                _direct_requeue_state["count"] += 1
                _count = _direct_requeue_state["count"]
                _limit = _DIRECT_LIVE_CHAT_REQUEUE_LIMIT
                _delay = _DIRECT_LIVE_CHAT_REQUEUE_DELAY_S * _count

            def _put_again() -> None:
                try:
                    _queue.put_nowait(lambda: _async_direct_delivery_job(_queue))
                except Exception as _put_err:
                    logger.error(
                        f"[DIRECT-DELIVERY] Direct requeue failed "
                        f"customer={_customer_name!r}: {_put_err}"
                    )

            try:
                _loop = _asyncio.get_running_loop()
                if _delay > 0:
                    _loop.call_later(_delay, _put_again)
                else:
                    _loop.call_soon(_put_again)
                logger.warning(
                    f"[DIRECT-DELIVERY] Requeued direct delivery to queue tail "
                    f"customer={_customer_name!r} reason={_reason!r} "
                    f"requeue={_count}/{_limit} "
                    f"delay={_delay:.2f}s"
                )
                _ledger(
                    (
                        "direct_cdp_cooldown_requeue_scheduled"
                        if _is_cdp_cooldown
                        else "direct_requeue_scheduled"
                    ),
                    reason=_reason,
                    requeue_count=_count,
                    delay_s=_delay,
                    error=_error,
                )
                return True
            except Exception as _sched_err:
                logger.error(
                    f"[DIRECT-DELIVERY] Direct requeue scheduling failed "
                    f"customer={_customer_name!r}: {_sched_err}"
                )
                return False

        def _run_direct_delivery_blocking() -> bool:
            _lock = _DIRECT_LIVE_CHAT_DELIVERY_LOCK
            if not _lock.acquire(timeout=20.0):
                if _live_chat_ds is not None:
                    _live_chat_ds.unclaim_send_for_turn(_customer_name, _response_text, _source_msg_id)
                logger.warning(
                    f"[DIRECT-DELIVERY] Skipping: direct delivery lock timeout "
                    f"customer={_customer_name!r} task={target_task.name}"
                )
                _ledger("direct_blocking_lock_timeout")
                return False
            try:
                _track_direct_live_chat_job(_direct_job_id, _parsed, "blocking")
                _ledger("direct_blocking_job_start")
                for _attempt in range(_DIRECT_LIVE_CHAT_MAX_RETRIES + 1):
                    _outcome = _asyncio.run(
                        _asyncio.wait_for(
                            _do_guarded_direct_delivery(),
                            timeout=_DIRECT_LIVE_CHAT_JOB_TIMEOUT_S,
                        )
                    )
                    _reason = str(getattr(_outcome, "reason", "") or "")
                    _retry = (
                        _attempt < _DIRECT_LIVE_CHAT_MAX_RETRIES
                        and not bool(getattr(_outcome, "ok", False))
                        and _direct_failure_is_retryable(_reason)
                    )
                    if _handle_direct_outcome(_outcome, release_on_failure=not _retry):
                        return True
                    if not _retry:
                        return False
                    logger.warning(
                        f"[DIRECT-DELIVERY] Blocking retry "
                        f"{_attempt + 1}/{_DIRECT_LIVE_CHAT_MAX_RETRIES} "
                        f"customer={_customer_name!r} reason={_reason!r}"
                    )
                    time.sleep(_DIRECT_LIVE_CHAT_RETRY_DELAY_S * (_attempt + 1))
                return False
            except _asyncio.TimeoutError:
                if _live_chat_ds is not None:
                    _live_chat_ds.unclaim_send_for_turn(_customer_name, _response_text, _source_msg_id)
                logger.warning(
                    f"[DIRECT-DELIVERY] Blocking job timed out after "
                    f"{_DIRECT_LIVE_CHAT_JOB_TIMEOUT_S:.1f}s; will fall back to queue "
                    f"customer={_customer_name!r}"
                )
                return False
            except Exception as _direct_err:
                if _live_chat_ds is not None:
                    _live_chat_ds.unclaim_send_for_turn(_customer_name, _response_text, _source_msg_id)
                logger.info(
                    f"[DIRECT-DELIVERY] Exception, will fall back to queue: "
                    f"{_direct_err} customer={_customer_name!r}"
                )
                return False
            finally:
                _untrack_direct_live_chat_job(_direct_job_id)
                try:
                    _lock.release()
                except Exception:
                    pass

        async def _async_direct_delivery_job(_queue: Any = None) -> None:
            _track_direct_live_chat_job(_direct_job_id, _parsed, "running")
            _ledger("direct_job_start")
            try:
                _attempt = 0
                _generic_retries = 0
                _focus_retries = 0
                while True:
                    _frontdesk_idle = await _wait_for_frontdesk_browser_idle(_attempt)
                    if not _frontdesk_idle:
                        if _schedule_direct_requeue(_queue, "frontdesk_browser_busy"):
                            return
                        logger.warning(
                            f"[DIRECT-DELIVERY] Front-desk stayed busy and "
                            f"direct requeue limit exhausted; proceeding with "
                            f"guarded send customer={_customer_name!r}"
                        )
                    try:
                        _outcome = await _asyncio.wait_for(
                            _do_guarded_direct_delivery(),
                            timeout=_DIRECT_LIVE_CHAT_JOB_TIMEOUT_S,
                        )
                    except _asyncio.TimeoutError:
                        if _generic_retries < _DIRECT_LIVE_CHAT_MAX_RETRIES:
                            _generic_retries += 1
                            _attempt += 1
                            logger.warning(
                                f"[DIRECT-DELIVERY] Async timeout retry "
                                f"{_generic_retries}/{_DIRECT_LIVE_CHAT_MAX_RETRIES} "
                                f"after {_DIRECT_LIVE_CHAT_JOB_TIMEOUT_S:.1f}s "
                                f"customer={_customer_name!r}"
                            )
                            await _asyncio.sleep(
                                _DIRECT_LIVE_CHAT_RETRY_DELAY_S * _generic_retries
                            )
                            continue
                        logger.warning(
                            f"[DIRECT-DELIVERY] Async job timed out after "
                            f"{_DIRECT_LIVE_CHAT_JOB_TIMEOUT_S:.1f}s "
                            f"customer={_customer_name!r}"
                        )
                        # ws024: if the typing eval was already IN FLIGHT when we
                        # timed out, the bubble was almost certainly typed (the
                        # slow phases — per-char typing, source-guard polling,
                        # lock_held — all run AFTER input-found; a genuine
                        # pre-type failure returns an explicit error, not a
                        # timeout). Requeuing re-types the SAME reply before the
                        # DOM dedup (latestVisibleBubble) can catch it under
                        # render-race load → the customer sees the reply TWICE.
                        # Presume delivered: record it on every dedup ledger so
                        # no path re-sends, clear the durable-pending marker, and
                        # SKIP the requeue/fallback. If the eval never dispatched
                        # (stuck on tab-resolve / typing-lock), nothing was typed
                        # → fall through to the normal requeue (no dup risk).
                        # Kill-switch: ECAN_LIVE_CHAT_TIMEOUT_PRESUME_DELIVERED=0.
                        # ws161: presume-delivered previously DROPPED the reply
                        # whenever the typing eval hung mid-type rather than merely
                        # ran slow — the bubble never lands (live 2026-07-10 陆地飞鱼
                        # '有打折吗': the correct discount answer was generated, the
                        # eval timed out IN FLIGHT, ws024 presumed it delivered, and
                        # nothing ever showed to the customer). The loop was HEALTHY
                        # at that timeout — canary lag 0ms, recovery scans ~2ms — so
                        # this was NOT renderer starvation; the send eval alone hung,
                        # which means an echo-confirm scrape WOULD have worked. Before
                        # presuming, do ONE bounded scrape: presume delivered ONLY on
                        # a positive confirm (our reply IS the latest agent bubble);
                        # an unconfirmed / not-found / scrape-failed result falls
                        # through to the requeue below (an unanswered customer breaks
                        # the 40s SLA far worse than a rare duplicate, which the DOM
                        # dedup on requeue usually catches anyway). For card: identities
                        # the real DOM name is resolved via name_for_talk so the scrape
                        # can focus the thread. Kill-switch: ECAN_LIVE_CHAT_TIMEOUT_ECHO_CONFIRM=0.
                        _ws161_name = str(_customer_name or "")
                        if _ws161_name.startswith("card:"):
                            try:
                                _ws161_wss = _live_chat_bridge().ws_session
                                _ws161_rn = str(
                                    _ws161_wss.name_for_talk(_ws161_name[5:]) or ""
                                ).strip()
                                if _ws161_rn and not _ws161_rn.startswith("card:"):
                                    _ws161_name = _ws161_rn
                            except Exception:
                                pass
                        # ws169: card: identities are no longer excluded here. The DOM
                        # scrape can't resolve a synthetic card row (why ws161 skipped
                        # them), but that made EVERY card timeout fall into the blind
                        # presume-delivered below — live 2026-07-12 09:19:51 a card ack
                        # timed out mid row-hunt (row never rendered), was presumed
                        # delivered, and silently died. The conversation is WS-live by
                        # construction (the card ARRIVED over WS), so confirm via the
                        # WS thread snapshot instead: a typed reply echoes back as the
                        # latest agent frame.
                        _ws161_is_card = bool(_ws161_name) and _ws161_name.startswith(
                            "card:"
                        )
                        _ws161_confirm_on = (
                            _eval_dispatch_state.get("dispatched")
                            and _session is not None
                            and _ws161_name
                            and (_live_chat_env("ECAN_LIVE_CHAT_TIMEOUT_ECHO_CONFIRM") or "1") != "0"
                        )
                        if (
                            _ws161_is_card
                            and (_live_chat_env("ECAN_LIVE_CHAT_TIMEOUT_ECHO_CONFIRM_CARD") or "1") == "0"
                        ):
                            _ws161_confirm_on = False  # revert switch: old card exclusion
                        _ws161_delivered = None  # None=unchecked/failed, bool=verdict
                        if _ws161_confirm_on:
                            try:
                                _ws161_bridge = _live_chat_bridge()
                                _ws161_match = _ws161_bridge.dispatch_state.reply_echo_matches
                                if _ws161_is_card:
                                    _ws161_snap = _ws161_bridge.ws_session.ws_thread_snapshot
                                    _ws161_lab = (
                                        (_ws161_snap(_ws161_name) or {}).get("agent")
                                        or {}
                                    )
                                else:
                                    _ws161_scrape = _ws161_bridge.scrape_latest_customer_bubble
                                    _ws161_res = await _asyncio.wait_for(
                                        _ws161_scrape(_session, _ws161_name),
                                        timeout=float(
                                            (_live_chat_env("ECAN_LIVE_CHAT_TIMEOUT_ECHO_CONFIRM_S") or "4") or 4
                                        ),
                                    )
                                    _ws161_lab = (_ws161_res or {}).get(
                                        "latest_agent_bubble"
                                    ) or {}
                                _ws161_lab_txt = str(_ws161_lab.get("text") or "")
                                _ws161_delivered = bool(
                                    _ws161_lab_txt
                                    and _ws161_match(_ws161_lab_txt, _response_text)
                                )
                                logger.warning(
                                    f"[DIRECT-DELIVERY] ws161 echo-confirm "
                                    f"cust={_ws161_name!r} delivered={_ws161_delivered} "
                                    f"lane={'ws-snapshot' if _ws161_is_card else 'dom'} "
                                    f"latest_agent={_ws161_lab_txt[:40]!r}"
                                )
                            except Exception as _ws161_e:
                                _ws161_delivered = None
                                logger.warning(
                                    f"[DIRECT-DELIVERY] ws161 echo-confirm scrape "
                                    f"failed cust={_ws161_name!r}: {_ws161_e} — "
                                    f"treating as NOT delivered (will requeue)"
                                )
                        # Presume delivered only when the confirm is disabled (legacy
                        # behavior) OR the scrape POSITIVELY found our reply. When the
                        # confirm ran and returned not-found / failed, skip this block
                        # and requeue below.
                        _ws161_presume = (not _ws161_confirm_on) or (
                            _ws161_delivered is True
                        )
                        if (
                            _eval_dispatch_state.get("dispatched")
                            and _ws161_presume
                            and (_live_chat_env("ECAN_LIVE_CHAT_TIMEOUT_PRESUME_DELIVERED") or "1") != "0"
                        ):
                            if _live_chat_ds is not None:
                                try:
                                    _live_chat_ds.mark_sent_for_turn(
                                        _customer_name, _response_text, _source_msg_id,
                                    )
                                    _live_chat_ds.mark_reply_delivered(
                                        _customer_name, _response_text,
                                        _source_msg_id,  # ws164
                                    )
                                    _live_chat_ds.remember_agent_reply(
                                        _customer_name, _response_text,
                                    )
                                except Exception:
                                    pass
                            try:
                                _live_chat_bridge().delivery_durability.clear_pending_delivery(_parsed)
                            except Exception:
                                pass
                            _ledger(
                                "direct_timeout_presumed_delivered",
                                note=(
                                    "typing eval in flight at timeout; bubble "
                                    "likely typed; suppressing requeue to avoid "
                                    "duplicate"
                                ),
                            )
                            logger.warning(
                                f"[DIRECT-DELIVERY] Async timeout but typing eval "
                                f"was IN FLIGHT — presuming delivered, NOT "
                                f"requeuing (avoids duplicate) "
                                f"customer={_customer_name!r}"
                            )
                            return
                        if _schedule_direct_requeue(_queue, "direct_delivery_timeout"):
                            return
                        if _live_chat_ds is not None:
                            _live_chat_ds.unclaim_send_for_turn(
                                _customer_name,
                                _response_text,
                                _source_msg_id,
                            )
                        _enqueue_direct_fallback("direct_delivery_timeout")
                        return
                    except Exception as _direct_err:
                        if _generic_retries < _DIRECT_LIVE_CHAT_MAX_RETRIES:
                            _generic_retries += 1
                            _attempt += 1
                            logger.warning(
                                f"[DIRECT-DELIVERY] Async exception retry "
                                f"{_generic_retries}/{_DIRECT_LIVE_CHAT_MAX_RETRIES} "
                                f"customer={_customer_name!r}: {_direct_err}"
                            )
                            await _asyncio.sleep(
                                _DIRECT_LIVE_CHAT_RETRY_DELAY_S * _generic_retries
                            )
                            continue
                        logger.info(
                            f"[DIRECT-DELIVERY] Async exception, will fall back to queue: "
                            f"{_direct_err} customer={_customer_name!r}"
                        )
                        if _schedule_direct_requeue(_queue, "direct_delivery_exception"):
                            return
                        if _live_chat_ds is not None:
                            _live_chat_ds.unclaim_send_for_turn(
                                _customer_name,
                                _response_text,
                                _source_msg_id,
                            )
                        _enqueue_direct_fallback("direct_delivery_exception")
                        return

                    _reason = str(getattr(_outcome, "reason", "") or "")
                    _error = str(getattr(_outcome, "last_tool_error", "") or "")
                    _requeue = (
                        not bool(getattr(_outcome, "ok", False))
                        and _should_requeue_direct(_reason, _error)
                    )
                    _retry = False
                    _focus_retry = (
                        _focus_retries < _DIRECT_LIVE_CHAT_FOCUS_RETRIES
                        and not bool(getattr(_outcome, "ok", False))
                        and _direct_failure_is_focus_retryable(_reason)
                    )
                    if _focus_retry:
                        _retry = True
                    else:
                        _retry = (
                            _generic_retries < _DIRECT_LIVE_CHAT_MAX_RETRIES
                            and not bool(getattr(_outcome, "ok", False))
                            and _direct_failure_is_retryable(_reason)
                        )
                    if _handle_direct_outcome(
                        _outcome,
                        release_on_failure=not (_retry or _requeue),
                    ):
                        return
                    if _requeue:
                        if _schedule_direct_requeue(_queue, _reason, _error=_error):
                            return
                        if _live_chat_ds is not None:
                            _live_chat_ds.unclaim_send_for_turn(
                                _customer_name,
                                _response_text,
                                _source_msg_id,
                            )
                        _enqueue_direct_fallback("direct_delivery_requeue_exhausted")
                        return
                    if not _retry:
                        _enqueue_direct_fallback("direct_delivery_failed")
                        return
                    _attempt += 1
                    if _focus_retry:
                        _focus_retries += 1
                        logger.warning(
                            f"[DIRECT-DELIVERY] Async focus retry "
                            f"{_focus_retries}/{_DIRECT_LIVE_CHAT_FOCUS_RETRIES} "
                            f"customer={_customer_name!r} reason={_reason!r}"
                        )
                        await _asyncio.sleep(
                            _DIRECT_LIVE_CHAT_FOCUS_RETRY_DELAY_S * _focus_retries
                        )
                        continue
                    _generic_retries += 1
                    logger.warning(
                        f"[DIRECT-DELIVERY] Async retry "
                        f"{_generic_retries}/{_DIRECT_LIVE_CHAT_MAX_RETRIES} "
                        f"customer={_customer_name!r} reason={_reason!r}"
                    )
                    await _asyncio.sleep(
                        _DIRECT_LIVE_CHAT_RETRY_DELAY_S * _generic_retries
                    )
            finally:
                logger.info(
                    f"[DIRECT-DELIVERY] Direct delivery job finished "
                    f"customer={_customer_name!r}"
                )
                _ledger("direct_job_finished")
                _untrack_direct_live_chat_job(_direct_job_id)

        async def _async_direct_delivery_worker(_queue: Any) -> None:
            """Concurrent worker — dispatches each job as an independent
            asyncio task so multiple pool tabs can type in parallel.

            Before Phase 3.5 (2026-05-21) this used ``await _job()`` which
            serialised everything through a single typing operation,
            negating the multi-tab pool's parallelism.  Now each job runs
            concurrently; mutual exclusion is enforced per-tab by
            ``tab_pool.allocate_for_typing``'s ``in_use`` flag, and by
            ``pool.allocate`` returning None when the pool is exhausted
            (jobs then bypass to HOT-PATH-B as before, or fall through
            to monitor-tab typing).
            """
            _in_flight: set = set()
            while True:
                _job = await _queue.get()
                try:
                    _task = _asyncio.create_task(_job())
                    _in_flight.add(_task)
                    _task.add_done_callback(_in_flight.discard)
                except Exception as _worker_err:
                    logger.error(
                        f"[DIRECT-DELIVERY] Async worker dispatch failed: {_worker_err}"
                    )
                finally:
                    try:
                        _queue.task_done()
                    except Exception:
                        pass

        def _submit_loop_direct_delivery(_caller_loop: Any = None) -> bool:
            global _DIRECT_LIVE_CHAT_ASYNC_WORKER
            with _DIRECT_LIVE_CHAT_ASYNC_WORKER_LOCK:
                _entry = _DIRECT_LIVE_CHAT_ASYNC_WORKER
                _worker_loop = _entry[0] if _entry is not None else None
                _worker_task = _entry[2] if _entry is not None else None
                _worker_thread = _entry[3] if _entry is not None and len(_entry) > 3 else None
                _worker_dead = (
                    _entry is None
                    or getattr(_worker_loop, "is_closed", lambda: True)()
                    or not getattr(_worker_loop, "is_running", lambda: False)()
                    or getattr(_worker_task, "done", lambda: True)()
                    or (
                        _worker_thread is not None
                        and not getattr(_worker_thread, "is_alive", lambda: False)()
                    )
                )
                if _worker_dead:
                    import threading as _threading

                    _ready = _threading.Event()
                    _holder: dict[str, Any] = {}

                    def _worker_thread_main() -> None:
                        _loop = _asyncio.new_event_loop()
                        _asyncio.set_event_loop(_loop)
                        _queue = _asyncio.Queue()
                        _task = _loop.create_task(_async_direct_delivery_worker(_queue))
                        _holder.update({"loop": _loop, "queue": _queue, "task": _task})
                        _ready.set()
                        try:
                            _loop.run_forever()
                        finally:
                            try:
                                _task.cancel()
                                _loop.run_until_complete(
                                    _asyncio.gather(_task, return_exceptions=True)
                                )
                            except Exception:
                                pass
                            try:
                                _loop.close()
                            except Exception:
                                pass

                    _thread = _threading.Thread(
                        target=_worker_thread_main,
                        name="LiveChatDirectDelivery",
                        daemon=True,
                    )
                    _thread.start()
                    if not _ready.wait(timeout=2.0):
                        raise RuntimeError("direct delivery worker did not start")
                    _worker_loop = _holder["loop"]
                    _queue = _holder["queue"]
                    _task = _holder["task"]
                    _DIRECT_LIVE_CHAT_ASYNC_WORKER = (
                        _worker_loop,
                        _queue,
                        _task,
                        _thread,
                    )
                    logger.info(
                        f"[DIRECT-DELIVERY] Started background async delivery worker "
                        f"loop_id={id(_worker_loop)}"
                    )
                else:
                    _worker_loop, _queue, _task = _entry[:3]
            try:
                _depth = _queue.qsize() + 1
            except Exception:
                _depth = -1
            try:
                _caller_loop_id = id(_caller_loop) if _caller_loop is not None else 0
            except Exception:
                _caller_loop_id = 0
            # Phase 3.5 (2026-05-21): when the typing-tab pool has
            # capacity, raise the effective depth threshold to match.
            # Otherwise a 6-tab pool would still bypass at depth=2
            # because the static tunable defaults to 1.  Live data
            # showed 16/20 customers getting bypassed despite the
            # pool sitting idle.
            _effective_max_depth = _DIRECT_LIVE_CHAT_MAX_ASYNC_QUEUE_DEPTH
            try:
                _dd_tab_pool = _live_chat_bridge().tab_pool
                _dd_pool_size = _dd_tab_pool.get_pool().get_typing_tab_count()
                if _dd_pool_size > 0:
                    _effective_max_depth = max(
                        _DIRECT_LIVE_CHAT_MAX_ASYNC_QUEUE_DEPTH, _dd_pool_size
                    )
            except Exception:
                pass
            if (
                _effective_max_depth > 0
                and _depth > _effective_max_depth
            ):
                if _direct_live_chat_bypass_on_backpressure():
                    # 2026-05-19 Fix B: v0.9.79 bypass behavior.  Return
                    # False so the outer caller falls through to
                    # target_task.queue.put_nowait — the per-task queue
                    # path picks the reply up via the regular front-desk
                    # task executor + HOT-PATH-B, sharing the typing-lock
                    # but acting as a safety valve so this direct-delivery
                    # queue never accumulates beyond the configured depth.
                    logger.warning(
                        f"[DIRECT-DELIVERY] Bypassing direct delivery due "
                        f"to async queue backpressure customer="
                        f"{_customer_name!r} async_queue_depth={_depth} "
                        f"max_async_queue_depth={_effective_max_depth} "
                        f"(pool_size_contributed={_dd_pool_size if 'dd_pool_size' in dir() else 0}) "
                        f"worker_loop_id={id(_worker_loop)} "
                        f"caller_loop_id={_caller_loop_id} "
                        f"(falling back to per-task queue path)"
                    )
                    _ledger(
                        "direct_backpressure_bypass",
                        async_queue_depth=_depth,
                        max_async_queue_depth=_effective_max_depth,
                        worker_loop_id=id(_worker_loop),
                        caller_loop_id=_caller_loop_id,
                    )
                    # 2026-05-19 bypass-recovery signal.  The per-task
                    # queue + HOT-PATH-B path that this bypass falls
                    # through to has a long-standing bug: HOT-PATH-B's
                    # chat_message rule does not match a2a_response
                    # events, so the bypassed reply gets dropped via
                    # 'first_invocation_skip' (reproduced live 2026-05-19
                    # 19:14 for 客户02/05/06/09/14/15 — all 6 had
                    # direct_backpressure_bypass followed by no actual
                    # delivery).  Reuse the drift-recovery signal channel
                    # to mark this customer so HOT-PATH-B's existing
                    # override (front_desk.py:267-313) forces the rule
                    # match and the bypassed reply is actually typed.
                    # One-shot consumption + 60s TTL keep it bounded.
                    try:
                        mark_drift_recovery_pending = (
                            _live_chat_bridge().drift_recovery.mark_drift_recovery_pending
                        )
                        mark_drift_recovery_pending(
                            _customer_name,
                            source_msg_id=_source_msg_id,
                            response_text=_response_text,
                        )
                    except Exception as _bypass_sig_err:
                        logger.warning(
                            f"[DIRECT-DELIVERY] bypass-recovery signal mark "
                            f"failed (non-fatal): {_bypass_sig_err}"
                        )
                    return False
                logger.warning(
                    f"[DIRECT-DELIVERY] Direct delivery async queue is backed up; "
                    f"retaining reply in direct worker customer={_customer_name!r} "
                    f"async_queue_depth={_depth} "
                    f"max_async_queue_depth={_effective_max_depth} "
                    f"worker_loop_id={id(_worker_loop)} "
                    f"caller_loop_id={_caller_loop_id}"
                )
                _ledger(
                    "direct_backpressure_queued",
                    async_queue_depth=_depth,
                    max_async_queue_depth=_effective_max_depth,
                    worker_loop_id=id(_worker_loop),
                    caller_loop_id=_caller_loop_id,
                )
            logger.info(
                f"[DIRECT-DELIVERY] Queued background direct delivery "
                f"customer={_customer_name!r} async_queue_depth={_depth} "
                f"worker_loop_id={id(_worker_loop)} "
                f"caller_loop_id={_caller_loop_id}"
            )
            _ledger(
                "direct_job_queued",
                async_queue_depth=_depth,
                worker_loop_id=id(_worker_loop),
                caller_loop_id=_caller_loop_id,
            )
            _track_direct_live_chat_job(_direct_job_id, _parsed, "queued")
            try:
                _worker_loop.call_soon_threadsafe(
                    _queue.put_nowait,
                    lambda: _async_direct_delivery_job(_queue),
                )
            except Exception as _enqueue_err:
                _untrack_direct_live_chat_job(_direct_job_id)
                _ledger("direct_job_enqueue_failed", error=str(_enqueue_err))
                raise
            return True

        _caller_loop = None
        try:
            _candidate_loop = _asyncio.get_running_loop()
            if _candidate_loop.is_running():
                _caller_loop = _candidate_loop
        except RuntimeError:
            pass

        try:
            logger.info(
                f"[DIRECT-DELIVERY] Submitting background direct delivery "
                f"customer={_customer_name!r} task={target_task.name}"
            )
            if _submit_loop_direct_delivery(_caller_loop):
                return True
            if _live_chat_ds is not None:
                _live_chat_ds.unclaim_send_for_turn(
                    _customer_name,
                    _response_text,
                    _source_msg_id,
                )
            return False
        except Exception as _bg_submit_err:
            logger.warning(
                f"[DIRECT-DELIVERY] Background worker submit failed; "
                f"falling back to blocking direct delivery "
                f"customer={_customer_name!r}: {_bg_submit_err}"
            )

        try:
            return _run_direct_delivery_blocking()
        except Exception as _direct_err:
            if _live_chat_ds is not None:
                _live_chat_ds.unclaim_send_for_turn(_customer_name, _response_text, _source_msg_id)
            logger.info(
                f"[DIRECT-DELIVERY] Exception, will fall back to queue: "
                f"{_direct_err} customer={_customer_name!r}"
            )
            return False

    def _route_async_callback(self, request: Any) -> bool:
        """
        Route an async callback event to the correct task.

        Uses the correlation_id to find the target task.

        Args:
            request: The callback request (dict with correlation_id, result, error)

        Returns:
            True if routed successfully, False otherwise
        """
        from .pending_events import parse_correlation_id, build_callback_event
        
        try:
            # Extract correlation_id from request
            if isinstance(request, dict):
                correlation_id = request.get("correlation_id")
                result = request.get("result")
                error = request.get("error")
            else:
                correlation_id = getattr(request, "correlation_id", None)
                result = getattr(request, "result", None)
                error = getattr(request, "error", None)
            
            if not correlation_id:
                logger.error("[CALLBACK] No correlation_id in request")
                return False
            
            # Parse task_id from correlation_id
            task_id, _ = parse_correlation_id(correlation_id)
            if not task_id:
                logger.error(f"[CALLBACK] Invalid correlation_id format: {correlation_id}")
                return False
            
            # Find the task
            target_task = self._find_task_by_id(task_id)
            if not target_task:
                logger.error(f"[CALLBACK] Task not found: {task_id}")
                return False
            
            if not target_task.queue:
                logger.error(f"[CALLBACK] Task has no queue: {task_id}")
                return False
            
            # Build and queue the callback event
            event = build_callback_event(correlation_id, result, error)
            target_task.queue.put(event)
            
            logger.info(f"[CALLBACK] Routed callback {correlation_id} to task {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"[CALLBACK] Error routing callback: {e}")
            return False
    
    def _find_task_by_id(self, task_id: str) -> Optional[ManagedTask]:
        """
        Find a task by its ID or run_id.
        
        Searches both self.tasks and agent.tasks.
        
        Args:
            task_id: The task ID or run_id to find
            
        Returns:
            The ManagedTask if found, None otherwise
        """
        # Check local tasks dict first
        if task_id in self.tasks:
            return self.tasks[task_id]
        
        # Check agent.tasks list (match by id or run_id)
        try:
            for t in getattr(self.agent, "tasks", []) or []:
                if t and (getattr(t, "id", None) == task_id or getattr(t, "run_id", None) == task_id):
                    return t
        except Exception:
            pass
        
        return None
    
    def route_webhook_callback(
        self,
        correlation_id: str,
        result: Any = None,
        error: Optional[str] = None
    ) -> bool:
        """
        Public API for routing webhook callbacks.
        
        Call this from your webhook endpoint handler.
        
        Args:
            correlation_id: The operation's correlation ID
            result: Success result (if any)
            error: Error message (if failed)
            
        Returns:
            True if routed successfully, False otherwise
        """
        request = {
            "correlation_id": correlation_id,
            "result": result,
            "error": error,
        }
        return self._route_async_callback(request)
    
    # ==================== Resume Payload Building ====================
    
    def _extract_text_from_message(self, message) -> str:
        """Extract text from a Message object."""
        try:
            parts = getattr(message, "parts", None)
            if not parts and isinstance(message, dict):
                parts = message.get("parts")
            if not parts:
                return getattr(message, "text", "") if hasattr(message, "text") else str(message or "")
            
            texts = []
            for p in parts:
                ptype = getattr(p, "type", None) or (p.get("type") if isinstance(p, dict) else None)
                if ptype == "text":
                    txt = getattr(p, "text", None) or (p.get("text") if isinstance(p, dict) else None)
                    if txt:
                        texts.append(txt)
            return "\n".join(texts)
        except Exception:
            return ""
    
    def _build_resume_payload(self, task: ManagedTask, msg: Any) -> Tuple[Dict[str, Any], Any]:
        """Build a resume payload from incoming message."""
        # Try V2 path first
        try:
            use_v2 = os.getenv("RESUME_PAYLOAD_V2", "true").lower() in ("1", "true", "yes", "on")
            if use_v2:
                return self._build_resume_payload_v2(task, msg)
        except Exception as e:
            logger.debug(f"V2 resume payload failed, falling back: {e}")
        
        # Legacy behavior
        return self._build_resume_payload_legacy(task, msg)
    
    def _build_resume_payload_v2(self, task: ManagedTask, msg: Any) -> Tuple[Dict[str, Any], Any]:
        """Build resume payload using V2 logic."""
        resume_payload, resume_cp, state_patch = build_general_resume_payload(task, msg)
        
        # Merge state_patch into task.metadata["state"]
        if isinstance(state_patch, dict) and state_patch:
            cur_state = task.metadata.get("state") if isinstance(task.metadata, dict) else None
            if isinstance(cur_state, dict):
                merged = self._deep_merge(cur_state, state_patch)
                
                # Sync chatId
                self._sync_chat_id_in_messages(merged)
                
                task.metadata["state"] = merged
                
                # Update checkpoint values
                self._update_checkpoint_values(resume_cp, merged)
        
        # Include state_patch in resume payload
        if isinstance(resume_payload, dict) and isinstance(state_patch, dict):
            resume_payload["_state_patch"] = state_patch
        
        return resume_payload, resume_cp
    
    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Deep merge two dictionaries."""
        out = dict(base)
        for k, v in override.items():
            if k in out and isinstance(out[k], dict) and isinstance(v, dict):
                out[k] = self._deep_merge(out[k], v)
            else:
                out[k] = v
        return out
    
    def _sync_chat_id_in_messages(self, merged: dict):
        """Sync chatId from attributes.params to messages[1]."""
        try:
            new_chat_id = _safe_get(merged, "attributes.params.chatId")
            
            if not new_chat_id:
                params = merged.get("attributes", {}).get("params")
                if hasattr(params, 'metadata') and isinstance(params.metadata, dict):
                    metadata_params = params.metadata.get("params", {})
                    if isinstance(metadata_params, dict):
                        new_chat_id = metadata_params.get("chatId")
            
            if new_chat_id and isinstance(merged.get("messages"), list) and len(merged["messages"]) > 1:
                old_chat_id = merged["messages"][1]
                if old_chat_id != new_chat_id:
                    logger.info(f"Syncing chatId: {old_chat_id} -> {new_chat_id}")
                    merged["messages"][1] = new_chat_id
        except Exception as e:
            logger.error(f"Failed to sync chatId: {e}")
    
    def _update_checkpoint_values(self, resume_cp: Any, merged: dict):
        """Update checkpoint values with merged state."""
        try:
            if hasattr(resume_cp, "values"):
                vals = getattr(resume_cp, "values")
                if isinstance(vals, dict):
                    vals.clear()
                    vals.update(merged)
            elif isinstance(resume_cp, dict):
                resume_cp["values"] = merged
        except Exception as e:
            logger.debug(f"Failed to update checkpoint values: {e}")
    
    def _build_resume_payload_legacy(self, task: ManagedTask, msg: Any) -> Tuple[Dict[str, Any], Any]:
        """Build resume payload using legacy logic."""
        try:
            if hasattr(msg, "params"):
                message = getattr(msg.params, "message", None)
                metadata = getattr(msg.params, "metadata", {}) or {}
            elif isinstance(msg, dict):
                message = msg.get("params", {}).get("message") or msg.get("message")
                metadata = msg.get("params", {}).get("metadata", {}) or msg.get("metadata", {}) or {}
            else:
                message, metadata = None, {}
            
            human_text = self._extract_text_from_message(message) if message else ""
            qa_form = metadata.get("qa_form_to_agent") or metadata.get("qa_form") or {}
            notification = metadata.get("notification_to_agent") or metadata.get("notification") or {}
            
            payload = {
                "human_text": human_text,
                "qa_form_to_agent": qa_form,
                "notification_to_agent": notification,
            }
            
            pending_tag = metadata.get("i_tag")
            resume_cp = task.pop_checkpoint_by_tag(pending_tag) if pending_tag else None
            
            if resume_cp:
                resume_cp = resume_cp.get("checkpoint")
            
            return payload, resume_cp
            
        except Exception:
            return {"human_text": ""}, None
    
    # ==================== Unified Execution Loop ====================
    
    def launch_unified_run(
        self,
        task2run: Optional[ManagedTask] = None,
        trigger_type: "str | List[str]" = "queue",
        *,
        dev_init_state: Optional[dict] = None,
        dev_single_run: bool = False
    ):
        """Run-scope wrapper: every log line emitted by this run (and by the
        asyncio tasks / threadsafe handoffs it spawns) carries
        ``[agent=… task=… skill=…]`` — see utils/log_scope.py. The scope is
        restored on exit so a pooled worker thread never leaks it into the
        next job. Behavior of the run itself is unchanged (see _impl)."""
        card = getattr(self.agent, 'card', None)
        _skill = getattr(task2run, 'skill', None) if task2run is not None else None
        with _log_scope(
            agent_id=getattr(card, 'id', None) or (card.get('id') if isinstance(card, dict) else None),
            agent_name=self._get_agent_name(),
            task_id=getattr(task2run, 'id', None) if task2run is not None else None,
            task_name=getattr(task2run, 'name', None) if task2run is not None else None,
            skill_name=(getattr(_skill, 'name', None) or getattr(_skill, 'skill_name', None)
                        or (_skill.get('name') if isinstance(_skill, dict) else None)),
        ):
            return self._launch_unified_run_impl(
                task2run, trigger_type,
                dev_init_state=dev_init_state, dev_single_run=dev_single_run,
            )

    def _launch_unified_run_impl(
        self,
        task2run: Optional[ManagedTask] = None,
        trigger_type: "str | List[str]" = "queue",
        *,
        dev_init_state: Optional[dict] = None,
        dev_single_run: bool = False
    ):
        """
        Unified task execution loop supporting all trigger types.
        
        Args:
            task2run: ManagedTask to execute.
            trigger_type: str or list of str, e.g. "schedule", ["schedule", "message"]
                          Supported values: "schedule", "message", "auto", "dev"
                          Legacy values (a2a_queue, chat_queue, interaction) are
                          treated as "message".
            dev_init_state: Initial state for dev runs.
            dev_single_run: If True, exit after one run.
        """
        # Normalize trigger_type to a list
        if isinstance(trigger_type, str):
            triggers = [trigger_type]
        else:
            triggers = list(trigger_type)
        
        logger.info(f"[WORKER] launch_unified_run: triggers={triggers}, agent={self.agent.card.name}")
        
        if "dev" in triggers:
            self._dev_exit_requested = False
        
        current_task = task2run
        # A ManagedTask can be reused across multiple workflow/event invocations.
        # If a prior run set cooperative cancellation, clear that stale state before
        # entering a fresh execution loop; otherwise browser/LLM nodes will observe
        # an already-set cancellation_event and abort immediately.
        if current_task is not None:
            try:
                if hasattr(current_task, "cancellation_event") and current_task.cancellation_event.is_set():
                    current_task.cancellation_event.clear()
                    logger.info(f"[WORKER] Cleared stale cancellation_event for task {current_task.id}")
            except Exception as e:
                logger.warning(f"[WORKER] Failed clearing cancellation_event for task {getattr(current_task, 'id', '')}: {e}")
            try:
                if hasattr(current_task, "pause_event") and not current_task.pause_event.is_set():
                    current_task.pause_event.set()
            except Exception:
                pass
        consecutive_errors = 0
        consecutive_validation_failures = 0
        max_errors = 10
        max_validation_failures = 5
        loop_count = 0
        
        # Cache agent type check
        is_twin_agent = "Twin" in self.agent.card.name
        
        while not self._stop_event.is_set():
            # Check task cancellation
            if current_task and current_task.is_cancelled():
                logger.info(f"[WORKER] Task {current_task.name} cancelled")
                break
            
            loop_count += 1
            msg = None
            message_taken = False
            
            try:
                # Get next work item
                current_task, msg, message_taken = self._get_next_work_item(
                    triggers, current_task, task2run, loop_count, is_twin_agent, dev_init_state
                )
                
                if current_task is None:
                    if self._stop_event.wait(timeout=0.5):
                        break
                    continue
                
                if msg is None:
                    # No work item available.  Only fall through to execution
                    # for *pure* schedule tasks (schedule is the ONLY trigger).
                    # Multi-trigger tasks that also have "message" must wait for
                    # an explicit queue message — otherwise the schedule path
                    # keeps re-executing them with empty input every cycle.
                    has_message_trigger = "message" in triggers or any(
                        t in triggers for t in ("a2a_queue", "chat_queue", "interaction")
                    )
                    is_pure_schedule = "schedule" in triggers and not has_message_trigger
                    if not is_pure_schedule:
                        if self._stop_event.wait(timeout=0.5):
                            break
                        continue
                
                # Handle shutdown signal
                if isinstance(msg, dict) and msg.get("__shutdown__"):
                    logger.info("[WORKER] Shutdown signal received")
                    break
                
                # Validate task
                if not self._validate_task_for_execution(current_task):
                    consecutive_validation_failures += 1
                    if consecutive_validation_failures >= max_validation_failures:
                        logger.error(f"[WORKER] Task '{current_task.name}' failed validation {consecutive_validation_failures} times, stopping execution loop")
                        break
                    backoff = min(2 ** consecutive_validation_failures, 30)
                    if self._stop_event.wait(timeout=backoff):
                        break
                    continue
                
                # Determine the effective trigger for this execution.
                # If the message came from the queue (message_taken=True), it's always
                # a "message" trigger regardless of what other triggers the task has.
                if message_taken:
                    effective_trigger = "message"
                elif isinstance(msg, dict) and "__trigger_source__" in msg:
                    effective_trigger = msg["__trigger_source__"]
                else:
                    effective_trigger = triggers[0]
                
                # Submit execution
                self._submit_task_execution(current_task, msg, effective_trigger, dev_init_state)
                
                consecutive_errors = 0
                consecutive_validation_failures = 0
                
            except Exception as e:
                consecutive_errors += 1
                logger.error(get_traceback(e, f"ErrorUnifiedRun[{triggers}]"))
                
                if consecutive_errors >= max_errors:
                    logger.error(f"Too many errors ({max_errors}), stopping")
                    break
                
                if self._stop_event.wait(timeout=min(consecutive_errors, 10)):
                    break
            
            finally:
                # Mark queue task done
                if message_taken and current_task and current_task.queue:
                    try:
                        current_task.queue.task_done()
                    except Exception:
                        pass
            
            # Dev single-run exit check
            if "dev" in triggers and dev_single_run:
                if getattr(self, "_dev_exit_requested", False):
                    break
            
            # Loop delay
            if self._stop_event.wait(timeout=1.0):
                break
        
        logger.info(f"[WORKER] Exiting: triggers={triggers}")
    
    def _get_next_work_item(
        self,
        triggers: List[str],
        current_task: Optional[ManagedTask],
        task2run: Optional[ManagedTask],
        loop_count: int,
        is_twin_agent: bool,
        dev_init_state: Optional[dict]
    ) -> Tuple[Optional[ManagedTask], Any, bool]:
        """
        Get the next work item by checking all trigger sources.
        
        For multi-trigger tasks (e.g. ["schedule", "message"]), each source
        is checked in priority order per iteration:
          1. Dev kickoff (if "dev" in triggers)
          2. Schedule check (if "schedule" in triggers) — non-blocking
          3. Queue poll (if any queue-based trigger) — short timeout
        
        Returns:
            Tuple of (task, message, message_taken_from_queue)
        """
        has_schedule = "schedule" in triggers
        has_dev = "dev" in triggers
        has_auto = "auto" in triggers
        has_pending_queue_item = False
        try:
            task_queue = getattr(current_task, "queue", None) if current_task else None
            has_pending_queue_item = bool(task_queue is not None and task_queue.qsize() > 0)
        except Exception:
            has_pending_queue_item = False
        # Consolidate all message-based triggers (message, a2a_queue, chat_queue, interaction) into one
        has_message = (
            "message" in triggers
            or any(t in triggers for t in ("a2a_queue", "chat_queue", "interaction"))
            or has_pending_queue_item
        )
        has_queue = has_message or has_dev or has_auto
        if has_pending_queue_item and "message" not in triggers:
            try:
                logger.info(
                    f"[QUEUE-TRACE] enabling queue polling for task={getattr(current_task, 'name', '?')} "
                    f"despite triggers={triggers}; queue={_snapshot_queue(current_task.queue, limit=5)}"
                )
            except Exception:
                pass
        
        # --- Dev mode: initial kickoff ---
        if has_dev and current_task:
            if current_task.id not in self._task_states:
                self._task_states[current_task.id] = {'justStarted': True}
            
            state = self._task_states[current_task.id]
            if state.get('justStarted', True) and not state.get('dev_auto_started'):
                state['dev_auto_started'] = True
                return current_task, {"__dev_kickoff__": True, "__trigger_source__": "dev"}, False
        
        # --- Auto trigger: fire once on startup ---
        if has_auto and current_task:
            if current_task.id not in self._task_states:
                self._task_states[current_task.id] = {'justStarted': True}
            
            state = self._task_states[current_task.id]
            if not state.get('auto_started'):
                state['auto_started'] = True
                return current_task, {"__auto_kickoff__": True, "__trigger_source__": "auto"}, False
        
        # --- Schedule check (non-blocking) ---
        # Only use schedule-driven execution for *pure* schedule tasks.
        # Multi-trigger tasks (schedule + message) should wait for queue messages
        # to avoid re-executing with empty input every cycle.
        is_pure_schedule = has_schedule and not has_message
        if is_pure_schedule:
            sched_task = find_tasks_ready_to_run(self.agent.tasks)
            if sched_task:
                return sched_task, {"__trigger_source__": "schedule"}, False
        
        # --- Message queue triggers ---
        if has_queue and current_task:
            # Don't dequeue while the task is actively working — the message
            # would just bounce (dequeue → guard blocks → re-queue → repeat).
            # Wait until the task is idle (input_required / completed / failed)
            # so the next dequeue can actually be processed.
            _cur_state = getattr(getattr(current_task, "status", None), "state", None)
            _future_running = _task_execution_future_running(current_task)
            
            # Check for stale future: future is not done but task state is submitted (not working)
            # This indicates a zombie future that needs to be cleared
            # Also check for working state with future that's actually done (edge case from timeout/crash)
            _future = getattr(current_task, 'future', None)
            _future_done_check = False
            if _future is not None:
                try:
                    _future_done_check = _future.done()
                except Exception:
                    _future_done_check = True  # If we can't check, assume done
            _is_stale_future = (
                _future_running and 
                _future is not None and
                (
                    _cur_state == TaskState.submitted or
                    (_cur_state == TaskState.working and _future_done_check)
                )
            )
            
            # Check for zombie task - working state but no future running
            # This happens when a task crashes/times out but state wasn't cleaned up
            _is_zombie_task = (
                _cur_state == TaskState.working and 
                not _future_running and
                _future is None
            )
            
            # Check for blocked task - working state with future running but no progress
            # This handles the case where browser automation times out (>600s) but task state stays 'working'
            # We track how long the task has been blocked and force clear after a threshold
            _is_blocked_task = False
            if _cur_state == TaskState.working and _future_running and _future is not None:
                _blocked_since = getattr(current_task, '_blocked_since', None)
                if _blocked_since is None:
                    # Start tracking blocked time on first detection
                    setattr(current_task, '_blocked_since', time.time())
                    logger.debug(
                        f"[QUEUE-TRACE] Task blocked detected: task={current_task.name} "
                        f"state={_cur_state!r} future_running={_future_running}"
                    )
                else:
                    _blocked_elapsed = time.time() - _blocked_since
                    # Force clear only after an extended period. A running
                    # future is not necessarily stuck: browser research can
                    # spend several minutes navigating, extracting, and
                    # summarizing before returning an A2A result.
                    if _blocked_elapsed > RUNNING_TASK_BLOCKED_CLEAR_SEC:
                        _is_blocked_task = True
                        logger.warning(
                            f"[QUEUE-TRACE] Task blocked too long ({_blocked_elapsed:.1f}s > "
                            f"{RUNNING_TASK_BLOCKED_CLEAR_SEC:.1f}s), forcing clear: task={current_task.name}"
                        )
                # NOTE: Do NOT delete _blocked_since here - we need to track cumulative blocked time
            elif hasattr(current_task, '_blocked_since'):
                # Task is no longer blocked - clear the tracking
                delattr(current_task, '_blocked_since')
            _force_state_clear = False
            
            if _is_stale_future:
                # Log the stale future detection
                _stale_since = getattr(current_task, '_future_stale_since', None)
                if _stale_since is None:
                    setattr(current_task, '_future_stale_since', time.time())
                    logger.warning(
                        f"[QUEUE-TRACE] Stale future detected: task={current_task.name} "
                        f"future_running={_future_running} state={_cur_state!r}"
                    )
                else:
                    _elapsed = time.time() - _stale_since
                    # Clear stale future after 60 seconds to allow task to be restarted
                    if _elapsed > 60:
                        logger.warning(
                            f"[QUEUE-TRACE] Clearing stale future after {_elapsed:.1f}s: task={current_task.name}"
                        )
                        current_task.future = None
                        delattr(current_task, '_future_stale_since')
                        _future_running = False
                        _force_state_clear = True
                        # Update task state to allow restart
                        try:
                            current_task.status.state = TaskState.input_required
                        except Exception:
                            pass
            
            # Handle zombie tasks: working but no future means task crashed
            # Wait 10 seconds for recovery before marking as zombie
            if _is_zombie_task:
                _zombie_since = getattr(current_task, '_zombie_since', None)
                if _zombie_since is None:
                    setattr(current_task, '_zombie_since', time.time())
                    logger.info(
                        f"[QUEUE-TRACE] Possible zombie task detected: task={current_task.name} "
                        f"state={_cur_state!r} future_running={_future_running}, waiting for recovery..."
                    )
                else:
                    _elapsed = time.time() - _zombie_since
                    # After 10 seconds, assume task is dead and clean up
                    if _elapsed > 10:
                        logger.warning(
                            f"[QUEUE-TRACE] Clearing zombie task after {_elapsed:.1f}s: task={current_task.name}"
                        )
                        _zombie_cleared = True
                        try:
                            current_task.status.state = TaskState.failed
                        except Exception:
                            pass
                        try:
                            if hasattr(current_task, 'cancellation_event'):
                                current_task.cancellation_event.set()
                        except Exception:
                            pass
                        delattr(current_task, '_zombie_since')
                        logger.info(f"[QUEUE-TRACE] Zombie task cleared: task={current_task.name}")
                        _force_state_clear = True
            else:
                # Task recovered or became normal - clear zombie tracking
                if hasattr(current_task, '_zombie_since'):
                    delattr(current_task, '_zombie_since')
            
            # Handle blocked tasks - force clear after extended block
            if _is_blocked_task:
                current_task.future = None
                try:
                    current_task.status.state = TaskState.failed
                except Exception:
                    pass
                try:
                    if hasattr(current_task, 'cancellation_event'):
                        current_task.cancellation_event.set()
                except Exception:
                    pass
                if hasattr(current_task, '_blocked_since'):
                    delattr(current_task, '_blocked_since')
                _force_state_clear = True
                logger.info(f"[QUEUE-TRACE] Blocked task cleared: task={current_task.name}")
            
            _allow_parked_live_chat_response = (
                _cur_state == TaskState.input_required
                and _future_running
                and _has_queued_live_chat_response_payload(current_task)
            )
            
            # Only skip dequeuing if: task is truly working AND future is running AND no force clear
            # Also allow dequeuing if there's a parked live-chat response to deliver
            if (_cur_state == TaskState.working or _future_running) and not _allow_parked_live_chat_response and not _force_state_clear:
                # [QUEUE-TRACE] Visibility on dequeue-skipped-because-busy. This is
                # the most likely place a chat_message sits stranded: task is still
                # working so we do not touch the queue. Throttle to avoid spam (~1/s).
                try:
                    _qd = current_task.queue.qsize() if getattr(current_task, "queue", None) else 0
                    if _qd > 0:
                        _last_log_t = getattr(self, "_last_busy_skip_log_t", {})
                        import time as _t_busy
                        _now = _t_busy.time()
                        if _now - _last_log_t.get(current_task.id, 0.0) > 1.0:
                            # [DEBUG] Compute hash for each queued message to track duplicates
                            _queue_details = ""
                            try:
                                import hashlib
                                with current_task.queue.mutex:
                                    _all_msgs = list(current_task.queue.queue)
                                _hash_counts = {}
                                for _i, _m in enumerate(_all_msgs):
                                    _m_str = str(_m)[:100]  # First 100 chars
                                    _m_hash = hashlib.md5(_m_str.encode()).hexdigest()[:8]
                                    _hash_counts[_m_hash] = _hash_counts.get(_m_hash, 0) + 1
                                _dup_summary = ", ".join([f"#{k[:6]}x{n}" for k, n in _hash_counts.items() if n > 1])
                                _queue_details = f" queue_hashes=[{_dup_summary}]" if _dup_summary else ""
                            except Exception:
                                pass
                            
                            logger.info(
                                f"[QUEUE-TRACE] dequeue SKIPPED (task busy): "
                                f"state={_cur_state!r} future_running={_future_running} "
                                f"task={current_task.name} queue={_snapshot_queue(current_task.queue, limit=10)}{_queue_details}"
                            )
                            try:
                                with current_task.queue.mutex:
                                    _head_msg = current_task.queue.queue[0] if current_task.queue.queue else None
                                if _head_msg is not None:
                                    _log_live_chat_runner_stage(
                                        "runner_queue_busy_wait",
                                        _head_msg,
                                        task=current_task,
                                        task_state=str(_cur_state),
                                        future_running=bool(_future_running),
                                        queue_depth=_qd,
                                    )
                            except Exception:
                                pass
                            _last_log_t[current_task.id] = _now
                            self._last_busy_skip_log_t = _last_log_t
                except Exception:
                    pass

                # mt052D Day 2: out-of-band parallel dispatch.
                # When the task is busy with a previous browser_event AND
                # a new browser_event is at the head of the queue, peek at
                # its body and try to dispatch its non-overlapping customers
                # in parallel.  Default off; gated by
                # ECAN_FRONTDESK_OOB_DISPATCH=1 on the customer machine.
                #
                # Leaves the message in the queue — the in-band path will
                # eventually pick it up too, but any customers already
                # OOB-dispatched will be filtered by the
                # ``_dispatched_identity_keys`` ledger and skipped.  No
                # double-dispatch.
                try:
                    _qd_for_oob = (
                        current_task.queue.qsize()
                        if getattr(current_task, "queue", None) else 0
                    )
                    if _qd_for_oob > 0:
                        with current_task.queue.mutex:
                            _head = (
                                current_task.queue.queue[0]
                                if current_task.queue.queue else None
                            )
                        if _head is not None and _classify_queue_event(_head) == "browser_event":
                            _body = _browser_event_snapshot_body(_head)
                            _items = (
                                _body.get("items")
                                if isinstance(_body, dict) else None
                            )
                            if isinstance(_items, list) and _items:
                                _custs = set()
                                for _it in _items:
                                    if not isinstance(_it, dict):
                                        continue
                                    _cn = str(
                                        _it.get("customer_id")
                                        or _it.get("customer_name")
                                        or _it.get("name")
                                        or ""
                                    )
                                    if _cn:
                                        _custs.add(_cn)
                                if _custs:
                                    try:
                                        from agent.ec_skills.node_runtime.frontdesk_dispatch import (
                                            try_oob_dispatch as _try_oob,
                                        )
                                        _try_oob(
                                            _custs,
                                            reason=f"task_busy_qd={_qd_for_oob}",
                                            browser_event_items=_items,
                                        )
                                    except Exception as _oob_err:
                                        logger.debug(
                                            f"[mt052D] OOB invocation from runner "
                                            f"failed (non-fatal): {_oob_err}"
                                        )
                except Exception:
                    pass

                # Check cancellation via cancellation_registry
                from agent.ec_tasks import cancellation_registry
                cancel_evt = cancellation_registry.get(current_task.id)
                if cancel_evt and cancel_evt.is_set():
                    logger.info(f"[WORKER] Cancellation event set for task {current_task.id}, forcing task exit")
                    current_task.status.state = TaskState.canceled
                    # Clear future reference to allow task restart
                    if hasattr(current_task, 'future'):
                        current_task.future = None
                    return None, None, False
                
                if self._stop_event.wait(timeout=0.5):
                    return None, None, False
                return current_task, None, False
            if _allow_parked_live_chat_response:
                try:
                    logger.warning(
                        f"[QUEUE-TRACE] allowing live-chat response dequeue for "
                        f"input_required task despite future_running=True: "
                        f"task={current_task.name}"
                    )
                except Exception:
                    pass
            try:
                timeout = DEV_EVENT_POLL_INTERVAL_SEC if has_dev else 0.5
                msg = _priority_dequeue(current_task.queue, timeout=timeout)

                # Tag the message with trigger source
                if isinstance(msg, dict):
                    msg["__trigger_source__"] = "message"

                try:
                    _log_live_chat_runner_stage(
                        "runner_queue_dequeued",
                        msg,
                        task=current_task,
                        trigger_type="message",
                        remaining_queue_depth=current_task.queue.qsize(),
                    )
                except Exception:
                    pass
                return current_task, msg, True

            except Empty:
                # Check timeout for pending tasks
                primary_trigger = "dev" if has_dev else "message" if has_message else triggers[0]
                self._check_pending_timeout(current_task, primary_trigger)
                
                # For schedule-only: already checked above, return None
                # For multi-trigger with schedule: no queue msg, no schedule ready
                return current_task, None, False
        
        # Schedule-only or auto-only path: already checked above, nothing ready
        if has_schedule or has_auto:
            return None, None, False
        
        return None, None, False
    
    def _check_pending_timeout(self, task: ManagedTask, trigger_type: str):
        """Check if a pending task has timed out.

        Timeout is taken from state['_runtime_event_timeout'] if set (allows per-task
        override), otherwise falls back to the global DEFAULT_RUNTIME_EVENT_TIMEOUT_SEC.
        """
        try:
            state = self._task_states.get(task.id, {})
            pending_since = state.get('pending_since')

            if not pending_since:
                return

            elapsed = time.time() - pending_since

            if trigger_type == "dev":
                if elapsed > DEV_EVENT_TIMEOUT_SEC:
                    from gui.ipc.api import IPCAPI
                    ipc = IPCAPI.get_instance()
                    msg = f"[DEV] Timeout after {DEV_EVENT_TIMEOUT_SEC}s waiting for resume event"
                    logger.error(msg)
                    ipc.send_skill_editor_log("error", msg)
                    logger.error("[FAIL_REASON] reason=timeout scope=dev_resume_wait")
                    task.status.state = TaskState.failed
                    state['last_response'] = {"success": False, "error": "TimeoutWaitingForEvent"}
                    state['pending_since'] = None  # Clear so timeout only fires once
                    self._emit_task_status(task, "failed")
                    self._dev_exit_requested = True
            else:
                # Per-task override from state (set by skill config / env), else global default
                timeout_sec = float(state.get("_runtime_event_timeout", DEFAULT_RUNTIME_EVENT_TIMEOUT_SEC))
                if elapsed > timeout_sec:
                    logger.error(f"[RUN] Timeout after {timeout_sec}s (task={task.name})")
                    logger.error("[FAIL_REASON] reason=timeout scope=runtime_event_wait")
                    task.status.state = TaskState.failed
                    state['justStarted'] = True
                    state['pending_since'] = None
                    state['last_response'] = {"success": False, "error": "TimeoutWaitingForEvent"}
                    self._emit_task_status(task, "failed")
                    
                    # DEBUG: Log which node is causing the timeout
                    _current_node = state.get("current_node", "unknown")
                    _waiting_for = state.get("waiting_for_event", "unknown")
                    logger.error(f"[RUN][DEBUG] Pend event timeout: current_node={_current_node}, waiting_for={_waiting_for}")

        except Exception:
            pass
    
    def _validate_task_for_execution(self, task: ManagedTask) -> bool:
        """Validate a task is ready for execution.
        
        A task's cloud run characteristics are determined by its associated skill.
        A task without a skill cannot be scheduled or launched.
        """
        logger.info(f"[VALIDATE] Task: {task.id}, name: {task.name}")
        
        # Skip hybrid cloud tasks that already have an active cloud run
        # (subscriptions are live, waiting for cloud completion)
        if task.state.get("cloud_run_active"):
            logger.debug(f"[VALIDATE] Task '{task.name}' has active cloud run (run_id={task.state.get('cloud_run_id', '?')}), skipping re-execution")
            return False
        
        # Stop tasks that have hit max consecutive failures
        if hasattr(task, 'is_max_failures_reached') and task.is_max_failures_reached():
            logger.warning(f"[VALIDATE] Task '{task.name}' reached max failures ({task.consecutive_failures}), skipping")
            return False
        
        if task.skill is None:
            logger.error(f"[SKILL_MISSING] Task '{task.name}' (id={task.id}) has no skill attached — cannot determine execution mode. Skipping.")
            raise ValueError(f"Task '{task.name}' has no skill attached and cannot be scheduled or launched.")
        
        # Pure cloud tasks don't need a local runnable
        if self._is_pure_cloud_task(task) or self._is_hybrid_cloud_task(task):
            return True
        
        # Local tasks require a runnable
        if not hasattr(task.skill, 'runnable') or task.skill.runnable is None:
            skill = task.skill
            logger.error(
                f"[SKILL_MISSING] Task '{task.name}' (id={task.id}) skill has runnable=None!\n"
                f"  skill type: {type(skill).__name__}\n"
                f"  skill name: {getattr(skill, 'name', 'N/A')}\n"
                f"  skill id: {getattr(skill, 'id', 'N/A')}\n"
                f"  skill source: {getattr(skill, 'source', 'N/A')}\n"
                f"  skill is str: {isinstance(skill, str)}\n"
                f"  agent: {self.agent.card.name if self.agent and self.agent.card else 'N/A'}\n"
                f"  agent tasks count: {len(self.agent.tasks) if self.agent and self.agent.tasks else 0}\n"
                f"  agent skills count: {len(self.agent.skills) if self.agent and self.agent.skills else 0}\n"
                f"  mainwin.agent_skills count: {len(getattr(self.agent.mainwin, 'agent_skills', []) or []) if self.agent and self.agent.mainwin else 'N/A'}"
            )
            return False
        
        return True
    
    def _submit_task_execution(
        self,
        task: ManagedTask,
        msg: Any,
        trigger_type: str,
        dev_init_state: Optional[dict]
    ):
        """Submit task execution to thread pool."""
        # Generate a unique invocation ID for tracing this call
        import threading
        import time as time_module
        _call_id = f"{threading.current_thread().name}_{int(time_module.time()*1000)%100000}"

        # Extract waiter task ID
        waiter_task_id = self._extract_waiter_task_id(msg)
        
        # First log: function entry
        _entry_state = task.status.state
        logger.info(f"[SUBMIT][{_call_id}] ENTER _submit_task_execution for '{task.name}', state={_entry_state!r}")
        # [QUEUE-TRACE] What msg are we about to submit? If this is None it means a
        # schedule/auto kickoff; if it is a dict it is the popped queue item.
        try:
            if msg is None:
                logger.info(f"[QUEUE-TRACE] SUBMIT entry msg=None task={task.name} trigger={trigger_type}")
            else:
                logger.info(
                    f"[QUEUE-TRACE] SUBMIT entry task={task.name} trigger={trigger_type} "
                    f"msg={_describe_queue_msg(msg)}"
                )
        except Exception:
            pass
        
        # ── Interrupt guard: do NOT re-submit a task that is parked waiting for human input ──
        # When a skill hits a pend_event / __interrupt__, it is parked and emits status="paused".
        # The execution thread completes and the queue poll loop continues running.
        # Without this guard, the next queue poll returns (task, None, False) which re-triggers
        # _submit_task_execution, causing an infinite re-execution loop:
        # skill runs → LLM fails → interrupt → re-submit → repeat.
        #
        # Check: if task.state == input_required, it means the previous execution parked on
        # an interrupt. Do NOT re-run unless there's actual new input from the user.
        _task_state = task.status.state
        _is_input_required = _task_state == TaskState.input_required
        _is_working = _task_state == TaskState.working
        logger.info(
            f"[SUBMIT][{_call_id}] Guard check for '{task.name}': "
            f"state={_task_state!r}, is_input_required={_is_input_required}, is_working={_is_working}"
        )
        # Allow through if the message carries actual event data (browser_event,
        # chat_message, etc.) — these should resume the interrupted pend_event.
        _has_real_message = (
            isinstance(msg, dict)
            and msg.get("__trigger_source__") == "message"
            and not msg.get("__auto_kickoff__")
        )
        # Pair the dequeue-side `_allow_parked_live_chat_response` bypass: when a
        # Q&A reply payload arrives for an input_required task whose previous
        # execution future is still finalising, we must NOT re-queue it — the
        # dequeue side will immediately pop it again, the submit side will
        # re-queue it again, and the reply bounces in this tight loop until
        # the future actually clears (visible as the `runner_submit_future_busy_requeued`
        # ledger spam in the 2026-05-14 customer log). Letting Q&A responses
        # through here is the same trade-off the pre-merge code made (and
        # the dequeue side still makes): one extra execution can race with
        # the finalising future, but for Q&A replies the LangGraph state is
        # already at the pend_event interrupt and the resume just types the
        # message, which doesn't mutate skill state in a way that conflicts.
        _is_live_chat_response_resume = (
            _is_input_required
            and _has_real_message
            and bool(_live_chat_response_payload_from_queue_msg(msg))
        )
        try:
            _log_live_chat_runner_stage(
                "runner_submit_enter",
                msg,
                task=task,
                call_id=_call_id,
                trigger_type=trigger_type,
                has_real_message=bool(_has_real_message),
                future_running=_task_execution_future_running(task),
                queue_depth=task.queue.qsize() if getattr(task, "queue", None) is not None else 0,
            )
        except Exception:
            pass

        if _is_live_chat_shutdown_active() and trigger_type == "message":
            _shutdown_payload = _live_chat_payload_from_queue_msg(msg)
            if _shutdown_payload:
                _shutdown_response_payload = _live_chat_response_payload_from_queue_msg(msg)
                if _shutdown_response_payload and _is_live_chat_shutdown_drain_finalized():
                    _log_live_chat_delivery_aborted_shutdown(
                        _shutdown_response_payload,
                        reason="queued_response_after_shutdown_drain",
                        target_task=task.name,
                        task_id=getattr(task, "id", ""),
                    )
                    logger.warning(
                        f"[LIVE-CHAT-SHUTDOWN] aborting queued response after "
                        f"drain finalized task={task.name}"
                    )
                    return
                if not _shutdown_response_payload:
                    _log_live_chat_delivery_aborted_shutdown(
                        _shutdown_payload,
                        reason="live_chat_task_submit_suppressed_during_shutdown",
                        target_task=task.name,
                        task_id=getattr(task, "id", ""),
                    )
                    logger.warning(
                        f"[LIVE-CHAT-SHUTDOWN] aborting queued live-chat Q&A work "
                        f"during shutdown task={task.name}"
                    )
                    return

        # TaskState can briefly read input_required while the previous
        # resume/LLM execution future is still active. Under message floods that
        # allowed multiple SkillExec futures for the same Q&A task to mutate the
        # same LangGraph checkpoint/state concurrently, so a dequeued customer
        # turn could be overwritten before reaching the LLM node. Treat the
        # execution Future as the source of truth for per-task serialization.
        if _task_execution_future_running(task):
            if _is_live_chat_response_resume:
                # Don't re-queue / don't block — let the resume proceed.
                # See _is_live_chat_response_resume comment above for the rationale.
                logger.warning(
                    f"[SUBMIT][{_call_id}] Allowing live-chat response resume for "
                    f"'{task.name}' while previous future still reports running "
                    f"because task is input_required"
                )
                try:
                    _log_live_chat_runner_stage(
                        "runner_submit_future_running_input_required_resume",
                        msg,
                        task=task,
                        call_id=_call_id,
                        trigger_type=trigger_type,
                        queue_depth=task.queue.qsize() if getattr(task, "queue", None) is not None else 0,
                    )
                except Exception:
                    pass
                # Fall through to the rest of the guard ladder (live-chat resumes
                # land on the `_is_input_required and _has_real_message` path
                # at the bottom, which logs "Guard bypassed" and submits).
            elif _has_real_message:
                try:
                    task.queue.put_nowait(msg)
                    logger.info(
                        f"[SUBMIT][{_call_id}] Re-queued message for '{task.name}' "
                        f"because prior execution future is still running; "
                        f"queue={_snapshot_queue(task.queue, limit=10)}"
                    )
                    _log_live_chat_runner_stage(
                        "runner_submit_future_busy_requeued",
                        msg,
                        task=task,
                        call_id=_call_id,
                        trigger_type=trigger_type,
                        queue_depth=task.queue.qsize(),
                    )
                except Exception as _requeue_err:
                    logger.error(
                        f"[SUBMIT][{_call_id}] Failed to re-queue message for "
                        f"'{task.name}' while prior execution future is running: {_requeue_err}"
                    )
                return
            else:
                logger.info(
                    f"[SUBMIT][{_call_id}] Blocking '{task.name}' because prior "
                    f"execution future is still running"
                )
                return
        
        # Block re-submission while already working. A second concurrent execution
        # shares the cached browser-use agent object and other module-level state,
        # causing unpredictable interference. The event is already in task.queue
        # and will be picked up on the next pend_event cycle.
        if _is_working and not _has_real_message:
            # [QUEUE-TRACE] This path DROPS the popped msg on the floor (no re-queue).
            # If msg has event data but was not classified as a "real message"
            # (e.g. A2A Pydantic model without __trigger_source__ tag), this is a
            # silent chat-message drop point.
            try:
                _msg_kind = type(msg).__name__ if msg is not None else "None"
                _tgsrc = msg.get("__trigger_source__", "") if isinstance(msg, dict) else getattr(msg, "__trigger_source__", "")
                _auto = msg.get("__auto_kickoff__", False) if isinstance(msg, dict) else getattr(msg, "__auto_kickoff__", False)
                logger.warning(
                    f"[QUEUE-TRACE] DROP at SUBMIT guard: task={task.name} msg_kind={_msg_kind} "
                    f"trigger_source={_tgsrc!r} auto_kickoff={_auto!r} "
                    f"described={_describe_queue_msg(msg) if msg is not None else '(None)'}"
                )
            except Exception:
                pass
            logger.warning(
                f"[SUBMIT][{_call_id}] ⛔ GUARD TRIGGERED — blocking '{task.name}' with state={_task_state!r} "
                f"(already working, event will be processed in next cycle)"
            )
            return
        if _is_working and _has_real_message:
            logger.info(
                f"[SUBMIT][{_call_id}] Guard: task '{task.name}' is working but received real message — "
                f"re-queueing for next pend_event cycle"
            )
            # Don't start a second execution — but the message was already consumed
            # from task.queue by _get_next_work_item(), so we must put it back.
            # Otherwise it is silently dropped and the next pend_event cycle never
            # sees it, leaving the customer without a reply.
            try:
                task.queue.put_nowait(msg)
                logger.info(f"[SUBMIT][{_call_id}] Re-queued message for '{task.name}'")
                _log_live_chat_runner_stage(
                    "runner_submit_state_working_requeued",
                    msg,
                    task=task,
                    call_id=_call_id,
                    trigger_type=trigger_type,
                    queue_depth=task.queue.qsize(),
                )
            except Exception as _requeue_err:
                logger.error(f"[SUBMIT][{_call_id}] Failed to re-queue message for '{task.name}': {_requeue_err}")
            return
        if _is_input_required and not _has_real_message:
            logger.warning(
                f"[SUBMIT][{_call_id}] ⛔ GUARD TRIGGERED — blocking '{task.name}' with state={_task_state!r}"
            )
            try:
                self._emit_task_status(task, "paused")
                logger.warning(f"[SUBMIT][{_call_id}] ⛔ RETURNING early for '{task.name}' — skill is parked, waiting for human input")
            except Exception as e:
                logger.error(f"[SUBMIT][{_call_id}] Error in guard emit/return for '{task.name}': {e}")
            return
        if _is_input_required and _has_real_message:
            logger.info(
                f"[SUBMIT][{_call_id}] Guard bypassed for '{task.name}' — "
                f"real message arrived while parked on interrupt, will resume"
            )

        # Initialize task state
        logger.info(f"[SUBMIT][{_call_id}] Guard passed for '{task.name}', proceeding to submit...")

        # Initialize task state — both ``setdefault`` calls are atomic at
        # the C-level so they tolerate concurrent mutation from
        # ``_execute_skill`` (line 3994 ``setdefault(task.id, {})``) and
        # ``_on_skill_complete`` (line 4389 ``setdefault`` + line 4434
        # ``pop``).  The previous ``check-then-read`` form had a TOCTOU
        # window that crashed with ``KeyError: 'justStarted'`` when a
        # parallel ``SkillExec`` thread popped/recreated the entry
        # between our ``not in`` check and our ``['justStarted']`` read.
        # Liveness incident 2026-04-28 14:29:47: cejs's QA reply
        # ``chat_message`` was silently dropped this way and the
        # customer's "五一有新品吗？" went unanswered for ~13 minutes.
        # Default ``True`` matches the prior fresh-init semantic at
        # line 3054 — a missing ``justStarted`` key means no run has
        # been recorded yet, so treat as initial.
        state_entry = self._task_states.setdefault(task.id, {})
        is_initial_run = state_entry.setdefault('justStarted', True)
        if _is_input_required and _has_real_message:
            is_initial_run = False
            state_entry['justStarted'] = False
        
        # Determine cloud execution mode
        is_hybrid = self._is_hybrid_cloud_task(task)
        is_pure_cloud = self._is_pure_cloud_task(task)

        # ── Paid-skill guard: non-free, non-owned skills MUST run in cloud ──
        # This prevents local exposure of prompt IP for paid/rented skills.
        if not is_hybrid and not is_pure_cloud and task.skill is not None:
            _price = 0
            try:
                _price = int(getattr(task.skill, 'price', 0) or 0)
            except (TypeError, ValueError):
                pass
            if _price > 0:
                _skill_owner = (getattr(task.skill, 'skill_owner', '') or getattr(task.skill, 'owner', '') or '').strip().lower()
                _current_user = ''
                try:
                    _current_user = (self.agent.mainwin.user or '').strip().lower()
                except Exception:
                    pass
                if _skill_owner and _current_user and _skill_owner != _current_user:
                    logger.warning(
                        f"[SUBMIT] Paid skill '{getattr(task.skill, 'name', '?')}' (price={_price}) "
                        f"not owned by runner — forcing hybrid cloud execution to protect prompt IP"
                    )
                    is_hybrid = True

        # Pure cloud + schedule: cloud scheduler handles it, nothing to do locally
        if is_pure_cloud and trigger_type == "schedule":
            logger.info(f"[SUBMIT] Pure cloud task '{task.name}' with schedule trigger — cloud scheduler handles, skipping local execution")
            return
        
        # Hybrid cloud tasks must only be launched on-demand (via message/MCP tool call),
        # never by the local schedule loop.  The cloud side owns scheduling.
        if is_hybrid and trigger_type == "schedule":
            logger.debug(f"[SUBMIT] Hybrid cloud task '{task.name}' ignoring schedule trigger — only runs on explicit message")
            return
        
        # Amend global event routing with entries from this task's skill
        try:
            self._amend_event_routing_for_task(task)
        except Exception as e:
            logger.warning(f"[SUBMIT] Failed to amend event routing for task={task.name}: {e}")
        
        # ── Queue depth guard: reject if too many tasks are already queued ─────────
        # Instead of a blocking semaphore (which would stall the main thread), we
        # count pending futures to approximate queue depth.
        try:
            # Count futures not yet completed (pending + running)
            _queued = sum(
                1 for t_id, state in self._task_states.items()
                if not state.get("_done", False)
            )
            _max_queued = int(os.environ.get("ECAN_SKILL_MAX_QUEUED", "40"))
            if _queued > _max_queued:
                logger.warning(
                    f"[SUBMIT] Task queue at {_queued}/{_max_queued} — "
                    f"rejecting task '{task.name}' to prevent memory exhaustion"
                )
                self._emit_task_status(task, "error")
                return
        except Exception:
            pass

        def _execute():
            _exec_start = time_module.time()
            # ws118: cap concurrent QA-turn executions (exclude the persistent
            # front-desk monitor — it must keep detecting). Acquire BEFORE the
            # LLM/tool work; released in the finally below.
            _ws118_sem = None
            _ws118_held = False
            try:
                _nm = (getattr(task, "name", "") or "")
                _is_monitor = any(k in _nm for k in ("监测", "monitor", "前台", "front"))
                if _ws118_qa_cap() > 0 and not _is_monitor and self._is_chatter_task(task):
                    _ws118_sem = _ws118_get_qa_semaphore()
                    if _ws118_sem is not None:
                        try:
                            _ws118_wait = float((_live_chat_env("ECAN_LIVE_CHAT_QA_CAP_WAIT_S") or "30") or 30)
                        except (TypeError, ValueError):
                            _ws118_wait = 30.0
                        _ws118_held = _ws118_sem.acquire(timeout=_ws118_wait)
                        if not _ws118_held:
                            logger.warning(
                                f"[ws118] QA concurrency cap wait timed out for "
                                f"'{task.name}' — proceeding (soft cap)")
            except Exception:
                _ws118_held = False
            try:
                _log_live_chat_runner_stage(
                    "runner_execution_start",
                    msg,
                    task=task,
                    call_id=_call_id,
                    trigger_type=trigger_type,
                    is_initial_run=bool(is_initial_run),
                    mode="hybrid" if is_hybrid else ("pure_cloud" if is_pure_cloud else "local"),
                )
            except Exception:
                pass
            try:
                if is_hybrid:
                    return self._execute_hybrid_cloud_task(task, msg, trigger_type, is_initial_run, dev_init_state)
                if is_pure_cloud:
                    return self._execute_pure_cloud_task(task, trigger_type)
                return self._execute_skill(task, msg, trigger_type, is_initial_run, dev_init_state)
            except Exception as _exec_err:
                _log_live_chat_runner_stage(
                    "runner_execution_exception",
                    msg,
                    task=task,
                    level=logging.ERROR,
                    call_id=_call_id,
                    trigger_type=trigger_type,
                    error=str(_exec_err),
                )
                raise
            finally:
                # ws118: release the QA concurrency slot ASAP so the next turn runs.
                if _ws118_held and _ws118_sem is not None:
                    try:
                        _ws118_sem.release()
                    except Exception:
                        pass
                try:
                    _log_live_chat_runner_stage(
                        "runner_execution_finish",
                        msg,
                        task=task,
                        call_id=_call_id,
                        trigger_type=trigger_type,
                        duration_ms=int((time_module.time() - _exec_start) * 1000),
                    )
                except Exception:
                    pass
                # Mark task done in state tracker
                if task.id in self._task_states:
                    self._task_states[task.id]["_done"] = True

        def _on_complete(future):
            try:
                _future_exc = future.exception()
            except Exception:
                _future_exc = None
            _log_live_chat_runner_stage(
                "runner_future_callback",
                msg,
                task=task,
                call_id=_call_id,
                trigger_type=trigger_type,
                future_done=True,
                future_exception=str(_future_exc) if _future_exc else "",
            )
            try:
                self._on_skill_complete(future, task, waiter_task_id, trigger_type)
            except Exception as e:
                # CRITICAL: Catch all exceptions in completion handler to prevent:
                # 1. Task state remaining as 'working' forever
                # 2. Future not being cleaned up (causing stale future issues)
                # 3. Task being stuck in queue
                logger.error(
                    f"[ON_COMPLETE] _on_skill_complete failed for task={task.name}: {e}. "
                    f"Forcing task state update to 'failed'."
                )
                try:
                    task.status.state = TaskState.failed
                    task.status.message = _create_message("agent", f"Task execution failed: {e}")
                except Exception:
                    pass
                self._emit_task_status(task, "failed")
                # Clear the future reference to allow task to be restarted
                task.future = None
                if task.id in self._task_states:
                    self._task_states[task.id]["_done"] = True
        
        # Prevent idle sleep while task is running
        try:
            get_sleep_inhibitor().acquire()
        except Exception:
            pass
        
        # NOTE: pending_since is NOT cleared here. It was previously cleared at submit
        # time, which caused an infinite loop: after pend_event interrupted and
        # _on_skill_complete set pending_since, the next queue poll + submit would
        # immediately clear it again → timeout never fires, skill re-runs forever.
        #
        # Clearing is now done INSIDE _execute_skill (below), ONLY when this is
        # a genuine fresh initial run (is_initial_run=True), not a resume.
        _submit_lock = getattr(self, "_task_execution_lock", None)
        if _submit_lock is None:
            _submit_lock = threading.RLock()
            try:
                self._task_execution_lock = _submit_lock
            except Exception:
                pass

        with _submit_lock:
            if _task_execution_future_running(task):
                if _has_real_message:
                    try:
                        task.queue.put_nowait(msg)
                        logger.info(
                            f"[SUBMIT][{_call_id}] Re-queued message for '{task.name}' "
                            f"at submit lock because prior execution future is still running; "
                            f"queue={_snapshot_queue(task.queue, limit=10)}"
                        )
                        _log_live_chat_runner_stage(
                            "runner_submit_future_busy_requeued",
                            msg,
                            task=task,
                            call_id=_call_id,
                            trigger_type=trigger_type,
                            queue_depth=task.queue.qsize(),
                            submit_lock=True,
                        )
                    except Exception as _requeue_err:
                        logger.error(
                            f"[SUBMIT][{_call_id}] Failed to re-queue message for "
                            f"'{task.name}' at submit lock: {_requeue_err}"
                        )
                    return
                logger.info(
                    f"[SUBMIT][{_call_id}] Blocking '{task.name}' at submit lock "
                    f"because prior execution future is still running"
                )
                return

            # Executor threads don't inherit ContextVars — carry the run scope over.
            future = self._skill_executor.submit(_wrap_log_context(_execute))

            # CRITICAL: Save Future reference to task so cancel() can work, and
            # so the queue loop can serialize subsequent messages for this task.
            task.future = future
            logger.debug(f"[SUBMIT] Saved Future reference to task {task.name} for cancellation support")

            # Mark task as running (in-memory + IPC to frontend)
            try:
                task.status.state = TaskState.working
            except Exception:
                pass
            _log_live_chat_runner_stage(
                "runner_submit_accepted",
                msg,
                task=task,
                call_id=_call_id,
                trigger_type=trigger_type,
                future_id=id(future),
                is_initial_run=bool(is_initial_run),
                mode="hybrid" if is_hybrid else ("pure_cloud" if is_pure_cloud else "local"),
            )
            future.add_done_callback(_on_complete)
        self._emit_task_status(task, "running")

        task_mode = "hybrid" if is_hybrid else ("pure_cloud" if is_pure_cloud else "local")
        logger.info(f"[SUBMIT] Skill execution submitted for task={task.name} (mode={task_mode})")
    
    def _emit_task_status(self, task: ManagedTask, status: str):
        """Emit task-level status update to GUI via IPC.
        
        This notifies the frontend (e.g. AgentCard task popover) about
        task status changes such as 'running', 'completed', 'failed'.
        """
        try:
            from gui.ipc.api import IPCAPI
            ipc = IPCAPI.get_instance()
            ipc.update_run_stat(
                agent_task_id=task.run_id or task.id,
                current_node="",
                status=status,
                langgraph_state={
                    "task_id": task.id,
                    "task_name": getattr(task, "name", ""),
                    "task_status": status,
                },
                timestamp=int(time.time() * 1000),
            )
        except Exception as e:
            logger.debug(f"[TaskStatus] Failed to emit task status '{status}' for {getattr(task, 'name', '?')}: {e}")

    def _set_task_failed_state(self, task: ManagedTask, err_text: str):
        """Set task to failed state - centralized helper for consistent failure handling.

        This method handles all the boilerplate for marking a task as failed:
        1. Set task.status.state to TaskState.failed
        2. Set task.status.message with error text
        3. Emit 'failed' status to GUI
        4. Record failure for consecutive-failure tracking
        5. Handle schedule/message trigger-specific logic
        """
        try:
            task.status.state = TaskState.failed
            task.status.message = _create_message("agent", err_text)
        except Exception as e:
            logger.warning(f"[TaskFailed] Failed to set task status: {e}")
        self._emit_task_status(task, "failed")

        # Track consecutive failures on the task
        if hasattr(task, 'record_failure'):
            fail_count = task.record_failure()
            if hasattr(task, 'is_max_failures_reached') and task.is_max_failures_reached():
                logger.error(f"[TaskFailed] Task '{getattr(task, 'name', '?')}' reached max failures ({fail_count})")

    def _is_hybrid_cloud_task(self, task: ManagedTask) -> bool:
        """Check if a task uses a hybrid cloud skill."""
        skill = task.skill
        if skill is None:
            return False
        run_in_cloud = getattr(skill, 'run_in_cloud', False)
        hybrid_mode = getattr(skill, 'hybrid_cloud_mode', False)
        return bool(run_in_cloud and hybrid_mode)
    
    def _is_pure_cloud_task(self, task: ManagedTask) -> bool:
        """Check if a task is a pure cloud task (run_in_cloud but NOT hybrid)."""
        skill = task.skill
        if skill is None:
            return False
        run_in_cloud = getattr(skill, 'run_in_cloud', False)
        hybrid_mode = getattr(skill, 'hybrid_cloud_mode', False)
        return bool(run_in_cloud and not hybrid_mode)
    
    def _execute_pure_cloud_task(
        self,
        task: ManagedTask,
        trigger_type: str,
    ) -> Tuple[Optional[dict], bool]:
        """
        Execute a pure cloud task on-demand by calling runCloudTasks.
        
        For scheduled pure cloud tasks the cloud scheduler handles execution
        directly — this method is only called for on-demand triggers
        (message, interaction, etc.).
        """
        import requests
        import socket

        skill_name = getattr(task.skill, 'name', 'unknown') if task.skill else 'unknown'
        logger.info(f"[PureCloud] Launching cloud task on-demand: task={task.name}, skill={skill_name}, trigger={trigger_type}")

        try:
            from app_context import AppContext
            from agent.cloud_api.cloud_api import get_appsync_endpoint

            login = AppContext.get_login()
            tokens = login.auth_manager.get_tokens()
            token = tokens.get('access_token')
            if not token:
                logger.error("[PureCloud] No access token available")
                return {"success": False, "error": "No access token"}, True
            endpoint = get_appsync_endpoint()
            host_name = socket.gethostname()
        except Exception as e:
            logger.error(f"[PureCloud] Failed to get auth credentials: {e}")
            return {"success": False, "error": f"Auth error: {e}"}, True

        try:
            from agent.cloud_api.cloud_api import run_cloud_tasks

            session = requests.Session()
            client_id = self._get_client_id()
            result = run_cloud_tasks(session, token, [task.id], endpoint=endpoint,
                                     options={"host_name": host_name, "passive_client_id": client_id})

            if not result.get("success"):
                error_msg = result.get("error", "runCloudTasks failed")
                logger.error(f"[PureCloud] runCloudTasks failed: {error_msg}")
                return {"success": False, "error": error_msg}, True

            run_ids = result.get("run_ids", {})
            cloud_run_id = run_ids.get(task.id) or next(iter(run_ids.values()), None)
            logger.info(f"[PureCloud] Cloud task launched: run_id={cloud_run_id}")

            # Start onTaskStatus subscription for this cloud run
            if cloud_run_id:
                try:
                    self._start_task_status_subscription(task, cloud_run_id)
                except Exception as e:
                    logger.warning(f"[TaskStatus] Could not start subscription for pure cloud task={task.name}: {e}")

            task.state["cloud_run_id"] = cloud_run_id
            return {"success": True, "cloud_run_id": cloud_run_id}, True
        except Exception as e:
            logger.error(f"[PureCloud] Error calling runCloudTasks: {e}")
            logger.error(traceback.format_exc())
            return {"success": False, "error": f"runCloudTasks error: {e}"}, True
    
    def _execute_hybrid_cloud_task(
        self,
        task: ManagedTask,
        msg: Any,
        trigger_type: str,
        is_initial_run: bool,
        dev_init_state: Optional[dict]
    ) -> Tuple[Optional[dict], bool]:
        """
        Execute a hybrid cloud task:
        1. Poll queryCloudTaskRunId until the cloud task's runID is available
        2. Start onPassiveCommand WebSocket subscription with matching runID/clientID
        3. Execute the local helper skill (langgraph-based workflow)
        
        The cloud task and local helper are scheduled to run at the same time,
        but the local side waits for the cloud task to start first.
        """
        import socket
        import requests

        skill = task.skill
        skill_name = getattr(skill, 'name', 'unknown')
        logger.info(f"[HybridCloud] Starting hybrid cloud execution for task={task.name}, skill={skill_name}")

        # Get auth credentials
        try:
            from app_context import AppContext
            from agent.cloud_api.cloud_api import get_appsync_endpoint

            login = AppContext.get_login()
            tokens = login.auth_manager.get_tokens()
            token = tokens.get('access_token')
            if not token:
                logger.error("[HybridCloud] No access token available")
                return {"success": False, "error": "No access token"}, True
            endpoint = get_appsync_endpoint()
            username = login.auth_manager.current_user if login.auth_manager else "unknown"
            host_name = socket.gethostname()
        except Exception as e:
            logger.error(f"[HybridCloud] Failed to get auth credentials: {e}")
            return {"success": False, "error": f"Auth error: {e}"}, True

        # Step 1: Obtain cloud task's runID
        # Always try runCloudTasks first — it usually returns the runID directly.
        # Fall back to queryCloudTaskRunId polling only for scheduled triggers
        # where runCloudTasks didn't return a runID.
        session = requests.Session()
        cloud_run_id = None
        client_id = self._get_client_id()

        cloud_helper_skill_name = None  # may be set from runCloudTasks response

        logger.info(f"[HybridCloud] Step 1: Launching cloud task via runCloudTasks (task_id={task.id}, trigger={trigger_type})")
        try:
            from agent.cloud_api.cloud_api import run_cloud_tasks

            result = run_cloud_tasks(session, token, [task.id], endpoint=endpoint,
                                     options={"host_name": host_name, "passive_client_id": client_id})

            if result.get("success"):
                run_ids = result.get("run_ids", {})
                cloud_run_id = run_ids.get(task.id)
                if not cloud_run_id:
                    cloud_run_id = next(iter(run_ids.values()), None)

                # Extract local_helper_skill_name from response extras
                extras = result.get("extras", {})
                task_extras = extras.get(task.id) or extras.get("_default") or {}
                cloud_helper_skill_name = task_extras.get("local_helper_skill_name")
                if cloud_helper_skill_name:
                    logger.info(f"[HybridCloud] Cloud returned local_helper_skill_name: {cloud_helper_skill_name}")

            if cloud_run_id:
                logger.info(f"[HybridCloud] Got cloud runID from runCloudTasks: {cloud_run_id}")
            else:
                logger.warning(f"[HybridCloud] runCloudTasks did not return a runID: {result.get('error', result)}")
        except Exception as e:
            logger.warning(f"[HybridCloud] runCloudTasks call failed (will try polling): {e}")

        # Fall back to polling for scheduled triggers if runCloudTasks didn't yield a runID
        if not cloud_run_id and trigger_type == "schedule":
            logger.info(f"[HybridCloud] Step 1b: Falling back to polling for cloud runID (task_id={task.id}, host={host_name})")
            try:
                from agent.cloud_api.cloud_api import query_cloud_task_run_id_with_retry

                run_id_result = query_cloud_task_run_id_with_retry(
                    session, token, task.id, host_name,
                    meta_data={"owner": username},
                    endpoint=endpoint,
                    max_wait_seconds=120,
                    poll_interval=5,
                )

                if run_id_result.get("success"):
                    cloud_run_id = run_id_result["run_id"]
                    logger.info(f"[HybridCloud] Got cloud runID via polling: {cloud_run_id}")
                else:
                    error_msg = run_id_result.get("error", "Failed to get cloud runID")
                    logger.error(f"[HybridCloud] Failed to get cloud runID: {error_msg}")
                    return {"success": False, "error": error_msg}, True
            except Exception as e:
                logger.error(f"[HybridCloud] Error polling for cloud runID: {e}")
                logger.error(traceback.format_exc())
                return {"success": False, "error": f"RunID poll error: {e}"}, True

        if not cloud_run_id:
            logger.error(f"[HybridCloud] Could not obtain cloud runID for task {task.id}")
            return {"success": False, "error": "No cloud runID obtained"}, True

        # Step 2a: Start onTaskStatus subscription for this cloud run
        try:
            self._start_task_status_subscription(task, cloud_run_id)
        except Exception as e:
            logger.warning(f"[TaskStatus] Could not start subscription for hybrid task={task.name}: {e}")

        # Step 2b: Start passive command subscription
        client_id = self._get_client_id()
        logger.info(f"[HybridCloud] Step 2: Starting passive command subscription (run_id={cloud_run_id}, client_id={client_id})")
        try:
            self._start_hybrid_passive_subscription(token, endpoint, cloud_run_id, client_id)
            logger.info(f"[HybridCloud] Passive subscription started successfully")
        except Exception as e:
            logger.warning(f"[HybridCloud] Failed to start passive subscription (continuing anyway): {e}")

        # Step 3: Store cloud run_id on task for the helper skill to use
        task.state["cloud_run_id"] = cloud_run_id
        task.state["is_hybrid_cloud"] = True
        task.state["client_id"] = client_id

        # Step 4: Register run_id in event-task routing so incoming passive commands
        # can be routed to the correct task
        try:
            self._global_event_routing[f"passive_command_{cloud_run_id}"] = {
                "routing_key": "data.run_id",
                "task_selector": f"id:{task.id}",
            }
            logger.info(f"[HybridCloud] Step 4: Registered event routing for run_id={cloud_run_id} → task={task.name}")
        except Exception as e:
            logger.warning(f"[HybridCloud] Failed to register event routing: {e}")

        # Step 5: Find or create companion local task for passive command execution.
        # Resolution order:
        #   1. local_helper_skill_name from runCloudTasks response
        #   2. skill.local_helper_skill_id attribute on the cloud skill object
        #   3. Fallback: first local skill whose name contains "passive"
        companion_task = None
        helper_skill_key = cloud_helper_skill_name  # from runCloudTasks response (may be None)

        if not helper_skill_key:
            helper_skill_key = getattr(skill, 'local_helper_skill_id', None)
            if helper_skill_key:
                logger.info(f"[HybridCloud] Using skill.local_helper_skill_id: {helper_skill_key}")

        if not helper_skill_key:
            # Fallback: find any skill with "passive" in its name (agent skills + global pool)
            all_skills = list(getattr(self.agent, "skills", []) or [])
            try:
                from app_context import AppContext
                main_win = AppContext.get_main_window()
                if main_win:
                    for gsk in (getattr(main_win, "agent_skills", []) or []):
                        if gsk not in all_skills:
                            all_skills.append(gsk)
            except Exception:
                pass
            for sk in all_skills:
                sk_name = getattr(sk, "name", "") or ""
                if "passive" in sk_name.lower():
                    helper_skill_key = getattr(sk, "id", "") or sk_name
                    logger.info(f"[HybridCloud] Fallback: found passive skill '{sk_name}' (id={helper_skill_key})")
                    break

        if helper_skill_key:
            companion_task = self._ensure_companion_local_task(
                task, helper_skill_key, cloud_run_id, client_id
            )
        else:
            logger.warning(f"[HybridCloud] No companion skill found — no local_helper_skill_name in response, "
                           f"no local_helper_skill_id on skill, and no skill with 'passive' in name")

        # Step 6: The cloud is running the main skill; the local side just waits.
        # Mark task as having an active cloud run to prevent re-scheduling.
        task.state["cloud_run_active"] = True

        if companion_task:
            logger.info(f"[HybridCloud] Step 6: Cloud task launched, companion task '{companion_task.name}' ready. "
                        f"Waiting for cloud completion via onTaskStatus subscription.")
        else:
            logger.info(f"[HybridCloud] Step 6: Cloud task launched (no companion task). "
                        f"Waiting for cloud completion via onTaskStatus subscription.")
        return {"success": True, "cloud_run_id": cloud_run_id, "hybrid": True}, True
    
    def _get_client_id(self) -> str:
        """Get the client ID (acctSiteID) for passive command subscription."""
        try:
            mainwin = self.agent.mainwin
            if hasattr(mainwin, 'getAcctSiteID'):
                cid = mainwin.getAcctSiteID()
                if cid:
                    return cid
        except Exception:
            pass
        import socket
        return f"client-{socket.gethostname()}"
    
    def _start_hybrid_passive_subscription(self, token: str, endpoint: str, run_id: str, client_id: str) -> None:
        """Start onPassiveCommand WebSocket subscription for hybrid cloud execution."""
        try:
            from agent.ec_skills.browser_use_extension.passive_command_service import PassiveCommandService
            from agent.ec_skills.browser_use_extension.appsync_passive_client import (
                AppSyncPassiveClientConfig,
                _derive_realtime_endpoint,
                _derive_api_host,
            )

            mainwin = self.agent.mainwin
            http_endpoint = endpoint or mainwin.getWanApiEndpoint()
            ws_endpoint = getattr(mainwin, 'getWSApiEndpoint', lambda: None)() or _derive_realtime_endpoint(http_endpoint)
            api_host = getattr(mainwin, 'getWSApiHost', lambda: None)() or _derive_api_host(http_endpoint, ws_endpoint)

            config = AppSyncPassiveClientConfig(
                http_endpoint=http_endpoint,
                ws_endpoint=ws_endpoint,
                api_host=api_host,
                auth_token=token,
                run_id=run_id,
                client_id=client_id,
            )

            route_fn = getattr(mainwin, '_route_passive_command_to_task', None)
            if not route_fn:
                logger.warning("[HybridCloud] No _route_passive_command_to_task on mainwin")
                return

            service = PassiveCommandService(config=config, route_command=route_fn)

            # Track the service for cleanup on task completion
            sub_entry = self._active_subscriptions.setdefault(run_id, {})
            sub_entry["passive_service"] = service

            import asyncio as _asyncio

            async def _start():
                await service.start()

            loop = getattr(mainwin, '_async_loop', None)
            passive_thread_name = f"PassiveCmd-{run_id[:8]}"
            if loop and loop.is_running():
                _asyncio.run_coroutine_threadsafe(_start(), loop)
            else:
                def _run():
                    _asyncio.run(_start())
                t = threading.Thread(target=_run, daemon=True, name=passive_thread_name)
                t.start()
                sub_entry["_passive_thread"] = t
                try:
                    reg, _, _ = _get_thread_registry()
                    reg("PassiveCmd", passive_thread_name)
                    sub_entry["_passive_thread_reg"] = ("PassiveCmd", passive_thread_name)
                except Exception:
                    pass

            logger.info(f"[HybridCloud] Passive subscription started: client_id={client_id}, run_id={run_id}")
        except Exception as e:
            logger.error(f"[HybridCloud] Failed to start passive subscription: {e}")
            logger.error(traceback.format_exc())
    
    def _start_task_status_subscription(self, task: ManagedTask, run_id: str) -> None:
        """Start onTaskStatus WebSocket subscription for a running task.
        
        Called after obtaining the runId for any task type (local, cloud, hybrid).
        Uses the runId as the 'runner' parameter so the subscription receives
        status updates specific to this task run.
        """
        try:
            from app_context import AppContext
            from .appsync_pubsub import AppSyncApiKeyConfig, subscribe_task_status

            login = AppContext.get_login()
            tokens = login.auth_manager.get_tokens()
            
            mainwin = AppContext.get_main_window()
            auth_token = ""
            auth_token_source = "none"
            if mainwin:
                try:
                    auth_token = mainwin.get_auth_token() or ""
                    if auth_token:
                        auth_token_source = "mainwin.get_auth_token"
                except Exception:
                    auth_token = ""
            if not auth_token:
                auth_token = (
                    tokens.get('id_token')
                    or tokens.get('IdToken')
                    or tokens.get('access_token')
                    or tokens.get('AccessToken')
                    or ""
                )
                if auth_token:
                    if tokens.get('id_token'):
                        auth_token_source = "tokens.id_token"
                    elif tokens.get('IdToken'):
                        auth_token_source = "tokens.IdToken"
                    elif tokens.get('access_token'):
                        auth_token_source = "tokens.access_token"
                    elif tokens.get('AccessToken'):
                        auth_token_source = "tokens.AccessToken"
            api_key = mainwin.getWanApiKey() if mainwin else ""
            endpoint = mainwin.getWanApiEndpoint() if mainwin else ""

            masked_token = f"{auth_token[:12]}...{auth_token[-6:]}" if auth_token and len(auth_token) > 18 else ("<short>" if auth_token else "<empty>")
            masked_api_key = f"{api_key[:8]}...{api_key[-4:]}" if api_key and len(api_key) > 12 else ("<short>" if api_key else "<empty>")
            logger.info(
                f"[TaskStatus] Preparing subscription auth: run_id={run_id}, "
                f"token_source={auth_token_source}, token={masked_token}, "
                f"api_key={masked_api_key}, endpoint={endpoint or '<empty>'}"
            )
            
            config = AppSyncApiKeyConfig(
                http_endpoint=endpoint,
                api_key=api_key,
                auth_token=auth_token,
            )

            task_ref = task  # capture for callback closure

            async def _on_envelope(envelope: dict):
                self._on_task_status_envelope(task_ref, envelope)

            async def _run_subscription():
                await subscribe_task_status(
                    config=config,
                    runner=run_id,
                    on_envelope=_on_envelope,
                    max_retries=10,
                )

            import asyncio as _asyncio

            # Track the subscription future for cleanup
            sub_entry = self._active_subscriptions.setdefault(run_id, {})
            sub_entry["task_id"] = task.id

            loop = getattr(mainwin, '_async_loop', None)
            thread_name = f"TaskStatus-{run_id[:8]}"

            if loop and loop.is_running():
                future = _asyncio.run_coroutine_threadsafe(_run_subscription(), loop)
                sub_entry["status_future"] = future
            else:
                # Track thread so we can join it on cleanup
                t = threading.Thread(target=_run_subscription, daemon=True, name=thread_name)
                t.start()
                sub_entry["status_thread"] = t
                # Register with global thread registry for diagnosis
                try:
                    reg, _, _ = _get_thread_registry()
                    reg("TaskStatus", thread_name)
                    sub_entry["_thread_reg"] = ("TaskStatus", thread_name)
                except Exception:
                    pass

            logger.info(f"[TaskStatus] onTaskStatus subscription started: task={task.name}, run_id={run_id}")
        except Exception as e:
            logger.warning(f"[TaskStatus] Failed to start onTaskStatus subscription for run_id={run_id}: {e}")
            logger.debug(traceback.format_exc())

    def _on_task_status_envelope(self, task: ManagedTask, envelope: dict) -> None:
        """Handle an onTaskStatus WebSocket message for a task run.
        
        Envelope fields: id, runID, runner, error, success, status, timestamp
        """
        try:
            run_id = envelope.get("runID") or envelope.get("run_id") or ""
            success = envelope.get("success")
            error = envelope.get("error")
            status = envelope.get("status")

            logger.info(
                f"[TaskStatus] Received status update: task={task.name}, "
                f"run_id={run_id}, success={success}, status={status}, error={error}"
            )

            # Store latest cloud status on task state for visibility
            task.state["last_cloud_status"] = {
                "run_id": run_id,
                "success": success,
                "error": error,
                "status": status,
                "timestamp": envelope.get("timestamp"),
            }

            # If the cloud side reports failure, log it prominently
            if success is False and error:
                logger.error(f"[TaskStatus] Cloud-side failure for task={task.name}: {error}")

            # On terminal status, clean up subscriptions for this run
            terminal_statuses = {"complete", "completed", "failed", "cancelled", "canceled", "error"}
            status_str = str(status).lower() if status else ""
            if status_str in terminal_statuses:
                logger.info(f"[TaskStatus] Terminal status '{status_str}' for run_id={run_id}, cleaning up subscriptions")
                # Clear the active cloud run flag so the task can be re-scheduled
                task.state.pop("cloud_run_active", None)
                self._cleanup_hybrid_subscriptions(run_id)

        except Exception as e:
            logger.warning(f"[TaskStatus] Error processing status envelope: {e}")

    def _cleanup_hybrid_subscriptions(self, run_id: str) -> None:
        """Stop onPassiveCommand and onTaskStatus subscriptions for a completed cloud run."""
        sub_entry = self._active_subscriptions.pop(run_id, None)
        if not sub_entry:
            logger.debug(f"[HybridCloud] No active subscriptions to clean up for run_id={run_id}")
            return

        # Stop passive command service (may own threads)
        passive_service = sub_entry.get("passive_service")
        passive_thread = sub_entry.get("_passive_thread")
        if passive_service or passive_thread:
            try:
                import asyncio as _asyncio
                mainwin = self.agent.mainwin
                loop = getattr(mainwin, '_async_loop', None)

                async def _stop():
                    if passive_service:
                        await passive_service.stop()

                if loop and loop.is_running():
                    fut = _asyncio.run_coroutine_threadsafe(_stop(), loop)
                    # Give it a moment to take effect, but don't block
                    try:
                        fut.result(timeout=2.0)
                    except Exception:
                        pass
                else:
                    def _run():
                        _asyncio.run(_stop())
                    t = threading.Thread(target=_run, daemon=True)
                    t.start()
                logger.info(f"[HybridCloud] Stopped passive command subscription for run_id={run_id}")
            except Exception as e:
                logger.warning(f"[HybridCloud] Error stopping passive subscription: {e}")

        # Join passive subscription thread if exists
        passive_thread = sub_entry.get("_passive_thread")
        if passive_thread:
            try:
                passive_thread.join(timeout=5.0)
                if passive_thread.is_alive():
                    logger.warning(f"[HybridCloud] Passive thread still alive after join for run_id={run_id}")
                else:
                    logger.info(f"[HybridCloud] Passive thread joined for run_id={run_id}")
            except Exception as e:
                logger.warning(f"[HybridCloud] Error joining passive thread: {e}")

        # Unregister passive thread from registry
        passive_reg = sub_entry.get("_passive_thread_reg")
        if passive_reg:
            try:
                _, unreg, _ = _get_thread_registry()
                unreg(passive_reg[0], passive_reg[1])
            except Exception:
                pass

        # Cancel asyncio task (for subscriptions running in main event loop)
        status_future = sub_entry.get("status_future")
        if status_future and hasattr(status_future, 'cancel'):
            try:
                status_future.cancel()
                logger.info(f"[HybridCloud] Cancelled task status asyncio future for run_id={run_id}")
            except Exception as e:
                logger.warning(f"[HybridCloud] Error cancelling status future: {e}")

        # Join the daemon thread that ran _asyncio.run(_run_subscription())
        # This is critical: without join, the thread + its event loop persist forever.
        status_thread = sub_entry.get("status_thread")
        if status_thread:
            try:
                status_thread.join(timeout=5.0)
                if status_thread.is_alive():
                    logger.warning(f"[HybridCloud] TaskStatus thread still alive after join for run_id={run_id}")
                else:
                    logger.info(f"[HybridCloud] TaskStatus thread joined for run_id={run_id}")
            except Exception as e:
                logger.warning(f"[HybridCloud] Error joining status thread: {e}")

        # Unregister from thread registry
        thread_reg = sub_entry.get("_thread_reg")
        if thread_reg:
            try:
                _, unreg, _ = _get_thread_registry()
                unreg(thread_reg[0], thread_reg[1])
            except Exception:
                pass

        # Remove event routing entry for this run
        routing_key = f"passive_command_{run_id}"
        self._global_event_routing.pop(routing_key, None)

        logger.info(f"[HybridCloud] Cleanup complete for run_id={run_id}")

    def _ensure_companion_local_task(
        self,
        parent_task: ManagedTask,
        local_helper_skill_id: str,
        cloud_run_id: str,
        client_id: str,
    ) -> Optional[ManagedTask]:
        """Find or create a companion local task for hybrid cloud passive command execution.
        
        Looks for an existing running task that uses the companion skill.
        If found and already running, returns it (no-op).
        If not found, creates a new task and starts its execution loop.
        
        Args:
            parent_task: The hybrid cloud parent task
            local_helper_skill_id: Skill ID (or name) of the local companion skill
            cloud_run_id: The cloud task's run ID
            client_id: Client ID for passive command routing
            
        Returns:
            The companion ManagedTask, or None if skill not found.
        """
        agent = self.agent
        tasks = getattr(agent, "tasks", []) or []
        skills = getattr(agent, "skills", []) or []

        # Resolve the companion skill object — search agent skills first, then global pool
        companion_skill = None
        for sk in skills:
            if getattr(sk, "id", "") == local_helper_skill_id or getattr(sk, "name", "") == local_helper_skill_id:
                companion_skill = sk
                break

        if not companion_skill:
            # Fallback: search global compiled skills pool (mainwin.agent_skills)
            try:
                from app_context import AppContext
                main_win = AppContext.get_main_window()
                global_skills = getattr(main_win, "agent_skills", []) or [] if main_win else []
                for sk in global_skills:
                    if getattr(sk, "id", "") == local_helper_skill_id or getattr(sk, "name", "") == local_helper_skill_id:
                        companion_skill = sk
                        logger.info(f"[HybridCloud] Found companion skill '{local_helper_skill_id}' in global pool")
                        break
            except Exception as e:
                logger.debug(f"[HybridCloud] Could not search global skills pool: {e}")

        if not companion_skill:
            logger.warning(
                f"[HybridCloud] Companion skill not found: {local_helper_skill_id}. "
                f"Available: {[getattr(s, 'name', '?') for s in skills[:10]]}"
            )
            return None

        companion_skill_name = getattr(companion_skill, "name", local_helper_skill_id)

        # Check if a task using this companion skill is already running
        for t in tasks:
            t_skill = getattr(t, "skill", None)
            if t_skill is None:
                continue
            if getattr(t_skill, "id", "") == getattr(companion_skill, "id", "") or \
               getattr(t_skill, "name", "") == companion_skill_name:
                logger.info(
                    f"[HybridCloud] Companion task already exists: {t.name} (id={t.id}), "
                    f"skill={companion_skill_name} — no action needed"
                )
                # Inject cloud context into existing companion task state
                t.state["cloud_run_id"] = cloud_run_id
                t.state["client_id"] = client_id
                t.state["is_helper_skill"] = True
                t.state["parent_cloud_task_id"] = parent_task.id
                return t

        # No existing task — create and start one
        logger.info(f"[HybridCloud] Creating companion local task for skill: {companion_skill_name}")
        try:
            new_id = str(uuid.uuid4())
            companion_state = {
                "is_helper_skill": True,
                "parent_cloud_task_id": parent_task.id,
                "cloud_run_id": cloud_run_id,
                "client_id": client_id,
            }

            # SHARED_SKILL_MULTI_TASK_PLAN: the companion inherits the parent
            # task's carried variables and browser identity so the local
            # helper's prompts/browser match the hybrid task's configuration
            # (apply_task_vars reads these from task.metadata at run start).
            companion_metadata: dict = {"state": companion_state}
            try:
                parent_md = parent_task.metadata if isinstance(parent_task.metadata, dict) else {}
                for carried_key in ("task_vars", "browser_identity"):
                    if isinstance(parent_md.get(carried_key), dict) and parent_md[carried_key]:
                        companion_metadata[carried_key] = dict(parent_md[carried_key])
                        logger.info(
                            f"[HybridCloud] Companion task inherits {carried_key} "
                            f"keys: {sorted(parent_md[carried_key].keys())}"
                        )
            except Exception as _inherit_err:
                logger.warning(f"[HybridCloud] Failed to inherit task metadata: {_inherit_err}")

            from a2a.types import TaskState, TaskStatus as A2ATaskStatus

            new_task = ManagedTask(
                id=new_id,
                context_id=new_id,
                run_id=str(uuid.uuid4()),
                name=f"{companion_skill_name}_helper_{new_id[:8]}",
                description=f"Companion local task for hybrid cloud run {cloud_run_id[:8]}",
                source="hybrid_cloud",
                status=A2ATaskStatus(state=TaskState.submitted),
                sessionId="",
                skill=companion_skill,
                metadata=companion_metadata,
                state=companion_state,
                trigger=["message"],
                agent_id=getattr(getattr(agent, "card", None), "id", "") or "",
            )

            # Add to agent tasks
            if getattr(agent, "tasks", None) is None:
                agent.tasks = []
            agent.tasks.append(new_task)

            # Start execution loop
            mainwin = getattr(agent, "mainwin", None)
            thread_pool = getattr(mainwin, "threadPoolExecutor", None) if mainwin else None
            if not thread_pool:
                thread_pool = getattr(agent, "thread_pool_executor", None)
            if not thread_pool:
                from concurrent.futures import ThreadPoolExecutor
                thread_pool = ThreadPoolExecutor(max_workers=4)

            future = thread_pool.submit(self.launch_unified_run, new_task, ["message"])
            if hasattr(agent, "active_tasks") and hasattr(agent, "task_lock"):
                with agent.task_lock:
                    agent.active_tasks[new_task.run_id] = future

            logger.info(
                f"[HybridCloud] Companion task created and started: {new_task.name} "
                f"(id={new_id}, skill={companion_skill_name}, run_id={new_task.run_id})"
            )
            return new_task

        except Exception as e:
            logger.error(f"[HybridCloud] Failed to create companion task: {e}")
            logger.error(traceback.format_exc())
            return None

    def _extract_waiter_task_id(self, msg: Any) -> Optional[str]:
        """Extract waiter task ID from message."""
        try:
            if msg and hasattr(msg, 'params') and hasattr(msg.params, 'id'):
                return msg.params.id
            if msg and isinstance(msg, dict):
                attrs = msg.get('attributes')
                if isinstance(attrs, dict) and attrs.get('params'):
                    params = attrs['params']
                    return params.id if hasattr(params, 'id') else params.get('id')
                return msg.get('params', {}).get('id') or msg.get('id')
        except Exception:
            pass
        return None
    
    def _execute_skill(
        self,
        task: ManagedTask,
        msg: Any,
        trigger_type: str,
        is_initial_run: bool,
        dev_init_state: Optional[dict]
    ) -> Tuple[Optional[dict], bool]:
        """Execute a skill and return result.
        
        Uses hybrid async/sync execution with automatic fallback.
        Async mode can be controlled via:
        - Environment variable: ECAN_ASYNC_EXECUTION=true/false
        - Task metadata: task.metadata.get("use_async", True)
        """
        try:
            from .executor import execute_task_hybrid

            # Start onTaskStatus subscription for this task run
            try:
                self._start_task_status_subscription(task, task.run_id)
            except Exception as e:
                logger.warning(f"[TaskStatus] Could not start subscription for local task={task.name}: {e}")

            def _is_retryable_error_text(error_text: str) -> bool:
                et = (error_text or "").lower()
                # Only retry on genuine server-side / service errors, NOT on:
                # - timeout: timeout means the API didn't respond — the request may still be
                #   processing server-side; retrying creates duplicate requests and infinite loops
                #   when the skill also hits pend_event (interrupt), as the queue re-poll
                #   re-triggers the interrupted task.
                # - api connection / apiconnectionerror: almost always network/proxy issues,
                #   retrying with same config rarely helps and also compounds with pend_event.
                return any(
                    k in et
                    for k in (
                        "error code: 503",
                        " error code: 503",
                        "503",
                        "service unavailable",
                        "rate limit",
                        "429",
                        "temporarily unavailable",
                        "internalservererror",
                        "bad gateway",
                        "502",
                        "504",
                    )
                )

            def _extract_error_text(resp: Any) -> str:
                if isinstance(resp, dict):
                    return str(resp.get("Error") or resp.get("error") or resp.get("message") or "")
                return str(resp or "")
            
            task_metadata = task.metadata if isinstance(task.metadata, dict) else {}
            if not isinstance(task.metadata, dict):
                task.metadata = task_metadata

            # Determine if async execution should be used
            # Can be disabled per-task or globally via env var
            use_async = task_metadata.get("use_async", True)
            
            # Dev mode defaults to sync for easier debugging (can be overridden)
            if trigger_type == "dev":
                use_async = task_metadata.get("use_async", False)
            
            if is_initial_run:
                # Clear pending_since on fresh start so timeout tracking starts clean.
                # For resume (is_initial_run=False) we deliberately leave it intact
                # so _check_pending_timeout can fire if the interrupt hangs.
                self._task_states.setdefault(task.id, {})['pending_since'] = None

                # Prepare state
                if trigger_type == "dev" and isinstance(dev_init_state, dict):
                    final_state = self._prepare_dev_state(task, msg, dev_init_state)
                else:
                    initial_current_state = None
                    try:
                        if trigger_type == "message" and isinstance(task_metadata.get("state"), dict):
                            initial_current_state = task_metadata.get("state")
                    except Exception:
                        initial_current_state = None
                    final_state = prep_skills_run(task.skill, self.agent, task.id, msg, initial_current_state)

                # Phase 2 (SHARED_SKILL_MULTI_TASK_PLAN): seed task-carried
                # variables into the run state for EVERY trigger type — the
                # message-only current_state merge above never covered
                # schedule/auto runs (blocker B4).
                apply_task_vars(task, final_state)

                task_metadata["state"] = final_state

                max_retries = int(task_metadata.get("retry_max", 2) or 2)
                retry_base_delay = float(task_metadata.get("retry_delay", 1.0) or 1.0)
                retry_backoff = float(task_metadata.get("retry_backoff", 2.0) or 2.0)

                response = None
                for attempt in range(max_retries + 1):
                    response = execute_task_hybrid(task, final_state, use_async=use_async)
                    if isinstance(response, dict) and response.get("success") is False:
                        err_text = _extract_error_text(response)
                        if attempt < max_retries and _is_retryable_error_text(err_text):
                            delay = retry_base_delay * (retry_backoff ** attempt)
                            logger.warning(
                                f"[EXECUTOR] Retryable failure (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay:.1f}s: {err_text}"
                            )
                            time.sleep(delay)
                            continue
                    break

                # If the initial run interrupted (pend_event waiting for input) and the
                # original message carries data the pend_event needs, immediately
                # resume so the graph can continue.  This covers two cases:
                #   1. async_callback — passive command from cloud
                #   2. message trigger (human_chat / a2a) — the user's chat message
                #      is already in the state but pend_event always interrupts on
                #      first visit; auto-resume feeds the message as a resume payload
                #      so the graph advances to the LLM node.
                _is_interrupted = (
                    isinstance(response, dict)
                    and response.get("success") is False
                    and isinstance(response.get("step"), dict)
                    and "__interrupt__" in response.get("step", {})
                )
                _is_async_callback = isinstance(msg, dict) and msg.get("type") == "async_callback"
                _is_message_trigger = trigger_type == "message"
                _should_auto_resume = _is_async_callback or _is_message_trigger

                if _is_interrupted and _should_auto_resume:
                    logger.info(f"[EXECUTOR] Initial run interrupted at pend_event — auto-resuming (trigger={trigger_type}, async_cb={_is_async_callback})")
                    resume_payload, cp = self._build_resume_payload(task, msg)
                    resume_cmd = Command(resume=resume_payload)
                    resume_tag = None
                    if isinstance(resume_payload, dict):
                        resume_tag = resume_payload.get("_resuming_from")
                    if not resume_tag and cp:
                        resume_tag = _safe_get(cp, "values.attributes.i_tag") or _safe_get(cp, "values.attributes.tag")
                    resume_context = {"skip_bp_once": [resume_tag]} if resume_tag else None

                    if cp:
                        response = execute_task_hybrid(
                            task, resume_cmd, use_async=use_async,
                            checkpoint=cp, context=resume_context,
                        )
                    else:
                        response = execute_task_hybrid(
                            task, resume_cmd, use_async=use_async,
                            context=resume_context,
                        )
                    logger.info(f"[EXECUTOR] Auto-resume completed: success={response.get('success') if isinstance(response, dict) else '?'}")

                return response, True
            else:
                # Resume run
                resume_payload, cp = self._build_resume_payload(task, msg)
                resume_cmd = Command(resume=resume_payload)

                resume_tag = None
                if isinstance(resume_payload, dict):
                    resume_tag = resume_payload.get("_resuming_from")
                if not resume_tag and cp:
                    resume_tag = _safe_get(cp, "values.attributes.i_tag") or _safe_get(cp, "values.attributes.tag")

                resume_context = None
                if resume_tag:
                    resume_context = {"skip_bp_once": [resume_tag]}

                max_retries = int(task_metadata.get("retry_max", 2) or 2)
                retry_base_delay = float(task_metadata.get("retry_delay", 1.0) or 1.0)
                retry_backoff = float(task_metadata.get("retry_backoff", 2.0) or 2.0)

                response = None
                for attempt in range(max_retries + 1):
                    if cp:
                        response = execute_task_hybrid(
                            task,
                            resume_cmd,
                            use_async=use_async,
                            checkpoint=cp,
                            context=resume_context,
                        )
                    else:
                        response = execute_task_hybrid(
                            task,
                            resume_cmd,
                            use_async=use_async,
                            context=resume_context,
                        )

                    if isinstance(response, dict) and response.get("success") is False:
                        err_text = _extract_error_text(response)
                        if attempt < max_retries and _is_retryable_error_text(err_text):
                            delay = retry_base_delay * (retry_backoff ** attempt)
                            logger.warning(
                                f"[EXECUTOR] Retryable failure (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay:.1f}s: {err_text}"
                            )
                            time.sleep(delay)
                            continue
                    break

                return response, False
                
        except Exception as e:
            logger.error(f"[EXECUTOR] Failed: {e}")
            logger.error(traceback.format_exc())
            return None, True
    
    def _prepare_dev_state(self, task: ManagedTask, msg: Any, dev_init_state: dict) -> dict:
        """Prepare state for dev run."""
        logger.debug(f"[_prepare_dev_state] dev_init_state['result']: {dev_init_state.get('result')}")
        prepared_state = None
        try:
            prep_msg = msg if msg not in (None, {"__dev_kickoff__": True}) else None
            prepared_state = prep_skills_run(task.skill, self.agent, task.id, prep_msg, None)
            logger.debug(f"[_prepare_dev_state] prepared_state['result']: {prepared_state.get('result') if isinstance(prepared_state, dict) else 'NOT_A_DICT'}")
        except Exception as e:
            logger.error(f"[DEV] prep_skills_run failed: {e}")
        
        final_state = {}
        if isinstance(prepared_state, dict):
            final_state = prepared_state
        if isinstance(dev_init_state, dict):
            final_state = self._deep_merge(final_state, dev_init_state)
            logger.debug(f"[_prepare_dev_state] final_state['result'] after merge: {final_state.get('result')}")
        
        return final_state or task.metadata.get("state", {})
    
    def _log_task_node_timings(self, task: "ManagedTask", waiter_task_id: Optional[str], response: Any) -> None:
        try:
            cp = None
            values = None
            if isinstance(response, dict):
                cp = response.get("cp")
            if cp is not None and hasattr(cp, "values"):
                values = getattr(cp, "values", None)
            if values is None:
                values = task.metadata.get("state")

            if not isinstance(values, dict):
                return

            attrs = values.get("attributes")
            timings = attrs.get("__node_timings__") if isinstance(attrs, dict) else None
            if not (isinstance(timings, list) and timings):
                return

            total_ms = 0
            status_cnt = {}
            cleaned = []
            for t in timings:
                if not isinstance(t, dict):
                    continue
                dms = int(t.get("duration_ms") or 0)
                total_ms += max(dms, 0)
                st = str(t.get("status") or "")
                status_cnt[st] = status_cnt.get(st, 0) + 1
                cleaned.append(t)

            cleaned.sort(key=lambda x: int(x.get("duration_ms") or 0), reverse=True)
            topn = cleaned[:10]
            logger.info(
                f"[PERF][TASK] task={getattr(task, 'name', '')} waiter={waiter_task_id} "
                f"nodes={len(cleaned)} total_node_time={total_ms}ms status={status_cnt}"
            )
            for i, t in enumerate(topn, 1):
                logger.info(
                    f"[PERF][TASK][TOP{i}] {t.get('skill')}::{t.get('node')} "
                    f"status={t.get('status')} duration_ms={t.get('duration_ms')}"
                )
        except Exception:
            pass
    
    def _on_skill_complete(
        self,
        future: concurrent.futures.Future,
        task: ManagedTask,
        waiter_task_id: Optional[str],
        trigger_type: str
    ):
        """Handle skill execution completion."""
        _stale_completion = False
        _preserve_task_state = False
        try:
            # Check if there's a newer future already running - ignore this stale callback
            _current_future = getattr(task, "future", None)
            if _current_future is not None and _current_future is not future:
                _stale_completion = True
                logger.info(
                    f"[COMPLETE] Ignoring stale completion callback for "
                    f"task {task.name}; a newer future is active"
                )
                return
            
            response, was_initial = future.result()

            # Handle None response from browser automation (e.g., consecutive failures)
            if response is None:
                logger.error(f"[COMPLETE] Skill returned None for waiter={waiter_task_id} (likely consecutive failures)")
                self._set_task_failed_state(task, "Task failed: browser automation returned no result")
                return
            if isinstance(response, dict):
                terminal_status = str(response.get("terminal_status") or "").lower()

            if not terminal_status:
                try:
                    if task.is_cancelled() or str(getattr(task.status, "state", "")).lower().endswith("canceled"):
                        terminal_status = "cancelled"
                except Exception:
                    pass

            if not terminal_status:
                try:
                    if isinstance(response, dict):
                        cp = response.get("cp")
                        cp_values = cp.values if hasattr(cp, "values") else {}
                        # task_is_blocked only checks task-level result and the most-recent
                        # node output — not full history/messages — to avoid false positives
                        # from transient mid-task blocks (e.g. one platform hitting risk control).
                        if task_is_blocked(cp_values):
                            terminal_status = "blocked"
                except Exception:
                    pass

            if not terminal_status:
                try:
                    ts = self._task_states.get(task.id, {})
                    last_resp = ts.get("last_response") if isinstance(ts, dict) else None
                    if isinstance(last_resp, dict) and "timeoutwaitingforevent" in str(last_resp.get("error") or "").lower():
                        terminal_status = "timeout"
                except Exception:
                    pass

            if terminal_status in {"cancelled", "canceled"}:
                logger.info(f"[COMPLETE] Skill cancelled for waiter={waiter_task_id}")
                try:
                    task.status.state = TaskState.canceled
                    task.status.message = _create_message("agent", "Task cancelled by user")
                except Exception:
                    pass
                self._emit_task_status(task, "cancelled")
                return

            if terminal_status == "timeout":
                logger.error(f"[FAIL_REASON] reason=timeout scope=task_complete waiter={waiter_task_id}")
                self._set_task_failed_state(task, "Task timed out")

                # FIX: Send degraded notification to wake up pend_event waiters
                # When a task times out, we need to notify the waiting task so it can
                # handle the failure gracefully (e.g., show error message to user)
                if trigger_type == "message" and waiter_task_id:
                    # Extract partial data if available
                    partial_result = None
                    if isinstance(response, dict):
                        cp = response.get("cp")
                        if cp and hasattr(cp, "values"):
                            state_values = cp.values
                            if isinstance(state_values, dict):
                                # Try to get any partial research data from the failed task
                                tool_result = state_values.get("tool_result", {})
                                if isinstance(tool_result, dict):
                                    # Get the last successful extraction if any
                                    for key in reversed(list(tool_result.keys())):
                                        val = tool_result.get(key)
                                        if isinstance(val, dict) and val.get("competitors"):
                                            partial_result = val
                                            logger.info(f"[COMPLETE][TIMEOUT] Found partial data in tool_result.{key}")
                                            break

                    # Build degraded response for the waiting task
                    degraded_response = {
                        "success": False,
                        "error": "timeout",
                        "message": "任务执行超时",
                        "partial_data": partial_result,
                        "terminal_status": "timeout",
                        "task_id": task.id,
                        "task_name": getattr(task, "name", ""),
                    }

                    logger.info(f"[COMPLETE][TIMEOUT] Sending degraded notification to waiter={waiter_task_id}")
                    try:
                        self.agent.a2a_server.task_manager.resolve_waiter(waiter_task_id, degraded_response)
                    except Exception as _resolve_err:
                        logger.error(f"[COMPLETE][TIMEOUT] Failed to resolve waiter: {_resolve_err}")

                return

            # Distinguish real failures from interrupts: an interrupt returns
            # success=False but carries __interrupt__ in the step dict and has
            # no Error/error key.  Let interrupts fall through to the handler
            # below so the loop stays alive waiting for resume events.
            _step_data = response.get("step") if isinstance(response, dict) else None
            _is_interrupt = isinstance(_step_data, dict) and "__interrupt__" in _step_data

            def _false_response_has_completed_send(_response: Any) -> bool:
                """Detect graph false-negatives after a successful send_chat.

                Some loop/condition graphs return ``success=False`` when the
                loop condition evaluates false after work is already complete.
                In the flood logs this happened after ``send_chat`` succeeded
                and ``llm_result.all_done`` was true, so the Q&A service task
                was incorrectly counted as failed and eventually disabled by
                the max-failure guard.  The same false-negative shape also
                appears when a configurable hot path finishes a browser send
                and parks the long-running task back on ``pend_event``.
                """
                if not isinstance(_response, dict) or _response.get("success") is not False:
                    return False
                if _response.get("Error") or _response.get("error"):
                    return False

                roots: list[Any] = [_response.get("step")]
                cp = _response.get("cp")
                cp_values = getattr(cp, "values", None)
                if isinstance(cp_values, dict):
                    roots.append(cp_values)

                seen: set[int] = set()
                stack: list[tuple[Any, int]] = [(r, 0) for r in roots if r is not None]
                inspected = 0
                while stack and inspected < 500:
                    obj, depth = stack.pop()
                    oid = id(obj)
                    if oid in seen:
                        continue
                    seen.add(oid)
                    inspected += 1
                    if depth > 7:
                        continue
                    if isinstance(obj, dict):
                        llm_result = obj.get("llm_result")
                        if isinstance(llm_result, dict):
                            work_result = llm_result.get("work_result")
                            if not isinstance(work_result, dict):
                                work_result = {}
                            if (
                                llm_result.get("Error")
                                or llm_result.get("error")
                                or work_result.get("Error")
                                or work_result.get("error")
                            ):
                                continue
                            if (
                                llm_result.get("all_done") is True
                                and (
                                    llm_result.get("hot_path") is True
                                    or str(llm_result.get("tool_name") or "") == "send_chat"
                                    or str(llm_result.get("hot_path_type") or "") == "configurable"
                                    or work_result.get("last_action_succeeded") is True
                                    or work_result.get("chat_sent") is True
                                )
                            ):
                                return True

                        send_chat_result = obj.get("send_chat_result")
                        if (
                            isinstance(send_chat_result, dict)
                            and send_chat_result.get("success") is True
                        ):
                            return True

                        for key, val in obj.items():
                            if key in {"prompts", "history", "messages", "threads", "events"}:
                                continue
                            if isinstance(val, (dict, list, tuple)):
                                stack.append((val, depth + 1))
                        continue

                    if isinstance(obj, (list, tuple)):
                        for val in obj:
                            if isinstance(val, (dict, list, tuple)):
                                stack.append((val, depth + 1))
                return False

            if (
                isinstance(response, dict)
                and response.get("success") is False
                and not _is_interrupt
                and _false_response_has_completed_send(response)
            ):
                logger.info(
                    f"[COMPLETE] Treating success=False as completed for "
                    f"waiter={waiter_task_id}: work already completed"
                )
                response = dict(response)
                response["success"] = True

            if isinstance(response, dict) and response.get("success") is False and not _is_interrupt:
                err_text = str(response.get("Error") or response.get("error") or response)
                logger.error(f"[COMPLETE] Skill failed for waiter={waiter_task_id}: {err_text}")
                # Liveness fix (incident 2026-04-27): release live-chat
                # dispatch dedup + inflight locks so the customer's
                # message is re-dispatchable instead of permanently
                # locked behind a stale stamp.  See
                # ``_release_dispatch_locks_on_skill_failure`` for the
                # full write-up.
                _release_dispatch_locks_on_skill_failure(response)
                self._set_task_failed_state(task, err_text)

                # Extract partial data for degraded response
                partial_result = None
                if isinstance(response, dict):
                    cp = response.get("cp")
                    if cp and hasattr(cp, "values"):
                        state_values = cp.values
                        if isinstance(state_values, dict):
                            tool_result = state_values.get("tool_result", {})
                            if isinstance(tool_result, dict):
                                for key in reversed(list(tool_result.keys())):
                                    val = tool_result.get(key)
                                    if isinstance(val, dict) and val.get("competitors"):
                                        partial_result = val
                                        break

                if trigger_type == "message" and waiter_task_id:
                    degraded_response = {
                        "success": False,
                        "error": "failed",
                        "message": err_text,
                        "partial_data": partial_result,
                        "terminal_status": "failed",
                        "task_id": task.id,
                        "task_name": getattr(task, "name", ""),
                    }
                    self.agent.a2a_server.task_manager.resolve_waiter(waiter_task_id, degraded_response)
                elif trigger_type == "schedule":
                    from datetime import datetime
                    task.last_run_datetime = datetime.now()
                    task.already_run_flag = True
                    logger.warning(f"[SCHEDULE] Task '{task.name}' failed, updated last_run_datetime")
                    self.agent.a2a_server.task_manager.set_exception(task.id, RuntimeError(err_text))
                return

            # Also check for 'status': 'failed' (used by browser automation nodes)
            # This handles cases where browser automation returns {'status': 'failed', 'error': ...}
            # without the 'success' field
            elif isinstance(response, dict) and response.get("status") == "failed" and not _is_interrupt:
                err_text = str(response.get("error") or response.get("Error") or response)
                logger.error(f"[COMPLETE] Skill failed (status=failed) for waiter={waiter_task_id}: {err_text}")
                _release_dispatch_locks_on_skill_failure(response)
                self._set_task_failed_state(task, err_text)

                # Extract partial data for degraded response
                partial_result = None
                if isinstance(response, dict):
                    cp = response.get("cp")
                    if cp and hasattr(cp, "values"):
                        state_values = cp.values
                        if isinstance(state_values, dict):
                            tool_result = state_values.get("tool_result", {})
                            if isinstance(tool_result, dict):
                                for key in reversed(list(tool_result.keys())):
                                    val = tool_result.get(key)
                                    if isinstance(val, dict) and val.get("competitors"):
                                        partial_result = val
                                        break

                # Build degraded response for message trigger with waiter
                if trigger_type == "message" and waiter_task_id:
                    degraded_response = {
                        "success": False,
                        "error": "failed",
                        "message": err_text,
                        "partial_data": partial_result,
                        "terminal_status": "failed",
                        "task_id": task.id,
                        "task_name": getattr(task, "name", ""),
                    }
                    self.agent.a2a_server.task_manager.resolve_waiter(waiter_task_id, degraded_response)
                elif trigger_type == "schedule":
                    from datetime import datetime
                    task.last_run_datetime = datetime.now()
                    task.already_run_flag = True
                    logger.warning(f"[SCHEDULE] Task '{task.name}' failed, updated last_run_datetime")
                    self.agent.a2a_server.task_manager.set_exception(task.id, RuntimeError(err_text))
                return

            # Check for interrupt
            task_interrupted = False
            if response:
                step = response.get('step') or {}
                current_state = response.get('cp')
                
                if isinstance(step, dict) and '__interrupt__' in step:
                    task_interrupted = True
                    logger.info(f"[COMPLETE] task_interrupted=True for '{task.name}' (step has __interrupt__)")
                    # Still send the response back to GUI even when interrupted (e.g., pend_for_next_human_msg)
                    if current_state and hasattr(current_state, 'values'):
                        already_sent = (current_state.values.get("attributes") or {}).get("chat_response_sent", False)
                        if already_sent:
                            logger.debug("[COMPLETE] Skipping send_response_back (interrupted): chat node already sent response")
                        else:
                            try:
                                from agent.ec_skills.llm_utils.llm_utils import send_response_back
                                chatId = current_state.values.get("messages", [None, None])[1]
                                if chatId:
                                    send_response_back(current_state.values)
                            except Exception as srb_err:
                                logger.error(f"[COMPLETE] send_response_back failed (interrupted): {srb_err}")
                else:
                    logger.info(f"[COMPLETE] task_interrupted=False for '{task.name}' (step={step}, interrupt in step={isinstance(step, dict) and '__interrupt__' in step})")
                    # Send the LLM response back to the GUI/opposite agent
                    # Skip if a chat node already delivered the response (chat_response_sent flag)
                    if current_state and hasattr(current_state, 'values'):
                        already_sent = (current_state.values.get("attributes") or {}).get("chat_response_sent", False)
                        if already_sent:
                            logger.debug("[COMPLETE] Skipping send_response_back: chat node already sent response")
                            # But if notification is present, send A2A response to trigger pend_event waiters
                            notification_data = (current_state.values.get("attributes") or {}).get("notification")
                            logger.info(f"[COMPLETE] Debug: already_sent=True, notification_data={notification_data}")
                            if notification_data:
                                logger.info("[COMPLETE] Sending A2A response for notification to trigger pend_event waiters")
                                try:
                                    from agent.ec_skills.llm_utils.llm_utils import send_response_back
                                    send_response_back(current_state.values)
                                except Exception as srb_err:
                                    logger.error(f"[COMPLETE] send_response_back for notification failed: {srb_err}")
                        else:
                            try:
                                from agent.ec_skills.llm_utils.llm_utils import send_response_back
                                chatId = current_state.values.get("messages", [None, None])[1]
                                if chatId:
                                    send_response_back(current_state.values)
                            except Exception as srb_err:
                                logger.error(f"[COMPLETE] send_response_back failed: {srb_err}")

            # Reset failure counter on success/parked interrupt
            if hasattr(task, 'reset_failures'):
                task.reset_failures()

            if task_interrupted:
                _preserve_task_state = True
                logger.info(f"[COMPLETE] Skill parked on interrupt for waiter={waiter_task_id}")
                self._emit_task_status(task, "paused")
            elif terminal_status == "blocked":
                logger.error(f"[FAIL_REASON] reason=blocked scope=task_complete waiter={waiter_task_id}")
                self._set_task_failed_state(task, "Task blocked")
            else:
                logger.info(f"[COMPLETE] Skill completed for waiter={waiter_task_id}")
                self._emit_task_status(task, "completed")
                
                # DEBUG: Log response structure for debugging data flow issues
                _resp_keys = list(response.keys()) if isinstance(response, dict) else type(response).__name__
                _has_result = isinstance(response, dict) and "result" in response
                _result_keys = list(response.get("result", {}).keys()) if _has_result and isinstance(response.get("result"), dict) else "N/A"
                logger.info(f"[COMPLETE][DEBUG] response_type={type(response).__name__}, keys={_resp_keys}, has_result={_has_result}, result_keys={_result_keys}")

                # Emit task_completed to TaskProgressBus only for real completion
                try:
                    lineage = task.metadata.get("lineage") if hasattr(task, "metadata") and isinstance(task.metadata, dict) else None
                    if isinstance(lineage, dict) and lineage.get("correlation_id"):
                        from .task_progress_bus import TaskProgressBus, TaskProgressEvent
                        TaskProgressBus.get_instance().emit(TaskProgressEvent(
                            correlation_id=lineage["correlation_id"],
                            run_id=getattr(task, "run_id", ""),
                            parent_run_id=lineage.get("parent_run_id", ""),
                            task_id=getattr(task, "id", ""),
                            task_name=getattr(task, "name", ""),
                            depth=lineage.get("depth", 0),
                            event_type="task_completed",
                            result=response,
                        ))
                except Exception:
                    pass

            self._log_task_node_timings(task, waiter_task_id, response)
            
            # Update task state
            state = self._task_states.setdefault(task.id, {})
            # FIX: justStarted should be False after ANY skill completion (success or interrupted)
            # The previous logic: justStarted = not task_interrupted
            # was WRONG because:
            # - When skill SUCCEEDS (task_interrupted=False), justStarted=True causes infinite loops
            #   because _submit_task_execution uses justStarted to determine is_initial_run
            # - When skill INTERRUPTS (task_interrupted=True), justStarted=False is correct
            #   because we want to resume (not re-run from scratch)
            state['justStarted'] = False
            logger.info(f"[COMPLETE] Set justStarted=False for '{task.name}' (interrupted={task_interrupted})")
            
            if task_interrupted:
                state['pending_since'] = time.time()
            else:
                state['pending_since'] = None
                if trigger_type == "dev":
                    self._dev_exit_requested = True
            
            # Update scheduling state for scheduled tasks (only on successful completion)
            if trigger_type == "schedule" and not task_interrupted:
                from datetime import datetime
                task.last_run_datetime = datetime.now()
                task.already_run_flag = True
                logger.info(f"[SCHEDULE] Task '{task.name}' completed, updated last_run_datetime")
            
            # Resolve waiter
            if trigger_type == "schedule":
                if response:
                    self.agent.a2a_server.task_manager.set_result(task.id, response)
                else:
                    self.agent.a2a_server.task_manager.set_exception(task.id, RuntimeError("Task failed"))
            elif trigger_type == "message" and waiter_task_id:
                self.agent.a2a_server.task_manager.resolve_waiter(waiter_task_id, response)
                
        except Exception as e:
            logger.error(f"[COMPLETE] Callback error: {e}")
            logger.error(traceback.format_exc())
            
            # IMPORTANT: Set already_run_flag even on failure to prevent infinite retries
            # The task will be retried in the next schedule cycle (e.g., tomorrow for daily tasks)
            if trigger_type == "schedule":
                from datetime import datetime
                task.last_run_datetime = datetime.now()
                task.already_run_flag = True
                logger.warning(f"[SCHEDULE] Task '{task.name}' failed but marked as run to prevent infinite retries")
            
            # For message trigger tasks, ensure task state is set to failed
            # This prevents the task from being stuck in 'working' state
            if trigger_type == "message":
                try:
                    task.status.state = TaskState.failed
                    task.status.message = _create_message("agent", f"Task execution error: {e}")
                except Exception:
                    pass
                self._emit_task_status(task, "failed")
        finally:
            # Clean up Future reference - only clear if this is still the same future
            # or if we're handling a stale completion (don't interfere with new futures)
            if hasattr(task, 'future'):
                _should_clear_future = (
                    task.future is None  # No active future
                    or task.future is future  # This is our future
                    or _stale_completion  # We're ignoring stale, leave new future alone
                )
                if _should_clear_future:
                    task.future = None
                    logger.debug(f"[COMPLETE] Cleared Future reference for task {task.name}")
            
            # Clean up task state to prevent unbounded memory growth
            # _task_states stores per-task execution metadata that accumulates over time
            if not _stale_completion and task.id in self._task_states:
                _current_task_state = getattr(getattr(task, "status", None), "state", None)
                if _preserve_task_state or _current_task_state == TaskState.input_required:
                    logger.debug(f"[COMPLETE] Preserved task state for parked task {task.name}")
                else:
                    self._task_states.pop(task.id, None)
                    logger.debug(f"[COMPLETE] Cleared task state for task {task.name}")
            
            # Allow idle sleep once this task execution completes
            try:
                get_sleep_inhibitor().release()
            except Exception as _sleep_err:
                logger.warning(f"[COMPLETE] Failed to release sleep inhibitor for task {task.name}: {_sleep_err}")
    
    # ==================== Deprecated Methods ====================
    
    def launch_scheduled_run(self, task=None):
        """DEPRECATED: Use launch_unified_run(trigger_type="schedule")."""
        logger.warning("[DEPRECATED] Use launch_unified_run(trigger_type='schedule')")
        self.launch_unified_run(task2run=task, trigger_type="schedule")
    
    def launch_reacted_run(self, task2run=None):
        """DEPRECATED: Use launch_unified_run(trigger_type="message")."""
        logger.warning("[DEPRECATED] Use launch_unified_run(trigger_type='message')")
        self.launch_unified_run(task2run=task2run, trigger_type="message")
    
    def launch_interacted_run(self, task2run=None):
        """DEPRECATED: Use launch_unified_run(trigger_type="message")."""
        logger.warning("[DEPRECATED] Use launch_unified_run(trigger_type='message')")
        self.launch_unified_run(task2run=task2run, trigger_type="message")
    
    def update_event_handler(self, event_type="", event_queue=None):
        """DEPRECATED: No-op for backward compatibility."""
        pass
    
    async def step_task(self, task_id: str):
        """Step through a task one node at a time."""
        task = self.tasks[task_id]
        task.status.state = TaskState.working
        task.pause_event.set()
        
        async def one_step():
            async for step in task.graph.astream(task.state):
                task.metadata["state"] = step
                task.status.state = TaskState.unknown
                task.pause_event.clear()
                break
        
        task.task = asyncio.create_task(one_step())
    
    async def run_until_node(self, task_id: str, target_node: str):
        """Run task until reaching a specific node."""
        task = self.tasks[task_id]
        task.status.state = TaskState.working
        
        async def runner():
            async for step in task.graph.astream(task.state):
                await task.pause_event.wait()
                task.state = step
                if step.get("current_node") == target_node:
                    task.status.state = TaskState.input_required
                    task.pause_event.clear()
                    return
            task.status.state = TaskState.completed
        
        task.task = asyncio.create_task(runner())
    
    async def resume_on_external_event(self, task_id: str, injected_state: dict):
        """Resume task with external event data."""
        from a2a.types import Part
        task = self.tasks[task_id]
        if task.status.message:
            task.status.message.parts.append(Part(type="text", text=str(injected_state)))
        await self.resume_task(task_id)
