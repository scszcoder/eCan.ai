"""Pinduoduo default SiteAdapter preset (selectors from real page snapshots, 2026-09-25).

Read by the platform through ``runner_bridge().site_adapter_preset``. A
conversation row is ``.chat-item-box[data-random="<uid>-0-<group>"]``; the
uid is the identity (nicknames are masked, e.g. ``S*******n``, and collide).
"""
from __future__ import annotations

DEFAULT_SITE_ADAPTER: dict = {
    "name": "pinduoduo",
    "sidebar": {
        "item_selector": ".chat-item-box[data-random]",
        "name_readers": [
            {"selector": ".nickname-span", "source": "text"},
        ],
        "active_strategies": [
            {"type": "class_token", "token": "active"},
            {"type": "odd_one_out"},
        ],
    },
    "header": {
        "root_selector": ".chatWindowHeader .base-info",
        "leaf_candidates": ".name",
        "exclude_texts": ["点击添加备注信息"],
        "max_text_len": 60,
        "fallback_attr": "",
    },
    "verify_policy": "affirmative_and_no_conflict",
}

__all__ = ["DEFAULT_SITE_ADAPTER"]
