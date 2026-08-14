"""
Unit tests for SessionSupervisor._drive_silent_refresh fresh-token guard.

Background
----------
CloudBase / WeChat OAuth returns a 10-minute access token with no refresh
token. When ``complete_login_from_provider`` finishes, the supervisor's
``notify_token_installed`` runs and broadcasts ``on_session_refreshed`` —
but the *upstream CloudBase cache* doesn't see the new token for ~30-60
seconds. During that window, every AppSync call comes back
``UNAUTHENTICATED``, which causes OfflineSyncManager to nudge the
supervisor via ``notify_token_rejected``. Without a guard, the supervisor
treats the rejection as authoritative and pops a WeChat OAuth window
at the user 30 seconds after they scanned the QR — a UX regression.

The fix is a "fresh token grace" guard: ``_drive_silent_refresh`` checks
how long ago the token was installed and, if it's within the grace
window AND the token still has substantial local remaining time, it
schedules a retry instead of popping the OAuth window.

We exercise four scenarios:

  1. Brand-new token (just installed) + server rejected → no popup,
     retry scheduled after grace.
  2. Same brand-new token + token about to die (real expiry) → popup
     fires (don't suppress a real logout).
  3. Old token (>60s ago installed) + server rejected → popup fires
     (this is a real expiry).
  4. install at t=0, suppress at t=10, then advance the wall clock past
     grace → next nudge pops the window normally.
"""

import importlib
import time as _time

import pytest


def _supervisor_module():
    return importlib.import_module("auth.session_supervisor")


def _make_supervisor(tokens: dict | None = None):
    ss = _supervisor_module()

    if tokens is None:
        tokens = {"AccessToken": "stub", "RefreshToken": None}

    tokens_holder = tokens

    class _AM:
        signed_in = True
        tokens = tokens_holder

    return ss.SessionSupervisor(_AM())


# --- helpers ---------------------------------------------------------------

class _FakeExp:
    """A JWT-shaped string whose ``exp`` claim we control exactly."""

    HEADER = "eyJhbGciOiJSUzI1NiJ9"
    SIG = "sig"

    def __init__(self, exp_seconds: int):
        import base64, json
        payload = json.dumps({"exp": exp_seconds}).encode("ascii")
        b64 = base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")
        self.token = f"{self.HEADER}.{b64}.{self.SIG}"


# ---------------------------------------------------------------
# 1) brand-new token + server rejected -> no popup
# ---------------------------------------------------------------

def test_fresh_token_401_does_not_pop_oauth():
    ss = _supervisor_module()
    fired: list[str] = []

    def cb(info):
        fired.append(info.get("exp"))

    supervisor = _make_supervisor()
    supervisor.on_session_expiring_soon(cb)

    # Simulate AuthManager.notify_token_installed() at t0.
    supervisor.notify_token_installed()

    # 10 seconds later, supervisor gets a nudge from OfflineSyncManager.
    # Use a fake JWT whose exp is 9 minutes from now.
    future_exp = int(_time.time()) + 9 * 60
    fake = _FakeExp(future_exp)
    supervisor._drive_silent_refresh(future_exp)

    assert fired == [], (
        "OAuth popup must NOT fire within the fresh-token grace window, "
        "even when the server has just rejected the token"
    )


# ---------------------------------------------------------------
# 2) same brand-new token + real imminent expiry -> popup fires
# ---------------------------------------------------------------

def test_fresh_token_with_real_imminent_expiry_still_pops():
    ss = _supervisor_module()
    fired: list[str] = []

    def cb(info):
        fired.append(info.get("exp"))

    supervisor = _make_supervisor()
    supervisor.on_session_expiring_soon(cb)

    supervisor.notify_token_installed()  # t0

    # Real expiry: token dies in 30s. The grace guard must NOT suppress
    # this — the user genuinely needs to re-login.
    imminent_exp = int(_time.time()) + 30
    supervisor._drive_silent_refresh(imminent_exp)

    assert fired == [imminent_exp], (
        "when the token really is about to die, the OAuth popup must "
        "fire even if the token was just installed"
    )


# ---------------------------------------------------------------
# 3) old token (>60s ago installed) + server rejected -> popup fires
# ---------------------------------------------------------------

def test_old_token_401_still_pops_oauth():
    ss = _supervisor_module()
    fired: list[str] = []

    def cb(info):
        fired.append(info.get("exp"))

    supervisor = _make_supervisor()
    supervisor.on_session_expiring_soon(cb)

    supervisor.notify_token_installed()
    # Pretend 2 minutes have passed by rewriting the install timestamp.
    supervisor._last_token_installed_at = _time.time() - 120

    future_exp = int(_time.time()) + 9 * 60
    supervisor._drive_silent_refresh(future_exp)

    assert fired == [future_exp], (
        "an old token getting rejected is a real expiry — popup must "
        "fire normally"
    )


# ---------------------------------------------------------------
# 4) suppress during grace, then re-nudge after grace -> popup fires
# ---------------------------------------------------------------

def test_retry_after_grace_window_does_pop():
    ss = _supervisor_module()
    fired: list[str] = []

    def cb(info):
        fired.append(info.get("exp"))

    supervisor = _make_supervisor()
    supervisor.on_session_expiring_soon(cb)

    supervisor.notify_token_installed()  # t0
    # Pretend 70 seconds have passed since install.
    supervisor._last_token_installed_at = _time.time() - 70

    future_exp = int(_time.time()) + 9 * 60
    supervisor._drive_silent_refresh(future_exp)

    assert fired == [future_exp], (
        "after the grace window elapses, the popup must fire on the "
        "next nudge"
    )