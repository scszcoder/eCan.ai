"""Tier-aware port of front_desk.before_run_hook (Step 2f, cloud half).

This is the **cloud_only** half of PreDispatch — the per-item dispatch
decision flow that:

1. Asks local to scrape each customer's latest bubble (via
   :class:`ScrapeFunction` proxy)
2. Applies dedup guards (msg-id strict, dom-echo fallback, legacy
   assigned_sessions fallback)
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
    text-based dom-echo, and legacy assigned_sessions heuristic.
    """
    # (a) text-based dom-echo
    last_reply = state_get(_LAST_AGENT_REPLY_PREFIX + customer_key, "") or ""
    item_last_norm = _normalize_reply_text(item.get("last_message") or "")
    if last_reply and item_last_norm and item_last_norm == last_reply:
        logger.info(
            f"[V2 pre_dispatch] dom-echo skip session={session_id!r} "
            f"cust={customer_key!r} (sidebar last_message matches our "
            f"pre-recorded reply)"
        )
        return True, "dom_echo"

    # (b) legacy assigned_sessions
    assigned = state_get(_ASSIGNED_SESSION_PREFIX + session_id, None)
    if assigned:
        logger.info(
            f"[V2 pre_dispatch] assigned-sessions skip session={session_id!r} "
            f"cust={customer_key!r} (prior assignment={assigned})"
        )
        return True, "assigned_sessions_legacy"

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

    if not customer_key:
        outcome.skip_reason = "no_customer_key"
        return outcome

    # ── 1. Local DOM scrape (the only cross-tier call) ──
    try:
        scrape = await scrape_fn(customer_name=customer_name)
    except Exception as exc:
        logger.warning(
            f"[V2 pre_dispatch] scrape_fn failed for cust={customer_key!r}: "
            f"{type(exc).__name__}: {exc!r}"
        )
        scrape = ScrapeResult(scrape_ok=False, error=f"scrape_call_error:{exc}")

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

    # ── 2. Msg-id dedup (only meaningful when scrape gave us an id) ──
    skip, reason = _check_msg_id_dedup(
        customer_key,
        scrape.msg_id,
        last_dispatched_lookup=ctx.dispatch_state.get_last_dispatched_msg_id,
    )
    if skip:
        outcome.skip_reason = reason
        return outcome

    # ── 3. Scrape-failure fallback guards ──
    if not scrape.msg_id:
        skip, reason = _check_dom_echo_fallback(
            item, customer_key, session_id, state_get=ctx.state.get,
        )
        if skip:
            outcome.skip_reason = reason
            return outcome

    # ── 4. Inflight check ──
    if ctx.dispatch_state.is_inflight(customer_key) > 0:
        outcome.skip_reason = "inflight"
        return outcome

    # ── 5. Recipient pick (round-robin) ──
    if not recipient_pool:
        outcome.skip_reason = "no_recipients"
        return outcome
    rr_idx = int(ctx.state.get(rr_idx_key, 0) or 0)
    recipient_agent_id = recipient_pool[rr_idx % len(recipient_pool)]
    ctx.state.set(rr_idx_key, rr_idx + 1)
    outcome.recipient_agent_id = recipient_agent_id

    # ── 6. Mark inflight BEFORE send (closes duplicate-fire window) ──
    try:
        ctx.dispatch_state.mark_inflight(customer_key)
    except Exception as exc:
        logger.debug(
            f"[V2 pre_dispatch] mark_inflight failed for {customer_key!r}: {exc}"
        )

    # ── 7. send_chat ──
    payload = {
        "customer_id": customer_id or customer_name,
        "session_id": session_id,
        "customer_name": customer_name,
        "last_message": str(item.get("last_message") or ""),
    }
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
        return outcome

    if not result.get("success"):
        # send_chat returned failure — release inflight
        try:
            ctx.dispatch_state.clear_inflight(customer_key)
        except Exception:
            pass
        outcome.error = str(result.get("error") or "send_chat_failed")
        return outcome

    # ── 8. Record success state ──
    outcome.message_id = str(result.get("task_id") or result.get("message_id") or "")

    # Record last-dispatched msg_id (only when scrape gave us one — the
    # next cycle's strict dedup needs this).
    if scrape.msg_id:
        try:
            ctx.dispatch_state.set_last_dispatched_msg_id(customer_key, scrape.msg_id)
        except Exception as exc:
            logger.debug(
                f"[V2 pre_dispatch] set_last_dispatched_msg_id failed: {exc}"
            )

    # Update assigned_sessions cache (for the dom-echo fallback path).
    ctx.state.set(
        _ASSIGNED_SESSION_PREFIX + session_id,
        {
            "recipient_agent_id": recipient_agent_id,
            "message_id": outcome.message_id,
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
