"""Tier-aware port of front_desk.before_run_hook (Step 2f, cloud half).

This is the **cloud_only** half of PreDispatch — the per-item dispatch
decision flow that:

1. Asks local to scrape each customer's latest bubble (via
   :class:`ScrapeFunction` proxy)
2. Applies dedup guards (msg-id strict, dom-echo fallback,
   assigned_sessions same-message fallback)
3. Acquires the cross-customer inflight lock
4. Routes to a Q&A worker via ``ctx.send_chat``
5. Records last-dispatched-msg-id for the next cycle's dedup

Companion to :mod:`pre_dispatch_scrape_v2` (local_extract half) — the
two together replicate v1's PreDispatch fan-out per customer item.

What's deferred from v1
-----------------------

The v1 ``frontdesk_dispatch.run`` orchestrator wraps this per-item flow
with several integration concerns: monitor lookup, tab discovery,
recipient-pool building from agent registry, multi-item loop with
opened/assigned/failure row tracking.  Those are integration plumbing
(belong to the runtime, not the hook) and stay in v1 until step 4 wires
them up.

Step 2f's port focuses on the **per-item decision flow** because that's
where the cloud/local boundary lives.  The cloud hook accepts already-
extracted ``actionable_items`` and a ``recipient_pool`` as direct
parameters so tests can drive it without staging an event monitor.

What stays identical
--------------------

* Three-stage dedup: msg-id strict → dom-echo text → assigned_sessions
  same-message text
* Inflight-acquire-before-send protocol (closes the 100-500ms window
  v1 docstring identifies as a duplicate-fire risk)
* On send_chat success: record last-dispatched-msg-id; on failure:
  release inflight
* Recipient assignment via round-robin over the supplied pool
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from agent.ec_skills.browser_node.contexts import (
    CloudHookContext,
    PromptBuildResult,
)
from .pre_dispatch_scrape_v2 import ScrapeFunction, ScrapeResult
from .trace_ledger import log_event, log_payload, short_text

logger = logging.getLogger("ecan.hooks.feige_chat.v2")

__all__ = [
    "DispatchOutcome",
    "FeigePreDispatchHookV2",
    "before_run_hook_v2",
]


# ─────────────────────────────────────────────────────────────────────────────
# State-key prefixes (mirror actionable_items_v2's pattern)
# ─────────────────────────────────────────────────────────────────────────────


# `assigned_sessions[session_id]` — what session was last assigned and to whom.
# In v1 this was a dict at module scope; in cloud world it's per-session KV
# so multiple front-desk skill runs don't share it across sessions.
_ASSIGNED_SESSION_PREFIX = "pd:assigned_session:"  # pd = pre_dispatch

# `last_agent_reply[customer_key]` — the reply HOT-PATH-B pre-recorded
# before typing.  In v1 this lives in dispatch_state.last_agent_reply_by_customer.
# In hybrid mode, HOT-PATH-B (local) writes via cloud RPC; cloud reads it here
# during the dom-echo fallback.  Stored on ctx.state for now (Step 4 will
# decide whether to surface it as a typed DispatchState field).
_LAST_AGENT_REPLY_PREFIX = "pd:last_agent_reply:"

# `rr_index` — round-robin pointer for recipient assignment.  Stored per node
# so concurrent skill runs don't share their RR state.
_RR_INDEX_KEY_PREFIX = "pd:rr_index:"


@dataclass
class _ItemOutcome:
    """Internal: per-item decision result, exposed in DispatchOutcome.assigned/skipped/failed."""
    session_id: str
    customer_key: str
    skip_reason: str = ""
    recipient_agent_id: str = ""
    message_id: str = ""
    error: str = ""

    @property
    def assigned(self) -> bool:
        return bool(self.recipient_agent_id and not self.error)


@dataclass
class DispatchOutcome:
    """Aggregate result returned by :func:`before_run_hook_v2`.

    Used by the orchestrator to populate state["result"]["llm_result"]
    and to decide whether to short-circuit the LLM (any successful
    assignment → short-circuit).
    """
    assigned: list[_ItemOutcome] = field(default_factory=list)
    skipped: list[_ItemOutcome] = field(default_factory=list)
    failed: list[_ItemOutcome] = field(default_factory=list)

    @property
    def short_circuit(self) -> bool:
        return bool(self.assigned)


# ─────────────────────────────────────────────────────────────────────────────
# Dedup helpers — pure-ish (read state via callables, no module-level dicts)
# ─────────────────────────────────────────────────────────────────────────────


def _normalize_reply_text(text: str) -> str:
    """Collapse whitespace and prefix-limit so DOM-echo comparisons are
    robust against Feige's sidebar text trimming.

    Mirrors v1's ``dispatch_state.normalize_reply_text`` semantics.
    """
    if not isinstance(text, str):
        return ""
    return " ".join(text.split())[:120]


def _check_msg_id_dedup(
    customer_key: str,
    scraped_msg_id: str,
    *,
    last_dispatched_lookup: Callable[[str], str],
) -> tuple[bool, str]:
    """Strict msg-id dedup: customer hasn't said anything new.

    Returns ``(skip, reason)``.  Safe no-op when scraped_msg_id is empty.
    """
    if not scraped_msg_id:
        return False, ""
    prev = last_dispatched_lookup(customer_key)
    if prev and prev == scraped_msg_id:
        return True, "msg_id_dedup"
    return False, ""


def _check_dom_echo_fallback(
    item: dict,
    customer_key: str,
    session_id: str,
    *,
    state_get: Callable[[str, Any], Any],
) -> tuple[bool, str]:
    """Two secondary defences when the chat-thread scrape failed:
    text-based dom-echo, and assigned_sessions same-message dedup.
    """
    # (a) text-based dom-echo
    last_reply = state_get(_LAST_AGENT_REPLY_PREFIX + customer_key, "") or ""
    item_last_raw = str(
        item.get("last_message")
        or item.get("latest_message")
        or item.get("message")
        or ""
    )
    item_last_norm = _normalize_reply_text(item_last_raw)
    try:
        from .dispatch_state import reply_echo_matches as _reply_echo_matches
    except Exception:
        _reply_echo_matches = None
    if last_reply and item_last_norm and (
        item_last_norm == last_reply
        or (
            _reply_echo_matches is not None
            and _reply_echo_matches(item_last_raw, last_reply)
        )
    ):
        logger.info(
            f"[V2 pre_dispatch] dom-echo skip session={session_id!r} "
            f"cust={customer_key!r} (sidebar last_message matches our "
            f"pre-recorded reply)"
        )
        return True, "dom_echo"

    # (b) assigned_sessions same-message guard
    assigned = state_get(_ASSIGNED_SESSION_PREFIX + session_id, None)
    if assigned:
        prior_text = ""
        if isinstance(assigned, dict):
            prior_text = str(
                assigned.get("latest_message")
                or assigned.get("last_message")
                or assigned.get("source_latest_message")
                or ""
            )
        prior_norm = _normalize_reply_text(prior_text) if prior_text else ""
        if prior_norm and item_last_norm and prior_norm == item_last_norm:
            logger.info(
                f"[V2 pre_dispatch] assigned-sessions skip "
                f"session={session_id!r} cust={customer_key!r} "
                f"(same message already assigned; prior assignment={assigned})"
            )
            return True, "assigned_sessions_same_message"
        # Multi-slot recent-reply ledger: also block supersede when
        # sidebar echoes any of our recently-typed messages (real reply
        # OR placeholder).  Single-slot last_reply check above misses
        # placeholders typed alongside the real reply.
        try:
            from .dispatch_state import (
                matches_recent_agent_reply as _matches_recent_reply,
            )
        except Exception:
            _matches_recent_reply = None
        if (
            _matches_recent_reply is not None
            and item_last_raw
            and _matches_recent_reply(customer_key, item_last_raw)
        ):
            logger.info(
                f"[V2 pre_dispatch] recent-echo skip "
                f"session={session_id!r} cust={customer_key!r} "
                f"(sidebar text matches a recent typed message — "
                f"DOM-echo of real reply or placeholder; "
                f"current={item_last_raw[:80]!r})"
            )
            return True, "recent_echo_supersede_blocked"
        logger.info(
            f"[V2 pre_dispatch] assigned-sessions supersede "
            f"session={session_id!r} cust={customer_key!r} "
            f"(current sidebar text differs from prior assignment, "
            f"allowing dispatch; current={item_last_raw[:80]!r}, "
            f"prior={prior_text[:80]!r}, prior assignment={assigned})"
        )

    return False, ""


# ─────────────────────────────────────────────────────────────────────────────
# Per-item dispatcher
# ─────────────────────────────────────────────────────────────────────────────


async def _dispatch_one_item(
    item: dict,
    *,
    ctx: CloudHookContext,
    scrape_fn: ScrapeFunction,
    recipient_pool: list[str],
    rr_idx_key: str,
    node_name: str,
) -> _ItemOutcome:
    """Per-item pipeline — port of v1's ``_dispatch_one_item`` minus
    the tab/session plumbing."""
    customer_name = str(item.get("customer_name") or "")
    customer_id = str(item.get("customer_id") or "")
    session_id = str(item.get("session_id") or customer_id or customer_name or "")
    customer_key = ctx.normalize_dispatch_identity_key(customer_id or customer_name)

    outcome = _ItemOutcome(session_id=session_id, customer_key=customer_key)

    def _ledger_skip(reason: str, **extra: Any) -> None:
        log_event(
            "predispatch_skip",
            customer=customer_key or customer_name or customer_id,
            customer_id=customer_id,
            customer_name=customer_name,
            session_id=session_id,
            source_msg_id=str(
                extra.pop("source_msg_id", "")
                or item.get("latest_message_msg_id")
                or item.get("msg_id")
                or ""
            ),
            latest_preview=str(item.get("last_message") or item.get("latest_message") or ""),
            reason=reason,
            node=node_name,
            **extra,
        )

    log_event(
        "predispatch_item_start",
        customer=customer_key or customer_name or customer_id,
        customer_id=customer_id,
        customer_name=customer_name,
        session_id=session_id,
        source_msg_id=str(item.get("latest_message_msg_id") or item.get("msg_id") or ""),
        latest_preview=str(item.get("last_message") or item.get("latest_message") or ""),
        node=node_name,
    )

    if not customer_key:
        outcome.skip_reason = "no_customer_key"
        _ledger_skip("no_customer_key")
        return outcome

    # ── Terminal-undeliverable fast-fail ─────────────────────────────
    # See ``front_desk_hot_path_v2._is_session_unrecoverable`` for the
    # incident write-up.  If a previous HOT-PATH-B delivery attempt for
    # this customer hit "Session not found in current conversations"
    # (or another terminal marker), Feige has closed the chat server-
    # side.  Skip dispatching to a dead chat — the reply would just hit
    # the same ``feige_open_session`` failure again.  The flag clears
    # when the customer re-engages and PreDispatch sees their fresh
    # bubble succeed below (after scrape + actual dispatch).
    try:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.front_desk_hot_path_v2 import (
            is_customer_undeliverable as _is_undeliverable,
        )
        if _is_undeliverable(customer_key):
            outcome.skip_reason = "customer_undeliverable_session_gone"
            _ledger_skip("customer_undeliverable_session_gone")
            logger.warning(
                f"[V2 pre_dispatch] skipping cust={customer_key!r}: "
                f"flagged undeliverable by previous HOT-PATH-B failure "
                f"(Feige chat is gone).  Will retry when customer re-engages."
            )
            return outcome
    except Exception:  # pragma: no cover — defensive only
        pass

    # ── 1. Local DOM scrape (the only cross-tier call) ──
    try:
        scrape = await scrape_fn(customer_name=customer_name)
    except Exception as exc:
        logger.warning(
            f"[V2 pre_dispatch] scrape_fn failed for cust={customer_key!r}: "
            f"{type(exc).__name__}: {exc!r}"
        )
        scrape = ScrapeResult(scrape_ok=False, error=f"scrape_call_error:{exc}")

    log_event(
        "predispatch_scrape_result",
        customer=customer_key,
        customer_id=customer_id,
        customer_name=customer_name,
        session_id=session_id,
        source_msg_id=scrape.msg_id,
        latest_preview=scrape.text or str(item.get("last_message") or ""),
        scrape_ok=bool(scrape.scrape_ok),
        scrape_error=str(scrape.error or ""),
        attachments=len(scrape.attachments or []),
        node=node_name,
    )

    # If scrape succeeded, override item['last_message'] with ground-truth text.
    if scrape.scrape_ok and scrape.text:
        orig = str(item.get("last_message") or "")
        if scrape.text != orig:
            logger.info(
                f"[V2 pre_dispatch] thread-scrape overrode last_message for "
                f"cust={customer_key!r}: sidebar={orig[:40]!r} -> "
                f"customer_bubble={scrape.text[:40]!r}"
            )
            item["last_message"] = scrape.text

    # ── System / platform message guard ──────────────────────────────
    # The IM platform and the built-in 智能客服 inject text into the
    # chat thread (and, more often, into the sidebar preview) that
    # looks like a customer message but isn't.  Examples observed in
    # production logs:
    #
    #   * "当前会话已长时间未回复，若后续仍未回复，平台可能主动介入处理。"
    #     (platform stall warning)
    #   * "您好，现在是人工客服为您服务。为了更高效..."
    #     (handover system msg)
    #   * "亲亲，在哒~很高兴为您服务，请问有什么可以帮您？"
    #     (built-in bot pre-handover greeting)
    #   * "已读" / "转人工"  (DOM label leakage)
    #
    # If we dispatch any of these to the Q&A worker, the LLM
    # earnestly *answers them* — leading to "您好，这条提示像是
    # 系统状态提醒..." kinds of replies that confuse customers and
    # waste tokens.  Filter HERE, before any inflight/send_chat
    # bookkeeping is touched.
    try:
        from .system_message_filter import (
            first_system_row_match as _first_row_match,
            first_matching_pattern as _first_pat,
        )
        _row_hit = _first_row_match(item)
        if _row_hit:
            logger.info(
                f"[V2 pre_dispatch] system-message filter SKIP for "
                f"cust={customer_key!r} reason={_row_hit!r}"
            )
            outcome.skip_reason = _row_hit
            _ledger_skip(_row_hit, source_msg_id=scrape.msg_id)
            return outcome
        _candidate_text = str(item.get("last_message") or "")
        _hit = _first_pat(_candidate_text)
        if _hit:
            logger.info(
                f"[V2 pre_dispatch] system-message filter SKIP for "
                f"cust={customer_key!r} pattern={_hit!r} "
                f"text={_candidate_text[:80]!r}"
            )
            outcome.skip_reason = f"system_message:{_hit}"
            _ledger_skip(f"system_message:{_hit}", source_msg_id=scrape.msg_id)
            return outcome
    except Exception as _smf_exc:
        # Defence-in-depth: a filter failure must not abort dispatch.
        logger.debug(
            f"[V2 pre_dispatch] system-message filter raised "
            f"(non-fatal): {type(_smf_exc).__name__}: {_smf_exc}"
        )

    # Multimodal: when the scraped bubble carries image attachments,
    # eagerly fetch + base64-encode them in parallel here so the Q&A
    # worker's payload is self-contained and the signed CDN URLs (which
    # carry ``x-expires``) don't have a chance to expire en route.  On
    # any per-URL fetch failure we still keep the entry — with a
    # ``fetch_error`` reason and the original URL — so the worker can
    # retry with a longer timeout if it has a vision-capable LLM.
    if scrape.scrape_ok and scrape.attachments:
        try:
            from .image_fetch import fetch_attachments  # local import: avoid hard dep at import time
            enriched = await fetch_attachments(scrape.attachments)
            if enriched:
                item["last_message_attachments"] = enriched
        except Exception as fetch_exc:
            # Never let an attachment fetch break dispatch — fall back
            # to passing raw URLs straight through.
            logger.warning(
                f"[V2 pre_dispatch] fetch_attachments failed for "
                f"cust={customer_key!r}: {type(fetch_exc).__name__}: {fetch_exc!r}; "
                f"forwarding raw URLs"
            )
            item["last_message_attachments"] = list(scrape.attachments)

    # ── 2. Msg-id dedup (only meaningful when scrape gave us an id) ──
    skip, reason = _check_msg_id_dedup(
        customer_key,
        scrape.msg_id,
        last_dispatched_lookup=ctx.dispatch_state.get_last_dispatched_msg_id,
    )
    if skip:
        outcome.skip_reason = reason
        _ledger_skip(reason, source_msg_id=scrape.msg_id)
        return outcome

    # ── 3. Scrape-failure fallback guards ──
    if not scrape.msg_id:
        skip, reason = _check_dom_echo_fallback(
            item, customer_key, session_id, state_get=ctx.state.get,
        )
        if skip:
            outcome.skip_reason = reason
            _ledger_skip(reason, source_msg_id=scrape.msg_id)
            return outcome

    # ── 4. Inflight check ──
    inflight_age = ctx.dispatch_state.is_inflight(customer_key)
    if inflight_age > 0:
        outcome.skip_reason = "inflight"
        _ledger_skip("inflight", source_msg_id=scrape.msg_id, inflight_age_s=inflight_age)
        return outcome

    # ── 5. Recipient pick (sticky-first, busy-aware) ──
    # Replaces pure round-robin (Fix #3, 2026-05-18).  Was: every
    # dispatch incremented rr_idx and picked ``pool[rr_idx % N]``,
    # often landing on a worker still processing its prior turn —
    # observed in 2026-05-18 customer trace where customer 瓦哒嘻哇
    # waited 75 s for assigned worker to finish customer rice robot's
    # earlier "凑满减" turn.
    #
    # New policy (see dispatch_state.pick_recipient):
    #   sticky_if_free → free_worker → round_robin_fallback
    # `sticky` preserves Q&A worker's in-process conversation history
    # for natural multi-turn context; `free_worker` avoids head-of-
    # line blocking when sticky busy; `round_robin` is the safety
    # net when all workers busy (no worse than today's behavior).
    if not recipient_pool:
        outcome.skip_reason = "no_recipients"
        _ledger_skip("no_recipients", source_msg_id=scrape.msg_id)
        return outcome
    rr_idx = int(ctx.state.get(rr_idx_key, 0) or 0)
    from . import dispatch_state as _ds
    recipient_agent_id, pick_reason = _ds.pick_recipient(
        recipient_pool, customer_key, rr_idx,
    )
    if not recipient_agent_id:
        outcome.skip_reason = "no_recipients"
        _ledger_skip("no_recipients", source_msg_id=scrape.msg_id)
        return outcome
    # Always advance rr_idx so the "free pool" rotation spreads across
    # workers even when the sticky path takes precedence.
    ctx.state.set(rr_idx_key, rr_idx + 1)
    outcome.recipient_agent_id = recipient_agent_id
    log_event(
        "predispatch_recipient_selected",
        customer=customer_key,
        customer_id=customer_id,
        customer_name=customer_name,
        session_id=session_id,
        source_msg_id=scrape.msg_id,
        latest_preview=str(item.get("last_message") or ""),
        recipient_agent_id=recipient_agent_id,
        pick_reason=pick_reason,
        rr_index=rr_idx,
        recipient_pool_size=len(recipient_pool),
        node=node_name,
    )

    # ── 6. Mark inflight BEFORE send (closes duplicate-fire window) ──
    try:
        ctx.dispatch_state.mark_inflight(customer_key)
        log_event(
            "predispatch_inflight_marked",
            customer=customer_key,
            customer_id=customer_id,
            customer_name=customer_name,
            session_id=session_id,
            source_msg_id=scrape.msg_id,
            latest_preview=str(item.get("last_message") or ""),
            recipient_agent_id=recipient_agent_id,
            node=node_name,
        )
    except Exception as exc:
        logger.debug(
            f"[V2 pre_dispatch] mark_inflight failed for {customer_key!r}: {exc}"
        )
        log_event(
            "predispatch_inflight_mark_failed",
            customer=customer_key,
            customer_id=customer_id,
            customer_name=customer_name,
            session_id=session_id,
            source_msg_id=scrape.msg_id,
            latest_preview=str(item.get("last_message") or ""),
            recipient_agent_id=recipient_agent_id,
            error=str(exc),
            node=node_name,
            level=logging.WARNING,
        )

    # ── 7. send_chat ──
    payload = {
        "customer_id": customer_id or customer_name,
        "session_id": session_id,
        "customer_name": customer_name,
        "last_message": str(item.get("last_message") or ""),
    }
    if scrape.msg_id:
        payload["latest_message_msg_id"] = scrape.msg_id
    latest_msg = str(item.get("last_message") or "").strip()
    if latest_msg:
        payload["latest_message"] = latest_msg
    _atts = item.get("last_message_attachments")
    if isinstance(_atts, list) and _atts:
        _raw_attachment_count = len(_atts)
        try:
            from .image_store import compact_attachments
            _atts = compact_attachments(_atts)
        except Exception:
            _atts = [dict(a) for a in _atts if isinstance(a, dict)]
        _image_ref_count = sum(1 for a in _atts if isinstance(a, dict) and a.get("image_ref"))
        _stripped_count = sum(1 for a in _atts if isinstance(a, dict) and a.get("data_uri_stripped"))
        _total_bytes = sum(int(a.get("byte_len") or 0) for a in _atts if isinstance(a, dict))
        logger.info(
            "[data-uri-mitigation] predispatch_payload_attachments_compacted "
            "customer=%r raw_count=%d image_refs=%d stripped=%d total_bytes=%d",
            customer_name or customer_id,
            _raw_attachment_count,
            _image_ref_count,
            _stripped_count,
            _total_bytes,
        )
        payload["latest_message_attachments"] = _atts
        payload["last_message_attachments"] = _atts
    log_payload(
        "predispatch_send_chat_start",
        payload,
        recipient_agent_id=recipient_agent_id,
        node=node_name,
    )
    try:
        result = await ctx.send_chat.send_chat(
            recipient_agent_id,
            json.dumps(payload, ensure_ascii=False),
            metadata={
                "sender_agent_id": ctx.calling_agent_id,
                "chat_id": session_id,
                "node_name": node_name,
            },
        )
    except Exception as exc:
        # Release inflight so this customer isn't blocked for the full TTL
        try:
            ctx.dispatch_state.clear_inflight(customer_key)
        except Exception:
            pass
        outcome.error = f"send_chat_exception:{type(exc).__name__}:{exc}"
        log_payload(
            "predispatch_send_chat_exception",
            payload,
            recipient_agent_id=recipient_agent_id,
            error=outcome.error,
            node=node_name,
            level=logging.WARNING,
        )
        return outcome

    if not result.get("success"):
        # send_chat returned failure — release inflight
        try:
            ctx.dispatch_state.clear_inflight(customer_key)
        except Exception:
            pass
        outcome.error = str(result.get("error") or "send_chat_failed")
        log_payload(
            "predispatch_send_chat_failed",
            payload,
            recipient_agent_id=recipient_agent_id,
            error=outcome.error,
            result_preview=short_text(result),
            node=node_name,
            level=logging.WARNING,
        )
        return outcome

    # ── 8. Record success state ──
    outcome.message_id = str(result.get("task_id") or result.get("message_id") or "")
    log_payload(
        "predispatch_send_chat_success",
        payload,
        recipient_agent_id=recipient_agent_id,
        message_id=outcome.message_id,
        resolved_recipient_id=str(result.get("recipient_id") or result.get("recipient") or ""),
        resolved_recipient_name=str(result.get("recipient_name") or ""),
        node=node_name,
    )

    # Successful dispatch → the customer's chat is alive again.  Clear any
    # lingering "terminal undeliverable" flag from a prior session-gone
    # failure so subsequent loops don't fast-fail this customer.  No-op if
    # the flag wasn't set.
    try:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.front_desk_hot_path_v2 import (
            clear_customer_undeliverable as _clear_undeliv,
        )
        _clear_undeliv(customer_key)
    except Exception:  # pragma: no cover — defensive only
        pass

    # ── Sticky + busy-aware tracking (Fix #3, 2026-05-18) ──
    # Record that ``recipient_agent_id`` was just dispatched to so the
    # next cycle's pick_recipient() can avoid the same worker if it's
    # still processing this turn, AND can route the same customer back
    # to it (sticky) for natural multi-turn context preservation.
    try:
        _ds.record_recipient_pick(customer_key, recipient_agent_id)
    except Exception as exc:  # pragma: no cover — defensive only
        logger.debug(
            f"[V2 pre_dispatch] record_recipient_pick failed for "
            f"cust={customer_key!r}: {exc}"
        )

    # Record last-dispatched msg_id (only when scrape gave us one — the
    # next cycle's strict dedup needs this).
    if scrape.msg_id:
        try:
            ctx.dispatch_state.set_last_dispatched_msg_id(customer_key, scrape.msg_id)
            log_payload(
                "predispatch_last_dispatched_recorded",
                payload,
                recipient_agent_id=recipient_agent_id,
                message_id=outcome.message_id,
                node=node_name,
            )
        except Exception as exc:
            logger.debug(
                f"[V2 pre_dispatch] set_last_dispatched_msg_id failed: {exc}"
            )
            log_payload(
                "predispatch_last_dispatched_record_failed",
                payload,
                recipient_agent_id=recipient_agent_id,
                message_id=outcome.message_id,
                error=str(exc),
                node=node_name,
                level=logging.WARNING,
            )

    # Update assigned_sessions cache (for the dom-echo fallback path).
    ctx.state.set(
        _ASSIGNED_SESSION_PREFIX + session_id,
        {
            "recipient_agent_id": recipient_agent_id,
            "message_id": outcome.message_id,
            "latest_message": latest_msg,
            "last_message": latest_msg,
            "latest_message_msg_id": scrape.msg_id,
        },
    )

    return outcome


# ─────────────────────────────────────────────────────────────────────────────
# Cloud-only hook entry point
# ─────────────────────────────────────────────────────────────────────────────


async def before_run_hook_v2(
    state: dict,
    inputs: dict,
    ctx: CloudHookContext,
    *,
    actionable_items: list[dict],
    recipient_pool: list[str],
    scrape_fn: ScrapeFunction,
) -> dict | None:
    """Cloud-only port of front_desk.before_run_hook (PreDispatch).

    Iterates over ``actionable_items``, asks local to scrape each one's
    latest customer bubble, applies the three-stage dedup, and fans out
    survivors to ``recipient_pool`` via ``ctx.send_chat``.

    Parameters
    ----------
    actionable_items
        Items to consider, already extracted by an upstream hook
        (typically :func:`actionable_items_v2.before_prompt_build_hook_v2`)
        OR injected directly via ``inputs``.  Each item is a dict with
        at least ``{customer_name, customer_id, session_id?, last_message}``.
    recipient_pool
        Q&A worker agent IDs available for this round.  Round-robin
        distribution.
    scrape_fn
        :class:`ScrapeFunction` proxy.  In full_local mode wraps a
        direct in-process call to
        :func:`pre_dispatch_scrape_v2.scrape_customer_bubble_v2`; in
        hybrid mode wraps an AppSync RPC to the local executor.

    Returns
    -------
    * ``None`` — no item dispatched (let LLM proceed)
    * a populated state dict with ``hot_path_type='pre_dispatch'`` —
      at least one item dispatched (short-circuit LLM)
    """
    if not actionable_items:
        return None
    if not recipient_pool:
        logger.info(
            f"[V2 pre_dispatch] no recipients in pool; skipping, node={ctx.node_name}"
        )
        return None

    rr_idx_key = _RR_INDEX_KEY_PREFIX + (ctx.node_name or "")
    outcome = DispatchOutcome()

    for item in actionable_items:
        try:
            r = await _dispatch_one_item(
                item,
                ctx=ctx,
                scrape_fn=scrape_fn,
                recipient_pool=recipient_pool,
                rr_idx_key=rr_idx_key,
                node_name=ctx.node_name,
            )
        except Exception as exc:
            logger.warning(
                f"[V2 pre_dispatch] _dispatch_one_item raised "
                f"(non-fatal, item logged then skipped): {exc!r}",
                exc_info=True,
            )
            r = _ItemOutcome(
                session_id=str(item.get("session_id") or ""),
                customer_key="",
                error=f"dispatch_exception:{type(exc).__name__}",
            )

        if r.assigned:
            outcome.assigned.append(r)
            logger.info(
                f"[V2 pre_dispatch] sent session={r.session_id!r} → "
                f"recipient=...{r.recipient_agent_id[-6:] if r.recipient_agent_id else ''} "
                f"msg={r.message_id[:8] if r.message_id else ''}, node={ctx.node_name}"
            )
        elif r.error:
            outcome.failed.append(r)
            logger.warning(
                f"[V2 pre_dispatch] failure for session={r.session_id!r} "
                f"cust={r.customer_key!r}: {r.error}, node={ctx.node_name}"
            )
        else:
            outcome.skipped.append(r)
            logger.info(
                f"[V2 pre_dispatch] skip session={r.session_id!r} "
                f"cust={r.customer_key!r} reason={r.skip_reason!r}, "
                f"node={ctx.node_name}"
            )

    if not outcome.short_circuit:
        return None

    return {
        "result": {
            "llm_result": {
                "all_done": False,
                "work_done": False,
                "hot_path": True,
                "hot_path_type": "pre_dispatch",
                "assigned_count": len(outcome.assigned),
                "skipped_count": len(outcome.skipped),
                "failed_count": len(outcome.failed),
            }
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# Class wrapper
# ─────────────────────────────────────────────────────────────────────────────


class FeigePreDispatchHookV2:
    """Tier ``cloud_only`` PreDispatch hook (cloud half of step 2f's split).

    The :class:`ScrapeFunction` is supplied at construction time:
    full_local binding wraps a direct call to
    :func:`pre_dispatch_scrape_v2.scrape_customer_bubble_v2`; hybrid
    binding wraps an AppSync RPC.
    """

    EXECUTION_TIER = "cloud_only"

    def __init__(
        self,
        config: dict | None = None,
        scrape_fn: ScrapeFunction | None = None,
    ):
        self.config = dict(config or {})
        self.scrape_fn = scrape_fn

    async def run(
        self,
        ctx: CloudHookContext,
        state: dict,
        inputs: dict,
        *,
        actionable_items: list[dict],
        recipient_pool: list[str],
    ) -> dict | None:
        if self.scrape_fn is None:
            logger.warning(
                f"[V2 pre_dispatch] no scrape_fn wired; cannot dispatch, "
                f"node={ctx.node_name}"
            )
            return None
        return await before_run_hook_v2(
            state, inputs, ctx,
            actionable_items=actionable_items,
            recipient_pool=recipient_pool,
            scrape_fn=self.scrape_fn,
        )
