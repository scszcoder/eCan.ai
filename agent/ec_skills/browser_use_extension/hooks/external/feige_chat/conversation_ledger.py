"""Which conversations we actually saw, and which we actually answered.

Built to answer one question definitively: when the site says it closed a
conversation because nobody replied, was that *us*?

Why the obvious accessor does not work
--------------------------------------
``dispatch_state.talk_recently_dispatched()`` looks like the right thing and is
not: ``TALK_DISPATCH_TTL_S`` is 15 seconds and it pops expired entries, so it
answers "dispatched in the last 15 seconds", not "ever served". A closure
notice arrives minutes after the last message, so using it would report a
definitive miss for essentially every conversation.

How a notice is matched to a conversation
-----------------------------------------
Measured against a real capture rather than assumed: the notice's
``security_customer_id`` is exactly the ``security_pigeon_uid`` carried on
messages, and ``security_biz_conversation_id`` has it as a prefix. The plaintext
``biz_conversation_id`` / ``customer_id`` / ``customer_name`` fields in the
notice are empty, so the security form is the only join available.

That uid rides only some messages (36 of 244 in the capture), so the ledger
keeps a uid -> talk_id mapping from whatever messages do carry both, and tracks
seen/served by ``talk_id``, which is far better populated.

What it will and will not claim
-------------------------------
A miss is only claimed when we *saw an inbound message for that conversation
ourselves* and never dispatched a reply. That makes the claim independent of
anything that happened before this process started: a conversation we never saw
is reported as unknown, never as a miss.

"Unknown" is not nothing, though. A closure for a conversation we never saw can
mean it predates us — or that we were blind to it, which is the failure nobody
can otherwise detect. So it is reported separately rather than discarded.
"""

from __future__ import annotations

import threading
import time
from typing import Dict, Optional, Tuple

from utils.logger_helper import logger_helper as logger

# How long a conversation stays on the books. A closure notice can follow the
# last message by many minutes; a few hours is comfortably longer than any
# plausible gap, and the maps stay small.
TTL_S = 6 * 3600

# Guard against a long-running process accumulating conversations forever.
MAX_TRACKED = 5000

_LOCK = threading.Lock()
_seen: Dict[str, float] = {}            # talk_id -> when we first saw a message
_served: Dict[str, float] = {}          # talk_id -> when we dispatched a reply
_uid_to_talk: Dict[str, str] = {}       # security uid -> talk_id


def _prune_locked(now: float) -> None:
    for store in (_seen, _served):
        for key in [k for k, ts in store.items() if now - ts > TTL_S]:
            store.pop(key, None)
    if len(_uid_to_talk) > MAX_TRACKED:
        # Drop mappings whose conversation is no longer tracked at all.
        for uid in [u for u, t in _uid_to_talk.items()
                    if t not in _seen and t not in _served]:
            _uid_to_talk.pop(uid, None)


def note_customer_message(talk_id: str = "", uid: str = "") -> None:
    """A customer wrote to us in this conversation, and we saw it.

    This is what makes a later miss claim defensible: the conversation was
    demonstrably ours to answer.
    """
    try:
        talk = str(talk_id or "").strip()
        secure = str(uid or "").strip()
        now = time.time()
        with _LOCK:
            if talk:
                _seen.setdefault(talk, now)
                if secure:
                    _uid_to_talk[secure] = talk
            if len(_seen) > MAX_TRACKED:
                _prune_locked(now)
    except Exception as exc:
        logger.debug(f"[conv-ledger] could not note message: {exc}")


def note_served(talk_id: str = "", uid: str = "") -> None:
    """We dispatched a reply for this conversation.

    Dispatched rather than confirmed-delivered on purpose: if we dispatched and
    the site still closed the conversation for non-reply, that is a delivery
    failure and is worth knowing about — arguably more than a plain miss.
    """
    try:
        talk = str(talk_id or "").strip()
        secure = str(uid or "").strip()
        now = time.time()
        with _LOCK:
            if talk:
                _served[talk] = now
                if secure:
                    _uid_to_talk[secure] = talk
            _prune_locked(now)
    except Exception as exc:
        logger.debug(f"[conv-ledger] could not note reply: {exc}")


def verdict(uid: str = "", talk_id: str = "") -> Tuple[str, str]:
    """``("missed" | "served" | "unknown", detail)`` for a closure notice.

    ``unknown`` means we have no record of the conversation — it started before
    this process, or we never saw it. Not a miss, and deliberately not silent.
    """
    try:
        secure = str(uid or "").strip()
        talk = str(talk_id or "").strip()
        with _LOCK:
            if not talk and secure:
                talk = _uid_to_talk.get(secure, "")
                # The conversation id has the customer uid as a prefix, so a
                # notice carrying only the longer form still resolves.
                if not talk:
                    for known_uid, known_talk in _uid_to_talk.items():
                        if secure.startswith(known_uid) or known_uid.startswith(secure):
                            talk = known_talk
                            break
            if not talk:
                return "unknown", "no conversation id we recognise"
            # Served is checked FIRST. On a cold start we can join a thread and
            # reply without ever having observed the inbound message, and a
            # reply we sent settles the question however we came to send it.
            if talk in _served:
                return "served", "we dispatched a reply"
            if talk not in _seen:
                return "unknown", "we never saw a message for this conversation"
            return "missed", "we saw the customer's message and never replied"
    except Exception as exc:
        logger.debug(f"[conv-ledger] verdict failed: {exc}")
        return "unknown", "ledger error"


def stats() -> Dict[str, int]:
    """For the run-end report and tests."""
    with _LOCK:
        return {"seen": len(_seen), "served": len(_served),
                "uid_mappings": len(_uid_to_talk),
                "unanswered": len([t for t in _seen if t not in _served])}


def reset() -> None:
    with _LOCK:
        _seen.clear()
        _served.clear()
        _uid_to_talk.clear()
