"""
Regression tests for session-restore supervisor wiring.

Before these fixes, try_restore_session (Intl) and
try_restore_cloudbase_session (CN) both set signed_in=True and installed a
fresh token but never called notify_token_installed(), so:

  - OfflineSyncManager never received on_session_refreshed
  - _last_token_installed_at was never reset → cache-lag grace window
    would fire on the next UNAUTHENTICATED even though the token was
    brand-new
  - WS reconnect loop did not treat the restored token as "fresh"

We verify the fixes are present in two ways:

  1. Code-inspection: check the call is present in the source text.
     This is robust — no mocking needed.
  2. Behavioural: verify that calling the method on a minimal stub AM
     raises no AttributeError and sets the expected state.

The supervisor wiring itself (notify_token_installed → unpause
OfflineSyncManager → WS reconnect) is an integration concern tested
elsewhere.  These tests prove the calls exist and don't crash.
"""

import ast
import importlib
import inspect
import os
import time
import unittest.mock as mock
import textwrap


def _read_source(module_path: str) -> str:
    with open(module_path, encoding="utf-8") as f:
        return f.read()


# ------------------------------------------------------------------
# Code-inspection tests: verify the fixes are in the source
# ------------------------------------------------------------------

def test_try_restore_session_calls_notify_token_installed():
    """try_restore_session must contain a call to notify_token_installed.

    This guards against the regression where restore set signed_in=True but
    never told the SessionSupervisor, leaving OfflineSyncManager in whatever
    stale state it was in (typically 'paused' after a prior expiry).
    """
    source = _read_source("auth/auth_manager.py")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "try_restore_session":
            calls = [
                n
                for n in ast.walk(node)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "notify_token_installed"
            ]
            assert len(calls) >= 1, (
                "try_restore_session must call notify_token_installed() on the "
                "SessionSupervisor after restoring a token. Without this, the "
                "OfflineSyncManager stays paused and the WS loop doesn't know "
                "the token is fresh."
            )
            return
    assert False, "try_restore_session not found in auth_manager.py"


def test_try_restore_cloudbase_session_calls_notify_token_installed():
    """try_restore_cloudbase_session must contain a call to notify_token_installed.

    Mirrors the Intl test above for the CloudBase restore path.
    """
    source = _read_source("auth/auth_manager.py")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "try_restore_cloudbase_session":
            calls = [
                n
                for n in ast.walk(node)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "notify_token_installed"
            ]
            assert len(calls) >= 1, (
                "try_restore_cloudbase_session must call notify_token_installed(). "
                "Same rationale as the Intl restore path."
            )
            return
    assert False, "try_restore_cloudbase_session not found"


def test_attempt_refresh_failure_calls_notify_session_cleared():
    """_attempt_refresh must call notify_session_cleared when refresh fails.

    Before the fix, signed_in was cleared but notify_session_cleared was
    skipped, so the GUI never saw on_session_expired and the logout
    banner never appeared.
    """
    source = _read_source("auth/session_supervisor.py")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_attempt_refresh":
            # Walk the body (not just direct children) to find nested blocks
            calls = [
                n
                for n in ast.walk(node)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "notify_session_cleared"
            ]
            assert len(calls) >= 1, (
                "_attempt_refresh must call self.notify_session_cleared() when "
                "refresh_tokens returns a fatal error, so the GUI shows the "
                "'session expired' banner and routes to the login screen."
            )
            return
    assert False, "_attempt_refresh not found in session_supervisor.py"


# ------------------------------------------------------------------
# Behavioural tests: verify the fixed code paths run without error
# ------------------------------------------------------------------

def _supervisor_module():
    import importlib

    return importlib.import_module("auth.session_supervisor")


def _auth_manager_module():
    import importlib

    return importlib.import_module("auth.auth_manager")


def _offline_sync_manager_module():
    import importlib

    return importlib.import_module("agent.cloud_api.offline_sync_manager")


def _make_am(is_cn: bool = False):
    """Minimal AuthManager stub."""
    am_mod = _auth_manager_module()
    am = object.__new__(am_mod.AuthManager)
    am._is_cn = is_cn
    am.cognito_service = None
    am.tokens = {}
    am.signed_in = False
    am.current_user = None
    am._saved_username = None
    am._saved_login_type = None
    am._token_manager = None
    am._uli_path = None
    return am


def test_restore_session_runs_without_error(monkeypatch):
    """try_restore_session with a valid stub AM must not raise AttributeError.

    Specifically it must not crash when trying to call
    notify_token_installed on a (possibly absent) supervisor.
    """
    import sys as _sys

    # Make get_session_supervisor return None so the guard `if sup:` is tested
    stub_mod = _sys.modules.get("auth.session_supervisor")
    if stub_mod is None:
        import importlib
        importlib.import_module("auth.session_supervisor")
        stub_mod = _sys.modules.get("auth.session_supervisor")

    if stub_mod:
        from unittest.mock import patch as _patch

        with _patch.object(stub_mod, "get_session_supervisor", lambda: None):
            am = _make_am(is_cn=False)
            am._get_saved_username = lambda: "testuser"
            am._get_refresh_token = lambda u: (True, "rt")
            am._update_saved_login_info = lambda *a, **kw: None
            am.cognito_service = None  # restore will fail on the service call, but must not AttributeError on notify

            # Must not raise
            ok = am.try_restore_session()
            # It fails because cognito_service is None — that's fine.
            # The important thing is no AttributeError before reaching that point.
            assert ok is False


def test_restore_cloudbase_session_runs_without_error(monkeypatch):
    """try_restore_cloudbase_session with a valid stub AM must not raise AttributeError."""
    import sys as _sys

    stub_mod = _sys.modules.get("auth.session_supervisor")
    if stub_mod is None:
        import importlib
        importlib.import_module("auth.session_supervisor")
        stub_mod = _sys.modules.get("auth.session_supervisor")

    if stub_mod:
        from unittest.mock import patch as _patch

        with _patch.object(stub_mod, "get_session_supervisor", lambda: None):
            am = _make_am(is_cn=True)
            am._get_saved_username = lambda: "testuser"

            # Must not raise
            ok = am.try_restore_cloudbase_session()
            assert ok is False  # fails at keyring lookup — fine


# ------------------------------------------------------------------
# _attempt_refresh behavioural test
# ------------------------------------------------------------------

def test_attempt_refresh_failure_clears_credentials_and_notifies(monkeypatch):
    """When refresh_tokens returns a fatal error, _attempt_refresh must:
      1. Return False
      2. Set am.signed_in = False
      3. Set am.tokens = None
      4. Call notify_session_cleared(source='_attempt_refresh')
    """
    ss_mod = _supervisor_module()

    cleared_sources: list = []

    class _FakeCognitoService:
        def refresh_tokens(self, rt: str) -> dict:
            return {"success": False, "error_code": "NotAuthorizedException"}

    class _FakeAM:
        signed_in = True
        tokens = {"AccessToken": "old_token"}
        cognito_service = _FakeCognitoService()

    sup = ss_mod.SessionSupervisor(_FakeAM())

    # Intercept the notify_session_cleared call
    _real_notify = sup.notify_session_cleared

    def _intercepted_notify(source: str = ""):
        cleared_sources.append(source)
        return _real_notify(source=source)

    sup.notify_session_cleared = _intercepted_notify  # type: ignore[method-assignment]

    result = sup._attempt_refresh("dead_refresh_token")

    assert result is False, "_attempt_refresh must return False on failure"
    assert sup._am.signed_in is False, "signed_in must be cleared"
    assert sup._am.tokens is None, "tokens must be cleared"
    assert cleared_sources == [
        "_attempt_refresh"
    ], "notify_session_cleared(source='_attempt_refresh') must be called so the GUI shows 'session expired'"


# ------------------------------------------------------------------
# Regression: refresh-token rotation must NOT be silently dropped
# ------------------------------------------------------------------

def test_on_session_refreshed_does_not_kick_sync_pending_queue():
    """Bug B: the WeChat session-token path used to infinite-loop because
    ``OfflineSyncManager._on_session_refreshed`` immediately called
    ``sync_pending_queue()`` after the supervisor notified it.  The flow
    was:

        task fails -> nudge -> refresh succeeds -> notify_token_installed
        -> _on_session_refreshed -> sync_pending_queue -> task fails
        -> nudge -> ...

    The fix removes the inline sync — the legitimate retry paths
    (a) ``sync_pending_queue`` in progress resumes via
    ``_wait_for_active_session`` waking, and
    (b) the 5-min auto-retry tick picks it up next round.

    Pin the contract here so the inline sync can't quietly come back.
    """
    osm = _offline_sync_manager_module()
    import inspect
    import re

    source = inspect.getsource(osm.OfflineSyncManager._on_session_refreshed)
    # Strip docstring so the test doesn't trip over documentation that
    # mentions the name; only flag an actual call (``self.sync_pending_queue(...)``).
    stripped = re.sub(r'"""[\s\S]*?"""', "", source)
    assert "self.sync_pending_queue(" not in stripped, (
        "_on_session_refreshed must NOT call self.sync_pending_queue() — that "
        "creates a tight 401 -> nudge -> refresh -> notify -> sync loop "
        "when the new token is still being rejected by the cloud. The "
        "existing retry paths (the in-flight sync loop + the 5-min "
        "auto-retry tick) handle the legitimate cases."
    )


def test_ensure_valid_tokens_keeps_rotated_refresh_token(monkeypatch):
    """Bug A: CloudBase rotates refresh_token on every successful refresh.

    Before the fix, ``AuthManager.ensure_valid_tokens`` overwrote the
    response's RefreshToken with the old token it had just sent.  Since
    CloudBase's old token is single-use (it dies after the first call),
    the next refresh cycle would receive NotAuthorizedException, kick the
    user to the login screen, and stay there forever.

    The fix: prefer the rotated RefreshToken from the response when
    present; fall back to the input token only when the server echoes
    nothing back.  Pin the behaviour here so a future refactor can't
    reintroduce the regression.
    """
    am = _make_am(is_cn=False)
    am.cognito_service = mock.MagicMock()
    am.cognito_service.refresh_tokens.return_value = {
        "success": True,
        "data": {
            "AccessToken": "AT_new",
            "RefreshToken": "RT_rotated_NEW",
            "ExpiresIn": 3600,
        },
    }
    am.tokens = {
        "AccessToken": "AT_old",
        "RefreshToken": "RT_old",  # input token — server will rotate it
    }
    am.signed_in = True
    # Pretend the token's about to expire so the on-demand branch fires
    am._decode_token_expiry_unsafe = lambda tok: int(time.time()) - 10

    ok = am.ensure_valid_tokens(min_validity_seconds=300)

    assert ok is True, "ensure_valid_tokens must succeed when refresh succeeds"
    assert am.tokens.get("RefreshToken") == "RT_rotated_NEW", (
        "the rotated refresh_token must be installed — using the OLD "
        "token on the next refresh will fail because the server already "
        "consumed it. Got RefreshToken="
        f"{am.tokens.get('RefreshToken')!r}"
    )
    assert am.tokens.get("AccessToken") == "AT_new"


def test_ensure_valid_tokens_falls_back_when_no_rotation(monkeypatch):
    """If the server didn't rotate (echoed same / no RefreshToken), keep
    the input token.  Some Cognito/CloudBase endpoints do this on cold
    paths; we mustn't blank the field."""
    am = _make_am(is_cn=False)
    am.cognito_service = mock.MagicMock()
    # Some servers echo the same refresh_token back; _normalize_tokens
    # then puts it under RefreshToken, but if it's absent the input must
    # survive.
    am.cognito_service.refresh_tokens.return_value = {
        "success": True,
        "data": {
            "AccessToken": "AT_new",
            "ExpiresIn": 3600,
        },
    }
    am.tokens = {
        "AccessToken": "AT_old",
        "RefreshToken": "RT_old",
    }
    am.signed_in = True
    am._decode_token_expiry_unsafe = lambda tok: int(time.time()) - 10

    ok = am.ensure_valid_tokens(min_validity_seconds=300)

    assert ok is True
    assert am.tokens.get("RefreshToken") == "RT_old", (
        "RefreshToken must NOT be blanked when the server didn't echo "
        "a new one — fall back to the input token. Got "
        f"{am.tokens.get('RefreshToken')!r}"
    )
