"""Feige-chat dispatch state (Phase 6, 2026-04-24).

State dicts + helpers that used to live in ``build_node.py`` module scope
but are purely Feige-customer-chat concerns:

* **HOT-PATH-B recent-send dedup** — suppresses replay loops when
  ``send_response_back``'s fallback path re-fires the same
  ``chat_message`` after a transient ``Chat not found`` error.

* **Last-typed reply per customer** — used by PreDispatch as a DOM-echo
  guard: when Feige's sidebar preview still echoes our outgoing text
  because the customer's freshest bubble hasn't refreshed the preview
  row yet, we compare and skip to wait for the real diff.

* **Last-dispatched msg_id per customer** — replaces the text-based
  dom-echo guard with a strict identity check on Feige's own
  ``data-id`` attribute.

* **Reply-text normaliser** — whitespace-collapsed, 120-char-prefix
  comparison because Feige's sidebar preview trims/collapses
  whitespace and may truncate long replies with an ellipsis.

All state is module-level; the Feige hooks and the Feige enrichment
plugin acquire it via sibling import (the same pattern we use for
``typing_lock``).  ``build_node`` no longer knows about any of this.
"""

from __future__ import annotations

import hashlib
import re
import threading
import time

# ── HOT-PATH-B recent-send dedup cache ───────────────────────────────
# Keyed by (normalised customer_id, sha1(response_text)) → timestamp.
# Prevents replay loops when the same (customer, reply) pair re-enters
# HOT-PATH-B due to a stale pend_event_node resume.  TTL keeps the
# cache bounded; after TTL expires a genuinely identical new reply can
# be re-sent.
_recent_sends: dict[tuple[str, str], float] = {}
_recent_turn_sends: dict[tuple[str, str, str], float] = {}
_recent_sends_lock = threading.Lock()
DEDUP_TTL_S = 15.0
SOURCE_TURN_DEDUP_TTL_S = 600.0

# ── Last reply HOT-PATH-B typed for each customer ────────────────────
# Keyed by normalised customer id.  Read by PreDispatch to recognise
# its own DOM-echo and wait for a genuinely new customer bubble.
last_agent_reply_by_customer: dict[str, str] = {}

# ── Per-customer record of the LAST customer bubble msg_id that
# PreDispatch successfully dispatched. ────────────────────────────────
# Strict identity check on Feige's own ``data-id`` attribute.
last_dispatched_msg_id_by_customer: dict[str, str] = {}

# ── Busy-aware sticky worker assignment (Fix #3, 2026-05-18) ──────────
# Goal: avoid PreDispatch's pure round-robin assigning a customer to a
# Q&A worker that's currently busy answering another customer's previous
# turn.  Doing so caused "head-of-line blocking" where the dispatched
# message sat in the worker's input queue for 30-90 s waiting for the
# prior turn to drain (observed in customer's 2026-05-18 trace: customer
# 瓦哒嘻哇's reply took 3 minutes because the assigned worker was busy
# with customer rice robot's earlier "凑满减" turn for 75 s).
#
# We use a TIMESTAMP-BASED heuristic rather than cross-agent runtime
# polling: a worker dispatched to within ``BUSY_WINDOW_S`` is "likely
# busy".  After that window it's considered free again.  A typical
# Q&A turn (LLM + rag_query + LLM + send_chat) is 8-15 s on this
# customer's hardware; 20 s gives ample buffer without permanently
# locking out workers when a turn finishes early.
#
# Sticky preference: the same customer is routed back to its previous
# worker IF that worker is free.  This preserves the worker's in-process
# conversation history for natural multi-turn context.  When the
# previous worker is busy, we fall through to any-free-worker, finally
# to round-robin.
last_recipient_by_customer: dict[str, str] = {}
last_dispatch_at_by_recipient: dict[str, float] = {}
BUSY_WINDOW_S = 20.0


def pick_recipient(
    recipient_pool: list[str],
    customer_key: str,
    rr_idx: int,
) -> tuple[str, str]:
    """Sticky-first, busy-aware recipient picker.

    Returns ``(recipient_agent_id, pick_reason)`` where ``pick_reason``
    is one of ``"sticky"``, ``"free"``, or ``"round_robin"`` for logging.
    """
    if not recipient_pool:
        return ("", "empty_pool")
    now = time.time()

    def _is_busy(agent_id: str) -> bool:
        last = last_dispatch_at_by_recipient.get(agent_id, 0.0)
        return (now - last) < BUSY_WINDOW_S

    # 1. Sticky-first: prefer the worker that handled this customer
    #    last time, IF it's free.  Preserves conversation context.
    sticky = last_recipient_by_customer.get(customer_key, "")
    if sticky and sticky in recipient_pool and not _is_busy(sticky):
        return (sticky, "sticky")

    # 2. Free worker: any pool member not dispatched to recently.
    free = [w for w in recipient_pool if not _is_busy(w)]
    if free:
        # Stable selection among the free pool — use rr_idx so the
        # spread is deterministic when multiple are free.
        return (free[rr_idx % len(free)], "free")

    # 3. Fallback: round-robin over the whole pool.  All workers busy,
    #    accept some queueing.  Better than starving the dispatch.
    return (recipient_pool[rr_idx % len(recipient_pool)], "round_robin")


def record_recipient_pick(customer_key: str, recipient_agent_id: str) -> None:
    """Update sticky + busy tracking after a successful send_chat dispatch."""
    if not recipient_agent_id:
        return
    now = time.time()
    last_dispatch_at_by_recipient[recipient_agent_id] = now
    if customer_key:
        last_recipient_by_customer[customer_key] = recipient_agent_id


def normalize_reply_text(text: str) -> str:
    """Normalise a reply for DOM-echo comparison against Feige's sidebar.

    The sidebar preview trims + collapses whitespace and truncates
    long replies with an ellipsis, so we compare whitespace-collapsed,
    stripped, 120-char-prefix versions.
    """
    if not text:
        return ""
    s = re.sub(r"\s+", " ", str(text)).strip()
    return s[:120]


def _preview_core(text: str) -> str:
    s = normalize_reply_text(text).replace("\u2026", "...")
    if s.endswith("..."):
        s = s[:-3].rstrip()
    return s


def reply_echo_matches(sidebar_text: str, recorded_reply: str) -> bool:
    """Return True when a sidebar preview is our own recorded reply.

    Feige may truncate previews. Exact equality is preferred; prefix matching
    is only allowed for long enough text to avoid suppressing short genuine
    customer messages such as "在吗".
    """
    sidebar = _preview_core(sidebar_text)
    reply = _preview_core(recorded_reply)
    if not sidebar or not reply:
        return False
    if sidebar == reply:
        return True
    common_len = min(len(sidebar), len(reply))
    if common_len < 16:
        return False
    return sidebar.startswith(reply[:common_len]) or reply.startswith(sidebar[:common_len])


def _fingerprint(customer: str, reply_text: str) -> tuple[str, str]:
    """Build a stable (customer, reply-hash) key for dedup."""
    # Imported lazily to avoid a startup-time circular dep with
    # build_node (which imports this bundle to trigger registration).
    from agent.ec_skills.build_node import _normalize_dispatch_identity_key
    cust = _normalize_dispatch_identity_key(customer or "")
    rtxt = normalize_reply_text(reply_text or "")
    h = hashlib.sha1(rtxt.encode("utf-8", errors="ignore")).hexdigest()[:16] if rtxt else ""
    return (cust, h)


def remember_agent_reply(customer: str, reply_text: str) -> str:
    """Record the latest intended agent reply for DOM-echo suppression.

    The value is normalized before storage because sidebar extraction applies
    the same whitespace collapse and preview truncation.
    """
    reply_norm = normalize_reply_text(reply_text or "")
    if not reply_norm:
        return ""
    cust, _ = _fingerprint(customer or "", reply_norm)
    if not cust:
        return ""
    last_agent_reply_by_customer[cust] = reply_norm
    return reply_norm


def _source_turn_fingerprint(
    customer: str,
    reply_text: str,
    source_msg_id: str,
) -> tuple[str, str, str]:
    cust, reply_hash = _fingerprint(customer, reply_text)
    msg_id = str(source_msg_id or "").strip()
    return (cust, msg_id, reply_hash)


def was_recently_sent(customer: str, reply_text: str) -> float:
    """Return age (s) of a recent identical send, or 0.0 if none/expired."""
    key = _fingerprint(customer, reply_text)
    if not key[0] or not key[1]:
        return 0.0
    now = time.time()
    with _recent_sends_lock:
        ts = _recent_sends.get(key)
        if ts is None:
            return 0.0
        age = now - ts
        if age > DEDUP_TTL_S:
            _recent_sends.pop(key, None)
            return 0.0
        return age if age > 0.0 else 0.000001


def was_recently_sent_for_turn(
    customer: str,
    reply_text: str,
    source_msg_id: str = "",
) -> float:
    if not str(source_msg_id or "").strip():
        return was_recently_sent(customer, reply_text)
    key = _source_turn_fingerprint(customer, reply_text, source_msg_id)
    if not key[0] or not key[1] or not key[2]:
        return was_recently_sent(customer, reply_text)
    now = time.time()
    with _recent_sends_lock:
        ts = _recent_turn_sends.get(key)
        if ts is None:
            return 0.0
        age = now - ts
        if age > SOURCE_TURN_DEDUP_TTL_S:
            _recent_turn_sends.pop(key, None)
            return 0.0
        return age if age > 0.0 else 0.000001


def claim_send(customer: str, reply_text: str) -> float:
    """Atomically reserve a (customer, reply) pair before typing it.

    Returns 0.0 when this caller acquired the claim.  Returns the age of
    an existing unexpired claim/send when another concurrent hot-path
    cycle already owns the same pair.
    """
    key = _fingerprint(customer, reply_text)
    if not key[0] or not key[1]:
        return 0.0
    now = time.time()
    with _recent_sends_lock:
        ts = _recent_sends.get(key)
        if ts is not None:
            age = now - ts
            if age <= DEDUP_TTL_S:
                return age if age > 0.0 else 0.000001
            _recent_sends.pop(key, None)
        _recent_sends[key] = now
        _gc_recent_sends_locked(now)
        return 0.0


def claim_send_for_turn(
    customer: str,
    reply_text: str,
    source_msg_id: str = "",
) -> float:
    """Reserve a reply keyed by Feige's source customer message id.

    The text-only cache is intentionally short because customers can ask
    the same thing again. A replay of the exact same Q&A answer for the
    exact same source bubble should be suppressed for much longer.
    """
    if not str(source_msg_id or "").strip():
        return claim_send(customer, reply_text)
    key = _source_turn_fingerprint(customer, reply_text, source_msg_id)
    if not key[0] or not key[1] or not key[2]:
        return claim_send(customer, reply_text)
    now = time.time()
    with _recent_sends_lock:
        ts = _recent_turn_sends.get(key)
        if ts is not None:
            age = now - ts
            if age <= SOURCE_TURN_DEDUP_TTL_S:
                return age if age > 0.0 else 0.000001
            _recent_turn_sends.pop(key, None)
        _recent_turn_sends[key] = now
        _gc_recent_sends_locked(now)
        return 0.0


def unclaim_send(customer: str, reply_text: str) -> None:
    """Release a pre-send claim after the DOM action failed.

    This lets a later retry deliver the same reply instead of suppressing
    it for the full dedup TTL.
    """
    key = _fingerprint(customer, reply_text)
    if not key[0] or not key[1]:
        return
    with _recent_sends_lock:
        _recent_sends.pop(key, None)


def unclaim_send_for_turn(
    customer: str,
    reply_text: str,
    source_msg_id: str = "",
) -> None:
    if not str(source_msg_id or "").strip():
        unclaim_send(customer, reply_text)
        return
    key = _source_turn_fingerprint(customer, reply_text, source_msg_id)
    if not key[0] or not key[1] or not key[2]:
        unclaim_send(customer, reply_text)
        return
    with _recent_sends_lock:
        _recent_turn_sends.pop(key, None)


def mark_sent(customer: str, reply_text: str) -> None:
    """Record that *reply_text* was just typed into Feige for *customer*."""
    key = _fingerprint(customer, reply_text)
    if not key[0] or not key[1]:
        return
    now = time.time()
    with _recent_sends_lock:
        _recent_sends[key] = now
        _gc_recent_sends_locked(now)


def mark_sent_for_turn(
    customer: str,
    reply_text: str,
    source_msg_id: str = "",
) -> None:
    if not str(source_msg_id or "").strip():
        mark_sent(customer, reply_text)
        return
    key = _source_turn_fingerprint(customer, reply_text, source_msg_id)
    if not key[0] or not key[1] or not key[2]:
        mark_sent(customer, reply_text)
        return
    now = time.time()
    with _recent_sends_lock:
        _recent_turn_sends[key] = now
        _gc_recent_sends_locked(now)


def _gc_recent_sends_locked(now: float) -> None:
    """Opportunistically keep the recent-send cache bounded.

    Caller must hold ``_recent_sends_lock``.
    """
    if len(_recent_sends) <= 256 and len(_recent_turn_sends) <= 512:
        return
    for k in list(_recent_sends.keys()):
        if now - _recent_sends[k] > DEDUP_TTL_S:
            _recent_sends.pop(k, None)
    for k in list(_recent_turn_sends.keys()):
        if now - _recent_turn_sends[k] > SOURCE_TURN_DEDUP_TTL_S:
            _recent_turn_sends.pop(k, None)
