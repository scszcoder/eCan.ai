"""One reply per buyer turn, for every live-chat site.

A buyer's message can reach the Q&A agents more than once: a front desk that
was down replays its queue and the next message supersedes the one in flight
(拼多多, KEN 2026-10-27: 3 messages -> 3 Q&A tasks -> 3 replies), or one message
is picked up by two detectors under two ids (千牛 memory scan + backstop, 10-25:
one question answered 4 times). Each extra reply was also billed.

Dispatch records which turns were folded into a newer one; delivery asks
``skip_reason`` before sending and calls ``note_delivered`` after. Site-agnostic:
only (buyer, message id, message text) is known here.
"""
from __future__ import annotations

import threading
import time

# A superseded turn's reply is dropped this long after the newer turn took it over.
SUPERSEDED_TTL_S = 600.0
# The same question text answered for the same buyer this recently = the same turn.
SAME_TEXT_WINDOW_S = 120.0

_lock = threading.Lock()
_superseded: dict[tuple[str, str], float] = {}            # (buyer, msg id or text) -> when
_answered: dict[str, list[tuple[str, str, float]]] = {}   # buyer -> [(msg id, text, when)]


def _norm(text: str) -> str:
    return "".join(str(text or "").split())


def _buyers(buyers) -> list[str]:
    return [b for b in {str(b or "").strip() for b in buyers} if b]


def mark_superseded(buyer: str, msg_id: str, text: str = "") -> None:
    """A newer dispatch for ``buyer`` carries this turn's text too."""
    # Keyed by text only when there is no id: a later turn with the same words is new.
    k = str(msg_id or "") or _norm(text)
    if not k:
        return
    now = time.time()
    with _lock:
        _superseded[(str(buyer), k)] = now
        for key in [k for k, t in _superseded.items() if now - t > SUPERSEDED_TTL_S]:
            _superseded.pop(key, None)


def skip_reason(buyers, msg_id: str, text: str = "") -> str:
    """'' = send it; else why this reply must not go out."""
    now, norm = time.time(), _norm(text)
    with _lock:
        for b in _buyers(buyers):
            t = _superseded.get((b, str(msg_id or "") or norm))
            if t and now - t <= SUPERSEDED_TTL_S:
                return "superseded_by_newer_turn"
            for a_id, a_text, t in _answered.get(b, []):
                if msg_id and a_id == msg_id:
                    return "turn_already_answered"
                if norm and a_text == norm and now - t <= SAME_TEXT_WINDOW_S:
                    return "turn_already_answered"
    return ""


def was_answered(buyer: str, msg_id: str) -> bool:
    if not msg_id:
        return False
    with _lock:
        return any(a_id == msg_id for a_id, _, _ in _answered.get(str(buyer), []))


def note_delivered(buyers, msg_id: str, text: str = "") -> None:
    now = time.time()
    with _lock:
        for b in _buyers(buyers):
            lst = [x for x in _answered.get(b, []) if now - x[2] <= SUPERSEDED_TTL_S]
            lst.append((str(msg_id or ""), _norm(text), now))
            _answered[b] = lst[-20:]


def reset() -> None:
    with _lock:
        _superseded.clear()
        _answered.clear()
