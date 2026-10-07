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
import re
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


# UI text that the header-band OCR can mistake for a buyer name. Alpha
# 2026-10-07: the 接待中心 header band held the promo "智能客服全新升级，助力客服高效
# 接待！", which was learned (and saved) as a buyer's display name.
# Alpha 2026-10-07 (yi): the header's rating badge "好评100.00%企超级" (next to
# the real name "sctisz") was the longest line, so it was learned instead.
_NOT_NAME_PUNCT = "，。！？、：；!?%％"
_NOT_NAME_WORDS = ("客服", "接待", "升级", "助力", "活动", "报名", "智能", "千牛", "工作台", "店铺", "通知",
                   "好评", "超级", "会员", "粉丝", "新客")


# A chat timestamp like "2026-10-714:51:37" (learned as a name, alpha 2026-10-07).
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{1,2}-\d|^\d{1,2}[:：]\d{2}|^[\d\-:：/ .]+$")


def looks_like_buyer_name(text: str) -> bool:
    """False for blank, overlong, punctuated, timestamp or UI-worded text."""
    t = (text or "").strip()
    if not t or len(t) > 24:
        return False
    if any(p in t for p in _NOT_NAME_PUNCT) or _TIMESTAMP_RE.search(t):
        return False
    return not any(w in t for w in _NOT_NAME_WORDS)


def name_for(sender_id: str) -> str:
    """Learned display name for a sender id, or "" (a stored UI-text "name"
    learned before this check existed is ignored)."""
    data = _load()
    sid = str(sender_id or "")
    name = data.get(sid, "")
    if not looks_like_buyer_name(name):
        return ""
    # A name stored for two buyers (learned before the one-name-one-buyer rule)
    # is ambiguous: use neither.
    if any(v == name for k, v in data.items() if k not in (sid, _SELF_KEY)):
        return ""
    return name


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
    if not looks_like_buyer_name(dn):
        logger.info(f"[qianniu] not learning {dn!r} for sender {sid!r}: looks like UI text, not a name")
        return False
    owner = next((k for k, v in _load().items() if v == dn and k not in (sid, _SELF_KEY)), "")
    if owner:
        # One name, one buyer: a second buyer "named" like a known one means the
        # screen read was wrong (alpha 2026-10-07: new buyer 3163207694 was
        # learned as 'sctisz', already buyer 678614304).
        logger.info(f"[qianniu] not learning {dn!r} for sender {sid!r}: already the name of {owner!r}")
        return False
    with _LOCK:
        data = _load()
        if data.get(sid) == dn:
            return False
        data[sid] = dn
        _save(data)
    logger.info(f"[qianniu] learned sender {sid!r} -> display name {dn!r}")
    return True


# The store's own sender id, learned when our sent reply shows up in memory
# (the standalone bot's rule). Kept in the same file under a reserved key.
_SELF_KEY = "__store_self_id__"


def store_self_id() -> str:
    return _load().get(_SELF_KEY, "")


def learn_store_self_id(sender_id: str) -> bool:
    sid = str(sender_id or "").strip()
    if not sid:
        return False
    with _LOCK:
        data = _load()
        if data.get(_SELF_KEY) == sid:
            return False
        data[_SELF_KEY] = sid
        _save(data)
    logger.info(f"[qianniu] learned the store's own sender id = {sid!r} (our reply echoed in memory)")
    return True


def known_ids() -> set:
    return set(_load().keys())
