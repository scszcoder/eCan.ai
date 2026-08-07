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

# 2026-05-24 mt036A: per-(customer, customer-question-msg_id) handled
# registry.  Replaces the per-customer-blanket _HUMAN_HANDLED_AT for the
# direct-delivery suppression check.
#
# WHY mt036A: the customer's 2026-05-24 11:34 trace showed packet's
# legitimate bot reply to "能不能包邮" (source_msg_id 9034feca) was
# dropped via human_intervention_skip at 11:34:41 because a different
# unrecognised agent bubble (msg_id 673c40e5) had triggered mark_handled
# at 11:34:21, putting packet into "blanket 120s suppression".  The bot
# regenerated and re-typed the answer 5 min later (Generation B
# chatcmpl-10ebd222 at 11:39:58).  Customer-visible wait: 5+ minutes for
# no good reason.
#
# Fix: mark_handled keyed by (customer, question_msg_id).  The bot's
# reply targets a specific source_customer_msg_id; if THAT exact
# question isn't in the handled registry, the reply proceeds.  A human
# answer to question X only suppresses bot replies targeting X — NOT
# replies for newer questions Y/Z.
#
# Compatible with existing blanket _HUMAN_HANDLED_AT (kept for the
# rare callers that don't carry a question_msg_id), but the
# direct-delivery hot-path uses the scoped check exclusively post-mt036.
_HANDLED_QUESTIONS: dict[tuple[str, str], float] = {}

# 2026-05-26 mt048B: human-typed bubble TEXT keyed by the same
# ``(customer, question_msg_id)`` pair as ``_HANDLED_QUESTIONS``.
# Captured at mark-time so the LLM relevance judge can compare the
# human's reply against the customer's question and decide whether to
# drop the bot's reply (human answered) or let it proceed (human said
# something off-topic, customer still needs the bot's answer).
_HANDLED_QUESTIONS_TEXT: dict[tuple[str, str], str] = {}

# ws005 (Situation 3): per-customer recent HUMAN-agent replies, captured when a human
# intervention answered the customer and we therefore suppressed our bot reply. Surfaced
# to the Q&A worker on the NEXT turn so it has the human's answer as conversation context
# (the requirement: the human answer rolls into context/memory for the next round). Longer
# TTL than the 120s handled-window because the customer's next question may come minutes
# later.
_RECENT_HUMAN_REPLIES: dict[str, list[tuple[str, float]]] = {}
RECENT_HUMAN_REPLY_TTL_S: float = 600.0
RECENT_HUMAN_REPLY_MAX: int = 3

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
    question_msg_id: str = "",
    bubble_text: str = "",
) -> None:
    """Record that a human typed a reply for ``customer_key``.

    Called from the chat-thread scraper when it detects an agent bubble
    whose text isn't in our recent-agent-reply ledger.  Idempotent —
    re-marking the same customer just refreshes the timestamp.

    2026-05-24 mt036A: ``question_msg_id`` is the latest CUSTOMER bubble
    msg_id at the moment the mark fires — i.e. the question the human
    appears to be answering.  When set, the mark is keyed by
    ``(customer, question_msg_id)`` so direct-delivery only suppresses
    the bot's reply that targets THIS specific question.  Replies to
    OTHER (later) questions proceed normally.  Before mt036A the mark
    blanketed the whole customer for 120 s, dropping legitimate replies
    to unrelated questions.

    2026-05-26 mt048B: ``bubble_text`` is the human-typed text itself,
    captured so the LLM relevance judge can later decide whether the
    human's reply ACTUALLY answers the customer's question.  When the
    judge says "no, the human just said hi" the bot's reply is allowed
    through instead of being dropped wholesale.
    """
    if not customer_key:
        return
    cust = str(customer_key)
    now = time.time()
    qid = str(question_msg_id or "").strip()
    txt = str(bubble_text or "").strip()
    with _LOCK:
        _HUMAN_HANDLED_AT[cust] = now
        if msg_id:
            _HUMAN_HANDLED_MSG_ID[cust] = str(msg_id)
        if qid:
            _HANDLED_QUESTIONS[(cust, qid)] = now
            if txt:
                _HANDLED_QUESTIONS_TEXT[(cust, qid)] = txt
    logger.info(
        f"[HUMAN-INTERVENTION] cust={cust!r} marked human-handled "
        f"msg_id=...{(msg_id or '')[-8:]} "
        f"question_msg_id=...{(qid or '')[-8:]} "
        f"source={source!r} ttl={HUMAN_HANDLED_TTL_S}s "
        f"text_len={len(txt)}"
    )


def is_handled_recent(customer_key: str) -> bool:
    """Returns True if a human reply was detected for ``customer_key``
    within the last ``HUMAN_HANDLED_TTL_S`` seconds.

    NOTE 2026-05-24 mt036A: this blanket check is deprecated for the
    direct-delivery hot path.  Use :func:`is_question_handled` instead,
    which scopes the check to a specific source_customer_msg_id and
    therefore doesn't drop replies for unrelated newer questions.  The
    function is kept for backwards compat with callers that don't carry
    a question_msg_id (e.g. observability/diagnostics)."""
    if not customer_key:
        return False
    with _LOCK:
        ts = _HUMAN_HANDLED_AT.get(str(customer_key), 0.0)
    if ts <= 0.0:
        return False
    return (time.time() - ts) <= HUMAN_HANDLED_TTL_S


def is_question_handled(customer_key: str, question_msg_id: str) -> bool:
    """2026-05-24 mt036A: scoped check — returns True iff a human reply
    was recorded for THIS specific ``(customer_key, question_msg_id)``
    within the TTL.

    The intent: a human's reply to question X should suppress the bot's
    reply to X only.  When the bot's reply targets question Y (newer),
    this check returns False and the reply proceeds.  Customer's
    2026-05-24 11:34:41 case: the 11:34:21 mark recorded an unrelated
    agent bubble (msg_id 673c40e5); the bot's reply targeted question
    msg_id 9034feca; before mt036A the blanket check dropped the reply,
    now the scoped check sees no (packet, 9034feca) entry and allows
    the send.

    Falls back to False (allow send) when either argument is empty —
    callers without a question_msg_id should use the legacy
    :func:`is_handled_recent` if they want the old per-customer
    behaviour.
    """
    if not customer_key or not question_msg_id:
        return False
    key = (str(customer_key), str(question_msg_id).strip())
    if not key[1]:
        return False
    with _LOCK:
        ts = _HANDLED_QUESTIONS.get(key, 0.0)
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


def get_handled_question_text(customer_key: str, question_msg_id: str) -> str:
    """2026-05-26 mt048B: returns the human-typed text that was
    captured when ``mark_handled`` fired for ``(customer_key,
    question_msg_id)``.  Empty string when nothing was recorded.

    Used by the LLM relevance judge in runner.py's direct-delivery
    drop check to decide whether the human actually answered the
    customer's question (drop bot reply) or said something off-topic
    (let bot reply proceed).
    """
    if not customer_key or not question_msg_id:
        return ""
    key = (str(customer_key), str(question_msg_id).strip())
    if not key[1]:
        return ""
    with _LOCK:
        return _HANDLED_QUESTIONS_TEXT.get(key, "")


def record_human_reply(customer_key: str, reply_text: str) -> None:
    """ws005 (Situation 3): remember a human-agent reply that ANSWERED the customer (so
    we suppressed our bot reply). Surfaced to the next Q&A turn as context."""
    cust = str(customer_key or "").strip()
    txt = str(reply_text or "").strip()
    if not cust or not txt:
        return
    now = time.time()
    cutoff = now - RECENT_HUMAN_REPLY_TTL_S
    with _LOCK:
        lst = _RECENT_HUMAN_REPLIES.setdefault(cust, [])
        lst[:] = [(t, ts) for (t, ts) in lst if ts >= cutoff and t != txt]
        lst.append((txt, now))
        if len(lst) > RECENT_HUMAN_REPLY_MAX:
            del lst[: len(lst) - RECENT_HUMAN_REPLY_MAX]


def get_recent_human_reply(customer_key: str) -> str:
    """ws005: the most recent human-agent reply for this customer within TTL, else ''.
    Read by PreDispatch to add `recent_human_reply` context to the next Q&A turn."""
    cust = str(customer_key or "").strip()
    if not cust:
        return ""
    now = time.time()
    with _LOCK:
        lst = _RECENT_HUMAN_REPLIES.get(cust)
        if not lst:
            return ""
        for txt, ts in reversed(lst):
            if (now - ts) <= RECENT_HUMAN_REPLY_TTL_S:
                return txt
    return ""


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
        # 2026-05-24 mt036A: also clear any per-question handled keys
        # for this customer so an operator's manual unblock fully
        # resumes automation.
        for k in [k for k in _HANDLED_QUESTIONS if k[0] == cust]:
            _HANDLED_QUESTIONS.pop(k, None)


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


def _normalize_for_typed_text(text: str) -> str:
    """2026-05-24 mt036B: whitespace-strip normalisation so our own
    typed text matches the scraper's DOM extraction.

    Same shape as ``dispatch_state.normalize_reply_text`` (mt034 fix):
    Feige's chat-thread bubble strips ``\\n`` characters between paragraphs
    without inserting a space.  Pre-mt036B, ``record_typed_text`` stored
    the bot's response with newlines (only outer ``.strip()``) and
    ``is_known_typed_text`` compared the scraper's whitespace-collapsed
    DOM text via membership — they almost-always failed to match for
    multi-line replies.  The downstream effect: mt017 thought our own
    bubble was a human reply and triggered ``mark_handled``, dropping
    the next legitimate bot reply via ``human_intervention_skip``.

    Live trace 2026-05-24 11:34:21 packet — agent bubble msg_id
    673c40e5 (= our 11:33:59 reply "可以的，今天下单一般会尽快安排
    发货。\\n优惠这边需要看...") wasn't recognised by
    ``is_known_typed_text`` because the scraper saw "可以的...发货。
    优惠这边需要看..." (no newline) → mark_handled fired → packet's
    11:34:41 reply to a different question dropped.
    """
    if not text:
        return ""
    import re
    return re.sub(r"\s+", "", str(text)).strip()


def record_typed_text(customer_key: str, text: str) -> None:
    """Permanent per-customer registry of agent-bubble texts WE typed.

    2026-05-23 mt028 — TEXT analog of :func:`record_typed_msg_id`.
    Called from the same code path on a verified send.  The mt023
    ``dispatch_state.recent_agent_replies_by_customer`` ledger has a
    90 s TTL; this set has none.  Used by the front-desk's supersede /
    dom-echo guards as a back-stop when the TTL'd ledger has aged out
    or the process restarted.

    2026-05-24 mt036B: storage key is the WHITESPACE-STRIPPED form (same
    shape as ``dispatch_state.normalize_reply_text``'s mt034 fix).  The
    Feige chat-thread scraper collapses ``\\n`` between paragraphs
    without inserting a space; storing the strip-only form (legacy)
    meant ``is_known_typed_text`` failed to find a match for any
    multi-line bot reply and mt017 mis-fired ``mark_handled``.  Storing
    normalised guarantees the scraper's text — also passed through
    :func:`_normalize_for_typed_text` in the matcher — finds the entry.

    Bounded by ``_TYPED_AGENT_TEXTS_CAP`` (16) per customer with LRU
    eviction so very long sessions don't unbounded-grow.
    """
    if not customer_key or not text:
        return
    cust = str(customer_key)
    txt = _normalize_for_typed_text(text)
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

    2026-05-24 mt036B: both record and check normalise to the
    whitespace-stripped form, so the scraper's DOM extraction (which
    collapses ``\\n``) finds the recorded entry even when the bot's
    reply spans multiple paragraphs.

    Used by frontdesk_dispatch's supersede check and
    pre_dispatch_enrich's dom-echo guards.
    """
    if not customer_key or not text:
        return False
    txt = _normalize_for_typed_text(text)
    if not txt:
        return False
    with _LOCK:
        s = _TYPED_AGENT_TEXTS.get(str(customer_key))
        if not s:
            return False
        return txt in s


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
    "is_question_handled",
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
