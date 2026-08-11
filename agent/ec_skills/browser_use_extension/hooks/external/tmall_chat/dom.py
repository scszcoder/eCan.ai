"""Qianniu (千牛) Web tab resolution for the Tmall chat bundle.

Lean Phase 1 port of ``feige_chat/dom_assets.resolve_feige_tab_target_id``:
URL-marker matching + a short per-session TTL cache.  No typing-tab pool,
no multi-candidate row-count probing yet — those come with the Phase 3
multi-tab work if live latency numbers justify them.

The Qianniu Web workbench URL is environment-dependent (it moved hosts
over the years), so the marker list is env-overridable:

    ECAN_TMALL_IM_URL_MARKERS=work.taobao.com,myseller.taobao.com

First live run: check which host the seller IM page actually lands on and
pin it (see README calibration playbook).
"""
from __future__ import annotations

import os
import time
from typing import Any

from utils.logger_helper import logger_helper as logger

_DEFAULT_URL_MARKERS = (
    "work.taobao.com",
    "myseller.taobao.com",
    "qianniu.taobao.com",
    "im.taobao.com",
)

_SESSION_TID_ATTR = "_ecan_tmall_tab_tid"
_SESSION_TID_TS_ATTR = "_ecan_tmall_tab_tid_ts"


def im_url_markers() -> tuple[str, ...]:
    """Return the URL substrings that identify a Qianniu IM tab."""
    raw = os.environ.get("ECAN_TMALL_IM_URL_MARKERS", "").strip()
    if raw:
        markers = tuple(m.strip() for m in raw.split(",") if m.strip())
        if markers:
            return markers
    return _DEFAULT_URL_MARKERS


def is_tmall_im_url(url: str) -> bool:
    """True when *url* looks like the Qianniu Web seller-IM page."""
    u = str(url or "")
    return any(m in u for m in im_url_markers())


def _cache_get(browser_session: Any, ttl_s: float) -> str:
    if ttl_s <= 0:
        return ""
    tid = str(getattr(browser_session, _SESSION_TID_ATTR, "") or "")
    ts = float(getattr(browser_session, _SESSION_TID_TS_ATTR, 0.0) or 0.0)
    if tid and (time.monotonic() - ts) <= ttl_s:
        return tid
    return ""


def _cache_set(browser_session: Any, tid: str) -> None:
    try:
        setattr(browser_session, _SESSION_TID_ATTR, str(tid or ""))
        setattr(browser_session, _SESSION_TID_TS_ATTR, time.monotonic())
    except Exception:
        pass


def clear_tab_cache(browser_session: Any, reason: str = "") -> None:
    try:
        setattr(browser_session, _SESSION_TID_ATTR, "")
        setattr(browser_session, _SESSION_TID_TS_ATTR, 0.0)
        if reason:
            logger.debug(f"[Tmall] tab cache cleared: {reason}")
    except Exception:
        pass


async def resolve_tmall_tab_target_id(
    browser_session: Any,
    *,
    customer_key: str = "",
) -> str:
    """Return the best Qianniu IM tab target id without changing focus.

    ``customer_key`` is accepted for platform-signature compatibility
    (``_resolve_live_chat_tab_target_id_bounded`` threads it through for
    typing-tab routing); Phase 1 has no typing-tab pool, so it is unused.
    """
    from .tunables import resolve_float, DEFAULT_TMALL_TAB_RESOLVE_CACHE_TTL_S

    ttl = resolve_float(
        "TMALL_TAB_RESOLVE_CACHE_TTL_S", DEFAULT_TMALL_TAB_RESOLVE_CACHE_TTL_S, None
    )

    try:
        sm = getattr(browser_session, "session_manager", None)
        all_targets = sm.get_all_targets() if sm else {}
    except Exception:
        all_targets = {}

    cached = _cache_get(browser_session, ttl)
    if cached:
        tgt = (all_targets or {}).get(cached)
        if tgt is not None and is_tmall_im_url(getattr(tgt, "url", "")):
            return cached
        clear_tab_cache(browser_session, "cached target stale")

    candidates: list[tuple[str, str]] = []
    for tid, tgt in (all_targets or {}).items():
        if getattr(tgt, "target_type", "") not in ("page", "tab"):
            continue
        url = str(getattr(tgt, "url", "") or "")
        if is_tmall_im_url(url):
            candidates.append((str(tid), url))
    if not candidates:
        return ""

    # Prefer the shallowest path (the workbench main page over deep-linked
    # sub-pages) — same heuristic Feige uses.
    def _path_depth(url: str) -> int:
        try:
            tail = url.split("//", 1)[-1]
            path = tail.split("/", 1)[1] if "/" in tail else ""
            path = path.split("?", 1)[0].split("#", 1)[0]
            return len([seg for seg in path.split("/") if seg])
        except Exception:
            return 99

    candidates.sort(key=lambda c: _path_depth(c[1]))
    tid = candidates[0][0]
    _cache_set(browser_session, tid)
    return tid
