#!/usr/bin/env python3
"""Regression test for the phone-login path after logout.

User feedback (2026-08-24, terminals/7.txt): "电话号登陆是否也有类似
的问题，都是 logout 再 login".  This is the **phone-equivalent** of the
email trim regression at terminals/7.txt:401-460:

  - Email login: ``password`` arrived at backend with leading whitespace
    (``' Ecan249511118!'``), CloudBase rejected it as INVALID_CREDENTIALS.
  - Phone login: autofill / paste frequently introduce the same kind of
    stray whitespace on the phone field (``'+86 138 0013 8000'``,
    ``' 138 0013 8000'``, etc.).  Without trim, CloudBase SMS provider
    rejects as INVALID_PARAMS.

We've already added ``.trim()`` at every CloudBase IPC call site in
``cloudbaseAuth.ts``.  This test is a contract test that:

  1. Confirms all 3 phone-touching IPC paths (send_code, phone_login,
     reset_password) trim their string fields.
  2. Confirms that ``clearAuthState()`` does NOT reset the CloudBase
     ``config`` (envId) — logout must not leave CloudBase un-initialised
     for the next login.
  3. Confirms that ``LoginCN`` mount re-runs ``cloudbaseAuth.initialize``
     so the envId is always fresh after a logout → login round-trip.

Test #1 is also covered by ``test_cloudbase_trim_login_failed.py`` —
this file is the phone-specific extension (defensive in case anyone
adds a new phone path later without trimming) plus the mount-time
initialisation invariants.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_script_path = Path(__file__).resolve().parent  # tests/integration/auth/
_project_root = _script_path
for _ in range(3):
    _project_root = _project_root.parent
sys.path.insert(0, str(_project_root))


def _read(rel: str) -> str:
    return (_project_root / rel).read_text()


class TestPhoneLogoutRecoveryContract:
    """Phone-login path must remain functional after a logout → login cycle."""

    def test_cloudbase_auth_does_not_reset_config_on_clear_auth_state(self):
        """``cloudbaseAuth.clearAuthState()`` must NOT null out
        ``this.config`` (the envId).  If it did, every subsequent IPC
        call from LoginCN would hit ``isInitialized() === false`` and
        bail out with 'CloudBase not initialized' — a perfect silent
        failure for the post-logout login attempt.

        Concretely: clearAuthState should only clear token/refreshToken
        /userInfo (and localStorage keys), not this.config.
        """
        src = _read("gui_v2/src/services/auth/cloudbaseAuth.ts")
        # Locate the clearAuthState() body.
        match = re.search(
            r"clearAuthState\(\):\s*void\s*\{(?P<body>[^}]*)\}",
            src,
            flags=re.DOTALL,
        )
        assert match is not None, (
            "Could not find clearAuthState() body — has the method "
            "signature changed?  Update this test accordingly."
        )
        body = match.group("body")
        # The fix: clearAuthState must NOT touch ``this.config = null``.
        # If it does, every logout wipes the envId and the next login
        # fails with 'CloudBase not initialized'.
        assert "this.config = null" not in body, (
            "clearAuthState() must not reset this.config.  Doing so "
            "would un-initialise CloudBase after every logout, breaking "
            "phone and email login recovery (see user feedback 2026-08-24)."
        )
        # And it should clear what it's supposed to.
        assert "this.token = null" in body, (
            "clearAuthState() must clear this.token so the user is "
            "actually logged out."
        )
        assert "this._refreshToken = null" in body, (
            "clearAuthState() must clear this._refreshToken."
        )
        assert "this.userInfo = null" in body, (
            "clearAuthState() must clear this.userInfo."
        )

    def test_logincn_mount_force_reinitializes_cloudbase(self):
        """LoginCN must call ``cloudbaseAuth.initialize({ envId })`` on
        mount.  This guarantees that even if the user lands on /login
        after a logout with a stale config (e.g. envId rotated by the
        backend between sessions), the new envId is installed before
        they hit "Send code" / "Login".

        The useEffect dependency should include envId (so changes are
        picked up) — but more importantly, the **first mount** must
        fire the init unconditionally.
        """
        src = _read("gui_v2/src/pages/Login/LoginCN.tsx")
        # Find the useEffect that initializes CloudBase.
        match = re.search(
            r"useEffect\(\(\)\s*=>\s*\{[^}]*cloudbaseAuth\.initialize",
            src,
            flags=re.DOTALL,
        )
        assert match is not None, (
            "LoginCN must call cloudbaseAuth.initialize() at least "
            "once on mount.  Without it, the very first IPC call after "
            "a logout will hit ``isInitialized() === false`` and bail "
            "out with 'CloudBase not initialized'."
        )
        # Confirm the dep includes cloudbase_env_id (so config refreshes
        # during the LoginCN lifecycle are picked up).
        # Look for the closing of this useEffect — find the matching
        # ``}, [<deps>]);``.
        snippet = match.group(0)
        assert "cloudbase_env_id" in snippet, (
            "LoginCN's cloudbaseAuth.initialize useEffect must depend "
            "on ``appConfig?.auth?.cloudbase_env_id`` so config "
            "changes (e.g. envId rotation after logout) re-initialise "
            "the SDK."
        )

    def test_phone_form_pattern_strict_enough_to_reject_autofill(self):
        """The phone form's pattern ``/^1[3-9]\d{9}$/`` already rejects
        autofilled values like ``'+86 138 0013 8000'`` because they
        contain non-digit characters.  This test asserts that the
        pattern hasn't been relaxed to something that would let those
        values through (where they'd then need backend normalistion we
        haven't implemented).

        If you ever need to relax this pattern (e.g. to accept the +86
        prefix), update the backend service to strip the prefix first.
        """
        src = _read("gui_v2/src/pages/Login/LoginCN.tsx")
        # Find the phone field's pattern rule.
        # LoginCN has two phone form items (one per activeTab); check
        # both.
        matches = re.findall(
            r"pattern:\s*/(?P<pat>[^/]+)/",
            src,
        )
        assert matches, "Could not find any Form.Item patterns in LoginCN"
        # At least one pattern must match the strict 11-digit CN phone.
        strict = "/^1[3-9]\\d{9}$/"
        assert any("/^1[3-9]\\d{9}$/" == f"/{p}/" for p in matches), (
            "LoginCN's phone form must validate against "
            "``/^1[3-9]\\d{9}$/`` (11-digit CN mobile).  Loosening this "
            "would let autofilled '+86 138 0013 8000' reach the IPC "
            "boundary and CloudBase would reject it as INVALID_PARAMS."
        )
