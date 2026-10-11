"""Call the running eCan app from the CLI.

Same handlers the GUI calls (gui/ipc/w2p_handlers/*), over the app's local
server: ``POST /graphql`` with ``extensions.method``.  The app publishes its
port and a per-start key in a file only this OS user can read
(utils/local_api.py).  Method names and params are the contract; anything
inside the app (e.g. the copilot) calls the same handlers in-process.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class AppNotRunning(Exception):
    """No running app to talk to (or it isn't answering)."""


class AppCallError(Exception):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code = code
        self.details = details


def find_app() -> Optional[Dict[str, Any]]:
    from utils.local_api import find_running
    return find_running()


def is_running() -> bool:
    return find_app() is not None


def call(method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 30.0) -> Any:
    """The handler's result, or AppCallError / AppNotRunning."""
    import requests
    info = find_app()
    if not info:
        raise AppNotRunning("eCan is not running")
    try:
        resp = requests.post(
            f"http://127.0.0.1:{int(info['port'])}/graphql",
            json={"query": "", "variables": params or {}, "extensions": {"method": method}},
            headers={"Authorization": f"Bearer {info['secret']}"},
            timeout=timeout,
        )
        body = resp.json()
    except requests.exceptions.ConnectionError as e:
        raise AppNotRunning(f"eCan is not answering on port {info['port']}") from e
    except ValueError as e:
        raise AppCallError("BAD_RESPONSE", f"unexpected reply from eCan (HTTP {resp.status_code})") from e
    if body.get("errors"):
        err = body["errors"][0] or {}
        ext = err.get("extensions") or {}
        raise AppCallError(str(ext.get("code") or "ERROR"), str(err.get("message") or "error"), ext.get("details"))
    return (body.get("data") or {}).get(method)


def same_user(cli_username: Optional[str]) -> bool:
    """The running app is signed in as the CLI's user (so it uses the same
    database). False when the app is not running or can't tell."""
    if not cli_username:
        return False
    try:
        status = call("get_cli_session", timeout=5.0) or {}
    except (AppNotRunning, AppCallError):
        return False
    return str(status.get("username") or "").lower() == str(cli_username).lower()


def edits_via_app(cli_username: Optional[str]) -> bool:
    """CLI edits go through the running app when it is signed in as this CLI
    user (same database): the app saves, updates what is running, and syncs to
    the cloud.  Otherwise the CLI writes the database itself and the app picks
    the change up when it starts.  ECAN_CLI_DIRECT_DB=1 forces the direct path."""
    import os
    return os.environ.get("ECAN_CLI_DIRECT_DB") != "1" and same_user(cli_username)


def call_or_exit(out, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 30.0) -> Any:
    """For commands that only make sense against the running app."""
    try:
        return call(method, params, timeout=timeout)
    except AppNotRunning as e:
        out.error(f"{e}. Start eCan first; this command works on the running app.")
    except AppCallError as e:
        out.error(f"{e} ({e.code})")
    raise SystemExit(1)
