"""
Pins the contract that the CloudBase IPC login path notifies the
SessionSupervisor of a freshly installed token.

Background: SessionSupervisor._last_token_installed_at starts at 0.
The fresh-token grace window in _drive_silent_refresh uses that timestamp
to suppress the CloudBase cache-lag 401 (returned ~30-60s after login)
from logging the user out. Without an explicit notify_token_installed
call somewhere in the login chain, the grace window never triggers.

LoginoutGUI._run() already notifies (line 349). This test pins that
the IPC handler cloudbase_handler._build_login_response also notifies
(equivalent path for IPC-driven logins).

We do NOT exercise the full _build_login_response because it depends
on a live Qt event loop, AppContext and settings_manager. Instead we
read the source and assert the call is present between the
complete_login_from_provider step and the AppContext endpoint storage
step, in the right block.
"""

import re
from pathlib import Path


_HANDLER = Path(
    "gui/ipc/w2p_handlers/cloudbase_handler.py"
)


def _read_handler() -> str:
    return _HANDLER.read_text(encoding="utf-8")


def test_build_login_response_calls_notify_token_installed():
    """cloudbase_handler._build_login_response must notify the supervisor.

    Without this, SessionSupervisor._last_token_installed_at stays at
    its constructor default of 0 and the fresh-token grace guard in
    _drive_silent_refresh never fires — see runlog 2026-08-14 10:32:50
    where a 401 returned 43s after login caused an unconditional logout.
    """
    src = _read_handler()

    # The function must exist.
    assert "def _build_login_response(" in src, (
        "_build_login_response must exist on cloudbase_handler"
    )

    # Inside _build_login_response the supervisor must be notified.
    # Pull the function body by matching from ``def _build_login_response``
    # to the next top-level ``def `` or the end of file.
    match = re.search(
        r"def _build_login_response\(.*?(?=\ndef |\Z)",
        src,
        re.DOTALL,
    )
    assert match, "_build_login_response body must be locatable"
    body = match.group(0)

    assert "notify_token_installed" in body, (
        "_build_login_response must call notify_token_installed on the "
        "SessionSupervisor so the fresh-token grace guard in "
        "_drive_silent_refresh can suppress CloudBase cache-lag 401s"
    )
    assert "session_supervisor" in body, (
        "_build_login_response must reference session_supervisor "
        "(the attribute installed on LoginoutGUI by "
        "install_session_supervisor)"
    )