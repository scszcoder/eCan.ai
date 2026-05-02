"""Feige active-session race guard — process-wide typing lock.

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

* **State is module-level.** A single process owns one Feige browser
  session — so one lock-holder per process is correct.  If we ever
  introduce multi-session fan-out we migrate to a
  ``{session_id: holder}`` dict here in one place.

* **TTL self-heals.** If HOT-PATH-B crashes between
  ``try_acquire`` and ``release``, the next ``try_acquire`` after
  ``_FEIGE_TYPING_LOCK_TTL_S`` seconds reclaims the lock.

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
    "try_acquire",
    "release",
    "holder",
    "reset",
]

# Max time HOT-PATH-B/direct delivery needs from ``feige_open_session``
# through the final ``feige_send_message``.  This must exceed
# runner._DIRECT_FEIGE_JOB_TIMEOUT_S (12s by default), otherwise another
# guarded send can reclaim the lock while the previous send is still
# unwinding from a timeout.
FEIGE_TYPING_LOCK_TTL_S: float = 35.0

_holder: str = ""
_ts: float = 0.0
_mu = threading.Lock()


def try_acquire(customer_key: str) -> bool:
    """Claim the Feige active-session for *customer_key*.

    Returns ``True`` if the lock was acquired (or the caller already
    holds it — re-entrant on the same key).  Returns ``False`` if
    another customer holds a fresh (non-stale) lock.  Expired locks
    are reclaimed automatically.
    """
    global _holder, _ts
    if not customer_key:
        return True  # un-keyed callers bypass the guard
    with _mu:
        now = time.time()
        cur = _holder
        cur_age = (now - _ts) if cur else 0.0
        if cur and cur != customer_key and cur_age < FEIGE_TYPING_LOCK_TTL_S:
            return False
        # reclaim stale or unset
        _holder = customer_key
        _ts = now
        return True


def release(customer_key: str) -> None:
    """Release the Feige typing lock if held by *customer_key*."""
    global _holder, _ts
    if not customer_key:
        return
    with _mu:
        if _holder == customer_key:
            _holder = ""
            _ts = 0.0


def holder() -> str:
    """Return the current holder (empty string if none or expired)."""
    with _mu:
        if not _holder:
            return ""
        if time.time() - _ts > FEIGE_TYPING_LOCK_TTL_S:
            return ""  # stale — will be reclaimed on next try_acquire
        return _holder


def reset() -> None:
    """Unconditionally clear the lock.  Intended for tests only."""
    global _holder, _ts
    with _mu:
        _holder = ""
        _ts = 0.0
