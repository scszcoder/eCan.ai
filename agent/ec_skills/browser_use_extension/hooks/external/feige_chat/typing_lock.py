"""Feige active-session race guard — per-session typing lock.

Phase 3 relocation (2026-04-23).  The state + the three helper
functions below previously lived as module-level globals in
``agent/ec_skills/build_node.py``.  They are now owned by the
``feige_chat`` hook bundle so that:

* the deterministic HOT-PATH-B orchestration in ``build_node`` can
  import them directly (pre-agent, no dispatcher available), and
* Tier-0 / external Feige hooks running inside the PrivacyAgent loop
  can share the *same* lock state via this module (no dispatcher
  state-store bridge required — the state is a true process-level
  singleton because all lanes run in-process).

See the long design note in ``build_node`` (above its legacy import
of these helpers) for the full race-condition repro.

Design notes
------------

* **State is a per-session dict** (SHARED_SKILL_MULTI_TASK_PLAN
  Phase 5, 2026-08-23 — the ``{session_id: holder}`` migration the
  original single-holder design note anticipated).  A "session" is one
  Feige browser session / one shop login.  Every public function takes
  an optional ``session_key``; callers that don't pass one use the
  DEFAULT session (""), which reproduces the historical single-shop
  behaviour exactly — one lock-holder per process.  Multi-session
  fan-out passes an explicit key per shop so shop A's typing never
  blocks shop B's.

* **TTL self-heals.** If HOT-PATH-B crashes between
  ``try_acquire`` and ``release``, the next ``try_acquire`` after
  ``FEIGE_TYPING_LOCK_TTL_S`` seconds reclaims that session's lock.

* **Empty customer_key bypasses.** Callers without a concrete
  customer target (e.g. ``browser_event``-only flows) get
  ``try_acquire → True`` and ``release → no-op``.

* **No asyncio primitives.** We use a plain ``threading.Lock``
  because the callers live on different event loops (one per
  per-customer scope's persistent loop) but share the same process.
"""

from __future__ import annotations

import threading
import time

__all__ = [
    "FEIGE_TYPING_LOCK_TTL_S",
    "DEFAULT_SESSION",
    "try_acquire",
    "release",
    "holder",
    "reset",
]

# Max time HOT-PATH-B/direct delivery needs from typing-lock acquisition
# through the final ``feige_send_message``.  This must exceed
# runner._DIRECT_LIVE_CHAT_JOB_TIMEOUT_S (35s by default), otherwise another
# guarded send can reclaim the lock while the previous send is still
# unwinding from a timeout.
FEIGE_TYPING_LOCK_TTL_S: float = 50.0

# The implicit session used by all legacy (single-shop) callers.
DEFAULT_SESSION: str = ""

# session_key -> (holder customer_key, acquired_at timestamp)
_holders: dict[str, tuple[str, float]] = {}
_mu = threading.Lock()


def try_acquire(customer_key: str, session_key: str = DEFAULT_SESSION) -> bool:
    """Claim *session_key*'s Feige active-session for *customer_key*.

    Returns ``True`` if the lock was acquired (or the caller already
    holds it — re-entrant on the same key).  Returns ``False`` if
    another customer holds a fresh (non-stale) lock on the SAME
    session.  Expired locks are reclaimed automatically.  Locks on
    different sessions never interact.
    """
    if not customer_key:
        return True  # un-keyed callers bypass the guard
    with _mu:
        now = time.time()
        cur, ts = _holders.get(session_key, ("", 0.0))
        cur_age = (now - ts) if cur else 0.0
        if cur and cur != customer_key and cur_age < FEIGE_TYPING_LOCK_TTL_S:
            return False
        # reclaim stale or unset
        _holders[session_key] = (customer_key, now)
        return True


def release(customer_key: str, session_key: str = DEFAULT_SESSION) -> None:
    """Release *session_key*'s typing lock if held by *customer_key*."""
    if not customer_key:
        return
    with _mu:
        cur, _ts = _holders.get(session_key, ("", 0.0))
        if cur == customer_key:
            _holders.pop(session_key, None)


def holder(session_key: str = DEFAULT_SESSION) -> str:
    """Return *session_key*'s current holder ("" if none or expired)."""
    with _mu:
        cur, ts = _holders.get(session_key, ("", 0.0))
        if not cur:
            return ""
        if time.time() - ts > FEIGE_TYPING_LOCK_TTL_S:
            return ""  # stale — will be reclaimed on next try_acquire
        return cur


def reset(session_key: str | None = None) -> None:
    """Clear the lock for *session_key*, or ALL sessions when None.
    Intended for tests only."""
    with _mu:
        if session_key is None:
            _holders.clear()
        else:
            _holders.pop(session_key, None)
