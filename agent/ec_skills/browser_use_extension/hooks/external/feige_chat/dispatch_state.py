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
import os
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

# ws003e: long-window ledger of REAL replies that were actually DELIVERED, keyed by
# (customer, sha1(reply)). The claim caches above suppress concurrent/near dups but
# expire in 15-600s; a stale direct-delivery retry (CDP cooldown/circuit deferring a
# re-queue) can fire many minutes later — after the claim aged out — and re-send an
# already-delivered answer (live 2026-06-05: packet's reply re-sent 19 min later, same
# turn_key). This survives long enough to catch that. Placeholders are NEVER recorded
# here (they intentionally repeat).
_delivered_replies: dict[tuple[str, str], float] = {}
DELIVERED_REPLY_TTL_S = 1800.0

# ── Last reply HOT-PATH-B typed for each customer ────────────────────
# Keyed by normalised customer id.  Read by PreDispatch to recognise
# its own DOM-echo and wait for a genuinely new customer bubble.
last_agent_reply_by_customer: dict[str, str] = {}

# ── Multi-slot recent-reply ledger for sidebar-echo suppression ──────
# Single-slot `last_agent_reply_by_customer` only remembers ONE text.
# Under flood load we type a real reply PLUS up to 3 placeholder texts
# into the same customer's chat in rapid succession; the sidebar can
# then echo ANY of those.  Without the multi-slot ledger PreDispatch's
# sidebar-only fallback sees the placeholder text in sidebar, fails the
# single-slot echo check, and treats the placeholder as a new customer
# question → infinite re-dispatch loop (root-cause of the 客户16
# 8-dispatch trace on 2026-05-20).  Each entry is (norm_text, ts);
# entries older than RECENT_REPLY_TTL_S are pruned on each touch.
recent_agent_replies_by_customer: dict[str, list[tuple[str, float]]] = {}
RECENT_REPLY_TTL_S: float = 90.0
RECENT_REPLY_MAX_PER_CUSTOMER: int = 6
_recent_replies_lock = threading.Lock()

# 2026-05-27 mt050K-(b) — separate ledger of NORMALIZED placeholder
# reply texts.  When the bot types a placeholder ("人工服务正在回复中..."),
# Feige updates the sidebar last_message to show it, EventMonitor sees
# the change, and PreDispatch's dom-echo guard skips the customer
# because the sidebar matches our recorded reply.  Problem: the
# underlying customer question is still unanswered (placeholder is just
# a "we're working on it" not a real reply).  Customer-visible result:
# 10-minute stuck (live trace 2026-05-27 15:41:13-15:51:21).
#
# This ledger tags which recorded texts are PLACEHOLDERS.  The
# dom-echo guard checks ``is_placeholder_text`` — if the matched
# sidebar text is a placeholder echo, the guard does NOT skip,
# allowing PreDispatch to fall through to the thread-scrape path
# (which sees the actual customer bubble, not the placeholder).
#
# Stored as a normalised text → timestamp dict so the same TTL pruning
# applies; lookups are constant-time.
_placeholder_reply_texts: dict[str, float] = {}
_placeholder_reply_lock = threading.Lock()

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

    The sidebar preview STRIPS whitespace (including newlines) without
    replacing them.  E.g. our recorded reply::

        "可以的，舒适度也可以。\\n如果您不想踩坑..."

    becomes in the sidebar::

        "可以的，舒适度也可以。如果您不想踩坑..."

    (no whitespace at all).  Previously we collapsed ``\\s+`` to a
    single space, which inserted a phantom space at every ``\\n`` and
    broke exact equality with the sidebar text — so multi-line bot
    replies leaked past the dom_echo filter and re-entered the
    front-desk queue as "new customer messages".  Live trace
    2026-05-23 16:22:26 肽斯特 "可以的，这款面料比较柔软亲肤..."
    (mt034).

    Truncate to 120 chars to match the sidebar's preview budget.
    """
    if not text:
        return ""
    s = re.sub(r"\s+", "", str(text)).strip()
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


def mark_placeholder_text(reply_text: str) -> str:
    """2026-05-27 mt050K-(b) — tag *reply_text* as a placeholder so the
    PreDispatch dom-echo guard knows not to suppress on a sidebar
    match.  Caller (placeholder_timer's submitter in runner.py)
    invokes this in addition to ``remember_agent_reply``.

    Returns the normalized text actually stored, or ``""`` when input
    is empty.  Idempotent — re-marking refreshes the TTL stamp.
    """
    norm = normalize_reply_text(reply_text or "")
    if not norm:
        return ""
    now = time.time()
    with _placeholder_reply_lock:
        _placeholder_reply_texts[norm] = now
        # GC entries older than the existing recent-reply TTL.  No
        # cap — placeholder texts are a tiny set (typically 1-3
        # entries) so unbounded growth isn't a concern; the TTL
        # handles process-lifetime cleanup.
        cutoff = now - RECENT_REPLY_TTL_S
        stale = [k for k, ts in _placeholder_reply_texts.items() if ts < cutoff]
        for k in stale:
            _placeholder_reply_texts.pop(k, None)
    return norm


# ws153: our OWN standby placeholder ("人工服务正在回复中…", placeholder_timer._PLACEHOLDER_
# DEFAULT_TEXTS) left in a reopened thread from a PRIOR turn/session/restart is NOT in the
# per-process runtime dict below, so is_placeholder_text() returned False → mt052N treated it as
# a real prior reply → mt030 masked the customer's NEW message with our own standby (live
# 2026-07-08 15:56:51 packet: baseline='人工服务正在回复中...' → mt030 skip → never answered →
# plain-text cold-start "not working"). Static fallback recognizes the standby phrase regardless
# of session/TTL. Precise phrase (customers don't type our standby), so safe to match always.
_STATIC_PLACEHOLDER_RE = re.compile(r"人工服务正在回复中")


def is_placeholder_text(text: str) -> bool:
    """Return True iff *text* was recently registered as a placeholder
    via :func:`mark_placeholder_text` (within ``RECENT_REPLY_TTL_S``), OR
    matches the known standby placeholder phrase (ws153 static fallback,
    for placeholders from a prior session / after restart / past TTL).

    Used by PreDispatch's dom-echo guard + mt052N to override mt030's
    "agent replied after customer" skip when the matched agent bubble is
    actually a placeholder (not a real answer).  Without the override,
    customers stay stuck for minutes after a placeholder fires (live
    trace 2026-05-27 15:41:13; cold-start mask 2026-07-08 15:56:51).
    """
    norm = normalize_reply_text(text or "")
    if not norm:
        return False
    now = time.time()
    cutoff = now - RECENT_REPLY_TTL_S
    with _placeholder_reply_lock:
        ts = _placeholder_reply_texts.get(norm, 0.0)
    if ts >= cutoff:
        return True
    # ws153: static fallback — a placeholder carried over in a reopened thread isn't in the
    # per-process runtime dict, but it's still OUR standby, not a real prior reply.
    if (
        os.environ.get("ECAN_FEIGE_PLACEHOLDER_STATIC_MATCH", "1") != "0"
        and _STATIC_PLACEHOLDER_RE.search(text or "")
    ):
        return True
    return False


def remember_agent_reply(customer: str, reply_text: str) -> str:
    """Record the latest intended agent reply for DOM-echo suppression.

    The value is normalized before storage because sidebar extraction applies
    the same whitespace collapse and preview truncation.

    Also appends to the multi-slot ``recent_agent_replies_by_customer``
    ledger so the sidebar-only echo guard recognises placeholder texts
    (which the single-slot field cannot remember alongside the real reply).
    """
    reply_norm = normalize_reply_text(reply_text or "")
    if not reply_norm:
        return ""
    cust, _ = _fingerprint(customer or "", reply_norm)
    if not cust:
        return ""
    last_agent_reply_by_customer[cust] = reply_norm
    _append_recent_agent_reply(cust, reply_norm)
    return reply_norm


def _append_recent_agent_reply(cust: str, reply_norm: str) -> None:
    """Append to the multi-slot ledger, pruning by TTL + cap."""
    if not cust or not reply_norm:
        return
    now = time.time()
    with _recent_replies_lock:
        lst = recent_agent_replies_by_customer.get(cust)
        if lst is None:
            lst = []
            recent_agent_replies_by_customer[cust] = lst
        cutoff = now - RECENT_REPLY_TTL_S
        # Drop expired entries
        i = 0
        while i < len(lst) and lst[i][1] < cutoff:
            i += 1
        if i:
            del lst[:i]
        # De-dup: if the same text is already in the list, refresh its ts
        for idx, (txt, _ts) in enumerate(lst):
            if txt == reply_norm:
                lst[idx] = (reply_norm, now)
                break
        else:
            lst.append((reply_norm, now))
        # Cap
        if len(lst) > RECENT_REPLY_MAX_PER_CUSTOMER:
            del lst[: len(lst) - RECENT_REPLY_MAX_PER_CUSTOMER]


def matches_recent_agent_reply(customer: str, sidebar_text: str) -> str:
    """Return the matching recorded reply if ``sidebar_text`` looks like
    our own DOM-echo for ``customer`` (real reply or a placeholder typed
    in the last ``RECENT_REPLY_TTL_S`` seconds), else "".

    Uses ``reply_echo_matches`` so prefix/truncation tolerance applies.
    """
    sidebar_norm = normalize_reply_text(sidebar_text or "")
    if not sidebar_norm:
        return ""
    cust, _ = _fingerprint(customer or "", sidebar_norm)
    if not cust:
        return ""
    now = time.time()
    cutoff = now - RECENT_REPLY_TTL_S
    with _recent_replies_lock:
        lst = recent_agent_replies_by_customer.get(cust)
        if not lst:
            return ""
        # Iterate newest-first so a hit returns the most recent match
        for txt, ts in reversed(lst):
            if ts < cutoff:
                continue
            if txt == sidebar_norm or reply_echo_matches(sidebar_text, txt):
                return txt
    return ""


def _source_turn_fingerprint(
    customer: str,
    reply_text: str,
    source_msg_id: str,
) -> tuple[str, str, str]:
    cust, reply_hash = _fingerprint(customer, reply_text)
    msg_id = str(source_msg_id or "").strip()
    return (cust, msg_id, reply_hash)


def clear_recent_replies(customer: str) -> None:
    """Drop every recent-agent-reply ledger entry for ``customer``.

    Called by the stale_reply rejection handler in ``feige_send_message``
    after the chat-thread guard discards our outgoing reply.  After the
    rejection, the customer's NEW bubble is sitting in the chat
    unanswered — but PreDispatch's recent-echo guard would keep skipping
    re-dispatch because the sidebar still shows our (now-orphaned)
    placeholder text that's still in this ledger.

    Clearing here is safe: the orphan reply was never delivered, so we
    have no in-flight DOM-echo to protect against.  The next front-desk
    cycle re-scrapes the chat, finds the customer's new bubble as the
    latest, and dispatches it normally.

    Customer-impact trace: 2026-05-22 08:19:23-08:22:34 (陆地飞鱼) —
    stale_reply at 08:19:41 left the customer un-answered for 173 s
    because every PreDispatch cycle between then and 08:22:22 logged
    "recent-echo skip echo='您好，稍等一下哦~'".
    """
    if not customer:
        return
    # Normalize the same way the writers do so we hit the same key
    cust, _ = _fingerprint(customer or "", "x")
    if not cust:
        return
    with _recent_replies_lock:
        recent_agent_replies_by_customer.pop(cust, None)
    last_agent_reply_by_customer.pop(cust, None)


def clear_dispatch_blockers(customer: str, *, reason: str = "") -> dict:
    """ws155: clear ONLY the re-dispatch-BLOCKING state for *customer*, across ALL identity key
    variants (real name / synthetic ``card:<talk>`` / bare ``<talk>``), so an orphaned cold-start
    message can be re-dispatched on the next monitor tick.

    Blockers cleared (the three stores whose survival BLOCKS a re-dispatch):
      1. ``last_dispatched_msg_id_by_customer`` — strict msg-id dedup (this module).
      2. ``_dispatched_identity_keys``          — actionable_items identity dedup.
      3. ``_dispatch_inflight``                 — build_node cross-scope inflight lock.
    Plus ``force_reemit_for_customer`` so EventMonitor re-emits even if the sidebar row text is
    unchanged after the drop.

    Deliberately does NOT touch the SUPPRESSOR stores (``_recent_sends`` / ``_recent_turn_sends``
    / ``_delivered_replies`` / ``recent_agent_replies_by_customer``): those prevent DUPLICATE
    sends and MUST survive — clearing them would risk a double-reply. A caller that also needs the
    echo-suppressor cleared (safe only when the reply was never delivered) calls
    :func:`clear_recent_replies` separately, exactly as today.

    This is the single, complete replacement for the scattered partial clears (mt046A / mt052L /
    mt053H2 / mt053J), each of which historically cleared a DIFFERENT subset and leaked one store
    (mt052L left identity_key stamped ~1h; mt053H2 left inflight ~30s → orphaned cold-start reply).
    Invoked ONLY from those failure/stale recovery sites — never from the normal dispatch/dedup
    check path — so it has NO effect on steady-state behaviour. All imports are lazy to avoid
    circular-import at module load. Returns per-store counts for logging.
    """
    out = {"msg_id": 0, "identity": 0, "inflight": 0, "reemit": False, "keys": 0}
    name = (customer or "").strip()
    if not name:
        return out
    # Full identity-key set: real name + synthetic card:<talk> + bare <talk>. Different dispatch
    # paths stamp blockers under different keys (WS hot path → card:<talk>; PreDispatch → name),
    # so we must clear all of them to be complete. Extra keys that were never stamped are no-ops.
    keys = [name]
    try:
        from .ws_session import talk_for_name as _cdb_t4n
        _talk = str(_cdb_t4n(name) or "").strip()
        if _talk:
            keys += [f"card:{_talk}", _talk]
    except Exception:
        pass
    out["keys"] = len(keys)
    # 1. strict msg-id dedup (local module dict)
    for _k in keys:
        try:
            if last_dispatched_msg_id_by_customer.pop(_k, None) is not None:
                out["msg_id"] += 1
        except Exception:
            pass
    # 2. identity_key dedup (actionable_items; prefix-matches "<key>|")
    try:
        from .actionable_items import clear_dispatched_identity_keys_for_customer as _cdb_ci
        for _k in keys:
            try:
                out["identity"] += int(_cdb_ci(_k) or 0)
            except Exception:
                pass
    except Exception:
        pass
    # 3. dispatch_inflight cross-scope lock (build_node)
    try:
        from agent.ec_skills.build_node import _clear_dispatch_inflight as _cdb_cif
        for _k in keys:
            try:
                _cdb_cif(_k)
                out["inflight"] += 1
            except Exception:
                pass
    except Exception:
        pass
    # 4. force EventMonitor to re-emit this customer on its next tick (real name only)
    try:
        from agent.ec_skills.browser_use_extension.event_monitor import (
            force_reemit_for_customer as _cdb_re,
        )
        _cdb_re(name)
        out["reemit"] = True
    except Exception:
        pass
    return out


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


def mark_reply_delivered(customer: str, reply_text: str) -> None:
    """ws003e: record that a REAL reply was actually delivered (success), for
    long-window dup suppression against stale retries / cross-path re-sends.
    Placeholders are never recorded (they intentionally repeat)."""
    if is_placeholder_text(reply_text):
        return
    key = _fingerprint(customer, reply_text)
    if not key[0] or not key[1]:
        return
    now = time.time()
    with _recent_sends_lock:
        _delivered_replies[key] = now
        _gc_recent_sends_locked(now)


def was_reply_delivered(customer: str, reply_text: str) -> float:
    """Age (s) of a prior successful delivery of this (customer, reply) within
    DELIVERED_REPLY_TTL_S, else 0.0. Used to drop a re-send of an answer already
    delivered — e.g. a stale direct-delivery retry firing minutes later."""
    if is_placeholder_text(reply_text):
        return 0.0
    key = _fingerprint(customer, reply_text)
    if not key[0] or not key[1]:
        return 0.0
    now = time.time()
    with _recent_sends_lock:
        ts = _delivered_replies.get(key)
        if ts is None:
            return 0.0
        age = now - ts
        if age > DELIVERED_REPLY_TTL_S:
            _delivered_replies.pop(key, None)
            return 0.0
        return age if age > 0.0 else 0.000001


def _gc_recent_sends_locked(now: float) -> None:
    """Opportunistically keep the recent-send cache bounded.

    Caller must hold ``_recent_sends_lock``.
    """
    if (len(_recent_sends) <= 256 and len(_recent_turn_sends) <= 512
            and len(_delivered_replies) <= 512):
        return
    for k in list(_recent_sends.keys()):
        if now - _recent_sends[k] > DEDUP_TTL_S:
            _recent_sends.pop(k, None)
    for k in list(_recent_turn_sends.keys()):
        if now - _recent_turn_sends[k] > SOURCE_TURN_DEDUP_TTL_S:
            _recent_turn_sends.pop(k, None)
    for k in list(_delivered_replies.keys()):
        if now - _delivered_replies[k] > DELIVERED_REPLY_TTL_S:
            _delivered_replies.pop(k, None)
