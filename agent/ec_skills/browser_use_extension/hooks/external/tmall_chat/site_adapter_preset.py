"""Tmall/Qianniu default SiteAdapter preset.

Consumed by the platform's ``hooks/builtin/site_adapter.py``
(``normalize_site_adapter(None)`` deep-copies it through
``runner_bridge().site_adapter_preset``).

⚠️ SPECULATIVE SELECTORS — NOT YET CALIBRATED AGAINST THE LIVE QIANNIU
WEB WORKBENCH.  These are educated placeholders using ``class*=`` wildcards
(partially informed by the old ``agent/ec_tasks/platform_profiles.json``
"tmall" entry, itself unvalidated).  On the first live run, capture the
real DOM and pin exact selectors here — see the bundle README calibration
playbook.  Feige's preset documents the shape these should take once
captured (``feige_chat/site_adapter_preset.py``).
"""
from __future__ import annotations

DEFAULT_SITE_ADAPTER: dict = {
    "name": "tmall",
    "sidebar": {
        # Conversation rows in the left-hand session list.
        "item_selector": (
            '[class*="conversation-item"], [class*="session-item"], '
            '[class*="conv-item"], li[class*="im-conversation"]'
        ),
        "name_readers": [
            {"selector": '[class*="nick"], [class*="user-name"], [class*="name"]',
             "source": "attr", "attr": "title"},
            {"selector": '[class*="nick"], [class*="user-name"], [class*="name"]',
             "source": "text"},
        ],
        "active_strategies": [
            {"type": "class_token", "token": "active"},
            {"type": "class_token", "token": "selected"},
            {"type": "aria_selected"},
            {"type": "odd_one_out"},
        ],
    },
    "header": {
        # Chat-pane header showing the currently open buyer's nick.
        "root_selector": '[class*="chat-header"], [class*="im-header"], [class*="header-nick"]',
        "leaf_candidates": "div, span",
        "exclude_texts": [],
        "max_text_len": 60,
        "fallback_attr": "",
    },
    "verify_policy": "affirmative_and_no_conflict",
}

__all__ = ["DEFAULT_SITE_ADAPTER"]
