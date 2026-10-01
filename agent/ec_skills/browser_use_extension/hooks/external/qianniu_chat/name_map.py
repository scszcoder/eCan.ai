"""千牛 ``sender_id ↔ display_name`` map (learned, persistent).

Detection reads a buyer **sender id** from memory; opening a conversation needs
the buyer's **display name** (the sidebar/search key). The two cannot be joined
from memory alone (v15: the active conversation id is not co-located with a
draft), so this map is learned by **content join**: when a message with a known
sender id and text is also visible on screen, the chat-header name beside that
text is that sender's display name. See ``observer._learn_pass``.

Persisted as JSON under the app data dir so the map survives restarts; a
per-process in-memory cache fronts it.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Dict, Optional

from utils.logger_helper import logger_helper as logger

_LOCK = threading.Lock()
_CACHE: Optional[Dict[str, str]] = None   # sender_id -> display_name


def _store_path() -> str:
    base = ""
    try:
        from config.app_info import app_info
        base = getattr(app_info, "appdata_path", "") or ""
    except Exception:
        base = ""
    if not base:
        import tempfile
        base = tempfile.gettempdir()
    d = os.path.join(base, "qianniu")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return os.path.join(d, "name_map.json")


def _load() -> Dict[str, str]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    data: Dict[str, str] = {}
    try:
        with open(_store_path(), "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        if isinstance(raw, dict):
            data = {str(k): str(v) for k, v in raw.items() if k and v}
    except Exception:
        data = {}
    _CACHE = data
    return _CACHE


def _save(data: Dict[str, str]) -> None:
    try:
        tmp = _store_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=0)
        os.replace(tmp, _store_path())
    except Exception as exc:
        logger.debug(f"[qianniu] name_map save failed: {exc}")


def name_for(sender_id: str) -> str:
    """Learned display name for a sender id, or ""."""
    return _load().get(str(sender_id or ""), "")


def id_for(display_name: str) -> str:
    """First sender id mapped to *display_name*, or ""."""
    dn = (display_name or "").strip()
    for sid, name in _load().items():
        if name == dn:
            return sid
    return ""


def learn(sender_id: str, display_name: str) -> bool:
    """Record ``sender_id -> display_name``. Returns True if it added/changed
    an entry. No-op on blanks."""
    sid, dn = str(sender_id or "").strip(), (display_name or "").strip()
    if not sid or not dn:
        return False
    with _LOCK:
        data = _load()
        if data.get(sid) == dn:
            return False
        data[sid] = dn
        _save(data)
    logger.info(f"[qianniu] learned sender {sid!r} -> display name {dn!r}")
    return True


def known_ids() -> set:
    return set(_load().keys())
