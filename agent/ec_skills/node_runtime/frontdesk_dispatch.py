"""Generic front-desk PreDispatch fast-path (extracted 2026-04-23).

Previously this lived as a ~645-line nested ``async def
_maybe_run_frontdesk_dispatch_fastpath(agent_obj)`` inside
``build_node._run_browser_use`` (original lines 9553-10198).  It
violated our "functions should be small and focused" guideline and
tied several site-agnostic concerns (monitor lookup, tab discovery,
round-robin recipient selection, send_chat dispatch) to several
Feige-specific concerns (chat-thread scrape, msg-id dedup, dom-echo
fallback).

The site-specific concerns now live in
``hooks/external/<site>/pre_dispatch_enrich.py`` plugins (see
``feige_chat/pre_dispatch_enrich.py`` for the reference
implementation).  This module owns **only** the generic skeleton and
discovers the plugin lazily by name from the ``preDispatch.site_plugin``
config field.

Design goals
------------

* Every function is short (< 120 LOC) and does one thing.
* All dependencies on ``build_node``-module-level state are injected
  via :class:`DispatchContext` so this module has zero core imports
  and can be unit-tested in isolation.
* The public entry-point is :func:`run`; :class:`DispatchConfig` and
  :class:`DispatchContext` are plain dataclasses.

Skip the extraction rationale? See Phase-4 refactor notes in the
project memory.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("eCan")

_PROMPT_ACTIONABLE_ITEMS_KEY = "_ecan_predispatch_actionable_items"
_PROMPT_ACTIONABLE_ITEMS_TS_KEY = "_ecan_predispatch_actionable_items_ts"
_PROMPT_ACTIONABLE_ITEMS_TTL_S = 10.0
_FEIGE_TYPING_LOCK_WAIT_S = 3.0
_FEIGE_TYPING_LOCK_POLL_S = 0.05
_TYPING_LOCK_ACTIVE_SENTINEL = "__typing_lock_active__"
# Self-rearm tunables (2026-05-11 fix for the "deferred customers never
# retried" gap).  When PreDispatch defers items because the typing-lock
# is held by an in-flight Q&A worker, the live-monitor never fires a
# re-trigger event (its ``emit_on=added`` rule with ``from_equals=customer``
# means our own outbound replies don't count, and the deferred customers'
# sidebar entries never change until they receive a new reply — which
# they're waiting on us for).  The reproduced 2026-05-11 12:00 run had
# 20 visible customers, 8 assigned, 11 deferred, 0 retried — only 8
# answers landed.  We schedule a single delayed asyncio.create_task
# that polls for typing-lock-stably-clear (queue drained), then re-runs
# ``run()`` on the same cfg/ctx so the deferred customers get a turn.
# Max-depth and ceiling caps protect against infinite rearm loops.
# 2026-05-19 reverted 30 → 12 along with the depth=1 revert in runner.py.
# The L2 bump was a follow-up to the depth=10 path that introduced
# starvation patterns under heavy queue contention; with depth=1
# restored, REARM rarely hits the cap.
_REARM_MAX_DEPTH = 12
_REARM_PER_ASSIGNED_S = 10.0    # rough per-customer typing+send time (observed ~8s)
_REARM_PER_DEFERRED_S = 3.0     # per-deferred proxy when assigned_count==0
_REARM_DRAIN_CEILING_S = 120.0  # absolute upper bound on a single rearm wait
_REARM_DRAIN_FLOOR_S = 20.0     # always wait at least this long before retry
_REARM_STABLE_CLEAR_S = 1.0     # typing-lock must be free this long → drained
_REARM_POLL_S = 0.3             # how often to poll typing-lock holder
_REARM_DEPTH_KEY = "_rearm_depth"
_REARM_TASK_KEY = "_rearm_task"
_REARM_CONTINUE_KEY = "_rearm_continue"
_REARM_LOOP: Any = None
_REARM_LOOP_THREAD: Any = None
_REARM_LOOP_LOCK = threading.Lock()

__all__ = [
    "DispatchConfig",
    "DispatchContext",
    "run",
]


# ─────────────────────────────── dataclasses ──────────────────────────────


@dataclass
class DispatchConfig:
    """Typed view of the ``inputs["preDispatch"]`` JSON blob.

    Build once per node invocation via :meth:`from_raw` then pass to
    :func:`run`.  Every field has a safe default so partial configs
    from the node editor still work.
    """

    enabled: bool = False
    source_monitor_label: str = ""
    require_url_path: str = ""
    allowed_statuses: set[str] = field(default_factory=lambda: {"ok", "empty", "no_match"})
    # item_fields — column-name aliases for the snapshot items.
    session_keys: list[str] = field(
        default_factory=lambda: ["session", "session_id", "customer_id"]
    )
    name_keys: list[str] = field(
        default_factory=lambda: ["customer_name", "name", "customer"]
    )
    chat_url_keys: list[str] = field(default_factory=lambda: ["chat_url"])
    chat_url_template: str = ""
    task_keywords: list[str] = field(default_factory=list)
    skill_keywords: list[str] = field(default_factory=list)
    flag_attr: str = "_ecan_frontdesk_dispatched_all"
    state_attr: str = "_ecan_frontdesk_dispatch_state"
    log_tag: str = "PreDispatch"
    fastpath_marker: str = "frontdesk_fastpath"
    history_prefix: str = "predispatch"
    assignment_extra_fields: list[str] = field(default_factory=list)
    site_plugin: str = ""  # "" → no enrichment; e.g. "feige_chat"

    @classmethod
    def from_raw(cls, raw: dict | None) -> "DispatchConfig":
        """Parse the node-editor JSON blob into a typed config."""
        if not isinstance(raw, dict):
            return cls()
        item_fields = raw.get("item_fields") or {}
        if not isinstance(item_fields, dict):
            item_fields = {}
        recip = raw.get("recipient_filter") or {}
        if not isinstance(recip, dict):
            recip = {}
        extra_fields = raw.get("assignment_extra_fields") or []
        if not isinstance(extra_fields, list):
            extra_fields = []
        allowed = raw.get("allowed_statuses") or ["ok", "empty", "no_match"]
        return cls(
            enabled=bool(raw.get("enabled", False)),
            source_monitor_label=str(raw.get("source_monitor_label") or "").strip(),
            require_url_path=str(raw.get("require_url_path") or "").strip(),
            allowed_statuses={str(s).strip().lower() for s in allowed if str(s).strip()},
            session_keys=[str(k) for k in (item_fields.get("session_id") or ["session", "session_id", "customer_id"])],
            name_keys=[str(k) for k in (item_fields.get("customer_name") or ["customer_name", "name", "customer"])],
            chat_url_keys=[str(k) for k in (item_fields.get("chat_url") or ["chat_url"])],
            chat_url_template=str(raw.get("chat_url_template") or ""),
            task_keywords=[str(k).lower() for k in (recip.get("task_keywords") or []) if str(k).strip()],
            skill_keywords=[str(k).lower() for k in (recip.get("skill_keywords") or []) if str(k).strip()],
            flag_attr=str(raw.get("dispatched_flag_attr") or "_ecan_frontdesk_dispatched_all"),
            state_attr=str(raw.get("dispatch_state_attr") or "_ecan_frontdesk_dispatch_state"),
            log_tag=str(raw.get("log_tag") or "PreDispatch"),
            fastpath_marker=str(raw.get("result_marker_key") or "frontdesk_fastpath"),
            history_prefix=str(raw.get("history_prefix") or "predispatch"),
            assignment_extra_fields=[str(k) for k in extra_fields],
            site_plugin=str(raw.get("site_plugin") or "").strip(),
        )


@dataclass
class DispatchContext:
    """Injected dependencies + mutable module-level state from
    ``build_node``.  Passed to :func:`run` so this module has no
    core imports (avoids circular imports + makes unit testing easy).
    """

    # Runtime identifiers.
    state: dict
    calling_agent_id: str
    node_name: str
    mainwin: Any
    scope_key: str
    # Shared dicts owned by ``build_node`` module scope.
    cached_browser_sessions: dict  # scope_key → BrowserSession
    dispatch_state_by_agent: dict  # mutated
    customer_last_dispatched_msg_id: dict  # mutated on success
    auto_dispatch_last_agent_reply: dict  # read-only (populated by HOT-PATH-B)
    # Inflight lock helpers (live in build_node; injected to avoid circular import).
    is_dispatch_inflight: Callable[[str], float]
    mark_dispatch_inflight: Callable[[str], None]
    clear_dispatch_inflight: Callable[[str], None]
    inflight_ttl_s: float
    # Pure string helpers.
    normalize_dispatch_identity_key: Callable[[str], str]
    normalize_reply_text: Callable[[str], str]
    # str.format_map-compatible dict subclass that swallows missing keys.
    safe_format_dict: type
    # Optional site-specific hooks.  ``feige_typing_holder_getter`` is
    # a zero-arg callable returning the current "who is currently
    # typing into Feige" customer-key (set by HOT-PATH-B); when set,
    # the feige_chat enrich plugin uses it to avoid stealing the
    # active Feige session during a concurrent reply (see race-guard
    # documented under ``feige_chat.typing_lock``).  ``None`` disables
    # the guard (acceptable for non-Feige sites).
    feige_typing_holder_getter: Callable[[], str] | None = None


# ─────────────────────────────────── helpers ────────────────────────────────


class _RearmHandle:
    def __init__(self) -> None:
        self.future: Any = None
        self.task: Any = None

    def done(self) -> bool:
        fut = self.future
        return bool(fut is not None and fut.done())

    def cancel(self) -> bool:
        fut = self.future
        if fut is None:
            return False
        return bool(fut.cancel())

    def __await__(self):
        async def _wait():
            while self.future is None:
                await asyncio.sleep(0.01)
            return await asyncio.wrap_future(self.future)

        return _wait().__await__()


def _ensure_rearm_loop() -> Any:
    global _REARM_LOOP
    global _REARM_LOOP_THREAD
    with _REARM_LOOP_LOCK:
        if (
            _REARM_LOOP is not None
            and getattr(_REARM_LOOP, "is_running", lambda: False)()
            and _REARM_LOOP_THREAD is not None
            and getattr(_REARM_LOOP_THREAD, "is_alive", lambda: False)()
        ):
            return _REARM_LOOP

        ready = threading.Event()
        holder: dict[str, Any] = {}

        def _thread_main() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            holder["loop"] = loop
            ready.set()
            try:
                loop.run_forever()
            finally:
                try:
                    loop.close()
                except Exception:
                    pass

        thread = threading.Thread(
            target=_thread_main,
            name="FeigePreDispatchRearm",
            daemon=True,
        )
        thread.start()
        if not ready.wait(timeout=2.0):
            raise RuntimeError("predispatch rearm loop did not start")
        _REARM_LOOP = holder["loop"]
        _REARM_LOOP_THREAD = thread
        return _REARM_LOOP


async def _detached_rearm_entry(
    handle: _RearmHandle,
    cfg: DispatchConfig,
    ctx: DispatchContext,
    agent_obj: Any,
    dispatch_state: dict,
    *,
    deferred_count: int,
    assigned_count: int,
) -> None:
    handle.task = asyncio.current_task()
    try:
        await _self_rearm_after_drain(
            cfg=cfg,
            ctx=ctx,
            agent_obj=agent_obj,
            dispatch_state=dispatch_state,
            deferred_count=deferred_count,
            assigned_count=assigned_count,
        )
    finally:
        if dispatch_state.get(_REARM_TASK_KEY) is handle:
            dispatch_state.pop(_REARM_TASK_KEY, None)
        handle.task = None


def _should_skip_for_event_type(state: dict, log_tag: str) -> bool:
    """PreDispatch is a customer-message fan-out; it must NOT run on
    agent-to-agent ``chat_message`` replies (those are HOT-PATH-B
    territory).  Running here would duplicate assignments because the
    resume scopes to a different cached browser session whose
    ``dispatch_state`` is empty.
    """
    try:
        evt = state.get("event_type") or state.get("event", {}).get("type") or ""
    except Exception:
        evt = ""
    if str(evt).strip().lower() == "chat_message":
        logger.info(
            f"[BrowserAutomation] {log_tag} skipped: event_type=chat_message "
            f"(agent-to-agent reply, handled by HOT-PATH-B; PreDispatch only "
            f"runs on customer browser_event)"
        )
        return True
    return False


def _event_type_from_state(state: dict) -> str:
    """Best-effort event type extraction across legacy/current state shapes."""
    if not isinstance(state, dict):
        return ""

    def _nested(obj: Any, *path: str) -> Any:
        cur = obj
        for key in path:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(key)
        return cur

    candidates = [
        state.get("event_type"),
        _nested(state, "event", "type"),
        _nested(state, "_event_envelope", "type"),
        _nested(state, "prompt_refs", "events", "event_type"),
        _nested(state, "prompt_refs", "events", "type"),
        _nested(state, "attributes", "browser_event", "event_type"),
        _nested(state, "attributes", "browser_event", "type"),
    ]
    for value in candidates:
        text = str(value or "").strip().lower()
        if text:
            return text
    return ""


def _is_browser_event_trigger(state: dict) -> bool:
    return _event_type_from_state(state) == "browser_event"


def _find_active_monitor(
    agent_obj, ctx: DispatchContext, cfg: DispatchConfig
) -> tuple[Any, dict, Any] | tuple[None, None, None]:
    """Locate an active ``EventMonitor`` whose label matches
    ``cfg.source_monitor_label`` on either the agent's live session or
    the cached session for this scope.  Returns
    ``(monitor_set, control_state, session)`` or ``(None, None, None)``.
    """
    browser_session = getattr(agent_obj, "browser_session", None)
    candidates = []
    for cand in (browser_session, ctx.cached_browser_sessions.get(ctx.scope_key)):
        if cand and cand not in candidates:
            candidates.append(cand)

    try:
        from agent.ec_skills.browser_use_extension.event_monitor_capability import (
            get_event_monitor_capability,
        )
    except Exception as exc:
        logger.warning(
            f"[BrowserAutomation] {cfg.log_tag} capability import failed: {exc}"
        )
        return None, None, None

    for cand in candidates:
        cap = get_event_monitor_capability(cand, create=False)
        monitor_set = cap.get_active_monitor_set() if cap else None
        if not monitor_set:
            continue
        for monitor in list(getattr(monitor_set, "monitors", []) or []):
            state = getattr(monitor, "state", None)
            mcfg = (state or {}).get("config") if isinstance(state, dict) else None
            if str(getattr(mcfg, "label", "") or "").strip() == cfg.source_monitor_label:
                return monitor_set, state, cand

    logger.info(
        f"[BrowserAutomation] {cfg.log_tag} skipped: no active monitor with "
        f"label={cfg.source_monitor_label!r} (scope={ctx.scope_key}, "
        f"candidates={len(candidates)})"
    )
    return None, None, None


def _validate_monitor_ready(control_state: dict, cfg: DispatchConfig) -> bool:
    """Check the monitor's last snapshot is in an allowed status AND
    (if required) on an allowed URL path.  Logs INFO and returns
    ``False`` when either check fails.
    """
    status = str(control_state.get("last_status") or "").strip().lower()
    current_url = str(control_state.get("last_current_url") or "").strip()
    if status not in cfg.allowed_statuses or (
        cfg.require_url_path and cfg.require_url_path not in current_url
    ):
        logger.info(
            f"[BrowserAutomation] {cfg.log_tag} skipped: monitor not ready "
            f"(status={status}, current_url={current_url}, "
            f"require_path={cfg.require_url_path!r})"
        )
        return False
    return True


def _monitor_state_detail(control_state: dict | None, cfg: DispatchConfig) -> str:
    if not isinstance(control_state, dict):
        return "no control_state"
    status = str(control_state.get("last_status") or "").strip().lower()
    current_url = str(control_state.get("last_current_url") or "").strip()
    return (
        f"status={status}, current_url={current_url}, "
        f"require_path={cfg.require_url_path!r}"
    )


def _get_prompt_actionable_fallback(state: dict) -> tuple[bool, list[dict]]:
    """Return same-invocation actionable items computed by the prompt hook.

    The prompt-build hook runs before this late PreDispatch hook. During
    Feige flood tests it can successfully compute actionable DOM rows, while
    the live monitor's control state is briefly ``starting`` by the time this
    hook asks for it. Use the prompt-hook rows as a short-lived fallback so
    transient monitor churn does not fall through into the slow browser-use
    LLM path.
    """
    if not isinstance(state, dict) or _PROMPT_ACTIONABLE_ITEMS_KEY not in state:
        return False, []
    raw_items = state.get(_PROMPT_ACTIONABLE_ITEMS_KEY)
    if not isinstance(raw_items, list):
        return False, []
    try:
        ts = float(state.get(_PROMPT_ACTIONABLE_ITEMS_TS_KEY) or 0.0)
    except Exception:
        ts = 0.0
    if ts <= 0.0 or (time.time() - ts) > _PROMPT_ACTIONABLE_ITEMS_TTL_S:
        return False, []
    return True, [dict(item) for item in raw_items if isinstance(item, dict)]


def _build_deferred_result(
    cfg: DispatchConfig,
    *,
    reason: str,
    detail: str = "",
    retry: bool = False,
) -> dict:
    payload = {
        "all_done": not retry,
        "work_done": False,
        "hot_path": True,
        "hot_path_type": "pre_dispatch_deferred",
        "reason": reason,
        "message": (
            f"{cfg.log_tag} deferred before LLM/browser-use fallback"
            + (f": {detail}" if detail else "")
        ),
    }
    if detail:
        payload["detail"] = detail
    if retry:
        payload["retry_pending"] = True
    return {
        "final": json.dumps(payload, ensure_ascii=False),
        "history": f"{cfg.history_prefix}:deferred:{reason}",
    }


def _current_feige_typing_holder(ctx: DispatchContext) -> str:
    getter = getattr(ctx, "feige_typing_holder_getter", None)
    if not callable(getter):
        return ""
    try:
        return str(getter() or "").strip()
    except Exception as exc:
        logger.debug(
            f"[BrowserAutomation] Feige typing-lock holder check failed: {exc}"
        )
        return ""


async def _wait_for_queue_drained(
    ctx: DispatchContext,
    cfg: DispatchConfig,
    *,
    deadline_s: float,
    stable_clear_s: float = _REARM_STABLE_CLEAR_S,
    poll_s: float = _REARM_POLL_S,
) -> bool:
    """Block until the typing-lock has been continuously free for
    ``stable_clear_s`` (queue drained) or until ``deadline_s`` elapses.

    Returns ``True`` when stably clear, ``False`` on deadline.  Used by
    the self-rearm task to know when it's safe to retry deferred
    customers without competing with an in-flight Q&A worker.
    """
    deadline = time.monotonic() + max(0.0, deadline_s)
    clear_since: float | None = None
    while time.monotonic() < deadline:
        holder = _current_feige_typing_holder(ctx)
        now = time.monotonic()
        if holder:
            clear_since = None
        else:
            if clear_since is None:
                clear_since = now
            elif (now - clear_since) >= stable_clear_s:
                logger.info(
                    f"[BrowserAutomation] {cfg.log_tag} rearm: typing-lock "
                    f"stably clear for {stable_clear_s:.1f}s — queue drained"
                )
                return True
        await asyncio.sleep(poll_s)
    holder = _current_feige_typing_holder(ctx)
    logger.info(
        f"[BrowserAutomation] {cfg.log_tag} rearm: drain wait expired after "
        f"{deadline_s:.1f}s (last holder={holder!r})"
    )
    return False


async def _self_rearm_after_drain(
    cfg: DispatchConfig,
    ctx: DispatchContext,
    agent_obj: Any,
    dispatch_state: dict,
    *,
    deferred_count: int,
    assigned_count: int,
) -> None:
    """Background coroutine that re-runs PreDispatch after the typing-lock
    queue drains, so customers deferred by ``typing_lock_active`` get a
    second chance without waiting for a customer-side message to wake
    up the live-monitor.

    Bounded by ``_REARM_MAX_DEPTH`` (per dispatch_state) so a chronic
    contention condition can't loop forever — each rearm increments the
    counter and bails out at the cap.  Successful rearms with no further
    deferrals reset the counter on the next normal run via
    :func:`_reset_rearm_depth_on_clean_run`.
    """
    try:
        while True:
            depth = int(dispatch_state.get(_REARM_DEPTH_KEY, 0)) + 1
            dispatch_state[_REARM_DEPTH_KEY] = depth
            if depth > _REARM_MAX_DEPTH:
                logger.warning(
                    f"[BrowserAutomation] {cfg.log_tag} rearm depth cap reached "
                    f"(depth={depth} max={_REARM_MAX_DEPTH}); leaving "
                    f"{deferred_count} deferred row(s) for the next live-monitor "
                    f"event to pick up"
                )
                return

            if assigned_count > 0:
                raw_estimate = float(assigned_count) * _REARM_PER_ASSIGNED_S
            else:
                raw_estimate = float(deferred_count) * _REARM_PER_DEFERRED_S
            drain_estimate_s = max(
                _REARM_DRAIN_FLOOR_S,
                min(_REARM_DRAIN_CEILING_S, raw_estimate),
            )
            logger.info(
                f"[BrowserAutomation] {cfg.log_tag} rearm scheduled: "
                f"depth={depth} deferred_count={deferred_count} "
                f"assigned_count={assigned_count} "
                f"drain_estimate_s={drain_estimate_s:.1f}"
            )
            dispatch_state.pop(_REARM_CONTINUE_KEY, None)
            await _wait_for_queue_drained(ctx, cfg, deadline_s=drain_estimate_s)
            logger.info(
                f"[BrowserAutomation] {cfg.log_tag} rearm: re-running "
                f"PreDispatch (depth={depth})"
            )
            await run(cfg, ctx, agent_obj)
            next_request = dispatch_state.pop(_REARM_CONTINUE_KEY, None)
            if not isinstance(next_request, dict):
                return
            deferred_count = int(next_request.get("deferred_count") or 0)
            assigned_count = int(next_request.get("assigned_count") or 0)
    except asyncio.CancelledError:
        # If the runner is shutting down our task gets cancelled — that's
        # the right behaviour, just exit quietly.
        logger.info(
            f"[BrowserAutomation] {cfg.log_tag} rearm cancelled (depth={depth})"
        )
        raise
    except Exception as exc:
        logger.warning(
            f"[BrowserAutomation] {cfg.log_tag} rearm depth={depth} "
            f"failed: {type(exc).__name__}: {exc}"
        )
    finally:
        # Clear the task reference so a later cycle can schedule again.
        if dispatch_state.get(_REARM_TASK_KEY) is asyncio.current_task():
            dispatch_state.pop(_REARM_TASK_KEY, None)
        dispatch_state.pop(_REARM_CONTINUE_KEY, None)


def _maybe_schedule_self_rearm(
    cfg: DispatchConfig,
    ctx: DispatchContext,
    agent_obj: Any,
    dispatch_state: dict,
    *,
    deferred_rows: list,
    assigned_rows: list,
) -> None:
    """Idempotently schedule a single in-flight rearm task per dispatch_state.

    Returns silently when there's nothing to do (no deferrals, or a
    rearm task is already running, or the depth cap is hit).

    Note: ``assigned_rows`` is allowed to be empty.  When a previous
    cycle's queue is still draining the typing-lock, the current cycle
    may produce 0 new assignments but still have deferred rows that
    need to be retried after the queue drains; loosened from the
    original ``deferred_rows AND assigned_rows`` condition because the
    2026-05-11 12:23:12 rearm chain broke exactly here (cycle had
    assigned=0 deferred=13, no rearm fired, 13 customers stuck).
    """
    if not deferred_rows:
        return
    # 2026-05-19 Fix C: gated behind tunable FRONTDESK_REARM_ENABLED
    # (per-node override → env ECAN_FRONTDESK_REARM_ENABLED →
    # DEFAULT_FRONTDESK_REARM_ENABLED = False).  v0.9.79 behaviour was
    # OFF — deferred customers wait for the next actual sidebar DOM
    # diff.  Commit 9299db8eb "fix flood test" added this REARM
    # mechanism to chase deferred rows by polling typing-lock until
    # it's stably clear, then re-running PreDispatch (up to 12 chained
    # levels).  Combined with B1 force-emit, this multiplied PreDispatch
    # firing rate under flood and contributed to the duplicate-dispatch
    # cascade documented in the 2026-05-19 customer log.
    try:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.tunables import (
            resolve_bool as _resolve_bool_rearm,
            DEFAULT_FRONTDESK_REARM_ENABLED as _DEFAULT_REARM,
        )
        _state_for_tunables = getattr(ctx, "state", None) if ctx is not None else None
        _rearm_enabled = _resolve_bool_rearm(
            "FRONTDESK_REARM_ENABLED", _DEFAULT_REARM, _state_for_tunables
        )
    except Exception:
        _rearm_enabled = False
    if not _rearm_enabled:
        logger.debug(
            f"[BrowserAutomation] {cfg.log_tag} rearm disabled by tunable — "
            f"leaving {len(deferred_rows)} deferred row(s) for the next "
            f"live-monitor event"
        )
        return
    existing = dispatch_state.get(_REARM_TASK_KEY)
    if existing is not None and not existing.done():
        current_handle = getattr(existing, "task", None)
        try:
            current_task = asyncio.current_task()
        except RuntimeError:
            current_task = None
        if existing is current_task or (
            current_task is not None and current_handle is current_task
        ):
            dispatch_state[_REARM_CONTINUE_KEY] = {
                "deferred_count": len(deferred_rows),
                "assigned_count": len(assigned_rows),
            }
            logger.info(
                f"[BrowserAutomation] {cfg.log_tag} rearm chaining follow-up "
                f"for {len(deferred_rows)} deferred row(s)"
            )
            return
        else:
            logger.info(
                f"[BrowserAutomation] {cfg.log_tag} rearm already in flight; "
                f"skipping duplicate scheduling for {len(deferred_rows)} "
                f"deferred row(s)"
            )
            return
    if int(dispatch_state.get(_REARM_DEPTH_KEY, 0)) >= _REARM_MAX_DEPTH:
        logger.info(
            f"[BrowserAutomation] {cfg.log_tag} rearm depth cap reached; "
            f"deferring {len(deferred_rows)} row(s) to the next live-monitor "
            f"event"
        )
        return
    try:
        loop = _ensure_rearm_loop()
        handle = _RearmHandle()
        future = asyncio.run_coroutine_threadsafe(
            _detached_rearm_entry(
                handle,
                cfg=cfg,
                ctx=ctx,
                agent_obj=agent_obj,
                dispatch_state=dispatch_state,
                deferred_count=len(deferred_rows),
                assigned_count=len(assigned_rows),
            ),
            loop,
        )
        handle.future = future
        dispatch_state[_REARM_TASK_KEY] = handle
        logger.info(
            f"[BrowserAutomation] {cfg.log_tag} rearm detached worker armed "
            f"for {len(deferred_rows)} deferred row(s)"
        )
    except Exception as exc:
        logger.warning(
            f"[BrowserAutomation] {cfg.log_tag} rearm scheduling failed: "
            f"{type(exc).__name__}: {exc}"
        )


def _reset_rearm_depth_on_clean_run(dispatch_state: dict) -> None:
    """Drop the rearm depth counter when a run completes without deferrals,
    so a subsequent contention event starts the depth counter from zero
    instead of inheriting the previous chain.
    """
    if dispatch_state.get(_REARM_DEPTH_KEY):
        dispatch_state[_REARM_DEPTH_KEY] = 0


async def _wait_for_feige_typing_lock_clear(
    ctx: DispatchContext,
    cfg: DispatchConfig,
    *,
    wait_s: float = _FEIGE_TYPING_LOCK_WAIT_S,
) -> str:
    """Return empty when Feige is safe to scrape; otherwise the holder.

    PreDispatch reads and clicks the same Feige browser session used by
    response delivery.  If a reply is being typed, scraping sidebar rows
    would either steal focus or consume stale previews.  Wait briefly for
    normal sends, then defer so the loop can retry instead of marking the
    snapshot handled.
    """
    holder = _current_feige_typing_holder(ctx)
    if not holder:
        return ""
    deadline = time.monotonic() + max(0.0, wait_s)
    while time.monotonic() < deadline:
        await asyncio.sleep(_FEIGE_TYPING_LOCK_POLL_S)
        holder = _current_feige_typing_holder(ctx)
        if not holder:
            logger.info(
                f"[BrowserAutomation] {cfg.log_tag} resumed after Feige "
                "typing lock cleared"
            )
            return ""
    logger.info(
        f"[BrowserAutomation] {cfg.log_tag} deferred: Feige typing lock "
        f"held by {holder!r}; not scraping sidebar rows while a reply is "
        "being typed"
    )
    return holder


def _fallback_session(agent_obj, ctx: DispatchContext):
    session = getattr(agent_obj, "browser_session", None)
    if session:
        return session
    try:
        return ctx.cached_browser_sessions.get(ctx.scope_key)
    except Exception:
        return None


def _resolve_dispatch_state(
    session, ctx: DispatchContext, cfg: DispatchConfig
) -> dict:
    """Get-or-create the shared ``assigned_sessions`` / ``opened_tabs``
    state dict for this (agent, node).  Mirrored onto the session as
    an attribute so legacy attribute-based reads still work.
    """
    key = (str(ctx.calling_agent_id or ""), str(ctx.node_name or ""), cfg.state_attr)
    state = ctx.dispatch_state_by_agent.get(key)
    if not isinstance(state, dict):
        state = {"opened_tabs": {}, "assigned_sessions": {}}
        ctx.dispatch_state_by_agent[key] = state
    setattr(session, cfg.state_attr, state)
    return state


def _extract_actionable_items(
    raw_items: list, cfg: DispatchConfig
) -> list[dict]:
    """Parse the monitor snapshot rows into minimal dispatch entries.

    Items missing a resolvable ``session_id`` are dropped.  URLs are
    either picked from configured field names or rendered from the
    ``chat_url_template`` if none of the field names held a value.
    """
    def _pick_first(item: dict, keys: list[str]) -> str:
        for k in keys:
            v = item.get(k)
            if v is None:
                continue
            s = str(v).strip()
            if s:
                return s
        return ""

    actionable: list[dict] = []
    for item in raw_items or []:
        if not isinstance(item, dict):
            continue
        try:
            from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.system_message_filter import (
                first_system_row_match,
            )
            system_reason = first_system_row_match(item)
            if system_reason:
                pending_marker = any(
                    str(item.get(k) or "").strip()
                    for k in (
                        "pending_timer",
                        "unread_badge",
                        "unread",
                        "needs_action",
                    )
                )
                if not pending_marker:
                    logger.info(
                        f"[BrowserAutomation] {cfg.log_tag} filtered system row "
                        f"before dispatch reason={system_reason!r} "
                        f"customer={item.get('customer_name')!r} "
                        f"last_message={str(item.get('last_message') or '')[:80]!r}"
                    )
                    continue
                logger.info(
                    f"[BrowserAutomation] {cfg.log_tag} keeping pending "
                    f"system-looking row for thread enrichment "
                    f"reason={system_reason!r} customer={item.get('customer_name')!r}"
                )
                # 2026-05-25 mt040A: stamp the trigger reason on the item so
                # _scrape_and_override_last_message can detect "the only
                # reason we're dispatching is a system event, not a real
                # customer message" and defer.  Live trace 2026-05-25
                # 12:34:06 J14N9: store_auto_greeting kept-for-enrichment
                # triggered a dispatch on a pre-existing product card,
                # bot hallucinated 透气 answer (customer never asked),
                # that false reply then tripped mt017's HUMAN-INTERVENTION
                # for 2 min → customer ignored 7+ min.  Stamp is read by
                # enrich's mt040A defer check.
                item["_ecan_system_row_kept"] = system_reason
        except Exception as exc:
            logger.debug(
                f"[BrowserAutomation] {cfg.log_tag} system-row filter failed: {exc}"
            )
        session_id = _pick_first(item, cfg.session_keys)
        if not session_id:
            continue
        customer_name = _pick_first(item, cfg.name_keys)
        chat_url = _pick_first(item, cfg.chat_url_keys)
        if not chat_url and cfg.chat_url_template:
            try:
                from agent.ec_skills.build_node import _SafeFormatDict  # noqa: WPS433 — deferred to avoid top-level cycle
                chat_url = cfg.chat_url_template.format_map(_SafeFormatDict({
                    "session_id": session_id,
                    "customer_id": session_id,
                    "customer_name": customer_name,
                }))
            except Exception:
                chat_url = ""
        entry = {
            "customer_id": session_id,
            "session_id": session_id,
            "customer_name": customer_name,
            "chat_url": chat_url,
            # Preserve the original sidebar last_message for the enrich plugin's override.
            "last_message": str(item.get("last_message") or ""),
            # Preserve the live-monitor's ``identity_key`` (format:
            # ``<customer_name>|<last_message>``) so successful fastpath
            # dispatches can stamp ``_dispatched_identity_keys`` and the
            # later AUTO-DISPATCH filter in actionable_items.py can
            # recognise this customer as already-dispatched.  Without
            # this, the same customer message gets dispatched twice —
            # once via the fastpath here and once via the LLM-side
            # AUTO-DISPATCH inside ``_run_browser_use`` — causing
            # duplicate worker invocations and racing replies.
            "identity_key": str(item.get("identity_key") or ""),
        }
        for pending_key in (
            "pending_timer",
            "unread_badge",
            "unread",
            "needs_action",
        ):
            if pending_key in item:
                entry[pending_key] = item.get(pending_key)
        for extra_key in cfg.assignment_extra_fields:
            ek = str(extra_key)
            if ek and ek not in entry and ek in item:
                entry[ek] = item.get(ek)
        actionable.append(entry)
    return actionable


async def _open_tab_for_session(
    session,
    chat_url: str,
    session_id: str,
    opened_tabs: dict,
    log_tag: str,
) -> str:
    """Find a tab already pointed at *chat_url* or open a new one via
    CDP ``NavigateToUrlEvent``.  Returns the target id or ``""`` on
    failure.  Caches successful target ids in *opened_tabs* so repeated
    dispatches for the same session don't re-open.
    """
    cached = opened_tabs.get(session_id) or ""
    if cached:
        return cached

    sm = getattr(session, "session_manager", None)
    all_targets = sm.get_all_targets() if sm else {}

    def _find_target(url: str) -> str:
        for tid, tgt in (all_targets or {}).items():
            if getattr(tgt, "target_type", "") not in ("page", "tab"):
                continue
            if str(getattr(tgt, "url", "") or "").strip() == url:
                return str(tid or "")
        return ""

    tab_id = _find_target(chat_url) if chat_url else ""
    if tab_id:
        opened_tabs[session_id] = tab_id
        return tab_id
    if not chat_url:
        return ""

    try:
        from browser_use.browser.events import NavigateToUrlEvent
        await session.event_bus.dispatch(NavigateToUrlEvent(url=chat_url, new_tab=True))
        await asyncio.sleep(0.8)
        sm2 = getattr(session, "session_manager", None)
        all_targets2 = sm2.get_all_targets() if sm2 else {}
        for tid2, tgt2 in (all_targets2 or {}).items():
            if getattr(tgt2, "target_type", "") not in ("page", "tab"):
                continue
            if str(getattr(tgt2, "url", "") or "").strip().rstrip("/") == chat_url.rstrip("/"):
                tab_id = str(tid2)
                break
        if tab_id:
            opened_tabs[session_id] = tab_id
            logger.info(
                f"[BrowserAutomation] {log_tag} opened tab "
                f"tab_id=...{tab_id[-6:]} for session={session_id}"
            )
        return tab_id
    except Exception as exc:
        logger.warning(
            f"[BrowserAutomation] {log_tag} failed to open tab for "
            f"session={session_id}: {exc}"
        )
        return ""


def _resolve_recipient_agents(
    cfg: DispatchConfig,
    ctx: DispatchContext,
    sender_agent_id: str,
    dispatch_state: dict,
) -> list[str]:
    """Dynamic round-robin recipient discovery with per-dispatch_state
    caching.  Excludes the sender + disabled agents.  When a
    recipient_filter is configured, non-matching agents are excluded
    and an empty result aborts dispatch rather than silently falling
    back to "all live agents".
    """
    cached = dispatch_state.get("service_agents")
    if cached:
        return list(cached)

    try:
        from agent.mcp.server.chat_utils.chat_tools import list_chat_agents
    except Exception as exc:
        logger.warning(
            f"[BrowserAutomation] {cfg.log_tag} list_chat_agents import failed: {exc}"
        )
        return []

    all_agents = list_chat_agents(ctx.mainwin, {"exclude_self": sender_agent_id}).get("agents", [])

    def _is_live(a: dict) -> bool:
        s = str(a.get("status") or "").strip().lower()
        return bool(s) and s != "disabled"

    live = [a for a in all_agents if _is_live(a)]
    dropped = [a.get("id", "")[-8:] for a in all_agents if not _is_live(a)]
    if dropped:
        logger.info(
            f"[BrowserAutomation] {cfg.log_tag} excluded {len(dropped)} "
            f"non-live agents from recipient pool: {dropped}"
        )

    def _matches(a: dict) -> bool:
        if cfg.task_keywords:
            tasks = [str(t).lower() for t in a.get("tasks", [])]
            if any(any(kw in t for t in tasks) for kw in cfg.task_keywords):
                return True
        if cfg.skill_keywords:
            skills = [str(s).lower() for s in a.get("skills", [])]
            if any(any(kw in s for s in skills) for kw in cfg.skill_keywords):
                return True
        return False

    has_filter = bool(cfg.task_keywords or cfg.skill_keywords)
    if has_filter:
        service = [a for a in live if _matches(a)]
        if not service:
            logger.warning(
                f"[BrowserAutomation] {cfg.log_tag} no live agents match "
                f"recipient_filter (task_keywords={cfg.task_keywords}, "
                f"skill_keywords={cfg.skill_keywords}); live_pool="
                f"{[a['id'][-8:] for a in live]}. Aborting dispatch — "
                f"configure recipient_filter to match an enabled agent's "
                f"task or skill."
            )
            return []
    else:
        service = list(live)

    ids = [a["id"] for a in service]
    dispatch_state["service_agents"] = ids
    dispatch_state.setdefault("rr_index", 0)
    logger.info(
        f"[BrowserAutomation] {cfg.log_tag} discovered {len(service)} "
        f"recipient agents: {[a['id'][-8:] for a in service]}"
    )
    return ids


def _load_enrich_plugin(name: str) -> Callable | None:
    """Resolve a site-specific enrichment plugin by short name.

    Empty name → no plugin (pass-through).  Unknown name → logs WARN
    and returns ``None`` so dispatch proceeds without enrichment
    (preferable to hard-failing).
    """
    if not name:
        return None
    if name == "feige_chat":
        try:
            from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.pre_dispatch_enrich import (
                enrich_item,
            )
            logger.info(
                "[BrowserAutomation] PreDispatch enrich plugin loaded: "
                "feige_chat.pre_dispatch_enrich.enrich_item"
            )
            return enrich_item
        except Exception as exc:
            logger.warning(
                f"[BrowserAutomation] PreDispatch failed to import "
                f"feige_chat.pre_dispatch_enrich: {exc}"
            )
            return None
    logger.warning(
        f"[BrowserAutomation] PreDispatch unknown site_plugin={name!r}; "
        f"proceeding without enrichment"
    )
    return None


def _build_assignment_payload(item: dict, tab_id: str, cfg: DispatchConfig) -> dict:
    """Shape the JSON body of the ``send_chat`` dispatch call."""
    payload = {
        "customer_id": item["customer_id"],
        "session_id": item["session_id"],
        "chat_url": item.get("chat_url", ""),
    }
    if tab_id:
        payload["tab_id"] = tab_id
    if item.get("customer_name"):
        payload["customer_name"] = item["customer_name"]
    # ── Fix C: Q&A-compatible payload ────────────────────────────────
    # Some recipients of this fastpath dispatch are Q&A workers (e.g.
    # ``飞鸽客户应答``) whose contract requires ``latest_message`` — the
    # customer's actual original message text — so the worker can answer
    # the customer's question.  Without it the worker falls back to a
    # generic "请详细描述一下" clarification template and the customer
    # never gets a real answer (the LLM-driven ``bu_send_chat`` path
    # provides this field correctly via Fix A in extension_tools_service,
    # but this fastpath bypasses ``bu_send_chat`` and so was missing it).
    #
    # ``item["last_message"]`` is populated by ``_parse_dispatch_items``
    # from the monitor snapshot's ``last_message`` field.  We only set
    # ``latest_message`` when the source value is non-empty so we don't
    # signal a Q&A dispatch with a blank value (which the worker prompt
    # treats as "missing").
    last_msg = str(item.get("last_message") or "").strip()
    if last_msg:
        payload["latest_message"] = last_msg
    source_msg_id = str(
        item.get("latest_message_msg_id")
        or item.get("source_customer_msg_id")
        or ""
    ).strip()
    if source_msg_id:
        payload["latest_message_msg_id"] = source_msg_id
    # ── Multimodal: customer-attached images ─────────────────────────
    # The hot-path scraper (``feige_chat.pre_dispatch_v2`` /
    # ``pre_dispatch_enrich``) populates ``item["last_message_attachments"]``
    # with a list of dicts ``{"kind": "image", "url": "...", "data_uri":
    # "data:image/...;base64,...", "alt": "..."}`` — ``data_uri`` present
    # on successful eager-fetch, ``fetch_error`` present on fallback.
    # We forward the list verbatim so the Q&A worker side can decide
    # how to surface it to its LLM (vision content parts when the model
    # supports vision; descriptive text-only fallback otherwise).
    atts = item.get("last_message_attachments")
    if isinstance(atts, list) and atts:
        raw_attachment_count = len(atts)
        # Defensive shallow copy + filter to JSON-serialisable dicts so
        # a malformed entry can't poison the send_chat envelope.
        cleaned: list[dict] = []
        try:
            from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.image_store import (
                compact_attachment,
            )
        except Exception:
            compact_attachment = None
        for a in atts:
            if isinstance(a, dict) and (a.get("data_uri") or a.get("image_ref") or a.get("url")):
                cleaned.append(compact_attachment(a) if callable(compact_attachment) else dict(a))
        if cleaned:
            image_ref_count = sum(1 for a in cleaned if a.get("image_ref"))
            stripped_count = sum(1 for a in cleaned if a.get("data_uri_stripped"))
            total_bytes = sum(int(a.get("byte_len") or 0) for a in cleaned)
            logger.info(
                "[data-uri-mitigation] frontdesk_payload_attachments_compacted "
                "customer=%r raw_count=%d kept=%d image_refs=%d stripped=%d total_bytes=%d",
                item.get("customer_name") or item.get("customer_id") or item.get("session_id"),
                raw_attachment_count,
                len(cleaned),
                image_ref_count,
                stripped_count,
                total_bytes,
            )
            payload["latest_message_attachments"] = cleaned
    for extra_key in cfg.assignment_extra_fields:
        ek = str(extra_key)
        if ek and ek in item and ek not in payload:
            payload[ek] = item.get(ek)
    # 2026-05-27 mt050J — forward prior customer message previews
    # (mt050E logic, originally only wired into actionable_items.py's
    # auto-dispatch).  The PreDispatch path (this file) is what
    # production actually runs — the auto-dispatch path almost never
    # fires.  Live trace 2026-05-27 showed ``customer_recent_messages``
    # NEVER appeared in any dispatch payload because mt050E was on the
    # wrong code path.
    try:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.actionable_items import (
            _get_recent_messages as _mt050j_get_recent,
            _append_recent_message as _mt050j_append_recent,
        )
        _mt050j_cust_id = str(
            payload.get("customer_id")
            or payload.get("customer_name")
            or ""
        ).strip()
        if _mt050j_cust_id:
            _mt050j_prior = _mt050j_get_recent(_mt050j_cust_id)
            if _mt050j_prior:
                payload["customer_recent_messages"] = _mt050j_prior
            # Append the CURRENT message preview so the NEXT dispatch
            # for this customer (whether via PreDispatch or auto-
            # dispatch) carries it in turn.  Done after the read so the
            # current turn's payload only carries PRIOR messages — no
            # duplication with ``latest_message``.
            _mt050j_text = str(
                payload.get("latest_message")
                or payload.get("last_message")
                or ""
            ).strip()
            if _mt050j_text:
                _mt050j_append_recent(_mt050j_cust_id, _mt050j_text)
    except Exception as _mt050j_err:
        logger.debug(
            f"[BrowserAutomation] mt050J recent-messages forward failed "
            f"(non-fatal): {_mt050j_err}"
        )
    return payload


async def _dispatch_one_item(
    item: dict,
    *,
    session,
    ctx: DispatchContext,
    cfg: DispatchConfig,
    dispatch_state: dict,
    enrich_fn: Callable | None,
    sender_agent_id: str,
    service_agent_ids: list[str],
) -> tuple[str, str, str]:
    """Per-item pipeline: tab open → enrich → dedup → send_chat →
    bookkeeping.

    Returns ``(opened_row, assigned_row, failure_row)`` where each
    slot is either a descriptive string or ``""``.  The caller
    aggregates these into the final fastpath payload.
    """
    session_id = item["session_id"]
    chat_url = item.get("chat_url", "")
    log_tag = cfg.log_tag
    opened_tabs = dispatch_state.setdefault("opened_tabs", {})
    assigned_sessions = dispatch_state.setdefault("assigned_sessions", {})

    # Open tab first — instant, deterministic, costs no LLM tokens.
    tab_id = await _open_tab_for_session(
        session, chat_url, session_id, opened_tabs, log_tag
    )
    opened_row = session_id

    customer_key = ctx.normalize_dispatch_identity_key(
        item.get("customer_name") or item.get("customer_id") or session_id or ""
    )

    # Cross-scope dispatch-inflight guard (the single source of truth
    # for cross-agent dedup — per-dispatch_state.assigned_sessions is
    # not shared across scopes).
    #
    # IMPORTANT (race fix 2026-04-27): we **mark** inflight immediately
    # after passing the check, BEFORE the (slow) site-specific scrape
    # runs.  Previously the mark happened only after enrich + RR pick
    # (~500 ms-2 s later for Feige), leaving a wide window where
    # multiple parallel "新消息" events for the same customer all
    # passed the check, all did their scrape, and all dispatched —
    # resulting in 3 Q&A worker invocations within 4 s and the wrong
    # (oldest, stalest) reply being typed (observed live 2026-04-27
    # 10:33:01-05 for customer `sc`).
    #
    # Any early-return BELOW this point MUST release the lock — see
    # the explicit ``ctx.clear_dispatch_inflight(customer_key)`` calls
    # along each non-success path.
    try:
        inflight_age = ctx.is_dispatch_inflight(customer_key)
        if inflight_age > 0:
            current_text = str(
                item.get("last_message")
                or item.get("latest_message")
                or item.get("message")
                or ""
            )
            current_norm = ctx.normalize_reply_text(current_text) if current_text else ""
            assigned = assigned_sessions.get(session_id)
            prior_text = ""
            if isinstance(assigned, dict):
                prior_text = str(
                    assigned.get("latest_message")
                    or assigned.get("last_message")
                    or assigned.get("source_latest_message")
                    or ""
                )
            prior_norm = ctx.normalize_reply_text(prior_text) if prior_text else ""
            # 2026-05-19 Fix A: bot-reply DOM-echo guard for the inflight
            # supersede path.  Mirror of the same fix in
            # pre_dispatch_enrich._check_dom_echo_fallback (b).  Without
            # this, the sidebar last_message updating to OUR own reply
            # text (Feige rendering the outbound bubble on the
            # customer's side) trips the "current_norm != prior_norm"
            # branch — supersede fires, inflight is cleared, and a
            # fresh duplicate dispatch goes out to a Q&A worker.  The
            # 2026-05-19 21:11 customer trace had packet "这件穿了会不
            # 会过敏" dispatched 5× via exactly this race.
            last_reply_norm = ""
            try:
                _last_reply_cache = ctx.auto_dispatch_last_agent_reply
            except Exception:
                _last_reply_cache = None
            if _last_reply_cache:
                last_reply_raw = str(
                    _last_reply_cache.get(customer_key, "") or ""
                )
                if last_reply_raw:
                    try:
                        last_reply_norm = ctx.normalize_reply_text(last_reply_raw)
                    except Exception:
                        last_reply_norm = ""
            if (
                last_reply_norm
                and current_norm
                and current_norm == last_reply_norm
            ):
                logger.info(
                    f"[BrowserAutomation] {log_tag} inflight bot-reply-"
                    f"echo skip session={session_id!r} cust={customer_key!r} "
                    f"(sidebar text matches our last reply — DOM-echo, "
                    f"not a new customer turn; age={inflight_age:.1f}s, "
                    f"echo={current_text[:80]!r})"
                )
                return opened_row, "", ""
            # Multi-slot recent-reply ledger: also block supersede when
            # the sidebar echoes any of our recently-typed messages
            # (real reply OR placeholder).  Single-slot last_reply_norm
            # above misses placeholders typed after the real reply.
            try:
                from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.dispatch_state import (
                    matches_recent_agent_reply as _matches_recent_reply,
                )
            except Exception:
                _matches_recent_reply = None
            if (
                _matches_recent_reply is not None
                and current_text
                and _matches_recent_reply(customer_key, current_text)
            ):
                logger.info(
                    f"[BrowserAutomation] {log_tag} inflight recent-echo "
                    f"skip session={session_id!r} cust={customer_key!r} "
                    f"(sidebar text matches a recent typed message — DOM-echo "
                    f"of real reply or placeholder; age={inflight_age:.1f}s, "
                    f"echo={current_text[:80]!r})"
                )
                return opened_row, "", ""
            # 2026-05-23 mt028: back-stop dom-echo guards with the no-TTL
            # typed-text set and the per-process baseline text from
            # mt021/mt028.  These catch the cases the TTL'd
            # recent_agent_replies ledger misses: process just
            # restarted (ledger empty) but yesterday's agent bubble
            # still in chat DOM.  Without these, the 2026-05-22 13:46
            # flood test cascaded 客户16/18/19 into 3-5 wasted dispatches
            # each because supersede fired on stale yesterday-text.
            if current_text:
                try:
                    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
                        human_intervention as _hi_dom,
                    )
                    _baseline_txt = _hi_dom.get_baseline_text(customer_key)
                    if _baseline_txt and current_text.strip() == _baseline_txt.strip():
                        logger.info(
                            f"[BrowserAutomation] {log_tag} inflight baseline-text "
                            f"skip session={session_id!r} cust={customer_key!r} "
                            f"(sidebar text matches mt028 pre-existing baseline; "
                            f"echo={current_text[:80]!r})"
                        )
                        return opened_row, "", ""
                    if _hi_dom.is_known_typed_text(customer_key, current_text):
                        logger.info(
                            f"[BrowserAutomation] {log_tag} inflight typed-text "
                            f"skip session={session_id!r} cust={customer_key!r} "
                            f"(sidebar text matches a bubble WE typed earlier; "
                            f"echo={current_text[:80]!r})"
                        )
                        return opened_row, "", ""
                except Exception:
                    pass
            if assigned and current_norm and prior_norm and current_norm != prior_norm:
                logger.info(
                    f"[BrowserAutomation] {log_tag} inflight supersede "
                    f"session={session_id!r} cust={customer_key!r} "
                    f"(new sidebar text differs from prior assignment; "
                    f"age={inflight_age:.1f}s, current={current_text[:80]!r}, "
                    f"prior={prior_text[:80]!r})"
                )
                try:
                    ctx.clear_dispatch_inflight(customer_key)
                except Exception as clear_exc:
                    logger.debug(
                        f"[BrowserAutomation] {log_tag} inflight supersede "
                        f"clear failed for cust={customer_key!r}: {clear_exc}"
                    )
                # 2026-05-21 Fix A: cancel the orphaned placeholder timer
                # for the superseded turn.  Without this, the phantom
                # dispatch (e.g. PreDispatch mis-scraped an old agent
                # reply as a customer msg, dispatched it to Q&A which
                # never sends a useful reply) leaves its timer running.
                # That timer fires its full 3 placeholders AFTER the
                # real turn's own timer also fires its 3 → 6 placeholders
                # per customer (客户01-12 trace 01:02:35-01:03:18).  The
                # old src_msg_id lives in the assignment payload.
                try:
                    _prior_src_msg_id = ""
                    if isinstance(assigned, dict):
                        _prior_src_msg_id = str(
                            assigned.get("latest_message_msg_id") or ""
                        )
                    if _prior_src_msg_id:
                        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
                            placeholder_timer as _ph_timer_sup,
                        )
                        if _ph_timer_sup.cancel(customer_key, _prior_src_msg_id):
                            logger.info(
                                f"[BrowserAutomation] {log_tag} inflight "
                                f"supersede cancelled orphan placeholder "
                                f"timer for cust={customer_key!r} "
                                f"old_src_msg_id={_prior_src_msg_id!r}"
                            )
                    # 2026-05-27 mt050K-(a) — also broad-cancel ALL
                    # active timers for the customer.  The targeted
                    # cancel above only handles the timer keyed on
                    # ``assigned.latest_message_msg_id``; if the prior
                    # turn was a different shape (card-turn template
                    # msg_id vs text-turn UUID), the targeted cancel
                    # misses it and the stale timer fires its
                    # placeholder for the wrong turn.  Live trace
                    # 2026-05-27 15:41:14: placeholder for the 15:40:58
                    # card turn fired 1 s after the 15:41:13 text-turn
                    # dispatch superseded it.  cancel_any_for_customer
                    # is idempotent + cheap, so we belt-and-braces
                    # broad-cancel here even when the targeted cancel
                    # already succeeded.
                    try:
                        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
                            placeholder_timer as _ph_timer_broad,
                        )
                        _broad_cancelled = _ph_timer_broad.cancel_any_for_customer(
                            customer_key,
                        )
                        if _broad_cancelled:
                            logger.info(
                                f"[BrowserAutomation] {log_tag} mt050K "
                                f"broad-cancel removed {_broad_cancelled} "
                                f"placeholder timer(s) for cust="
                                f"{customer_key!r} on supersede"
                            )
                    except Exception as _ph_bcx:
                        logger.debug(
                            f"[BrowserAutomation] {log_tag} mt050K "
                            f"broad-cancel failed (non-fatal): {_ph_bcx}"
                        )
                except Exception as _ph_cx:
                    logger.debug(
                        f"[BrowserAutomation] {log_tag} supersede "
                        f"placeholder-cancel failed (non-fatal): {_ph_cx}"
                    )
                # mt050N-#1a (2026-05-27) — proactively clear the prior
                # turn's dedup ledger.  Background: when supersede fires,
                # the OLD turn's LLM is already in-flight (or its reply
                # is queued for delivery).  When that reply lands with
                # the now-stale source_msg_id, the JS source-guard
                # rejects it (stale_reply_source_msg_id) and direct-
                # delivery drops it.  mt046A's reactive clear at
                # runner.py only fires AFTER the drop is observed, but
                # by then the next EventMonitor tick has already
                # filtered the customer's earlier message out as
                # ``already_dispatched`` — the message is orphaned
                # forever (45 % of LLM outputs dropped silently per the
                # 2026-05-27 forensic).  Calling the clear NOW, at
                # supersede time, lets the next tick re-pick the old
                # turn for re-dispatch if its reply does drop.  Cost is
                # idempotent and cheap (prefix scan on a small dict).
                try:
                    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.actionable_items import (
                        clear_dispatched_identity_keys_for_customer as _mt050n_clear,
                    )
                    _cleared = _mt050n_clear(customer_key)
                    if _cleared:
                        logger.info(
                            f"[BrowserAutomation] {log_tag} mt050N-#1a "
                            f"proactively cleared {_cleared} identity_key "
                            f"entry(s) for cust={customer_key!r} on "
                            f"supersede so orphaned old turn can be "
                            f"re-dispatched if its reply drops"
                        )
                except Exception as _mt050n_exc:
                    logger.debug(
                        f"[BrowserAutomation] {log_tag} mt050N-#1a "
                        f"proactive clear failed (non-fatal): "
                        f"{_mt050n_exc}"
                    )
                assigned_sessions.pop(session_id, None)
            else:
                logger.info(
                    f"[BrowserAutomation] {log_tag} inflight skip "
                    f"session={session_id!r} cust={customer_key!r} "
                    f"(another dispatch is in flight, age={inflight_age:.1f}s, "
                    f"ttl={ctx.inflight_ttl_s}s)"
                )
                return opened_row, "", ""
    except Exception as exc:
        logger.debug(
            f"[BrowserAutomation] {log_tag} inflight check failed: {exc}"
        )

    # ── Mark inflight EARLY (closes the parallel-scrape race) ──
    _inflight_marked_early = False
    try:
        ctx.mark_dispatch_inflight(customer_key)
        _inflight_marked_early = True
        logger.debug(
            f"[BrowserAutomation] {log_tag} pre-acquired inflight lock "
            f"for cust={customer_key!r} BEFORE enrich/scrape "
            f"(prevents parallel-fire race)"
        )
    except Exception as exc:
        logger.debug(
            f"[BrowserAutomation] {log_tag} early mark_inflight failed "
            f"(non-fatal, fallback path remains): {exc}"
        )

    def _release_inflight_on_early_exit(reason: str) -> None:
        """Release the early-acquired inflight lock when we bail out
        BEFORE actually firing send_chat.  Without this, a skip during
        enrich (e.g. msg-id dedup, system-message filter) would leave
        the lock held for the full 30 s TTL and silently suppress this
        customer's NEXT genuine message."""
        if not _inflight_marked_early:
            return
        try:
            ctx.clear_dispatch_inflight(customer_key)
            logger.debug(
                f"[BrowserAutomation] {log_tag} released early inflight "
                f"lock for cust={customer_key!r} (reason={reason})"
            )
        except Exception as exc:
            logger.debug(
                f"[BrowserAutomation] {log_tag} early inflight release "
                f"failed: {exc}"
            )

    # Optional site-specific enrichment (ground-truth scrape + dedup).
    scraped_msg_id = ""
    if enrich_fn is not None:
        try:
            enrich = await enrich_fn(
                item=item,
                browser_session=session,
                customer_key=customer_key,
                session_id=session_id,
                log_tag=log_tag,
                assigned_sessions=assigned_sessions,
                customer_last_dispatched_msg_id=ctx.customer_last_dispatched_msg_id,
                auto_dispatch_last_agent_reply=ctx.auto_dispatch_last_agent_reply,
                normalize_reply_text=ctx.normalize_reply_text,
                typing_holder_getter=ctx.feige_typing_holder_getter,
            )
        except Exception as exc:
            # Enrich raising is non-fatal but we MUST release the
            # early-inflight lock or this customer is stuck for 30 s.
            logger.warning(
                f"[BrowserAutomation] {log_tag} enrich_fn raised "
                f"({type(exc).__name__}: {exc!r}); releasing inflight "
                f"and continuing with sidebar-preview as last_message."
            )
            _release_inflight_on_early_exit(f"enrich_raised:{type(exc).__name__}")
            return opened_row, "", ""
        if enrich.skip:
            skip_reason = enrich.skip_reason or "unspecified"
            _release_inflight_on_early_exit(f"enrich_skip:{skip_reason}")
            if skip_reason in {"typing_lock_active", "active_customer_mismatch"}:
                return "", "", _TYPING_LOCK_ACTIVE_SENTINEL
            return opened_row, "", ""
        scraped_msg_id = enrich.scraped_msg_id
        if scraped_msg_id:
            item["latest_message_msg_id"] = scraped_msg_id
        if enrich.should_clear_stale_assignment:
            assigned_sessions.pop(session_id, None)

    # Round-robin recipient pick.
    rr_idx = dispatch_state.get("rr_index", 0) % len(service_agent_ids)
    recipient_agent_id = service_agent_ids[rr_idx]
    dispatch_state["rr_index"] = rr_idx + 1

    assignment_payload = _build_assignment_payload(item, tab_id, cfg)

    # Re-mark inflight just before send_chat — idempotent if already
    # held from the early acquire above; the timestamp refresh extends
    # the TTL so a slow QA worker doesn't free the lock prematurely.
    try:
        ctx.mark_dispatch_inflight(customer_key)
        logger.debug(
            f"[BrowserAutomation] {log_tag} acquired inflight lock for "
            f"cust={customer_key!r} (recipient=...{recipient_agent_id[-6:]})"
        )
    except Exception as exc:
        logger.debug(
            f"[BrowserAutomation] {log_tag} inflight acquire failed: {exc}"
        )

    try:
        from agent.mcp.server.chat_utils.chat_tools import send_chat
    except Exception as exc:
        logger.warning(
            f"[BrowserAutomation] {log_tag} send_chat import failed: {exc}"
        )
        try:
            ctx.clear_dispatch_inflight(customer_key)
        except Exception:
            pass
        return opened_row, "", f"{session_id}: send_chat import failed: {exc}"

    # 2026-05-23 mt027 (Tier 4): with parallelisation re-enabled in
    # ``_run_with_lock_held``, the synchronous ``send_chat`` call needs
    # to be offloaded to the thread-pool executor — otherwise the sync
    # blocking HTTP POST inside a2a_send_chat_message_sync (~400-1100
    # ms) would block the event loop and ALL N concurrent items would
    # still effectively serialise on this single call.
    _send_payload = {
        "sender_agent_id": sender_agent_id,
        "recipient_agent_id": recipient_agent_id,
        "chat_id": session_id,
        "message": json.dumps(assignment_payload, ensure_ascii=False),
        "message_type": "text",
        "async_send": False,
    }
    _t_send_start = time.monotonic()
    _send_loop = asyncio.get_running_loop()
    send_result = await _send_loop.run_in_executor(
        None, send_chat, ctx.mainwin, _send_payload,
    )
    _send_ms = int((time.monotonic() - _t_send_start) * 1000)
    logger.debug(
        f"[FEIGE-FRONTDESK-TIMING] {log_tag} send_chat customer={customer_key!r} "
        f"dt_ms={_send_ms}"
    )
    if send_result.get("success"):
        assigned_sessions[session_id] = {
            "recipient_agent_id": recipient_agent_id,
            "message_id": str(send_result.get("message_id") or ""),
            "timestamp": int(send_result.get("timestamp") or 0),
            "latest_message": str(assignment_payload.get("latest_message") or ""),
            "last_message": str(assignment_payload.get("latest_message") or ""),
            "latest_message_msg_id": str(
                assignment_payload.get("latest_message_msg_id") or ""
            ),
        }
        if scraped_msg_id:
            ctx.customer_last_dispatched_msg_id[customer_key] = scraped_msg_id
        # Phase 3.5 placeholder-timer guardrail: arm a per-turn timer
        # so a stand-by message ("您好，稍等一下哦~") is auto-typed if
        # the real reply hasn't been delivered within the configured
        # deadline.  Resets Feige's red-flag clock without waiting for
        # the actual Q&A turn.  Disabled by default (tunable defaults
        # to timeout=0); operator opts in via
        # ECAN_FEIGE_PLACEHOLDER_TIMEOUT_S=20 or similar.
        try:
            from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.tunables import (
                resolve_float as _ph_resolve_float,
                DEFAULT_FEIGE_PLACEHOLDER_TIMEOUT_S as _DEF_PH_TIMEOUT,
            )
            _ph_timeout = _ph_resolve_float(
                "FEIGE_PLACEHOLDER_TIMEOUT_S", _DEF_PH_TIMEOUT, None
            )
            if _ph_timeout > 0:
                from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
                    placeholder_timer as _ph_timer_arm,
                )
                _ph_timer_arm.arm(
                    customer_key=str(customer_key or ""),
                    source_msg_id=str(scraped_msg_id or ""),
                    timeout_s=_ph_timeout,
                )
        except Exception as _ph_arm_err:
            logger.debug(
                f"[BrowserAutomation] {log_tag} placeholder timer arm "
                f"failed (non-fatal): {_ph_arm_err}"
            )
        # ── Cross-path dedup: stamp the AUTO-DISPATCH identity-key
        #   table so the LLM-side AUTO-DISPATCH (in
        #   actionable_items.py) recognises this customer as already
        #   handled and skips its own dispatch.  Both paths share the
        #   same ``_dispatched_identity_keys`` dict; they were just
        #   never wired together.  Best-effort import — if
        #   actionable_items isn't loaded (non-Feige skill) we silently
        #   no-op.
        try:
            _ident = str(item.get("identity_key") or "").strip()
            if _ident:
                from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.actionable_items import (
                    _dispatched_identity_keys as _ai_identity_keys,
                )
                import time as _t
                _ai_identity_keys[_ident] = _t.time()
                logger.debug(
                    f"[BrowserAutomation] {log_tag} stamped AUTO-DISPATCH "
                    f"identity_key={_ident!r} so the LLM-side path skips "
                    f"this customer."
                )
        except Exception as _stamp_exc:
            logger.debug(
                f"[BrowserAutomation] {log_tag} cross-path identity-key "
                f"stamp failed (non-fatal): {_stamp_exc}"
            )
        assigned_row = (
            f"{session_id}->{recipient_agent_id[-6:]} "
            f"msg={str(send_result.get('message_id') or '')[:8]}"
        )
        # Grep-friendly per-customer state marker — one [FEIGE-CUSTOMER-STATE]
        # at every junction.  Search with:
        #   grep "FEIGE-CUSTOMER-STATE.*客户XX" runlogs/eCan.log
        logger.info(
            f"[FEIGE-CUSTOMER-STATE] cust={customer_key!r} "
            f"phase=dispatched recipient=...{recipient_agent_id[-6:]} "
            f"msg_id={str(send_result.get('message_id') or '')[:8]}"
        )
        return opened_row, assigned_row, ""

    # send_chat failed → release the inflight lock so this customer
    # isn't blocked for the full TTL on a no-op.
    try:
        ctx.clear_dispatch_inflight(customer_key)
    except Exception:
        pass
    return (
        opened_row,
        "",
        f"{session_id}: assignment failed: {send_result.get('error', 'unknown error')}",
    )


def _build_result_payload(
    cfg: DispatchConfig,
    actionable: list[dict],
    opened_rows: list[str],
    assigned_rows: list[str],
    failure_rows: list[str],
    deferred_rows: list[str] | None = None,
) -> dict:
    """Final result dict returned to the caller when dispatch ran
    (even partially).  Matches the shape of the legacy inline
    ``_maybe_run_frontdesk_dispatch_fastpath`` return.
    """
    deferred_rows = deferred_rows or []
    payload = {
        "all_done": not bool(deferred_rows),
        "work_result": {
            cfg.fastpath_marker: True,
            "visible_session_count": len(actionable),
            "opened_count": len(opened_rows),
            "assigned_count": len(assigned_rows),
            "last_action_succeeded": not bool(failure_rows or deferred_rows),
            "no_customers": False,
        },
        "opened_sessions": opened_rows,
        "assigned_sessions": assigned_rows,
        "failures": failure_rows,
        "message": (
            f"{cfg.log_tag} completed"
            if not failure_rows
            else f"{cfg.log_tag} completed with failures"
        ),
    }
    if deferred_rows:
        payload["work_done"] = False
        payload["hot_path"] = True
        payload["hot_path_type"] = "pre_dispatch_deferred"
        payload["reason"] = "feige_focus_contention"
        payload["retry_pending"] = True
        payload["deferred_sessions"] = deferred_rows
        payload["work_result"]["deferred_count"] = len(deferred_rows)
        payload["message"] = (
            f"{cfg.log_tag} partially completed; "
            f"{len(deferred_rows)} row(s) deferred"
        )
    return payload


def _deferred_row_label(item: dict) -> str:
    return str(
        item.get("session_id")
        or item.get("customer_name")
        or item.get("customer_id")
        or _TYPING_LOCK_ACTIVE_SENTINEL
    )


# ───────────────────────────── orchestrator ───────────────────────────────


async def run(
    cfg: DispatchConfig, ctx: DispatchContext, agent_obj
) -> dict | None:
    """Run the front-desk PreDispatch fan-out fast-path.

    Returns ``None`` to signal the caller should fall through to the
    normal LLM-driven node path, or a ``{"final": ..., "history": ...}``
    dict when the fast-path owned the outcome.
    """
    # 2026-05-22 mt025: per-phase timing markers so a slow front-desk
    # run's bottleneck is visible without re-running the trace.  Grep
    # for ``[FEIGE-FRONTDESK-TIMING]`` to see entry → monitor lookup →
    # lock acquire → actionable extract → item dispatch.  The mystery
    # 1-2 s gaps in the 2026-05-22 08:14 trace (Pre-copy → first scrape)
    # were invisible before this; markers narrow future investigations.
    _t_run_start = time.monotonic()
    if not cfg.enabled:
        return None
    if not cfg.source_monitor_label:
        logger.warning(
            f"[BrowserAutomation] {cfg.log_tag} skipped: "
            f"preDispatch.source_monitor_label is required but missing"
        )
        return None
    if _should_skip_for_event_type(ctx.state, cfg.log_tag):
        return None
    is_browser_event = _is_browser_event_trigger(ctx.state)
    fallback_session = _fallback_session(agent_obj, ctx)
    if not fallback_session:
        logger.info(
            f"[BrowserAutomation] {cfg.log_tag} skipped: no browser session on agent"
        )
        if is_browser_event:
            return _build_deferred_result(
                cfg,
                reason="no_browser_session",
                detail="no browser session available for browser_event",
            )
        return None

    try:
        monitor_set, control_state, session = _find_active_monitor(agent_obj, ctx, cfg)
        if not monitor_set or not control_state:
            has_fallback, fallback_items = _get_prompt_actionable_fallback(ctx.state)
            if has_fallback and is_browser_event:
                session = session or fallback_session
                raw_items = fallback_items
                logger.info(
                    f"[BrowserAutomation] {cfg.log_tag} using prompt-hook "
                    f"actionable fallback: count={len(raw_items)} "
                    f"scope={ctx.scope_key}"
                )
            elif is_browser_event:
                return _build_deferred_result(
                    cfg,
                    reason="monitor_missing",
                    detail=(
                        f"no active monitor with label={cfg.source_monitor_label!r}"
                    ),
                )
            else:
                return None
        elif not _validate_monitor_ready(control_state, cfg):
            has_fallback, fallback_items = _get_prompt_actionable_fallback(ctx.state)
            if has_fallback and is_browser_event:
                session = session or fallback_session
                raw_items = fallback_items
                logger.info(
                    f"[BrowserAutomation] {cfg.log_tag} using prompt-hook "
                    f"actionable fallback while monitor not ready: "
                    f"count={len(raw_items)} {_monitor_state_detail(control_state, cfg)}"
                )
            elif is_browser_event:
                return _build_deferred_result(
                    cfg,
                    reason="monitor_not_ready",
                    detail=_monitor_state_detail(control_state, cfg),
                )
            else:
                return None
        else:
            raw_items = control_state.get("last_items") or []

        if not isinstance(raw_items, list):
            raw_items = []
        logger.info(
            f"[BrowserAutomation] {cfg.log_tag} candidate items: "
            f"count={len(raw_items)} scope={ctx.scope_key} "
            f"chosen_session_obj={id(session) if session else 'none'}"
        )

        dispatch_state = _resolve_dispatch_state(session, ctx, cfg)

        # Serialise concurrent fast-path invocations on the same dispatch_state.
        fp_lock = dispatch_state.get("_lock")
        if fp_lock is None:
            import threading
            fp_lock = threading.Lock()
            dispatch_state["_lock"] = fp_lock
        lock_acquired = fp_lock.acquire(blocking=False)
        if not lock_acquired:
            logger.info(
                f"[BrowserAutomation] {cfg.log_tag} skipped: another "
                f"invocation already running; waiting briefly"
            )
            # Flood tests can legitimately overlap browser_event invocations:
            # one pass may spend several seconds thread-scraping many sessions
            # while the monitor queues a newer snapshot behind it.  Treat that
            # as backpressure, not as "handled"; wait long enough for the
            # in-flight pass to finish so the newer snapshot is still processed.
            deadline = time.monotonic() + 15.0
            while time.monotonic() < deadline:
                await asyncio.sleep(0.05)
                lock_acquired = fp_lock.acquire(blocking=False)
                if lock_acquired:
                    logger.info(
                        f"[BrowserAutomation] {cfg.log_tag} acquired lock "
                        f"after waiting for concurrent invocation"
                    )
                    break
        if not lock_acquired:
            logger.info(
                f"[BrowserAutomation] {cfg.log_tag} busy: concurrent "
                f"invocation still running; short-circuiting without "
                f"marking dispatch handled"
            )
            return {
                "final": json.dumps({
                    "all_done": True,
                    "work_done": False,
                    "hot_path": True,
                    "hot_path_type": "pre_dispatch_busy",
                    "message": f"{cfg.log_tag} busy: another invocation is running",
                }, ensure_ascii=False),
                "history": f"{cfg.history_prefix}:busy",
            }

        logger.info(
            f"[FEIGE-FRONTDESK-TIMING] {cfg.log_tag} phase=lock_acquired "
            f"dt_ms={int((time.monotonic() - _t_run_start) * 1000)} "
            f"raw_items={len(raw_items)}"
        )
        try:
            _result = await _run_with_lock_held(
                cfg, ctx, session, dispatch_state, raw_items, agent_obj
            )
            logger.info(
                f"[FEIGE-FRONTDESK-TIMING] {cfg.log_tag} phase=run_complete "
                f"dt_ms={int((time.monotonic() - _t_run_start) * 1000)}"
            )
            return _result
        finally:
            if fp_lock.locked():
                try:
                    fp_lock.release()
                except Exception:
                    pass
    except Exception as exc:
        logger.warning(f"[BrowserAutomation] {cfg.log_tag} failed: {exc}")
        if _is_browser_event_trigger(ctx.state):
            return _build_deferred_result(
                cfg,
                reason="exception",
                detail=f"{type(exc).__name__}: {exc}",
            )
        return None


async def _run_with_lock_held(
    cfg: DispatchConfig,
    ctx: DispatchContext,
    session,
    dispatch_state: dict,
    raw_items: list,
    agent_obj,
) -> dict | None:
    """Body of :func:`run` executed while holding the per-dispatch_state
    lock.  Split into its own function so :func:`run` is a short
    readable orchestrator.
    """
    actionable = _extract_actionable_items(raw_items, cfg)
    if not actionable:
        logger.info(
            f"[BrowserAutomation] {cfg.log_tag} completed: no visible sessions"
        )
        return {
            "final": json.dumps({
                "all_done": True,
                "work_result": {
                    cfg.fastpath_marker: True,
                    "visible_session_count": 0,
                    "opened_count": 0,
                    "assigned_count": 0,
                    "last_action_succeeded": True,
                    "no_customers": True,
                },
                "message": f"{cfg.log_tag}: no visible customer sessions.",
            }, ensure_ascii=False),
            "history": f"{cfg.history_prefix}:no_customers",
        }

    sender_agent_id = str(ctx.calling_agent_id or "").strip()
    if not sender_agent_id:
        logger.info(
            f"[BrowserAutomation] {cfg.log_tag} skipped: missing runtime "
            f"sender agent id"
        )
        return None

    service_agent_ids = _resolve_recipient_agents(cfg, ctx, sender_agent_id, dispatch_state)
    if not service_agent_ids:
        failure_rows = ["no recipient agents available"]
        return _build_result_payload(cfg, actionable, [], [], failure_rows)

    enrich_fn = _load_enrich_plugin(cfg.site_plugin)

    opened_rows: list[str] = []
    assigned_rows: list[str] = []
    failure_rows: list[str] = []
    deferred_rows: list[str] = []

    # 2026-05-23 mt027 (Tier 4): re-introduce parallel dispatch.
    # mt024 tried this and was reverted in mt025 because parallel
    # scrapes raced on sidebar focus.  The proper fix landed alongside
    # this commit: ``dom_assets.scrape_sequence_lock(browser_session)``
    # now serialises the click+verify+scrape sequence per browser
    # session, so concurrent ``_dispatch_one_item`` callers naturally
    # queue on the scrape phase but their A2A send_chat HTTP POSTs run
    # in parallel.  See ``dom_assets._scrape_locked_body`` for the
    # locked body and ``[FEIGE-SCRAPE-LOCK]`` log markers for observed
    # lock-wait times.
    #
    # send_chat is offloaded to the thread-pool executor inside
    # ``_dispatch_one_item`` (mt025 reintroduced for this commit) so
    # the sync HTTP call doesn't block the event loop during gather.
    _t_pp_start = time.monotonic()
    logger.info(
        f"[FEIGE-FRONTDESK-TIMING] {cfg.log_tag} phase=item_dispatch_start "
        f"items={len(actionable)} mode=parallel"
    )
    _dispatch_results = await asyncio.gather(
        *(
            _dispatch_one_item(
                item,
                session=session,
                ctx=ctx,
                cfg=cfg,
                dispatch_state=dispatch_state,
                enrich_fn=enrich_fn,
                sender_agent_id=sender_agent_id,
                service_agent_ids=service_agent_ids,
            )
            for item in actionable
        ),
        return_exceptions=True,
    )
    _items_total_ms = int((time.monotonic() - _t_pp_start) * 1000)
    logger.info(
        f"[FEIGE-FRONTDESK-TIMING] {cfg.log_tag} phase=item_dispatch_done "
        f"items={len(actionable)} dt_ms={_items_total_ms} "
        f"avg_per_item_ms={_items_total_ms // max(1, len(actionable))}"
    )
    for item, result in zip(actionable, _dispatch_results):
        if isinstance(result, BaseException):
            logger.warning(
                f"[BrowserAutomation] {cfg.log_tag} item dispatch raised "
                f"for session={item.get('session_id')!r}: "
                f"{type(result).__name__}: {result}"
            )
            failure_rows.append(
                f"{item.get('session_id', '?')}: dispatch raised "
                f"{type(result).__name__}: {result}"
            )
            continue
        opened, assigned, failure = result
        if opened:
            opened_rows.append(opened)
        if assigned:
            assigned_rows.append(assigned)
        if failure:
            if failure == _TYPING_LOCK_ACTIVE_SENTINEL:
                deferred_rows.append(_deferred_row_label(item))
            else:
                failure_rows.append(failure)

    if not opened_rows and not assigned_rows and not failure_rows:
        if deferred_rows:
            # All-deferred case: a previous cycle's queue is still
            # draining and every visible item is blocked on the
            # typing-lock.  Schedule a rearm so the deferred items
            # eventually get a turn — without this, the only consumer
            # of ``retry_pending=True`` is dead code and the chain
            # silently dies.
            _maybe_schedule_self_rearm(
                cfg,
                ctx,
                agent_obj,
                dispatch_state,
                deferred_rows=deferred_rows,
                assigned_rows=[],
            )
            return _build_deferred_result(
                cfg,
                reason="feige_focus_contention",
                detail=f"{len(deferred_rows)} row(s) deferred",
                retry=True,
            )
        return None

    payload = _build_result_payload(
        cfg,
        actionable,
        opened_rows,
        assigned_rows,
        failure_rows,
        deferred_rows,
    )
    logger.info(
        f"[BrowserAutomation] {cfg.log_tag} completed: "
        f"visible={len(actionable)} opened={len(opened_rows)} "
        f"assigned={len(assigned_rows)} failures={len(failure_rows)} "
        f"deferred={len(deferred_rows)}"
    )
    # Self-rearm: when this cycle leaves behind any deferred rows,
    # schedule a single delayed background task that waits for the
    # in-flight queue to drain and then re-runs ``run()`` so the
    # deferred customers get a turn.  Loosened from the original
    # ``deferred_rows AND assigned_rows`` condition: when a previous
    # cycle's queue is still draining, the current cycle may produce 0
    # new assignments but still have deferred rows that need to be
    # retried — and that's exactly the case where the rearm chain
    # used to die.  Without this the live-monitor's ``emit_on=added``
    # rule (filter ``from_equals=customer``) never re-fires for our
    # own outbound replies, and the deferred customers stay stuck
    # until a brand-new customer message arrives.  Idempotent: a
    # duplicate call while a rearm is in flight is a no-op.  When the
    # run completes with zero deferrals we reset the depth counter so
    # a later contention event isn't penalised by an earlier chain.
    if deferred_rows:
        _maybe_schedule_self_rearm(
            cfg,
            ctx,
            agent_obj,
            dispatch_state,
            deferred_rows=deferred_rows,
            assigned_rows=assigned_rows,
        )
    else:
        _reset_rearm_depth_on_clean_run(dispatch_state)
    # Signal any concurrently-running LLM invocation to stop — it would
    # just duplicate work.
    assigned_sessions = dispatch_state.setdefault("assigned_sessions", {})
    if not deferred_rows and (assigned_rows or (not failure_rows and assigned_sessions)):
        setattr(session, cfg.flag_attr, True)
    return {
        "final": json.dumps(payload, ensure_ascii=False),
        "history": (
            f"{cfg.history_prefix}:deferred:feige_focus_contention"
            if deferred_rows
            else cfg.history_prefix
        ),
    }
