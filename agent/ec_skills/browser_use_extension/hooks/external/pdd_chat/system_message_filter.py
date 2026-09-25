"""Drop Pinduoduo page noise that a DOM scrape can mistake for a customer message.

A ``ws_frontier`` item is a decoded customer message from the titan socket --
never noise (Feige learnt this when a customer literally typed "转人工").
"""
from __future__ import annotations

_NOISE = (
    ("transfer_button", "转移会话"),
    ("unread_hint", "“未读”表示对方尚未阅读您的消息"),
    ("faq_setup_hint", "您好像还没有配置消费者问到的常见问题回答"),
    ("robot_label", "-自动回复"),
    ("inducement_warning", "严禁与消费者交换手机号"),
)


def first_system_row_match(item: dict, resolved: dict | None = None) -> str | None:
    if not isinstance(item, dict):
        return None
    if item.get("source") == "ws_frontier":
        return None
    text = str(item.get("last_message") or item.get("latest_message") or "").strip()
    if not text:
        return None
    for reason, marker in _NOISE:
        if marker in text:
            return reason
    return None
