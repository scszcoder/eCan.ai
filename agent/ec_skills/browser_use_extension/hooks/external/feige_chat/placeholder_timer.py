"""Placeholder-timer guardrail (Phase 3.5, 2026-05-21).

Background
----------
Feige's seller dashboard tracks a "未回复" red-flag against the store's
performance score when a customer message goes unanswered beyond the
service-level deadline (~30 seconds).  Under heavy 20-customer floods,
even with the multi-tab pool, tail customers can wait 60s+ for the
first real Q&A reply — well past the deadline.

This module provides a guardrail: after PreDispatch dispatches a
customer's question, arm a per-(customer, source_msg_id) timer.  If
the real reply isn't typed within ``FEIGE_PLACEHOLDER_TIMEOUT_S``,
type a brief stand-by like "您好，稍等一下哦~" so Feige's red-flag
clock resets.  Re-arm up to ``FEIGE_PLACEHOLDER_MAX`` times.

Why this works (now that we have the pool)
-------------------------------------------
Pre-multitab attempts at this idea ran into typing-lock contention:
placeholders fought with real replies for the same typing-lock, so
under load placeholders were as delayed as the replies they were
supposed to prevent.

With the multi-tab pool:
* Placeholders enter the SAME direct-delivery worker queue as real
  replies and get pool-tab routing.
* Different pool tabs type concurrently, so a placeholder for
  customer X doesn't delay a real reply for customer Y.
* The pool's ``in_use`` flag is per-tab, so placeholders and real
  replies for DIFFERENT customers don't block each other.

Lifecycle
---------
1. PreDispatch dispatches customer X's question → ``arm(X, msg_id)``
2. Sweeper task ticks every ``SWEEP_INTERVAL_S`` seconds.
3. For entries past their deadline:
     - synthesize a fake reply payload with a short stand-by text
     - submit through ``runner._submit_loop_direct_delivery`` (same
       path real replies use, so pool routing kicks in)
     - increment placeholder count, set next deadline
     - stop after ``MAX`` placeholders to avoid spam
4. When direct-delivery successfully types the REAL reply, the
   runner's ``_outcome.ok = True`` branch calls ``cancel(X, msg_id)``
   to remove the entry from the timer registry.

Failure modes handled
---------------------
* Real reply never arrives (Q&A bot crashed): max=3 placeholders
  fire, then we give up silently.  Customer sees "稍等" / "再稍等" /
  "马上就好" and no more — better than no acknowledgement at all.
* Customer asks 2 questions back-to-back: each turn has its own
  (customer, source_msg_id) entry; cancelling one doesn't affect
  the other.
* Real reply was dropped due to drift / bypass: placeholders still
  fire on schedule, giving the user feedback while drift_recovery_signal
  retries the real delivery.

Adapting to other platforms
---------------------------
The text variations (``_PLACEHOLDER_TEXTS``) are Chinese, tuned for
Feige's customer base.  For another platform, copy this module and
swap the text list.  The mechanism (per-turn timer registry + periodic
sweep + queue-submit) is platform-agnostic.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("eCan")


# Different text per attempt so the recent-sends dedup cache doesn't
# suppress the second/third attempt as a near-duplicate.  Ordered by
# escalation tone: gentle → reassuring → apologetic.
#
# 2026-05-26 mt048A — operators can override these by dropping a JSON
# array at <user_data_home>/ecan/placeholder_texts.json (e.g.
# ``["text1", "text2", "text3"]``).  Loaded on first arm() per process,
# cached for the lifetime.  Empty / malformed / missing file falls back
# to the in-code defaults below.
# 2026-05-27 mt050L — customer feedback: shrink default placeholder
# set to a single message.  The previous 3-text rotation was designed
# for dedup-busting under ``_PLACEHOLDER_MAX > 1`` re-fires, but the
# customer prefers seeing one consistent message regardless of how
# many times the timer re-arms.  Operators who want the rotation can
# still drop a list at <user_data_home>/ecan/placeholder_texts.json
# (mt048A loader picks it up first).
_PLACEHOLDER_DEFAULT_TEXTS = [
    "人工服务正在回复中...",
]
_PLACEHOLDER_TEXTS_FILENAME = "ecan/placeholder_texts.json"
_PLACEHOLDER_MAX_TEXTS = 5  # cap to keep dedup-cache headroom

# Lazily-loaded cache.  None means "not yet loaded"; an empty list is a
# sentinel that should never appear (load always returns >=1 entry via
# fallback).  Loaded once on first ``arm()`` per process — restart eCan
# to pick up file changes.
_PLACEHOLDER_TEXTS_CACHE: Optional[list[str]] = None
_PLACEHOLDER_TEXTS_CACHE_LOCK = threading.Lock()


def _load_placeholder_texts_from_file() -> Optional[list[str]]:
    """Try to read the user override file.  Returns the validated list or
    None if the file is missing / unreadable / malformed.  Pure helper —
    no fallback logic here (caller handles that)."""
    try:
        from utils.path_manager import get_user_data_path
    except Exception as e:
        logger.debug(f"[placeholder_timer] mt048A: get_user_data_path import failed: {e}")
        return None
    try:
        base = get_user_data_path()
    except Exception as e:
        logger.debug(f"[placeholder_timer] mt048A: get_user_data_path() failed: {e}")
        return None
    if not base:
        return None
    file_path = os.path.join(base, _PLACEHOLDER_TEXTS_FILENAME)
    if not os.path.isfile(file_path):
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        logger.warning(
            f"[placeholder_timer] mt048A: failed to parse {file_path!r}: "
            f"{e} — using fallback texts"
        )
        return None
    if not isinstance(raw, list):
        logger.warning(
            f"[placeholder_timer] mt048A: {file_path!r} must contain a JSON "
            f"array of strings, got {type(raw).__name__} — using fallback"
        )
        return None
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        s = item.strip()
        if not s:
            continue
        if s in seen:
            continue  # dedupe to keep the recent-sends cache happy
        seen.add(s)
        cleaned.append(s)
        if len(cleaned) >= _PLACEHOLDER_MAX_TEXTS:
            break
    if not cleaned:
        logger.warning(
            f"[placeholder_timer] mt048A: {file_path!r} had no usable strings "
            "after validation — using fallback"
        )
        return None
    return cleaned


def _get_placeholder_texts() -> list[str]:
    """Return the active placeholder text list, loading on first call.

    mt048A — operator overrides via <user_data_home>/ecan/placeholder_texts.json.
    Empty / malformed / missing file falls back to ``_PLACEHOLDER_DEFAULT_TEXTS``.
    Cached for the lifetime of the process.
    """
    global _PLACEHOLDER_TEXTS_CACHE
    if _PLACEHOLDER_TEXTS_CACHE is not None:
        return _PLACEHOLDER_TEXTS_CACHE
    with _PLACEHOLDER_TEXTS_CACHE_LOCK:
        if _PLACEHOLDER_TEXTS_CACHE is not None:
            return _PLACEHOLDER_TEXTS_CACHE
        loaded = _load_placeholder_texts_from_file()
        if loaded:
            _PLACEHOLDER_TEXTS_CACHE = loaded
            logger.info(
                f"[placeholder_timer] mt048A: loaded {len(loaded)} placeholder "
                f"texts from user-data file (source=file): {loaded!r}"
            )
        else:
            _PLACEHOLDER_TEXTS_CACHE = list(_PLACEHOLDER_DEFAULT_TEXTS)
            logger.info(
                f"[placeholder_timer] mt048A: using {len(_PLACEHOLDER_TEXTS_CACHE)} "
                f"fallback placeholder texts (source=fallback): "
                f"{_PLACEHOLDER_TEXTS_CACHE!r}"
            )
        return _PLACEHOLDER_TEXTS_CACHE


@dataclass
class _TimerEntry:
    customer_key: str
    source_msg_id: str
    armed_at: float
    deadline_at: float
    placeholders_typed: int = 0
    cancelled: bool = False


# Module-level registry — process-wide
_REGISTRY: dict[tuple[str, str], _TimerEntry] = {}
_REGISTRY_LOCK = threading.Lock()

# Per-customer typed-placeholder ledger (2026-05-21 Fix B).
# Defense in depth: even when multiple timers exist for the same customer
# (e.g., PreDispatch mis-dispatched a phantom turn + the real turn — Fix A
# in frontdesk_dispatch.py cancels the orphan but covers only one supersede
# site), CAP the total placeholders typed per customer per window so the
# customer never sees more than N "稍等" messages per real question.
#
# Tracks wall-clock timestamps of typed placeholders per customer; entries
# older than PLACEHOLDER_CAP_WINDOW_S are pruned on each query.
_PLACEHOLDERS_TYPED_TS: dict[str, list[float]] = {}
PLACEHOLDER_CAP_WINDOW_S: float = 90.0


def mark_placeholder_typed(customer_key: str) -> None:
    """Record that a placeholder was typed for ``customer_key``.  Called
    by the placeholder send coroutine right after the type succeeds."""
    if not customer_key:
        return
    cust = str(customer_key)
    now = time.time()
    cutoff = now - PLACEHOLDER_CAP_WINDOW_S
    with _REGISTRY_LOCK:
        lst = _PLACEHOLDERS_TYPED_TS.setdefault(cust, [])
        # Drop expired
        while lst and lst[0] < cutoff:
            lst.pop(0)
        lst.append(now)


def count_recent_placeholders(customer_key: str) -> int:
    """Return how many placeholders were typed for this customer within
    the last ``PLACEHOLDER_CAP_WINDOW_S`` seconds."""
    if not customer_key:
        return 0
    cust = str(customer_key)
    now = time.time()
    cutoff = now - PLACEHOLDER_CAP_WINDOW_S
    with _REGISTRY_LOCK:
        lst = _PLACEHOLDERS_TYPED_TS.get(cust)
        if not lst:
            return 0
        # Prune expired
        while lst and lst[0] < cutoff:
            lst.pop(0)
        return len(lst)


# In-flight placeholder tasks (2026-05-20).  When cancel() arrives
# during the brief window between the second "is_real_reply_recent"
# check and _send_fn actually typing the bubble, we want the in-flight
# placeholder coroutine itself to be aborted.  Cancelling the task
# injects CancelledError into the awaited CDP call, preventing the
# placeholder from typing.  Tracking is per-(customer, source_msg_id)
# so we only cancel the placeholder for the answered turn — other
# turns' placeholders keep running.
_INFLIGHT_PLACEHOLDER_TASKS: dict[tuple[str, str], object] = {}


def register_inflight_placeholder(customer_key: str, source_msg_id: str, task) -> None:
    """Track an in-flight placeholder coroutine task so a late-arriving
    cancel can abort it.  Called by ``_placeholder_send`` on entry."""
    if not customer_key:
        return
    key = (str(customer_key), str(source_msg_id or ""))
    with _REGISTRY_LOCK:
        _INFLIGHT_PLACEHOLDER_TASKS[key] = task


def unregister_inflight_placeholder(customer_key: str, source_msg_id: str) -> None:
    """Remove the in-flight task entry on exit (success or failure)."""
    if not customer_key:
        return
    key = (str(customer_key), str(source_msg_id or ""))
    with _REGISTRY_LOCK:
        _INFLIGHT_PLACEHOLDER_TASKS.pop(key, None)

# Per-TURN "real reply just delivered" timestamps (2026-05-20 v2).
# Keyed by (customer_key, source_msg_id) — NOT by customer alone.
# Reason: when a customer has multiple in-flight turns (e.g., asked Q1
# and Q2 in succession, Q1's reply arrives first), the cancel must
# ONLY release Q1's placeholder timer.  Earlier per-customer keying
# (mt015) regressed this — an older turn's reply would kill the new
# turn's placeholder, leaving customers with no acknowledgment for
# 3+ minutes while the Q&A bot processed the new question.  Observed
# in the 2026-05-20 22:52 flood: 客户02 港澳台运费 had no placeholder
# because 客户02's earlier 婴儿66码 reply arrived first and cancelled.
_REAL_REPLY_AT: dict[tuple[str, str], float] = {}
REAL_REPLY_SUPPRESS_S: float = 60.0


def _reply_key(customer_key: str, source_msg_id: str) -> tuple[str, str]:
    return (str(customer_key or ""), str(source_msg_id or ""))


def is_real_reply_recent(customer_key: str, source_msg_id: str = "") -> bool:
    """Returns True if a real reply was delivered for this specific
    ``(customer_key, source_msg_id)`` turn within the last
    ``REAL_REPLY_SUPPRESS_S`` seconds.

    The placeholder-submitter checks this right before typing —
    suppresses placeholders for turns that have already been answered,
    leaving OTHER turns' placeholders intact.
    """
    if not customer_key:
        return False
    key = _reply_key(customer_key, source_msg_id)
    blank_key = _reply_key(customer_key, "")
    with _REGISTRY_LOCK:
        # 2026-05-24 mt038E: take max(exact, blank) so we catch the
        # arm/cancel key-mismatch race — see claim_expired() and
        # cancel() for full rationale.  This is consulted by the
        # submitter as a last-chance pre-type suppress.
        ts = max(
            _REAL_REPLY_AT.get(key, 0.0),
            _REAL_REPLY_AT.get(blank_key, 0.0),
        )
    if ts <= 0.0:
        return False
    age = time.time() - ts
    return 0.0 <= age <= REAL_REPLY_SUPPRESS_S


def mark_real_reply_delivered(customer_key: str, source_msg_id: str = "") -> None:
    """Record that a real reply was delivered for the specific turn
    ``(customer_key, source_msg_id)``.  Called by the runner's
    direct-delivery success path so the placeholder submitter can
    suppress already-claimed-but-not-typed placeholders for that turn
    (without affecting other turns).
    """
    if not customer_key:
        return
    key = _reply_key(customer_key, source_msg_id)
    now = time.time()
    with _REGISTRY_LOCK:
        _REAL_REPLY_AT[key] = now
        # 2026-05-24 mt038E: also stamp the empty-msg-id slot for
        # key-mismatch suppression — see cancel() for full rationale.
        _REAL_REPLY_AT[(str(customer_key), "")] = now


# Per-turn "customer message first seen in DOM" timestamps (2026-05-20).
# Populated by EventMonitor when a new customer message is detected, so
# the placeholder timer's deadline can be computed relative to MESSAGE
# ARRIVAL TIME — not relative to PreDispatch dispatch time.  Under flood
# load PreDispatch lag can be 5-15s; without this anchor, a 20s timeout
# means the placeholder fires 25-35s after the customer typed their
# message, missing Feige's 30s red-flag refresh cycle.  TTL prunes
# entries older than 5 minutes so the dict doesn't grow unbounded.
_FIRST_SEEN_AT: dict[tuple[str, str], float] = {}
# Per-customer fallback: at EventMonitor time the msg_id is usually
# unknown (PreDispatch's enrich learns it later), so we record the
# customer-level arrival timestamp here too.  arm() prefers the precise
# per-(customer,msg_id) timestamp but falls back to the latest
# per-customer one.  Updated on every dom_observed batch that includes
# the customer as an "added_items" entry (a new message arrival).
_FIRST_SEEN_BY_CUSTOMER: dict[str, float] = {}
FIRST_SEEN_TTL_S: float = 300.0


def mark_message_first_seen(customer_key: str, source_msg_id: str = "") -> None:
    """Record the wall-clock when a customer message arrival was first
    detected.  Called by EventMonitor for every new ``added_items``
    entry.  Idempotent — earliest observation wins so the deadline
    anchors to actual arrival.

    ``source_msg_id`` is optional: at EventMonitor time it's usually
    unknown (the deeper scrape happens in PreDispatch's enrich).  If
    empty we record only the per-customer arrival ts; PreDispatch can
    call again with the resolved msg_id later for the precise
    per-(customer,msg_id) record."""
    if not customer_key:
        return
    cust = str(customer_key)
    now = time.time()
    with _REGISTRY_LOCK:
        # Per-customer fallback — latest arrival wins (so a second
        # message from the same customer correctly anchors to its own
        # arrival rather than the older one).
        _FIRST_SEEN_BY_CUSTOMER[cust] = now
        if source_msg_id:
            key = (cust, str(source_msg_id))
            existing = _FIRST_SEEN_AT.get(key)
            if existing is None or now < existing:
                _FIRST_SEEN_AT[key] = now
        # Opportunistic prune
        if len(_FIRST_SEEN_AT) > 200:
            cutoff = now - FIRST_SEEN_TTL_S
            stale = [k for k, ts in _FIRST_SEEN_AT.items() if ts < cutoff]
            for k in stale:
                _FIRST_SEEN_AT.pop(k, None)
        if len(_FIRST_SEEN_BY_CUSTOMER) > 200:
            cutoff = now - FIRST_SEEN_TTL_S
            stale_c = [c for c, ts in _FIRST_SEEN_BY_CUSTOMER.items() if ts < cutoff]
            for c in stale_c:
                _FIRST_SEEN_BY_CUSTOMER.pop(c, None)


def get_message_first_seen(customer_key: str, source_msg_id: str = "") -> float:
    """Returns the best-available first-seen timestamp.  Tries precise
    per-(customer, source_msg_id) record first; falls back to the
    per-customer latest-arrival record.  Returns 0.0 if neither is
    recorded within TTL."""
    if not customer_key:
        return 0.0
    cust = str(customer_key)
    now = time.time()
    with _REGISTRY_LOCK:
        if source_msg_id:
            precise = _FIRST_SEEN_AT.get((cust, str(source_msg_id)), 0.0)
            if precise > 0.0 and (now - precise) <= FIRST_SEEN_TTL_S:
                return precise
        per_cust = _FIRST_SEEN_BY_CUSTOMER.get(cust, 0.0)
    if per_cust > 0.0 and (now - per_cust) <= FIRST_SEEN_TTL_S:
        return per_cust
    return 0.0


def _make_key(customer_key: str, source_msg_id: str) -> tuple[str, str]:
    """Key by (customer, source_msg_id).  Source_msg_id may be empty —
    that's still a valid key since the same customer's earlier turn
    (with a different/no msg_id) is tracked separately."""
    return (str(customer_key or ""), str(source_msg_id or ""))


def arm(customer_key: str, source_msg_id: str = "", *, timeout_s: float) -> None:
    """Record a dispatched turn so the sweeper can fire a placeholder
    if its deadline passes without a real reply.

    Called by PreDispatch right after it confirms the question went
    out to the Q&A bot.  Idempotent — re-arming the same key resets
    the deadline (useful for multi-attempt drift recovery).

    Deadline is anchored to the customer message's first-seen time
    (recorded by EventMonitor via ``mark_message_first_seen``) if
    known, NOT to PreDispatch's dispatch time.  Under flood load
    PreDispatch lag is 5-15s — without this anchor, a 20s timeout
    fires 25-35s after the customer typed their message, missing
    Feige's 30s red-flag refresh cycle.  Anchoring to first-seen
    keeps total customer-to-placeholder latency at timeout + ~3s
    regardless of PreDispatch latency.
    """
    if not customer_key or timeout_s <= 0:
        return
    now = time.time()
    # Anchor to message arrival time if EventMonitor recorded it
    first_seen = get_message_first_seen(customer_key, source_msg_id)
    armed_at = first_seen if first_seen > 0.0 else now
    deadline = armed_at + timeout_s
    # 2026-05-27 mt050F — DON'T clamp deadline to ``now + 1.0`` when
    # the first_seen-anchored deadline is already in the past.  Live
    # customer trace 2026-05-27 12:38-12:39: PreDispatch queue was
    # busy and arm() fired 49 s after dom_observed; first_seen-based
    # deadline was 12:38:10 but arm time was 12:39:02, so the old
    # clamp pushed deadline to 12:39:03 (~1 s after arm).  Total
    # customer-to-placeholder latency was 63 s — Feige's 30 s red-
    # flag deadline was blown.
    #
    # New behaviour: when the deadline is already past, leave it as
    # is.  The sweeper's next 1 s tick will fire the placeholder
    # immediately, restoring the first_seen anchor's contract
    # ("placeholder arrives ~timeout_s after the customer typed",
    # not "~timeout_s after eCan's PreDispatch finished").  The
    # spam-fire concern from the original comment is handled by the
    # per-customer placeholder cap (PLACEHOLDER_CAP_WINDOW_S +
    # PLACEHOLDER_CAP_MAX) further down — not by this clamp.
    key = _make_key(customer_key, source_msg_id)
    with _REGISTRY_LOCK:
        entry = _REGISTRY.get(key)
        if entry is None:
            entry = _TimerEntry(
                customer_key=str(customer_key),
                source_msg_id=str(source_msg_id or ""),
                armed_at=armed_at,
                deadline_at=deadline,
            )
            _REGISTRY[key] = entry
        else:
            # Re-arm: reset deadline but preserve placeholder count so
            # we don't spam endlessly on rapid re-dispatch.
            entry.deadline_at = deadline
            entry.cancelled = False
    delay_to_fire = max(0.0, deadline - now)
    logger.debug(
        f"[placeholder_timer] armed cust={customer_key!r} "
        f"source_msg_id={source_msg_id!r} timeout={timeout_s}s "
        f"anchor={'first_seen' if first_seen > 0 else 'now'} "
        f"fires_in={delay_to_fire:.1f}s"
    )


def cancel(customer_key: str, source_msg_id: str = "") -> bool:
    """Cancel the timer for ``(customer_key, source_msg_id)``.

    Called by the direct-delivery worker when the real reply succeeds.
    Returns True if a timer was active.

    Also: (a) stamps the per-turn "real reply just delivered" timestamp
    so any placeholder for THIS turn that was already claimed but not
    yet typed is suppressed at submit time, and (b) cancels any
    in-flight placeholder coroutine task so a placeholder that's mid-
    send when the cancel arrives gets aborted before its bubble lands.
    Other turns are untouched.
    """
    if not customer_key:
        return False
    key = _make_key(customer_key, source_msg_id)
    now = time.time()
    inflight_task = None
    with _REGISTRY_LOCK:
        entry = _REGISTRY.pop(key, None)
        _REAL_REPLY_AT[key] = now
        # 2026-05-24 mt038E: also stamp the empty-msg-id slot.  arm()
        # and cancel() can each see different msg_id values when the
        # PreDispatch scrape fails (arm gets '') OR the reply payload
        # loses source_customer_msg_id (cancel gets '').  Without the
        # blank stamp, the registry entry's key wouldn't match here
        # and claim_expired's suppress check (which now consults both
        # exact and blank slots, gated by armed_at) wouldn't fire ―
        # the sweeper would type the placeholder AFTER the real reply.
        # Live customer trace 2026-05-24 13:23: 客户14 (arm with real
        # id + cancel with ''), 客户15 (arm with '' + cancel with real
        # id).  Both saw mis-fired placeholders post-real-reply.
        _REAL_REPLY_AT[(str(customer_key), "")] = now
        inflight_task = _INFLIGHT_PLACEHOLDER_TASKS.pop(key, None)
    if entry is not None:
        elapsed = now - entry.armed_at
        logger.debug(
            f"[placeholder_timer] cancelled cust={customer_key!r} "
            f"source_msg_id={source_msg_id!r} "
            f"elapsed={elapsed:.1f}s "
            f"placeholders_typed={entry.placeholders_typed}"
        )
    if inflight_task is not None:
        try:
            inflight_task.cancel()
            logger.info(
                f"[placeholder_timer] cancelled IN-FLIGHT placeholder task "
                f"for cust={customer_key!r} src_msg={source_msg_id!r} — "
                f"real reply arrived during type window"
            )
        except Exception as _cx:
            logger.debug(f"[placeholder_timer] inflight task.cancel failed: {_cx}")
    return entry is not None


def cancel_any_for_customer(customer_key: str) -> int:
    """Cancel ALL timers for ``customer_key`` regardless of source_msg_id.

    Useful when source_msg_id is unknown at cancel time (e.g., the
    reply payload doesn't carry it back).  Returns count cancelled.

    NOTE (2026-05-20): prefer ``cancel(customer, src_msg_id)`` whenever
    src_msg_id is known.  Per-customer cancel kills timers for newer
    in-flight turns (e.g., an older reply landing cancels the latest
    question's placeholder — leaves customer with no acknowledgment).
    Stamps real-reply for both the empty-src key AND any keys we
    actually cancelled, so submit-time suppression catches in-flight
    placeholders too.
    """
    if not customer_key:
        return 0
    cancelled = 0
    now = time.time()
    cancelled_keys: list[tuple[str, str]] = []
    with _REGISTRY_LOCK:
        for k in list(_REGISTRY.keys()):
            if k[0] == customer_key:
                _REGISTRY.pop(k, None)
                cancelled_keys.append(k)
                cancelled += 1
        for k in cancelled_keys:
            _REAL_REPLY_AT[k] = now
        # Also stamp empty-src so unknown-src placeholders are suppressed
        _REAL_REPLY_AT[(customer_key, "")] = now
    if cancelled:
        logger.debug(
            f"[placeholder_timer] cancelled {cancelled} timers for "
            f"cust={customer_key!r}"
        )
    return cancelled


@dataclass
class ExpiredEntry:
    customer_key: str
    source_msg_id: str
    placeholders_typed: int
    placeholder_text: str  # next text to type
    is_final: bool         # True if this will be the LAST placeholder


def claim_expired(
    *,
    max_placeholders: int,
    rearm_s: float,
) -> list[ExpiredEntry]:
    """Atomically claim entries whose deadline has passed.

    Returns the entries to type as placeholders.  Each claimed entry's
    deadline is bumped by ``rearm_s`` and its placeholder count is
    incremented in-place; if the new count reaches ``max_placeholders``,
    the entry is removed from the registry (no more placeholders will
    fire — the customer either gets the real reply or stays silent).
    """
    now = time.time()
    out: list[ExpiredEntry] = []
    cutoff = now - REAL_REPLY_SUPPRESS_S
    ph_cap_cutoff = now - PLACEHOLDER_CAP_WINDOW_S
    with _REGISTRY_LOCK:
        for k, entry in list(_REGISTRY.items()):
            if entry.cancelled or entry.deadline_at > now:
                continue
            # 2026-05-21: skip if real reply is already in progress or
            # just delivered for THIS specific turn.  The runner's
            # direct_feige_send_start now stamps _REAL_REPLY_AT before
            # the JS eval starts (not just on success), so this check
            # catches placeholders that would otherwise race-type
            # alongside the actual reply (客户14 6ms-race trace).
            #
            # 2026-05-24 mt038E: take max(exact_key, blank_key) — when
            # arm and cancel use different msg_id values (because the
            # PreDispatch scrape failed on one side or the LLM reply
            # payload lost source_customer_msg_id on the other), the
            # exact-key lookup misses and the placeholder mis-fires
            # AFTER the real reply has already landed.  cancel() and
            # mark_real_reply_delivered now stamp the (customer, '')
            # slot too, so this max() catches both halves of the race.
            #
            # The ``ts_real > entry.armed_at`` guard preserves the
            # newer-turn semantic from 2026-05-20: if customer Q1
            # got answered (stamp at T=10), and customer Q2 was
            # armed AFTER (T=12), Q2's placeholder is NOT suppressed
            # — its armed_at exceeds the stamp.
            ts_real_exact = _REAL_REPLY_AT.get(k, 0.0)
            ts_real_blank = _REAL_REPLY_AT.get(
                (entry.customer_key, ""), 0.0
            )
            ts_real = max(ts_real_exact, ts_real_blank)
            # >= (not >) because time.time() has ~1ms granularity on
            # Windows — back-to-back arm() + cancel() can land in the
            # same tick.  A real next-turn arrival is separated from
            # the prior cancel by network + dispatch latency (>>1ms)
            # so the next-turn-preservation invariant holds.
            if ts_real >= entry.armed_at and ts_real > cutoff:
                # Real reply just started/completed for this turn —
                # drop the placeholder entry silently.
                _REGISTRY.pop(k, None)
                continue
            if entry.placeholders_typed >= max_placeholders:
                # Exhausted — remove silently
                _REGISTRY.pop(k, None)
                continue
            # 2026-05-21 Fix B: hard per-customer cap.  Regardless of how
            # many timers exist for this customer (e.g., phantom + real
            # turn both armed), never type more than max_placeholders
            # in the recent window.  Protects against orphan-timer cases
            # that Fix A (supersede-side cancel) might miss.
            cust_ts = _PLACEHOLDERS_TYPED_TS.get(entry.customer_key)
            if cust_ts:
                while cust_ts and cust_ts[0] < ph_cap_cutoff:
                    cust_ts.pop(0)
                if len(cust_ts) >= max_placeholders:
                    # Already typed max for this customer in window —
                    # drop this entry to avoid spamming the chat
                    _REGISTRY.pop(k, None)
                    continue
            # mt048A: resolved lazily so operator file overrides apply.
            _texts = _get_placeholder_texts()
            text_idx = min(entry.placeholders_typed, len(_texts) - 1)
            text = _texts[text_idx]
            entry.placeholders_typed += 1
            entry.deadline_at = now + rearm_s
            is_final = entry.placeholders_typed >= max_placeholders
            out.append(
                ExpiredEntry(
                    customer_key=entry.customer_key,
                    source_msg_id=entry.source_msg_id,
                    placeholders_typed=entry.placeholders_typed,
                    placeholder_text=text,
                    is_final=is_final,
                )
            )
            if is_final:
                # Remove now — caller will type but we won't fire again
                _REGISTRY.pop(k, None)
    return out


def snapshot() -> dict:
    """Return a JSON-safe snapshot for diagnostics / IPC."""
    with _REGISTRY_LOCK:
        return {
            "size": len(_REGISTRY),
            "entries": [
                {
                    "customer": e.customer_key,
                    "source_msg_id": e.source_msg_id,
                    "armed_at": e.armed_at,
                    "deadline_at": e.deadline_at,
                    "placeholders_typed": e.placeholders_typed,
                }
                for e in _REGISTRY.values()
            ],
        }


async def sweep_loop_async(
    *,
    timeout_s: float,
    max_placeholders: int,
    rearm_s: float,
    interval_s: float,
    placeholder_submitter,
) -> None:
    """Background coroutine — periodically checks for expired timers
    and submits placeholder sends via ``placeholder_submitter``.

    ``placeholder_submitter(customer_key, source_msg_id, text)`` is a
    callable that submits a synthetic reply through the same path real
    replies use (the runner's direct-delivery submit).  Wired in
    ``dom_assets`` at pool-init time so this module stays free of
    runner.py imports (avoiding circular deps).

    Quietly exits if cancelled (e.g., on app shutdown).
    """
    import asyncio as _asyncio

    if timeout_s <= 0 or interval_s <= 0:
        logger.info(
            "[placeholder_timer] sweeper not started — timeout=%s interval=%s",
            timeout_s, interval_s,
        )
        return
    logger.info(
        f"[placeholder_timer] sweeper started: timeout={timeout_s}s "
        f"max={max_placeholders} rearm={rearm_s}s interval={interval_s}s"
    )
    while True:
        try:
            await _asyncio.sleep(interval_s)
            expired = claim_expired(
                max_placeholders=max_placeholders, rearm_s=rearm_s
            )
            for entry in expired:
                # 2026-05-27 mt050G — re-check is_real_reply_recent
                # RIGHT before submit.  ``claim_expired`` already does
                # this check while it holds the registry lock, but the
                # gap between claim and submit (which involves a queue
                # push + thread handoff) is wide enough for the real
                # reply to land mid-flight.  Live trace 2026-05-27
                # 12:42:04-06: bot reply sent at 12:42:04.840 but
                # placeholder #2 already fired at 12:42:06.188 — the
                # mark_real_reply_delivered stamp arrived only after
                # the sweeper had pushed the placeholder to the
                # direct-delivery queue.  This second check closes the
                # final race window.
                if is_real_reply_recent(
                    entry.customer_key, entry.source_msg_id,
                ):
                    logger.info(
                        f"[placeholder_timer] mt050G suppressed placeholder "
                        f"#{entry.placeholders_typed} for cust={entry.customer_key!r} "
                        f"src_msg={entry.source_msg_id!r} — real reply landed "
                        f"between claim_expired and submit"
                    )
                    continue
                try:
                    submitted = placeholder_submitter(
                        entry.customer_key,
                        entry.source_msg_id,
                        entry.placeholder_text,
                    )
                    logger.info(
                        f"[placeholder_timer] fired placeholder #{entry.placeholders_typed}"
                        f"{' (FINAL)' if entry.is_final else ''} "
                        f"cust={entry.customer_key!r} "
                        f"text={entry.placeholder_text!r} "
                        f"submitted={submitted}"
                    )
                except Exception as e:
                    logger.warning(
                        f"[placeholder_timer] placeholder submit failed for "
                        f"cust={entry.customer_key!r}: {e}"
                    )
        except _asyncio.CancelledError:
            logger.info("[placeholder_timer] sweeper cancelled")
            return
        except Exception as e:
            logger.warning(f"[placeholder_timer] sweep tick failed: {e}")


__all__ = [
    "arm",
    "cancel",
    "cancel_any_for_customer",
    "claim_expired",
    "snapshot",
    "sweep_loop_async",
    "ExpiredEntry",
]
