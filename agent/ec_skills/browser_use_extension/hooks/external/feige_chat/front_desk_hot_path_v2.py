"""Tier-aware port of front_desk.before_session_setup_hook (Step 2e).

This is HOT-PATH-B — the most complex local hook in the bundle.  It
fires when a ``chat_message`` event arrives carrying a pre-computed
``{response_text, customer_name}`` payload, types the reply directly
into the page, and short-circuits the LLM.

Step 2e scope decision
----------------------

The legacy hook is ~440 lines split between an outer control flow
(payload extraction, rule matching, dedup, decision branches) and
inner DOM orchestration (``hot_path.execute`` — tab focus, typing-lock
acquire, action-sequence run with per-tool verification, post-success
tab restore).  The audit (HYBRID_HOOK_AUDIT.md) recommended a
monolithic first port; we split it slightly differently:

* **The OUTER control flow** (~250 lines) is ported here.  It carries
  most of the IP — payload sourcing rules, cross-customer bleed
  detection, replay dedup, pre-record-before-send protocol — and
  exercises the LocalReactiveContext fields end-to-end.
* **The INNER DOM orchestration** (the ~440-line ``hot_path.execute``)
  is left as v1 for now and reached via a pluggable
  :class:`HotPathExecutor`.  Production wires this to the legacy
  function via a primitives→browser_session adapter (Step 4); tests
  mock it directly.

This split lets Step 2e validate the LocalReactiveContext shape —
including the new ``dispatch_state`` field — without simultaneously
porting 440 lines of Feige-specific DOM choreography.

What changes vs. v1
-------------------

* ``hook_ctx.mainwin`` access — gone (cloud doesn't have it)
* ``hook_ctx.get_or_create_browser_session`` — gone; the
  ``hot_path_executor`` receives ``ctx.primitives`` instead
* ``hook_ctx.clear_dispatch_inflight`` → ``ctx.dispatch_state.clear_inflight``
* ``hook_ctx.dispatch_state_by_agent`` peek for ``assigned_sessions``
  eviction — deferred (covered by Step 2f's PreDispatch split)
* ``clear_qa_response_pending`` cross-agent state call — deferred
  (cloud-only orchestrator concern; soft-imported with a debug log)

What stays identical
--------------------

* Payload-sourcing priority order (prompt_refs.events →
  events[-1].data.human_text → state.input legacy fallback)
* Cross-customer bleed warning (cycle-vs-tail customer_name compare)
* Rule matching by event_type + has_fields
* Replay dedup via :mod:`dispatch_state.was_recently_sent`
* Pre-record reply text for PreDispatch DOM-echo guard
* Branching: dedup_skip → return state with ``hot_path_type=dedup_skip``;
  success → ``hot_path_type=configurable``; rule-not-matched → None
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable

from agent.ec_skills.browser_node.contexts import (
    BrowserPrimitives,
    LocalReactiveContext,
)

# Local-only sibling state — these are intra-bundle process-local
# helpers, audited as ``stays local`` in HYBRID_HOOK_AUDIT.md (only
# read/written by hooks running in the same process).
from . import dispatch_state as _ds
from .trace_ledger import log_payload

logger = logging.getLogger("ecan.hooks.feige_chat.v2")

__all__ = [
    "before_session_setup_hook_v2",
    "FeigeFrontDeskHotPathHookV2",
    "HotPathExecutor",
    "HotPathOutcome",
]


# ─────────────────────────────────────────────────────────────────────────────
# DOM-orchestration boundary
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class HotPathOutcome:
    """Result returned by :class:`HotPathExecutor`.

    Mirrors v1's ``hot_path.execute`` return shape so a
    primitives→browser_session adapter at Step 4 can map between them
    without changing the hook's branch logic.
    """
    ok: bool
    reason: str = ""
    actions_attempted: int = 0
    last_tool_error: str = ""
    typing_acquired: bool = False


@runtime_checkable
class HotPathExecutor(Protocol):
    """DOM-orchestration boundary for HOT-PATH-B.

    The hook delegates all DOM work — tab focus, typing-lock acquire,
    action-sequence execution with per-tool verification, post-success
    tab restore — to an instance of this Protocol.  Production binding
    wraps the legacy ``hot_path.execute`` with a primitives→browser_session
    adapter (Step 4); tests pass a mock directly.

    Note that ``primitives`` here is the only DOM access surface; the
    executor must NOT reach for ``ctx.browser_session`` (the cloud
    proxy doesn't have one).
    """
    async def __call__(
        self,
        *,
        primitives: BrowserPrimitives,
        customer_key: str,
        action_seq: list,
        payload: dict,
        resolve_template: Callable[[str, dict], str],
        node_name: str,
    ) -> HotPathOutcome: ...


# ─────────────────────────────────────────────────────────────────────────────
# Payload extraction — pure
# ─────────────────────────────────────────────────────────────────────────────


def _extract_payload(state: dict) -> tuple[str, dict, str, dict]:
    """Source the just-resumed event payload from ``state``.

    Returns ``(event_type, payload, payload_src, tail_payload)`` where
    ``tail_payload`` is the events[-1] payload kept separately so the
    caller can detect cross-customer bleed.

    Priority order matches v1:
      1. ``state["prompt_refs"]["events"]`` — authoritative per-cycle
      2. ``state["events"][-1].data.human_text`` — used iff (1) missing
      3. ``state["input"]`` — legacy chat_message-only fallback
    """
    event_type = ""
    payload: dict = {}
    payload_src = "none"
    tail_payload: dict = {}

    if not isinstance(state, dict):
        return event_type, payload, payload_src, tail_payload

    # 1. prompt_refs.events
    pr = state.get("prompt_refs")
    if isinstance(pr, dict):
        evt_str = pr.get("events", "")
        if isinstance(evt_str, str) and evt_str:
            try:
                evt = json.loads(evt_str)
                event_type = evt.get("event_type", "") or event_type
                pr_ht = evt.get("human_text")
                if isinstance(pr_ht, str) and pr_ht.strip():
                    try:
                        parsed = json.loads(pr_ht)
                        if isinstance(parsed, dict):
                            payload = parsed
                            payload_src = "prompt_refs.events.human_text"
                    except Exception:
                        pass
            except Exception:
                pass

    # 2. events[-1].data.human_text (always sample so we can detect bleed)
    events_list = state.get("events") or []
    if isinstance(events_list, list) and events_list:
        last_evt = events_list[-1] if isinstance(events_list[-1], dict) else {}
        tail_type = last_evt.get("event_type", "")
        evt_data = last_evt.get("data") or {}
        raw_ht = evt_data.get("human_text") if isinstance(evt_data, dict) else None
        if isinstance(raw_ht, str) and raw_ht.strip():
            try:
                parsed = json.loads(raw_ht)
                if isinstance(parsed, dict):
                    tail_payload = parsed
                    if not payload:
                        payload = parsed
                        payload_src = "events[-1].data.human_text"
                        event_type = tail_type or event_type
            except Exception:
                pass

    # 3. state.input legacy fallback (only for chat_message)
    if not payload and event_type == "chat_message":
        si = state.get("input", "")
        if isinstance(si, str) and si.strip():
            try:
                parsed = json.loads(si)
                if isinstance(parsed, dict):
                    payload = parsed
                    payload_src = "state.input[legacy-fallback]"
            except Exception:
                pass

    # 4. response-payload fallback. A queued front-desk chat_message can
    # resume with prompt_refs.events empty while stale browser_event state is
    # still present; state.input/messages[4] is then the only current truth.
    if not payload:
        candidates = []
        si = state.get("input", "")
        if isinstance(si, str) and si.strip():
            candidates.append(si)
        messages = state.get("messages")
        if isinstance(messages, list) and len(messages) > 4:
            msg_input = messages[4]
            if isinstance(msg_input, str) and msg_input.strip():
                candidates.append(msg_input)
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except Exception:
                continue
            if not isinstance(parsed, dict):
                continue
            if (
                str(parsed.get("response_text") or "").strip()
                and str(parsed.get("customer_name") or parsed.get("customer_id") or "").strip()
            ):
                payload = parsed
                payload_src = "state.input[response-fallback]"
                event_type = "chat_message"
                break

    return event_type, payload, payload_src, tail_payload


def _detect_cross_bleed_warning(
    payload: dict,
    tail_payload: dict,
    state: dict,
    payload_src: str,
) -> str | None:
    """Return a warning message if cross-customer bleed is detected.

    Two signals are checked:
    1. Cycle (prompt_refs) vs. tail (events[-1]) customer disagree
    2. payload customer vs. state.input customer disagree (residual)

    Returns the formatted warning string for logging, or ``None`` when
    no bleed is detected.
    """
    if not payload:
        return None

    # 1. Cycle vs tail
    if (
        tail_payload
        and payload is not tail_payload
    ):
        cn_cur = payload.get("customer_name") or payload.get("customer_id") or ""
        cn_tail = tail_payload.get("customer_name") or tail_payload.get("customer_id") or ""
        if cn_cur and cn_tail and cn_cur != cn_tail:
            return (
                f"HOT-PATH-B: cycle/tail customer disagreement — "
                f"cycle(prompt_refs)={cn_cur!r} tail(events[-1])={cn_tail!r}; "
                f"trusting cycle."
            )

    # 2. payload vs state.input
    if isinstance(state, dict):
        si = state.get("input", "")
        if isinstance(si, str) and si.strip():
            try:
                si_dict = json.loads(si)
                if isinstance(si_dict, dict):
                    cn_cur = payload.get("customer_name") or payload.get("customer_id") or ""
                    cn_stale = si_dict.get("customer_name") or si_dict.get("customer_id") or ""
                    if cn_cur and cn_stale and cn_cur != cn_stale:
                        return (
                            f"HOT-PATH-B: stale state.input bleed "
                            f"(cur_cycle_customer={cn_cur!r} src={payload_src} "
                            f"!= state.input_customer={cn_stale!r})"
                        )
            except Exception:
                pass

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Hook
# ─────────────────────────────────────────────────────────────────────────────


async def before_session_setup_hook_v2(
    state: dict,
    inputs: dict,
    ctx: LocalReactiveContext,
    *,
    hot_path_executor: HotPathExecutor | None = None,
) -> dict | None:
    """Outer control flow of HOT-PATH-B (early phase).

    Returns:
      * ``None`` when HOT-PATH-B is not configured / not triggered
        (lets the normal LLM flow proceed)
      * a populated ``state`` dict with ``state["result"]["llm_result"]``
        set when HOT-PATH-B handled the event (short-circuits the LLM)
    """
    claim_active = False
    claim_cust = ""
    claim_reply = ""
    claim_source_msg_id = ""
    try:
        # ── Parse hotPathActions config ──
        hp_raw = (inputs.get("hotPathActions") or {}).get("content")
        actions_list = None
        if isinstance(hp_raw, str) and hp_raw.strip():
            try:
                actions_list = json.loads(hp_raw)
            except Exception:
                actions_list = None
        elif isinstance(hp_raw, list):
            actions_list = hp_raw

        # ── Extract payload + detect bleed ──
        evt_type, payload, payload_src, tail_payload = _extract_payload(state)
        warning = _detect_cross_bleed_warning(payload, tail_payload, state, payload_src)
        if warning:
            logger.warning(f"[HOT-PATH-B-V2] {warning}, node={ctx.node_name}")

        logger.info(
            f"[HOT-PATH-B-V2] entry "
            f"event_type={evt_type or 'none'}, "
            f"payload_keys={list(payload.keys()) if payload else []}, "
            f"payload_src={payload_src}, "
            f"payload_customer={payload.get('customer_name') or payload.get('customer_id') or '-'}, "
            f"rules_configured={len(actions_list) if isinstance(actions_list, list) else 0}, "
            f"node={ctx.node_name}"
        )

        def _ledger(
            stage: str,
            *,
            level: int = logging.INFO,
            **fields: Any,
        ) -> None:
            if not payload:
                return
            try:
                log_payload(
                    stage,
                    payload,
                    level=level,
                    event_type=evt_type or "",
                    node=ctx.node_name,
                    payload_src=payload_src,
                    **fields,
                )
            except Exception:
                pass

        _ledger(
            "hot_path_b_entry",
            rules_configured=len(actions_list) if isinstance(actions_list, list) else 0,
            payload_key_count=len(payload.keys()) if payload else 0,
        )

        try:
            from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.system_message_filter import (
                first_system_row_match,
            )
            system_reason = first_system_row_match(payload)
            if system_reason:
                logger.warning(
                    f"[HOT-PATH-B-V2] dropped system/non-customer reply payload "
                    f"reason={system_reason!r}, "
                    f"customer={payload.get('customer_name') or payload.get('customer_id')!r}, "
                    f"node={ctx.node_name}"
                )
                _ledger(
                    "hot_path_b_system_drop",
                    reason=system_reason,
                    level=logging.WARNING,
                )
                state.setdefault("result", {})["llm_result"] = {
                    "all_done": True,
                    "work_done": False,
                    "hot_path": True,
                    "hot_path_type": "system_reply_drop",
                }
                return state
        except Exception as system_err:
            logger.debug(
                f"[HOT-PATH-B-V2] system-payload filter failed "
                f"(non-fatal): {system_err}"
            )

        if not isinstance(actions_list, list) or not actions_list:
            _ledger("hot_path_b_unconfigured", reason="no_actions_configured")
            return None

        # ── Match the first applicable rule ──
        for rule in actions_list:
            if not isinstance(rule, dict):
                continue
            trigger = rule.get("trigger", {})
            if trigger.get("event_type") and trigger["event_type"] != evt_type:
                continue
            required = trigger.get("has_fields", [])
            if not all(f in payload for f in required):
                continue
            action_seq = rule.get("actions", [])
            if not action_seq:
                continue

            logger.info(
                f"[HOT-PATH-B-V2] trigger matched (event={evt_type}, rule={trigger}), "
                f"executing {len(action_seq)} actions"
            )
            _ledger(
                "hot_path_b_rule_matched",
                action_count=len(action_seq),
                trigger_preview=str(trigger),
            )

            # ── Replay-dedup guard ──
            dedup_cust = (
                payload.get("customer_name")
                or payload.get("customer_id")
                or ""
            )
            dedup_reply = payload.get("response_text") or ""
            source_msg_id = str(
                payload.get("source_customer_msg_id")
                or payload.get("latest_message_msg_id")
                or payload.get("reply_to_msg_id")
                or ""
            ).strip()
            claim_cust = dedup_cust
            claim_reply = dedup_reply
            claim_source_msg_id = source_msg_id
            dedup_age = _ds.claim_send_for_turn(
                dedup_cust, dedup_reply, source_msg_id
            )
            if dedup_age > 0:
                logger.info(
                    f"[HOT-PATH-B-V2] dedup skip cust={dedup_cust!r} "
                    f"reply_len={len(dedup_reply)} (identical reply already "
                    f"sent {dedup_age:.1f}s ago, source_msg_id={source_msg_id!r}), "
                    f"node={ctx.node_name}"
                )
                _ledger("hot_path_b_dedup_skip", dedup_age_s=dedup_age)
                # Release inflight lock so the *next* genuine turn isn't blocked.
                try:
                    skip_cust = ctx.normalize_dispatch_identity_key(dedup_cust)
                    if skip_cust:
                        ctx.dispatch_state.clear_inflight(skip_cust)
                except Exception:
                    pass
                state.setdefault("result", {})["llm_result"] = {
                    "all_done": True,
                    "work_done": False,
                    "hot_path": True,
                    "hot_path_type": "dedup_skip",
                }
                return state
            claim_active = True
            _ledger("hot_path_b_send_claimed")

            # ── Pre-record reply BEFORE send ──
            # PreDispatch's equality guard compares the DOM's sidebar
            # last_message against this recorded text to recognise its
            # own DOM echo.  Recording before send closes the race
            # window even if a DOM diff fires while typing is in flight.
            try:
                pre_cust = ctx.normalize_dispatch_identity_key(
                    payload.get("customer_name")
                    or payload.get("customer_id")
                    or ""
                )
                pre_reply = _ds.remember_agent_reply(
                    pre_cust,
                    payload.get("response_text") or "",
                )
                if pre_cust and pre_reply:
                    logger.info(
                        f"[HOT-PATH-B-V2] pre-recorded last_agent_reply for "
                        f"{pre_cust!r} (len={len(pre_reply)}, before send), "
                        f"node={ctx.node_name}"
                    )
            except Exception as pre_err:
                logger.warning(f"[HOT-PATH-B-V2] pre-record reply failed: {pre_err}")

            # ── Delegate DOM work to the executor ──
            if hot_path_executor is None:
                logger.warning(
                    f"[HOT-PATH-B-V2] no hot_path_executor wired; cannot type "
                    f"reply, node={ctx.node_name}"
                )
                _ledger(
                    "hot_path_b_unavailable",
                    reason="no_hot_path_executor",
                    level=logging.WARNING,
                )
                if claim_active:
                    try:
                        _ds.unclaim_send_for_turn(
                            claim_cust,
                            claim_reply,
                            claim_source_msg_id,
                        )
                    except Exception:
                        pass
                    claim_active = False
                return None
            if ctx.primitives is None:
                logger.warning(f"[HOT-PATH-B-V2] no primitives, node={ctx.node_name}")
                _ledger(
                    "hot_path_b_unavailable",
                    reason="no_primitives",
                    level=logging.WARNING,
                )
                if claim_active:
                    try:
                        _ds.unclaim_send_for_turn(
                            claim_cust,
                            claim_reply,
                            claim_source_msg_id,
                        )
                    except Exception:
                        pass
                    claim_active = False
                return None

            typing_cust = ctx.normalize_dispatch_identity_key(
                payload.get("customer_name")
                or payload.get("customer_id")
                or ""
            )
            _ledger(
                "hot_path_b_executor_start",
                customer_key=typing_cust,
                action_count=len(action_seq),
            )
            outcome = await hot_path_executor(
                primitives=ctx.primitives,
                customer_key=typing_cust,
                action_seq=action_seq,
                payload=payload,
                resolve_template=ctx.resolve_template,
                node_name=ctx.node_name,
            )
            logger.info(
                f"[HOT-PATH-B-V2] executor returned ok={outcome.ok} "
                f"reason={outcome.reason!r} "
                f"actions_attempted={outcome.actions_attempted} "
                f"last_tool_error={outcome.last_tool_error!r}, "
                f"node={ctx.node_name}"
            )
            _ledger(
                "hot_path_b_executor_result",
                ok=bool(outcome.ok),
                reason=str(outcome.reason or ""),
                actions_attempted=outcome.actions_attempted,
                last_tool_error=str(outcome.last_tool_error or ""),
                typing_acquired=bool(outcome.typing_acquired),
            )

            if not outcome.ok and outcome.reason == "stale_reply_source_msg_id":
                # Keep the recent-send claim so this stale response is not
                # replayed, but avoid clearing a newer dispatch lock if the
                # customer has already been re-dispatched for a later bubble.
                claim_active = False
                try:
                    stale_cust = ctx.normalize_dispatch_identity_key(
                        payload.get("customer_name")
                        or payload.get("customer_id")
                        or ""
                    )
                    expected_msg_id = str(
                        payload.get("source_customer_msg_id")
                        or payload.get("latest_message_msg_id")
                        or payload.get("reply_to_msg_id")
                        or ""
                    ).strip()
                    current_msg_id = ctx.dispatch_state.get_last_dispatched_msg_id(
                        stale_cust
                    )
                    if stale_cust and (
                        not current_msg_id or current_msg_id == expected_msg_id
                    ):
                        ctx.dispatch_state.clear_inflight(stale_cust)
                        logger.info(
                            f"[HOT-PATH-B-V2] cleared dispatch_inflight after "
                            f"stale reply drop for cust={stale_cust!r}, "
                            f"node={ctx.node_name}"
                        )
                    else:
                        logger.info(
                            f"[HOT-PATH-B-V2] kept dispatch_inflight after "
                            f"stale reply drop for cust={stale_cust!r} "
                            f"because newer msg_id is recorded, node={ctx.node_name}"
                        )
                except Exception as stale_err:
                    logger.debug(
                        f"[HOT-PATH-B-V2] stale-drop inflight handling failed: "
                        f"{stale_err}"
                    )
                state.setdefault("result", {})["llm_result"] = {
                    "all_done": True,
                    "work_done": False,
                    "hot_path": True,
                    "hot_path_type": "stale_reply_drop",
                }
                logger.warning(
                    f"[HOT-PATH-B-V2] dropped stale reply instead of typing it, "
                    f"node={ctx.node_name}"
                )
                _ledger("hot_path_b_stale_dropped", level=logging.WARNING)
                return state

            if outcome.ok:
                # Mark (cust, reply) as sent so an immediate replay is deduped.
                try:
                    _ds.mark_sent_for_turn(dedup_cust, dedup_reply, source_msg_id)
                except Exception:
                    pass
                claim_active = False

                # Release qa_response_pending lock — soft-import: the call
                # is mainwin/cloud-orchestrator-coupled in the legacy
                # implementation.  In hybrid mode this becomes a cloud-side
                # operation; for now we attempt the legacy path and silently
                # skip if it's not available.
                try:
                    from agent.mcp.server.chat_utils.chat_tools import (
                        clear_qa_response_pending as _clear_pending,
                    )
                    clr_cust = ctx.normalize_dispatch_identity_key(
                        payload.get("customer_name")
                        or payload.get("customer_id")
                        or ""
                    )
                    if clr_cust and ctx.calling_agent_id:
                        _clear_pending(str(ctx.calling_agent_id), clr_cust)
                        logger.info(
                            f"[HOT-PATH-B-V2] cleared qa_response_pending for "
                            f"recipient={ctx.calling_agent_id!r} cust={clr_cust!r}, "
                            f"node={ctx.node_name}"
                        )
                except Exception as clr_err:
                    logger.debug(
                        f"[HOT-PATH-B-V2] qa_response_pending clear failed: {clr_err}"
                    )

                # Release the cross-scope inflight lock.
                try:
                    clr_cust = ctx.normalize_dispatch_identity_key(
                        payload.get("customer_name")
                        or payload.get("customer_id")
                        or ""
                    )
                    if clr_cust:
                        ctx.dispatch_state.clear_inflight(clr_cust)
                        logger.info(
                            f"[HOT-PATH-B-V2] cleared dispatch_inflight for "
                            f"cust={clr_cust!r}, node={ctx.node_name}"
                        )
                except Exception as cdi_err:
                    logger.debug(
                        f"[HOT-PATH-B-V2] dispatch_inflight clear failed: {cdi_err}"
                    )

                # NOTE: assigned_sessions eviction (v1's hook_ctx.dispatch_state_by_agent
                # peek) is deferred — that's a frontdesk_dispatch internal handled by
                # Step 2f's PreDispatch port.

                state.setdefault("result", {})["llm_result"] = {
                    "all_done": True,
                    "work_done": False,
                    "hot_path": True,
                    "hot_path_type": "configurable",
                }
                logger.info(
                    f"[HOT-PATH-B-V2] all actions completed, node={ctx.node_name}"
                )
                _ledger("hot_path_b_sent_and_cleaned")
                return state

            # ── Failure path ──
            if claim_active:
                try:
                    _ds.unclaim_send_for_turn(
                        claim_cust,
                        claim_reply,
                        claim_source_msg_id,
                    )
                except Exception:
                    pass
                claim_active = False

            # Release inflight lock so PreDispatch isn't blocked for the full TTL.
            try:
                fail_cust = ctx.normalize_dispatch_identity_key(
                    payload.get("customer_name")
                    or payload.get("customer_id")
                    or ""
                )
                if fail_cust:
                    ctx.dispatch_state.clear_inflight(fail_cust)
                    logger.info(
                        f"[HOT-PATH-B-V2] released dispatch_inflight after "
                        f"action-failure for cust={fail_cust!r}, "
                        f"node={ctx.node_name}"
                    )
            except Exception as fail_cdi_err:
                logger.debug(
                    f"[HOT-PATH-B-V2] inflight clear after failure: {fail_cdi_err}"
                )

            _ledger(
                "hot_path_b_failed",
                ok=False,
                reason=str(outcome.reason or ""),
                actions_attempted=outcome.actions_attempted,
                last_tool_error=str(outcome.last_tool_error or ""),
                level=logging.WARNING,
            )
            break  # Only try first matching rule
    except Exception as err:
        if claim_active:
            try:
                _ds.unclaim_send_for_turn(
                    claim_cust,
                    claim_reply,
                    claim_source_msg_id,
                )
            except Exception:
                pass
        try:
            if "_ledger" in locals():
                _ledger(
                    "hot_path_b_exception",
                    error=str(err),
                    level=logging.WARNING,
                )
        except Exception:
            pass
        logger.warning(
            f"[HOT-PATH-B-V2] check failed (non-fatal): {err}",
            exc_info=True,
        )

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Class wrapper — for symmetry with the other v2 hooks
# ─────────────────────────────────────────────────────────────────────────────


class FeigeFrontDeskHotPathHookV2:
    """Tier ``local_reactive`` port of front_desk.before_session_setup_hook.

    Class wrapper around :func:`before_session_setup_hook_v2`.  The
    HotPathExecutor is supplied at construction time; production binding
    (Step 4) provides a primitives→browser_session adapter wrapping the
    legacy ``hot_path.execute``; tests pass a mock executor directly.
    """

    EXECUTION_TIER = "local_reactive"

    def __init__(
        self,
        config: dict | None = None,
        hot_path_executor: HotPathExecutor | None = None,
    ):
        self.config = dict(config or {})
        self.hot_path_executor = hot_path_executor

    async def run(
        self,
        ctx: LocalReactiveContext,
        state: dict,
        inputs: dict,
    ) -> dict | None:
        return await before_session_setup_hook_v2(
            state, inputs, ctx, hot_path_executor=self.hot_path_executor
        )
