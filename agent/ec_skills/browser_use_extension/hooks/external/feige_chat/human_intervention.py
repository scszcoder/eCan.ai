"""Human-intervention state tracking (mt017, 2026-05-21).

When the human customer-service agent jumps into Feige and types a reply
directly to a customer, eCan must:

1. **Detect it** — agent bubble appears that we did NOT type ourselves
   (i.e., not in :mod:`dispatch_state.recent_agent_replies_by_customer`)
2. **Abort if in-flight** — cancel any pending placeholder timer for that
   customer and skip any Q&A bot reply that arrives later (already
   answered by human)
3. **No-op if our reply already typed** — too late to take back; just
   record the human action so future turns know

This module owns the state.  Detection lives in
``pre_dispatch_enrich.enrich_item`` (which already scrapes the chat
thread); the abort hook fires automatically when the customer is marked
handled (direct-delivery worker + PreDispatch consult
``is_human_handled_recent`` before doing work).
"""
from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger("eCan")

# Per-customer "human typed a reply at this wall-clock" timestamps.
# TTL keeps the state bounded; after expiry, the customer's automation
# resumes.  A second human reply re-stamps the entry.
_HUMAN_HANDLED_AT: dict[str, float] = {}
# Optional: the agent-bubble msg_id we observed as human-typed (for
# diagnostic and to suppress detection from re-firing on the same bubble
# in subsequent scrapes).
_HUMAN_HANDLED_MSG_ID: dict[str, str] = {}
HUMAN_HANDLED_TTL_S: float = 120.0

# Per-customer baseline agent-bubble msg_id.  Recorded on the FIRST
# scrape per customer per process lifetime.  Used by mt017 detection to
# distinguish a *new* unrecognised bubble (real human intervention) from
# a *pre-existing* one (stale DOM from a prior app session, or a bubble
# that aged out of the recent-reply ledger TTL).  Without this guard,
# the flood-test 2026-05-21 14:28 run mis-fired mt017 for all 20
# customers, silently dropping every Q&A reply.
_BASELINE_AGENT_MSG_ID: dict[str, str] = {}

# 2026-05-23 mt028: TEXT analog of _BASELINE_AGENT_MSG_ID.  Front-desk's
# dom-echo guard checks the SIDEBAR PREVIEW (a text field), not the
# bubble msg_id, so the mt021 msg_id baseline can't help it.  Without a
# text baseline, the flood-test 2026-05-22 13:46 run dispatched
# yesterday's bot replies (still in chat DOM after process restart) as
# new customer questions for 客户16 / 客户18 / 客户19 — 3-5 wasted
# dispatches each, 0-1 successful answers.
#
# Set in pre_dispatch_enrich._scrape_and_override_last_message on the
# SAME first-sighting that establishes the msg_id baseline.  Checked in
# frontdesk_dispatch's supersede / inflight-echo / pre-scrape-echo
# guards: a sidebar text matching the baseline → stale pre-existing
# bubble, do NOT treat as a new customer message.
_BASELINE_AGENT_TEXT: dict[str, str] = {}

# 2026-05-23 mt030: per-customer baseline of the LATEST CUSTOMER-side
# bubble msg_id observed at process start.  Mirror of mt021's agent
# baseline but for the customer side.
#
# Without this, fresh process + leftover customer bubbles from a prior
# run cause PreDispatch to mis-dispatch yesterday's customer question
# as if it were new.  Live trace 2026-05-22 16:06:37 客户18:
# yesterday's "你们默认走什么快递？" was still in chat; we dispatched
# it; bot generated reply about 快递; customer happened to type a
# NEW question ("退款一般几天到账？") at the same moment → bot's
# reply showed up answering the WRONG question.
#
# Set in pre_dispatch_enrich._scrape_and_override_last_message on the
# FIRST scrape per customer.  Checked there: if the scraped customer
# bubble msg_id equals the baseline, treat as pre-existing and skip
# dispatch (baseline_skip).  When the customer types a NEW bubble its
# msg_id changes, baseline mismatches, dispatch fires legitimately.
_BASELINE_CUSTOMER_MSG_ID: dict[str, str] = {}

# Per-customer set of agent-bubble msg_ids that WE typed (via the JS
# feige_send_message verify path) and have therefore registered as
# "ours" permanently.  No TTL — once recorded, the msg_id stays known
# for the process lifetime.  Used by mt017 detection as a third
# defence (after the recent-reply ledger and the baseline) so a bubble
# we typed an hour ago doesn't get mis-detected as human intervention
# when the recent-reply ledger has long since aged it out.
#
# Customer-impact trace: 2026-05-22 08:14:34 typed packet reply → ledger
# entry pruned at 08:16:04 (90 s TTL) → 08:19:40 thread scrape sees the
# bubble's msg_id, doesn't match ledger or baseline → mark_handled
# fires → packet's REAL reply at 08:19:59 dropped via DIRECT-DELIVERY
# human-intervention skip.  Same pattern for 肽斯特.
_TYPED_AGENT_MSG_IDS: dict[str, set[str]] = {}
# Cap per-customer set growth defensively (very long sessions could
# accumulate thousands of bubbles); evict the oldest on overflow.  16
# is plenty — only the *last* agent bubble msg_id is queried per scrape
# and we add msg_ids in chronological order; older entries can never
# re-appear as "latest agent bubble".
_TYPED_AGENT_MSG_IDS_CAP: int = 16
_TYPED_AGENT_MSG_IDS_ORDER: dict[str, list[str]] = {}

# 2026-05-23 mt028: TEXT analog of _TYPED_AGENT_MSG_IDS.  No TTL.  Used
# by frontdesk_dispatch's supersede check and pre_dispatch_enrich's
# dom-echo guards as a back-stop when the TTL-bounded
# dispatch_state.recent_agent_replies_by_customer has aged out OR when
# the process just restarted (fresh ledger but stale bubbles in DOM).
#
# Customer-impact trace 2026-05-22 13:46:48 客户16: yesterday's reply
# text "您好，男装XL码..." was in chat DOM, recent_agent_replies was
# empty (fresh process), supersede fired because sidebar_text != prior
# dispatched question, → 5 wasted dispatches, 0 answers.  With this
# set populated on every typed bubble (including yesterday's, if the
# process had still been alive), supersede would have skipped.
_TYPED_AGENT_TEXTS: dict[str, set[str]] = {}
_TYPED_AGENT_TEXTS_CAP: int = 16
_TYPED_AGENT_TEXTS_ORDER: dict[str, list[str]] = {}

_LOCK = threading.Lock()


def mark_handled(
    customer_key: str,
    msg_id: str = "",
    *,
    source: str = "",
) -> None:
    """Record that a human typed a reply for ``customer_key``.

    Called from the chat-thread scraper when it detects an agent bubble
    whose text isn't in our recent-agent-reply ledger.  Idempotent —
    re-marking the same customer just refreshes the timestamp.
    """
    if not customer_key:
        return
    cust = str(customer_key)
    now = time.time()
    with _LOCK:
        _HUMAN_HANDLED_AT[cust] = now
        if msg_id:
            _HUMAN_HANDLED_MSG_ID[cust] = str(msg_id)
    logger.info(
        f"[HUMAN-INTERVENTION] cust={cust!r} marked human-handled "
        f"msg_id=...{(msg_id or '')[-8:]} source={source!r} "
        f"ttl={HUMAN_HANDLED_TTL_S}s"
    )


def is_handled_recent(customer_key: str) -> bool:
    """Returns True if a human reply was detected for ``customer_key``
    within the last ``HUMAN_HANDLED_TTL_S`` seconds."""
    if not customer_key:
        return False
    with _LOCK:
        ts = _HUMAN_HANDLED_AT.get(str(customer_key), 0.0)
    if ts <= 0.0:
        return False
    return (time.time() - ts) <= HUMAN_HANDLED_TTL_S


def get_handled_msg_id(customer_key: str) -> str:
    """Returns the msg_id of the most-recently-observed human bubble for
    this customer (within TTL), or empty string."""
    if not customer_key:
        return ""
    if not is_handled_recent(customer_key):
        return ""
    with _LOCK:
        return _HUMAN_HANDLED_MSG_ID.get(str(customer_key), "")


def clear(customer_key: str) -> None:
    """Manually clear a customer's human-handled state.  Useful if the
    operator wants to resume automation immediately rather than waiting
    for TTL to expire.  Does NOT clear the baseline msg_id — the
    pre-existing bubble that triggered baselining is still in the DOM
    and shouldn't be re-detected as human intervention after clear."""
    if not customer_key:
        return
    cust = str(customer_key)
    with _LOCK:
        _HUMAN_HANDLED_AT.pop(cust, None)
        _HUMAN_HANDLED_MSG_ID.pop(cust, None)


def get_baseline_msg_id(customer_key: str) -> str:
    """Return the recorded baseline agent-bubble msg_id for this customer
    (the first agent bubble observed in their thread since process start),
    or empty string if none seen yet."""
    if not customer_key:
        return ""
    with _LOCK:
        return _BASELINE_AGENT_MSG_ID.get(str(customer_key), "")


def set_baseline_msg_id(customer_key: str, msg_id: str) -> None:
    """Record / refresh the baseline agent-bubble msg_id for this customer.
    Called by the chat-thread scraper on first sighting AND whenever a
    new unrecognised bubble triggers mark_handled (so subsequent scrapes
    of the same bubble don't re-fire)."""
    if not customer_key:
        return
    cust = str(customer_key)
    with _LOCK:
        _BASELINE_AGENT_MSG_ID[cust] = str(msg_id or "")


def record_typed_msg_id(customer_key: str, msg_id: str) -> None:
    """Register that ``msg_id`` is the data-id of an agent bubble WE
    typed (via feige_send_message).  Permanent (no TTL) — the next mt017
    scrape that sees this msg_id as the latest agent bubble will treat
    it as ours and skip the human-intervention mark.

    Called from extension_tools_service.py after a verified send returns
    ``verified_msg_id`` in its JS response.  Empty msg_id is a no-op
    (rare; the wrapper had no data-id attribute).
    """
    if not customer_key or not msg_id:
        return
    cust = str(customer_key)
    mid = str(msg_id).strip()
    if not mid:
        return
    with _LOCK:
        s = _TYPED_AGENT_MSG_IDS.setdefault(cust, set())
        if mid in s:
            return
        s.add(mid)
        order = _TYPED_AGENT_MSG_IDS_ORDER.setdefault(cust, [])
        order.append(mid)
        # Evict oldest if we're over the cap
        while len(order) > _TYPED_AGENT_MSG_IDS_CAP:
            old = order.pop(0)
            s.discard(old)


def is_known_typed_msg_id(customer_key: str, msg_id: str) -> bool:
    """Return True if ``msg_id`` was registered via
    :func:`record_typed_msg_id` for this customer.

    Used by the mt017 thread-scrape detection in pre_dispatch_enrich:
    if the latest agent bubble's msg_id is in our typed set, the bubble
    is ours and mark_handled MUST NOT fire — regardless of whether the
    recent-reply text-ledger has aged out.
    """
    if not customer_key or not msg_id:
        return False
    with _LOCK:
        s = _TYPED_AGENT_MSG_IDS.get(str(customer_key))
        if not s:
            return False
        return str(msg_id).strip() in s


def get_baseline_customer_msg_id(customer_key: str) -> str:
    """Return the per-process baseline customer-side bubble msg_id for
    this customer, or "" if no scrape has set it yet.

    mt030 — pre-existing customer bubble detection.  See module-level
    ``_BASELINE_CUSTOMER_MSG_ID`` for the live trace this prevents.
    """
    if not customer_key:
        return ""
    with _LOCK:
        return _BASELINE_CUSTOMER_MSG_ID.get(str(customer_key), "")


def set_baseline_customer_msg_id(customer_key: str, msg_id: str) -> None:
    """Set the per-process baseline customer-side bubble msg_id.

    Called from pre_dispatch_enrich on the FIRST scrape per customer.
    Idempotent: re-call with the same key is a no-op (the baseline
    only changes if the caller passes a different msg_id, which would
    happen during ``clear()`` flows we don't currently use here)."""
    if not customer_key:
        return
    cust = str(customer_key)
    mid = str(msg_id or "").strip()
    with _LOCK:
        _BASELINE_CUSTOMER_MSG_ID[cust] = mid


def get_baseline_text(customer_key: str) -> str:
    """Return the recorded baseline agent-bubble TEXT for this customer
    (the first agent-side bubble TEXT observed in their thread since
    process start), or empty string if none seen yet.

    2026-05-23 mt028 — back-stops the front-desk's text-based dom-echo
    guards against stale bubbles persisting in the DOM after a process
    restart.  Set in tandem with :func:`set_baseline_msg_id`.
    """
    if not customer_key:
        return ""
    with _LOCK:
        return _BASELINE_AGENT_TEXT.get(str(customer_key), "")


def set_baseline_text(customer_key: str, text: str) -> None:
    """Record / refresh the baseline agent-bubble TEXT for this customer."""
    if not customer_key:
        return
    cust = str(customer_key)
    with _LOCK:
        _BASELINE_AGENT_TEXT[cust] = str(text or "")


def record_typed_text(customer_key: str, text: str) -> None:
    """Permanent per-customer registry of agent-bubble texts WE typed.

    2026-05-23 mt028 — TEXT analog of :func:`record_typed_msg_id`.
    Called from the same code path on a verified send.  The mt023
    ``dispatch_state.recent_agent_replies_by_customer`` ledger has a
    90 s TTL; this set has none.  Used by the front-desk's supersede /
    dom-echo guards as a back-stop when the TTL'd ledger has aged out
    or the process restarted.

    Bounded by ``_TYPED_AGENT_TEXTS_CAP`` (16) per customer with LRU
    eviction so very long sessions don't unbounded-grow.
    """
    if not customer_key or not text:
        return
    cust = str(customer_key)
    txt = str(text).strip()
    if not txt:
        return
    with _LOCK:
        s = _TYPED_AGENT_TEXTS.setdefault(cust, set())
        if txt in s:
            return
        s.add(txt)
        order = _TYPED_AGENT_TEXTS_ORDER.setdefault(cust, [])
        order.append(txt)
        while len(order) > _TYPED_AGENT_TEXTS_CAP:
            old = order.pop(0)
            s.discard(old)


def is_known_typed_text(customer_key: str, text: str) -> bool:
    """Return True if ``text`` matches a previously-typed agent-bubble
    TEXT for this customer (registered via :func:`record_typed_text`).

    Used by frontdesk_dispatch's supersede check and
    pre_dispatch_enrich's dom-echo guards.
    """
    if not customer_key or not text:
        return False
    with _LOCK:
        s = _TYPED_AGENT_TEXTS.get(str(customer_key))
        if not s:
            return False
        return str(text).strip() in s


def snapshot() -> dict:
    """JSON-safe snapshot for diagnostics / IPC."""
    now = time.time()
    cutoff = now - HUMAN_HANDLED_TTL_S
    with _LOCK:
        return {
            "ttl_s": HUMAN_HANDLED_TTL_S,
            "active": {
                cust: {
                    "ts": ts,
                    "age_s": round(now - ts, 1),
                    "msg_id": _HUMAN_HANDLED_MSG_ID.get(cust, ""),
                }
                for cust, ts in _HUMAN_HANDLED_AT.items()
                if ts >= cutoff
            },
        }


__all__ = [
    "HUMAN_HANDLED_TTL_S",
    "mark_handled",
    "is_handled_recent",
    "get_handled_msg_id",
    "get_baseline_text",
    "set_baseline_text",
    "get_baseline_customer_msg_id",
    "set_baseline_customer_msg_id",
    "record_typed_text",
    "is_known_typed_text",
    "get_baseline_msg_id",
    "set_baseline_msg_id",
    "record_typed_msg_id",
    "is_known_typed_msg_id",
    "clear",
    "snapshot",
]
