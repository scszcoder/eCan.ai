"""Feige default SiteAdapter preset (2026-08-01).

Moved out of the platform module ``hooks/builtin/site_adapter.py`` so the
platform stays site-agnostic; platform code resolves this dict through
``live_chat_dispatch.runner_bridge().site_adapter_preset`` (see
``runner_bridge.py``) and ``normalize_site_adapter(None)`` deep-copies it.

Selectors captured 2026-04-23 from the live Feige site + emulation.  The
``wmvLQcpt39Hk9PSISrlN`` class is a CSS-in-JS hash Feige rotates every few
weeks; the ``odd_one_out`` strategy kicks in after it rotates so we don't
hard-fail during the window between rotation and config update.
"""
from __future__ import annotations

DEFAULT_SITE_ADAPTER: dict = {
    "name": "feige",
    "sidebar": {
        "item_selector": '[data-qa-id="qa-conversation-chat-item"]',
        "name_readers": [
            {"selector": ".MP1bk3ccfHC9V2SnPCGD", "source": "attr", "attr": "title"},
            {"selector": ".Jv6FtqUv5VoYARd2pp4y", "source": "text"},
            {"selector": '[data-qa-id="qa-conversation-nickname"]', "source": "text"},
        ],
        "active_strategies": [
            {"type": "class_token", "token": "active"},
            {"type": "aria_selected"},
            {"type": "class_token", "token": "wmvLQcpt39Hk9PSISrlN"},
            {"type": "odd_one_out"},
        ],
    },
    "header": {
        "root_selector": "#topbar-left-info",
        "leaf_candidates": "div, span",
        "exclude_texts": ["添加备注"],
        "max_text_len": 60,
        "fallback_attr": "data-btm-id",
    },
    "verify_policy": "affirmative_and_no_conflict",
}

# Historical name kept for external referencers.
DEFAULT_FEIGE_SITE_ADAPTER = DEFAULT_SITE_ADAPTER

__all__ = ["DEFAULT_SITE_ADAPTER", "DEFAULT_FEIGE_SITE_ADAPTER"]
