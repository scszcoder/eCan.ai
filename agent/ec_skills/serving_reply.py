"""Where a serving turn's answer is collected, so the turn can report it.

A chat skill answers by calling ``send_chat``. That tool already routes between
lanes — agent-to-agent, and the off-DOM live-chat lanes Feige uses — and picks
one from the run context. A serving turn is another lane, and it was missing:
a web visitor has no agent id, so the A2A precondition
("Either recipient_agent_id or recipient_agent_name is required") rejected the
call before any lane was chosen, and the answer never left the graph.

The destination for this lane is the turn itself: ``turn_done`` carries a
``result``, and that is what the widget renders. But ``send_chat`` runs in the
middle of the graph while the result is reported after the run returns, so the
answer needs somewhere to wait. This is that place.

Scoped to the turn, for the same reason as ``usage_window``: a pod runs several
turns at once (``cn_serve.Capacity``), and a process-wide slot would let one
turn answer another's visitor — which is worse than not answering at all. A
``ContextVar`` survives the boundaries a turn actually crosses: an
``asyncio.Task`` copies the context at creation, and ``asyncio.to_thread``
copies it too, which is how the execution core reaches back into its own turn.

**Known gap**, the same one usage_window has: a raw thread started deep inside a
skill does not inherit the context, so a reply sent from there is not collected.
That direction loses a reply rather than misrouting one — the safe way round,
and ``cn_serve`` still falls back to reading the run's final state.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, List, Optional


class ReplyWindow:
    """The replies a single turn produced, oldest first."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._replies: List[str] = []

    def add(self, text: str) -> None:
        if not isinstance(text, str) or not text.strip():
            return
        with self._lock:
            self._replies.append(text.strip())

    @property
    def replies(self) -> List[str]:
        with self._lock:
            return list(self._replies)

    @property
    def text(self) -> str:
        """The turn's answer.

        Joined rather than last-wins: a skill that sends two messages in one
        turn meant the visitor to see both, and silently dropping the first
        would be a reply the customer never gets.
        """
        with self._lock:
            return "\n\n".join(self._replies)


_current: ContextVar[Optional[ReplyWindow]] = ContextVar("ecan_serving_reply", default=None)


@contextmanager
def turn_replies() -> Iterator[ReplyWindow]:
    """Collect replies sent inside this block, isolated from other turns."""
    window = ReplyWindow()
    token = _current.set(window)
    try:
        yield window
    finally:
        _current.reset(token)


def serving_turn_active() -> bool:
    """True when a reply has somewhere to go other than another agent.

    ``send_chat`` asks this before enforcing the A2A recipient requirement: on a
    serving turn the destination is the turn, so a missing recipient is not an
    error.
    """
    return _current.get() is not None


def record_reply(text: str) -> bool:
    """Collect one reply for the current turn. Never raises.

    Returns True when it was collected, so the caller can tell "delivered to the
    turn" from "there was no turn to deliver to" rather than guessing.
    """
    try:
        window = _current.get()
        if window is None:
            return False
        window.add(text)
        return True
    except Exception:
        return False


def current_text() -> str:
    """The current turn's answer so far, or "" outside a turn."""
    try:
        window = _current.get()
        return window.text if window is not None else ""
    except Exception:
        return ""
