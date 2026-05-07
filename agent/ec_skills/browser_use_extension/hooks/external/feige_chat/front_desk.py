"""Feige front-desk hooks (Phases 5A + 5B, 2026-04-24).

Background
----------

The eCan.ai agentic app supports arbitrary browser-automation business
cases.  Feige customer chat is one such case; to meet its real-time
requirement it uses a **front-desk agent + Q&A worker team** pattern
where a single 'front-desk' browser_automation node watches the Feige
sidebar, fans out each new customer message to a pool of worker agents,
and never invokes its own LLM on the fan-out path.

Prior to Phase 5, both the PreDispatch fan-out wrapper AND the inline
HOT-PATH-B reply-typing block lived directly inside
`build_node._run_browser_use`, coupling the generic node factory to
this one business case.  Phase 5 relocates both to this module,
registered with `build_node` via its lifecycle-hook interface.

What this module owns
---------------------

* **Early hook — HOT-PATH-B** (`before_session_setup_hook`): when
  a `chat_message` event arrives carrying a pre-computed
  `{response_text, customer_name}` payload, type the reply directly
  into Feige via `feige_open_session` + `feige_send_message` and
  short-circuit the LLM.  Runs BEFORE the (expensive) browser-use
  agent is constructed so the latency win is real.

* **Late hook — PreDispatch** (`before_run_hook`): when a
  `browser_event` arrives indicating a new customer message, scrape
  the latest customer bubble and fan out to available Q&A workers via
  the generic `node_runtime.frontdesk_dispatch` skeleton.  Runs
  AFTER the browser-use agent is constructed so it can reuse the
  agent's browser session for DOM reads.

What this module does **not** own
---------------------------------

* The Feige DOM selectors + JS snippets (`dom_assets`), the typing
  lock state (`typing_lock`), the action-sequence executor
  (`hot_path.execute`), the per-item enrichment plugin
  (`pre_dispatch_enrich`), or the generic fan-out skeleton
  (`node_runtime.frontdesk_dispatch`) — see those modules.

* The shared state dicts used by HOT-PATH-B + PreDispatch
  (`_dispatch_state_by_agent`, `_auto_dispatch_last_agent_reply`,
  etc.) — still owned by `build_node` module scope and injected
  via `BrowserUseHookContext`.  Deferred to a later phase.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from agent.ec_skills.node_runtime.frontdesk_dispatch import (
    DispatchConfig,
    DispatchContext,
    run as _run_frontdesk_dispatch,
)
from . import dispatch_state as _ds
from . import typing_lock as _typing_lock

logger = logging.getLogger("eCan")

__all__ = ["before_run_hook", "before_session_setup_hook", "register"]


async def before_session_setup_hook(
    agent: Any,  # Always None at the early phase.
    state: dict,
    inputs: dict,
    hook_ctx: Any,
) -> dict | None:
    """Early-phase hook: HOT-PATH-B chat_message reply bypass.

    Fires when a `chat_message` event arrives with a pre-computed
    `{response_text, customer_name}` payload.  Types the reply
    directly into Feige and returns a completed state dict to
    short-circuit the LLM.  Returns `None` when the event is not a
    chat_message reply or HOT-PATH-B is not configured (lets the
    normal flow proceed).

    *hook_ctx* is a `build_node.BrowserUseHookContext` carrying the
    generic helpers + shared state dicts.  See that class for field
    documentation.  `agent` is unused (always `None` at this
    phase) — HOT-PATH-B acquires a browser session directly via
    `hook_ctx.get_or_create_browser_session`.
    """
    # ── Hot-path: configurable action templates (Option B) ──
    # Allows users to define custom hot-path triggers and action sequences
    # in the node editor.  Currently default-bypassed; enable by setting
    # hotPathActions in the node config.
    # Config format:
    #   hotPathActions: [
    #     {
    #       "trigger": {"event_type": "chat_message", "has_fields": ["response_text"]},
    #       "actions": [
    #         {"tool": "feige_open_session", "args": {"customer_name": "{{customer_name}}"}},
    #         {"tool": "feige_send_message", "args": {"text": "{{response_text}}"}}
    #       ]
    #     }
    #   ]
    _hp_b_claim_active = False
    _hp_b_claim_cust = ""
    _hp_b_claim_reply = ""
    _hp_b_claim_source_msg_id = ""
    try:
        _hp_b_raw = (inputs.get("hotPathActions") or {}).get("content")
        _hp_b_actions_list = None
        if isinstance(_hp_b_raw, str) and _hp_b_raw.strip():
            _hp_b_actions_list = json.loads(_hp_b_raw)
        elif isinstance(_hp_b_raw, list):
            _hp_b_actions_list = _hp_b_raw
        # Determine current event type and payload fields.
        # IMPORTANT (customer cross-talk fix 2026-04-22): We must read the
        # payload from the JUST-RESUMED event for THIS cycle, not from
        # state["input"] (stale) and not from state["events"][-1] alone
        # (which can contain an event from a different customer's cycle
        # when multiple chat_messages are interleaved on the same task's
        # shared graph state).
        #
        # Priority order for sourcing the payload:
        #   1. state["prompt_refs"]["events"] (AUTHORITATIVE — this is
        #      written by pend_event_node for THIS cycle's triggering
        #      event, and matches the "Injected triggering event
        #      context" log emitted just above)
        #   2. state["events"][-1].data.human_text (matches #1 in most
        #      cases; used when prompt_refs is missing)
        #   3. state["input"] (legacy fallback ONLY when the current
        #      event is itself a chat_message)
        #
        # Cross-check: if #1 and #2 disagree on customer_name, trust #1
        # and WARN — that is the cross-customer bleed scenario.
        _hp_b_evt_type = ""
        _hp_b_payload = {}
        _hp_b_payload_src = "none"
        _hp_b_payload_from_events_tail = {}
        if isinstance(state, dict):
            # --- 1. prompt_refs.events (authoritative per-cycle) ---
            _hp_b_pr = state.get("prompt_refs")
            if isinstance(_hp_b_pr, dict):
                _hp_b_evt_str = _hp_b_pr.get("events", "")
                if _hp_b_evt_str and isinstance(_hp_b_evt_str, str):
                    try:
                        _hp_b_evt = json.loads(_hp_b_evt_str)
                        _hp_b_evt_type = _hp_b_evt.get("event_type", "") or _hp_b_evt_type
                        _hp_b_pr_ht = _hp_b_evt.get("human_text")
                        if isinstance(_hp_b_pr_ht, str) and _hp_b_pr_ht.strip():
                            try:
                                _hp_b_parsed = json.loads(_hp_b_pr_ht)
                                if isinstance(_hp_b_parsed, dict):
                                    _hp_b_payload = _hp_b_parsed
                                    _hp_b_payload_src = "prompt_refs.events.human_text"
                            except Exception:
                                pass
                    except Exception:
                        pass
            # --- 2. state.events[-1] — also sample so we can detect
            # disagreement with #1 (cross-customer bleed warning). ---
            _hp_b_events_list = state.get("events") or []
            if isinstance(_hp_b_events_list, list) and _hp_b_events_list:
                _hp_b_last_evt = _hp_b_events_list[-1] if isinstance(_hp_b_events_list[-1], dict) else {}
                _hp_b_tail_type = _hp_b_last_evt.get("event_type", "")
                _hp_b_evt_data = _hp_b_last_evt.get("data") or {}
                _hp_b_raw_ht = _hp_b_evt_data.get("human_text") if isinstance(_hp_b_evt_data, dict) else None
                if isinstance(_hp_b_raw_ht, str) and _hp_b_raw_ht.strip():
                    try:
                        _hp_b_tail_parsed = json.loads(_hp_b_raw_ht)
                        if isinstance(_hp_b_tail_parsed, dict):
                            _hp_b_payload_from_events_tail = _hp_b_tail_parsed
                            # Fill in only if prompt_refs.events was empty.
                            if not _hp_b_payload:
                                _hp_b_payload = _hp_b_tail_parsed
                                _hp_b_payload_src = "events[-1].data.human_text"
                                _hp_b_evt_type = _hp_b_tail_type or _hp_b_evt_type
                    except Exception:
                        pass
            # --- 3. Legacy state.input fallback ---
            # Only trust state.input when the current cycle is itself a
            # chat_message AND we could not source a payload from #1/#2.
            # Otherwise the inherited value is from a previous customer.
            if not _hp_b_payload and _hp_b_evt_type == "chat_message":
                _hp_b_input = state.get("input", "")
                if isinstance(_hp_b_input, str) and _hp_b_input.strip():
                    try:
                        _hp_b_parsed = json.loads(_hp_b_input)
                        if isinstance(_hp_b_parsed, dict):
                            _hp_b_payload = _hp_b_parsed
                            _hp_b_payload_src = "state.input[legacy-fallback]"
                    except Exception:
                        pass
            # --- 4. Response-payload fallback ---
            # Under bursty queues prompt_refs.events can be empty while a
            # stale browser_event remains in state.  If the current input is
            # clearly a Q&A reply, recover it here and force HOT-PATH-B.
            if not _hp_b_payload and not state.get("_ecan_predispatch_actionable_items"):
                _hp_b_candidates = []
                _hp_b_input = state.get("input", "")
                if isinstance(_hp_b_input, str) and _hp_b_input.strip():
                    _hp_b_candidates.append(_hp_b_input)
                _hp_b_messages = state.get("messages")
                if isinstance(_hp_b_messages, list) and len(_hp_b_messages) > 4:
                    _hp_b_msg_input = _hp_b_messages[4]
                    if isinstance(_hp_b_msg_input, str) and _hp_b_msg_input.strip():
                        _hp_b_candidates.append(_hp_b_msg_input)
                for _hp_b_candidate in _hp_b_candidates:
                    try:
                        _hp_b_parsed = json.loads(_hp_b_candidate)
                    except Exception:
                        continue
                    if not isinstance(_hp_b_parsed, dict):
                        continue
                    if (
                        str(_hp_b_parsed.get("response_text") or "").strip()
                        and str(
                            _hp_b_parsed.get("customer_name")
                            or _hp_b_parsed.get("customer_id")
                            or ""
                        ).strip()
                    ):
                        _hp_b_payload = _hp_b_parsed
                        _hp_b_payload_src = "state.input[response-fallback]"
                        _hp_b_evt_type = "chat_message"
                        logger.warning(
                            f"[BrowserAutomation] HOT-PATH-B: recovered "
                            f"chat_message response payload from state input "
                            f"while prompt_refs/events were stale or empty; "
                            f"customer={_hp_b_payload.get('customer_name') or _hp_b_payload.get('customer_id')!r}"
                        )
                        break
        # Cross-customer bleed detection: if prompt_refs.events (cycle
        # truth) disagrees with state.events[-1] (accumulated tail), WARN
        # loudly and trust prompt_refs. Previously we trusted tail first,
        # which caused HOT-PATH-B to type customer B's reply into customer
        # C's chat when their cycles interleaved on the shared task state.
        try:
            if (
                _hp_b_payload
                and _hp_b_payload_from_events_tail
                and _hp_b_payload is not _hp_b_payload_from_events_tail
            ):
                _cn_cur = (
                    _hp_b_payload.get("customer_name")
                    or _hp_b_payload.get("customer_id")
                    or ""
                )
                _cn_tail = (
                    _hp_b_payload_from_events_tail.get("customer_name")
                    or _hp_b_payload_from_events_tail.get("customer_id")
                    or ""
                )
                if _cn_cur and _cn_tail and _cn_cur != _cn_tail:
                    logger.warning(
                        f"[BrowserAutomation] HOT-PATH-B: cycle/tail customer "
                        f"disagreement — cycle(prompt_refs)={_cn_cur!r} "
                        f"tail(events[-1])={_cn_tail!r}; trusting cycle. "
                        f"This indicates state.events accumulated from a "
                        f"prior customer's resume that is not the current "
                        f"cycle — defence-in-depth for graph-state bleed."
                    )
        except Exception:
            pass
        # Cross-check: detect stale-state bleed. If state.input carries a
        # customer_name different from the per-cycle payload's, log a
        # WARN so we can track residual bleed after this fix.
        try:
            if _hp_b_payload and isinstance(state, dict):
                _hp_b_state_input = state.get("input", "")
                if isinstance(_hp_b_state_input, str) and _hp_b_state_input.strip():
                    try:
                        _hp_b_si = json.loads(_hp_b_state_input)
                        if isinstance(_hp_b_si, dict):
                            _hp_b_cn_cur = (_hp_b_payload.get("customer_name") or _hp_b_payload.get("customer_id") or "")
                            _hp_b_cn_stale = (_hp_b_si.get("customer_name") or _hp_b_si.get("customer_id") or "")
                            if _hp_b_cn_cur and _hp_b_cn_stale and _hp_b_cn_cur != _hp_b_cn_stale:
                                logger.warning(
                                    f"[BrowserAutomation] HOT-PATH-B: detected stale state.input bleed "
                                    f"(cur_cycle_customer='{_hp_b_cn_cur}' src={_hp_b_payload_src} "
                                    f"!= state.input_customer='{_hp_b_cn_stale}'); using cur_cycle payload"
                                )
                    except Exception:
                        pass
        except Exception:
            pass
        # Entry-log so we can see HOT-PATH-B was considered and why it
        # did (not) fire.
        logger.info(
            f"[BrowserAutomation] HOT-PATH-B: entry "
            f"event_type={_hp_b_evt_type or 'none'}, "
            f"payload_keys={list(_hp_b_payload.keys()) if _hp_b_payload else []}, "
            f"payload_src={_hp_b_payload_src}, "
            f"payload_customer={_hp_b_payload.get('customer_name') or _hp_b_payload.get('customer_id') or '-'}, "
            f"rules_configured={len(_hp_b_actions_list) if isinstance(_hp_b_actions_list, list) else 0}, "
            f"node={hook_ctx.node_name}"
        )
        try:
            from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.system_message_filter import (
                first_system_row_match as _hp_b_system_row_match,
            )
            _hp_b_system_reason = _hp_b_system_row_match(_hp_b_payload)
            if _hp_b_system_reason:
                logger.warning(
                    f"[BrowserAutomation] HOT-PATH-B: dropped system/non-customer "
                    f"reply payload reason={_hp_b_system_reason!r}, "
                    f"customer={_hp_b_payload.get('customer_name') or _hp_b_payload.get('customer_id')!r}, "
                    f"node={hook_ctx.node_name}"
                )
                state.setdefault("result", {})["llm_result"] = {
                    "all_done": True,
                    "work_done": False,
                    "hot_path": True,
                    "hot_path_type": "system_reply_drop",
                }
                return state
        except Exception as _hp_b_system_err:
            logger.debug(
                f"[BrowserAutomation] HOT-PATH-B: system-payload filter failed "
                f"(non-fatal): {_hp_b_system_err}"
            )
        if isinstance(_hp_b_actions_list, list) and _hp_b_actions_list:

            for _hp_b_rule in _hp_b_actions_list:
                if not isinstance(_hp_b_rule, dict):
                    continue
                _hp_b_trigger = _hp_b_rule.get("trigger", {})
                # Check trigger conditions
                if _hp_b_trigger.get("event_type") and _hp_b_trigger["event_type"] != _hp_b_evt_type:
                    continue
                _hp_b_required = _hp_b_trigger.get("has_fields", [])
                if not all(f in _hp_b_payload for f in _hp_b_required):
                    continue
                # Trigger matched — execute action sequence
                _hp_b_action_seq = _hp_b_rule.get("actions", [])
                if not _hp_b_action_seq:
                    continue
                logger.info(
                    f"[BrowserAutomation] HOT-PATH-B: trigger matched "
                    f"(event={_hp_b_evt_type}, rule={_hp_b_trigger}), "
                    f"executing {len(_hp_b_action_seq)} actions"
                )
                # ── Replay dedup guard (fixes observed crosstalk loop) ──
                # 2026-04-22 11:51 run: HOT-PATH-B re-entered 8+ times with
                # an IDENTICAL payload ({customer_name:'客户B', response_text:...})
                # because send_response_back's fallback path keeps re-firing
                # the same chat_message after `Chat not found: 客户B` errors.
                # Each replay re-ran feige_open_session + feige_send_message,
                # and due to a brief focus race between cycles, some of those
                # sends landed in the wrong customer's chat pane (客户C got
                # 客户B's XXL answer).  Short-TTL dedup on (cust, reply-hash)
                # breaks the loop without blocking legitimate future replies.
                _hp_b_dedup_cust = (
                    _hp_b_payload.get("customer_name")
                    or _hp_b_payload.get("customer_id")
                    or ""
                )
                _hp_b_dedup_reply = _hp_b_payload.get("response_text") or ""
                _hp_b_source_msg_id = str(
                    _hp_b_payload.get("source_customer_msg_id")
                    or _hp_b_payload.get("latest_message_msg_id")
                    or _hp_b_payload.get("reply_to_msg_id")
                    or ""
                ).strip()
                _hp_b_claim_cust = _hp_b_dedup_cust
                _hp_b_claim_reply = _hp_b_dedup_reply
                _hp_b_claim_source_msg_id = _hp_b_source_msg_id
                _hp_b_dedup_age = _ds.claim_send_for_turn(
                    _hp_b_dedup_cust, _hp_b_dedup_reply, _hp_b_source_msg_id
                )
                if _hp_b_dedup_age > 0:
                    logger.info(
                        f"[BrowserAutomation] HOT-PATH-B: dedup skip "
                        f"cust={_hp_b_dedup_cust!r} reply_len="
                        f"{len(_hp_b_dedup_reply)} (identical reply already "
                        f"sent {_hp_b_dedup_age:.1f}s ago, "
                        f"source_msg_id={_hp_b_source_msg_id!r}), "
                        f"node={hook_ctx.node_name}"
                    )
                    # Release the cross-scope inflight lock so the
                    # *next* genuine customer turn isn't blocked by
                    # the stale inflight record from the loop.
                    try:
                        _hp_b_skip_cust = hook_ctx.normalize_dispatch_identity_key(_hp_b_dedup_cust)
                        if _hp_b_skip_cust:
                            hook_ctx.clear_dispatch_inflight(_hp_b_skip_cust)
                    except Exception:
                        pass
                    if (
                        _hp_b_payload_src == "state.input[response-fallback]"
                        and isinstance(state, dict)
                        and state.get("_ecan_predispatch_actionable_items")
                    ):
                        try:
                            state.pop("input", None)
                            state.pop("current_invocation_input", None)
                            _hp_b_msgs = state.get("messages")
                            if isinstance(_hp_b_msgs, list) and len(_hp_b_msgs) > 4:
                                _hp_b_msgs[4] = ""
                            _hp_b_attrs = state.get("attributes")
                            if isinstance(_hp_b_attrs, dict):
                                _hp_b_attrs.pop("current_invocation_input", None)
                        except Exception:
                            pass
                        logger.info(
                            f"[BrowserAutomation] HOT-PATH-B: deduped "
                            f"response-fallback will not short-circuit "
                            f"pre-dispatch actionable_items, "
                            f"node={hook_ctx.node_name}"
                        )
                        return None
                    state.setdefault("result", {})["llm_result"] = {
                        "all_done": True, "work_done": False,
                        "hot_path": True, "hot_path_type": "dedup_skip",
                    }
                    return state
                _hp_b_claim_active = True
                # ── Pre-record the outgoing reply text BEFORE send ──
                # The equality guard in PreDispatch compares the DOM's
                # sidebar `last_message` against this recorded text to
                # recognise our own DOM-echo events and skip them.  By
                # recording *before* feige_send_message runs, we close
                # the race window entirely: if a DOM diff fires while
                # typing is in flight, the recorded text is already
                # available for comparison.  If the send ultimately
                # fails, the recorded text is harmless — the DOM won't
                # contain it, so the equality guard will never match a
                # genuine event against it.
                try:
                    _hp_b_pre_cust = hook_ctx.normalize_dispatch_identity_key(
                        _hp_b_payload.get("customer_name")
                        or _hp_b_payload.get("customer_id")
                        or ""
                    )
                    _hp_b_pre_reply = _ds.remember_agent_reply(
                        _hp_b_pre_cust,
                        _hp_b_payload.get("response_text") or ""
                    )
                    if _hp_b_pre_cust and _hp_b_pre_reply:
                        logger.info(
                            f"[BrowserAutomation] HOT-PATH-B: pre-recorded "
                            f"last_agent_reply for '{_hp_b_pre_cust}' "
                            f"(len={len(_hp_b_pre_reply)}, before send), "
                            f"node={hook_ctx.node_name}"
                        )
                except Exception as _hp_b_pre_err:
                    logger.warning(
                        f"[BrowserAutomation] HOT-PATH-B: pre-record reply failed: {_hp_b_pre_err}"
                    )
                from agent.ec_skills.browser_use_extension.extension_tools_service import custom_controller as _hp_b_ctrl
                _hp_b_actions_reg = _hp_b_ctrl.registry.registry.actions
                _hp_b_session = await hook_ctx.get_or_create_browser_session(
                    hook_ctx.mainwin, state=state, calling_agent_id=hook_ctx.calling_agent_id
                )
                if not _hp_b_session:
                    logger.warning("[BrowserAutomation] HOT-PATH-B: no browser session")
                    if _hp_b_claim_active:
                        try:
                            _ds.unclaim_send_for_turn(
                                _hp_b_claim_cust,
                                _hp_b_claim_reply,
                                _hp_b_claim_source_msg_id,
                            )
                        except Exception:
                            pass
                        _hp_b_claim_active = False
                    break
                # ── Delegate Feige DOM orchestration to the hook bundle ──
                # (Phase 4 B-refined cleanup, 2026-04-23.)  The
                # ~440 lines of pre-action tab focus, typing-lock
                # acquire, action-sequence execution with per-tool
                # verification (post-open active-customer check,
                # pre-send re-verify + re-open recovery), and
                # post-success tab restore now live in
                # ``feige_chat.hot_path.execute``.  Typing-lock
                # release is handled inside the executor's
                # ``finally`` for every exit path (success,
                # abort, exception).
                from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.hot_path import (
                    execute as _hp_b_feige_execute,
                )
                _hp_b_typing_cust = hook_ctx.normalize_dispatch_identity_key(
                    _hp_b_payload.get("customer_name")
                    or _hp_b_payload.get("customer_id")
                    or ""
                )
                _hp_b_outcome = await _hp_b_feige_execute(
                    browser_session=_hp_b_session,
                    customer_key=_hp_b_typing_cust,
                    action_seq=_hp_b_action_seq,
                    payload=_hp_b_payload,
                    actions_registry=_hp_b_actions_reg,
                    resolve_template=hook_ctx.resolve_template,
                    node_name=hook_ctx.node_name,
                )
                _hp_b_all_ok = _hp_b_outcome.ok
                _hp_b_typing_acquired = _hp_b_outcome.typing_acquired
                logger.info(
                    f"[BrowserAutomation] HOT-PATH-B: executor returned "
                    f"ok={_hp_b_all_ok} reason={_hp_b_outcome.reason!r} "
                    f"actions_attempted={_hp_b_outcome.actions_attempted} "
                    f"last_tool_error={_hp_b_outcome.last_tool_error!r}, "
                    f"node={hook_ctx.node_name}"
                )

                # (Feige action-loop body moved to
                # ``feige_chat.hot_path.execute`` — see above.)
                if (
                    not _hp_b_all_ok
                    and _hp_b_outcome.reason == "stale_reply_source_msg_id"
                ):
                    # The reply reached the front desk correctly, but it
                    # answers an older Feige customer bubble.  Treat it as
                    # handled/dropped, leave the recent-send claim in place
                    # briefly to suppress replays, and do not clear a newer
                    # dispatch inflight lock for the same customer.
                    _hp_b_claim_active = False
                    try:
                        _stale_cust = hook_ctx.normalize_dispatch_identity_key(
                            _hp_b_payload.get("customer_name")
                            or _hp_b_payload.get("customer_id")
                            or ""
                        )
                        _expected_msg_id = str(
                            _hp_b_payload.get("source_customer_msg_id")
                            or _hp_b_payload.get("latest_message_msg_id")
                            or _hp_b_payload.get("reply_to_msg_id")
                            or ""
                        ).strip()
                        _current_msg_id = _ds.last_dispatched_msg_id_by_customer.get(
                            _stale_cust, ""
                        )
                        if _stale_cust and (
                            not _current_msg_id or _current_msg_id == _expected_msg_id
                        ):
                            hook_ctx.clear_dispatch_inflight(_stale_cust)
                            logger.info(
                                f"[BrowserAutomation] HOT-PATH-B: cleared "
                                f"dispatch_inflight after stale reply drop "
                                f"for cust={_stale_cust!r}, node={hook_ctx.node_name}"
                            )
                        else:
                            logger.info(
                                f"[BrowserAutomation] HOT-PATH-B: kept "
                                f"dispatch_inflight after stale reply drop "
                                f"for cust={_stale_cust!r} because newer "
                                f"msg_id is recorded, node={hook_ctx.node_name}"
                            )
                    except Exception as _hp_b_stale_err:
                        logger.debug(
                            f"[BrowserAutomation] HOT-PATH-B: stale-drop "
                            f"inflight handling failed: {_hp_b_stale_err}"
                        )
                    state.setdefault("result", {})["llm_result"] = {
                        "all_done": True,
                        "work_done": False,
                        "hot_path": True,
                        "hot_path_type": "stale_reply_drop",
                    }
                    logger.warning(
                        f"[BrowserAutomation] HOT-PATH-B: dropped stale "
                        f"reply instead of typing it, node={hook_ctx.node_name}"
                    )
                    return state
                if _hp_b_all_ok:
                    # Mark this (cust, reply) as sent so any immediate
                    # replay of the same chat_message (from
                    # send_response_back fallback path) is deduped
                    # by the guard at the top of HOT-PATH-B.
                    try:
                        _ds.mark_sent_for_turn(
                            _hp_b_dedup_cust,
                            _hp_b_dedup_reply,
                            _hp_b_source_msg_id,
                        )
                    except Exception:
                        pass
                    _hp_b_claim_active = False
                    # Reply text was already pre-recorded before send
                    # (see the `Pre-record the outgoing reply text BEFORE
                    # send` block above). No timer-based cooldown is
                    # needed — PreDispatch's equality guard uses the
                    # pre-recorded text directly to recognise DOM echoes.

                    # Release the QA-response pending lock so the next
                    # *genuine* customer turn for this customer can be
                    # dispatched again.  Acquired in
                    # agent.mcp.server.chat_utils.chat_tools.send_chat
                    # on the first response-bearing payload.  Keyed by
                    # (recipient=this typing agent, customer).  Safe
                    # no-op if the lock already expired via TTL.
                    try:
                        from agent.mcp.server.chat_utils.chat_tools import (
                            clear_qa_response_pending as _hp_b_clear_pending,
                        )
                        _hp_b_clr_cust = hook_ctx.normalize_dispatch_identity_key(
                            _hp_b_payload.get("customer_name")
                            or _hp_b_payload.get("customer_id")
                            or ""
                        )
                        if _hp_b_clr_cust and hook_ctx.calling_agent_id:
                            _hp_b_clear_pending(str(hook_ctx.calling_agent_id), _hp_b_clr_cust)
                            logger.info(
                                f"[BrowserAutomation] HOT-PATH-B: cleared "
                                f"qa_response_pending lock for "
                                f"recipient={hook_ctx.calling_agent_id!r} "
                                f"cust={_hp_b_clr_cust!r}, node={hook_ctx.node_name}"
                            )
                    except Exception as _hp_b_clr_err:
                        logger.debug(
                            f"[BrowserAutomation] HOT-PATH-B: "
                            f"qa_response_pending clear failed: {_hp_b_clr_err}"
                        )

                    # Release the cross-scope dispatch-inflight
                    # lock so the next customer turn (or a
                    # queued follow-up already visible in the
                    # sidebar) can be dispatched by the first
                    # PreDispatch that notices it.
                    try:
                        if _hp_b_clr_cust:
                            hook_ctx.clear_dispatch_inflight(_hp_b_clr_cust)
                            logger.info(
                                f"[BrowserAutomation] HOT-PATH-B: cleared "
                                f"dispatch_inflight lock for "
                                f"cust={_hp_b_clr_cust!r}, node={hook_ctx.node_name}"
                            )
                    except Exception as _hp_b_cdi_err:
                        logger.debug(
                            f"[BrowserAutomation] HOT-PATH-B: "
                            f"dispatch_inflight clear failed: {_hp_b_cdi_err}"
                        )
                    # Evict this customer from assigned_sessions so the next
                    # customer message for them re-dispatches. Without this, the
                    # PreDispatch dedup guard (`if assigned_sessions.get(sid): continue`)
                    # would permanently skip this customer after their first reply.
                    try:
                        # Prefer the shared module-level dispatch_state
                        # (see hook_ctx.dispatch_state_by_agent). Fall back
                        # to the per-session attribute only if for some reason
                        # PreDispatch hasn't run yet.
                        _hp_b_shared_key = (
                            str(hook_ctx.calling_agent_id or ""),
                            str(hook_ctx.node_name or ""),
                            "_ecan_frontdesk_dispatch_state",
                        )
                        _hp_b_ds = hook_ctx.dispatch_state_by_agent.get(_hp_b_shared_key)
                        if not isinstance(_hp_b_ds, dict):
                            _hp_b_ds = getattr(_hp_b_session, "_ecan_frontdesk_dispatch_state", None)
                        if isinstance(_hp_b_ds, dict):
                            _hp_b_as = _hp_b_ds.get("assigned_sessions") or {}
                            _hp_b_raw_sid = (
                                _hp_b_payload.get("session_id")
                                or _hp_b_payload.get("customer_name")
                                or _hp_b_payload.get("customer_id")
                                or ""
                            )
                            if _hp_b_raw_sid and _hp_b_raw_sid in _hp_b_as:
                                _hp_b_as.pop(_hp_b_raw_sid, None)
                                logger.info(
                                    f"[BrowserAutomation] HOT-PATH-B: evicted "
                                    f"assigned_sessions[{_hp_b_raw_sid!r}] so next "
                                    f"customer message will re-dispatch, node={hook_ctx.node_name}"
                                )
                    except Exception as _hp_b_evict_err:
                        logger.debug(
                            f"[BrowserAutomation] HOT-PATH-B: assigned_sessions eviction failed: {_hp_b_evict_err}"
                        )
                    # (Tab restore + typing-lock release now
                    # handled inside feige_chat.hot_path.execute.)
                    state.setdefault("result", {})["llm_result"] = {
                        "all_done": True, "work_done": False,
                        "hot_path": True, "hot_path_type": "configurable",
                    }
                    logger.info(f"[BrowserAutomation] HOT-PATH-B: all actions completed, node={hook_ctx.node_name}")
                    return state
                else:
                    if _hp_b_claim_active:
                        try:
                            _ds.unclaim_send_for_turn(
                                _hp_b_claim_cust,
                                _hp_b_claim_reply,
                                _hp_b_claim_source_msg_id,
                            )
                        except Exception:
                            pass
                        _hp_b_claim_active = False
                    # Any action in the sequence failed (e.g.
                    # feige_open_session returning "Session not
                    # found" when Feige's SPA is transiently in a
                    # bad state).  Release the cross-scope
                    # `_dispatch_inflight` lock here —
                    # otherwise PreDispatch keeps skipping the
                    # next message for this customer for the full
                    # 120 s TTL (observed 2026-04-22 11:18:38 —
                    # customer A's question sat unanswered for
                    # `1m 42s` with repeated
                    # `PreDispatch inflight skip ... ttl=120.0s`).
                    # We deliberately do NOT clear
                    # `qa_response_pending` or evict
                    # `assigned_sessions`: the QA worker already
                    # generated a reply and we want the *next*
                    # genuine customer turn to cause a fresh
                    # reply, not for PreDispatch to race with a
                    # half-consumed state.
                    try:
                        _hp_b_fail_cust = hook_ctx.normalize_dispatch_identity_key(
                            _hp_b_payload.get("customer_name")
                            or _hp_b_payload.get("customer_id")
                            or ""
                        )
                        if _hp_b_fail_cust:
                            hook_ctx.clear_dispatch_inflight(_hp_b_fail_cust)
                            logger.info(
                                f"[BrowserAutomation] HOT-PATH-B: released "
                                f"dispatch_inflight after action-failure "
                                f"for cust={_hp_b_fail_cust!r}, node={hook_ctx.node_name}"
                            )
                    except Exception as _hp_b_fail_cdi_err:
                        logger.debug(
                            f"[BrowserAutomation] HOT-PATH-B: inflight clear "
                            f"after failure: {_hp_b_fail_cdi_err}"
                        )
                    # (Typing-lock release now handled inside
                    # feige_chat.hot_path.execute's finally.)
                break  # Only try first matching rule
    except asyncio.CancelledError:
        # ── Diagnostic surface (2026-04-28) ──
        # ``CancelledError`` is ``BaseException`` (not ``Exception``)
        # in Python 3.8+, so the previous bare ``except Exception``
        # below would not log it.  When the parent persistent-worker
        # cycle is cancelled mid-await (e.g., the CDP focus call in
        # ``ensure_feige_tab_focused`` hangs under contention and the
        # supervisor pre-empts), HOT-PATH-B was silently torn down —
        # producing the "ensure-feige-tab: 1 candidate → silence"
        # signature that hid the cejs-reply-never-arrives regression
        # observed 2026-04-28 05:17:27.  Log + re-raise so the cancel
        # still propagates correctly to the runner.
        logger.warning(
            "[BrowserAutomation] HOT-PATH-B: cancelled mid-execute "
            "(parent cycle pre-empted) — typing-lock release handled "
            "by hot_path.execute's finally"
        )
        raise
    except Exception as _hp_b_err:
        if _hp_b_claim_active:
            try:
                _ds.unclaim_send_for_turn(
                    _hp_b_claim_cust,
                    _hp_b_claim_reply,
                    _hp_b_claim_source_msg_id,
                )
            except Exception:
                pass
        logger.warning(
            f"[BrowserAutomation] HOT-PATH-B: check failed (non-fatal): {_hp_b_err}",
            exc_info=True,
        )
        # (Typing-lock release now handled inside
        # feige_chat.hot_path.execute's finally — no defensive
        # release needed here.)



async def before_run_hook(
    agent: Any,
    state: dict,
    inputs: dict,
    hook_ctx: Any,
) -> dict | None:
    """Late-phase hook: PreDispatch customer-message fan-out.

    Fires when a `browser_event` arrives indicating a new customer
    message.  Reads the sidebar preview, scrapes the freshest customer
    bubble, applies msg-id dedup + DOM-echo guards, and fans out to
    available Q&A workers via the generic fan-out skeleton.  Returns a
    completed state dict when PreDispatch handled the event (skips the
    LLM); returns `None` to let the LLM proceed.
    """
    # ── Parse preDispatch config ──
    # Back-compat default: the pre-refactor monolithic wrapper always
    # invoked the Feige-specific enrichment (customer-bubble scrape,
    # msg-id dedup, dom-echo fallback).  The generic skeleton made
    # this opt-in via `preDispatch.site_plugin`, which silently broke
    # existing skill configs (2026-04-23 regression).  Default to
    # `feige_chat` when the raw config omits the field; explicit
    # empty string `""` still opts out.
    _pd_raw = hook_ctx.parse_json_input(inputs, "preDispatch") or {}
    if "site_plugin" not in _pd_raw:
        _pd_raw["site_plugin"] = "feige_chat"
    _pd_config = DispatchConfig.from_raw(_pd_raw)
    logger.info(
        f"[BrowserAutomation] PreDispatch config: enabled={_pd_config.enabled}, "
        f"source_monitor_label={_pd_config.source_monitor_label!r}, "
        f"site_plugin={_pd_config.site_plugin!r}, node={hook_ctx.node_name}"
    )
    if not _pd_config.enabled:
        return None

    # ── Build DispatchContext from hook_ctx ──
    _pd_ctx = DispatchContext(
        state=state,
        calling_agent_id=str(hook_ctx.calling_agent_id or ""),
        node_name=str(hook_ctx.node_name or ""),
        mainwin=hook_ctx.mainwin,
        scope_key=hook_ctx.resolve_scope_key(state),
        cached_browser_sessions=hook_ctx.cached_browser_sessions,
        dispatch_state_by_agent=hook_ctx.dispatch_state_by_agent,
        customer_last_dispatched_msg_id=_ds.last_dispatched_msg_id_by_customer,
        auto_dispatch_last_agent_reply=_ds.last_agent_reply_by_customer,
        is_dispatch_inflight=hook_ctx.is_dispatch_inflight,
        mark_dispatch_inflight=hook_ctx.mark_dispatch_inflight,
        clear_dispatch_inflight=hook_ctx.clear_dispatch_inflight,
        inflight_ttl_s=hook_ctx.inflight_ttl_s,
        normalize_dispatch_identity_key=hook_ctx.normalize_dispatch_identity_key,
        normalize_reply_text=_ds.normalize_reply_text,
        safe_format_dict=hook_ctx.safe_format_dict,
        feige_typing_holder_getter=_typing_lock.holder,
    )
    return await _run_frontdesk_dispatch(_pd_config, _pd_ctx, agent)


def register() -> None:
    """Register this bundle's hooks with `build_node`.

    Called automatically when the `feige_chat` package is imported
    (see `__init__.py`).  Idempotent: re-importing the package does
    not double-register.
    """
    from agent.ec_skills.build_node import (
        register_before_browser_session_setup_hook,
        register_before_browser_use_run_hook,
    )
    # Order matters for readability only — each hook is invoked at
    # its own distinct phase, so registration order within a phase is
    # the only thing the hook registry sees.
    register_before_browser_session_setup_hook(before_session_setup_hook)
    register_before_browser_use_run_hook(before_run_hook)
