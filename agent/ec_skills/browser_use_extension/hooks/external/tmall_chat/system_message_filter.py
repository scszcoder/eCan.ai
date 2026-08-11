"""Qianniu (千牛) platform/system message denylist.

Rows and bubbles whose text matches these markers are platform chrome —
system notices, bot lines, closure banners — not real buyer messages, and
must never be dispatched to a Q&A agent.

⚠️ PLACEHOLDER LIST — Qianniu's real system-row wording must be pinned
from the first live run's captures (the Feige equivalent,
``feige_chat/system_message_filter.py``, was built the same way from live
logs).  Keep this list in sync with the 预筛选 keyword list in the
front-desk prompt (``customer_logs/prompt_pr-tmall-fd.json``).
"""
from __future__ import annotations

# Substring markers, checked case-sensitively against the row/bubble text.
SYSTEM_MESSAGE_MARKERS: tuple[str, ...] = (
    # Session lifecycle
    "会话已结束",
    "会话已关闭",
    "超时未回复",
    "会话超时",
    # Platform / official notices
    "系统消息",
    "官方消息",
    "服务通知",
    "平台公告",
    # Store bot (店小蜜) auto-lines — suppress our own competing bot's rows
    "店小蜜",
    # Review / rating prompts
    "评价邀请",
    "邀请您对本次服务",
)


def is_system_message(text: str) -> bool:
    """True when *text* is platform chrome rather than a buyer message."""
    t = str(text or "")
    if not t:
        return False
    return any(marker in t for marker in SYSTEM_MESSAGE_MARKERS)
