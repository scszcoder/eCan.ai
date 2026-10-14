"""Let the ``ecan`` CLI (and other local tools) call the running app.

The app's local server already routes every GUI request (``/graphql``,
``extensions.method``) to the shared IPC handlers.  Those normally need a
token the app hands its own GUI at login; local tools get a separate key:

* the app, once its server is up, writes ``{pid, port, secret}`` to
  ``<app data>/local_api/<instance>.json`` (only this OS user can read the
  app data folder; the file is also made owner-only where chmod works);
* the server accepts that secret as a token (``is_local_secret``);
* ``find_running`` reads the file back for a client and drops it if that
  process is gone.

The secret changes on every start and the file is removed on a clean stop.
Anyone who can read it can already read the user's database.

Kill switch: ``ECAN_LOCAL_API=0`` (no file, secret never accepted).
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import time
from typing import Any, Dict, Optional

_secret: Optional[str] = None


def enabled() -> bool:
    return os.environ.get("ECAN_LOCAL_API", "1") != "0"


def _folder() -> str:
    from config.app_info import app_info
    return os.path.join(app_info.appdata_path, "local_api")


def discovery_path(instance: Optional[str] = None) -> str:
    if instance is None:
        from config.instance import instance_id
        instance = instance_id()
    return os.path.join(_folder(), f"{instance or 'default'}.json")


def publish(port: int) -> Optional[str]:
    """Called by the app once its local server is listening."""
    global _secret
    if not enabled():
        return None
    _secret = secrets.token_urlsafe(32)
    path = discovery_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "port": int(port), "secret": _secret, "started_at": time.time()}, f)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)
    return _secret


def withdraw() -> None:
    """Remove our file on a clean stop (only if it is still ours)."""
    global _secret
    _secret = None
    path = discovery_path()
    try:
        with open(path, encoding="utf-8") as f:
            ours = json.load(f).get("pid") == os.getpid()
        if ours:
            os.remove(path)
    except (OSError, ValueError):
        pass


def is_local_secret(token: Any) -> bool:
    return bool(_secret and isinstance(token, str) and enabled()
                and hmac.compare_digest(token.encode(), _secret.encode()))


def _alive(pid: int) -> bool:
    try:
        import psutil
        return psutil.pid_exists(int(pid))
    except Exception:
        return True   # can't tell: let the HTTP call decide


def find_running(instance: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """``{pid, port, secret, started_at}`` of the running app, or None."""
    path = discovery_path(instance)
    try:
        with open(path, encoding="utf-8") as f:
            info = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(info, dict) or not info.get("port") or not info.get("secret"):
        return None
    if not _alive(info.get("pid", 0)):
        return None
    return info
