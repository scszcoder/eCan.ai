"""mt023 #2: store auto-greeting now classified as platform/system text.

Live trace 2026-05-22 08:19 (陆地飞鱼) — the customer opened a chat and
the store's pre-configured welcome bubble "Hi，欢迎光临本店，请问
有什么可以帮助您?" appeared as the latest visible bubble.  The front-
desk dispatched THAT to a Q&A bot as ``latest_message``, wasting a
turn generating a generic "您好，欢迎光临！请问您想咨询..." reply
that was then rejected at delivery with stale_reply_source_msg_id once
the customer typed a real question — triggering the recent-echo
deadlock (covered by mt023 #1 fix).

Pattern is anchored to ``欢迎光临本店`` so it doesn't accidentally
match a customer who happens to write "欢迎"; the second alt covers
the bot-side reply pattern so we recognise our own welcome echoes too.
"""
from __future__ import annotations

import unittest

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    system_message_filter as _smf,
)


class StoreAutoGreetingPatternTests(unittest.TestCase):
    def test_exact_store_auto_greeting_matched(self) -> None:
        text = "Hi，欢迎光临本店，请问有什么可以帮助您?"
        self.assertEqual("store_auto_greeting", _smf.first_matching_pattern(text))
        self.assertTrue(_smf.is_platform_or_system_message(text))

    def test_alternate_phrasings_matched(self) -> None:
        # Common variants stores might configure
        for text in (
            "欢迎光临本店！",
            "您好，欢迎光临！",
            "您好,欢迎光临",
            "您好  欢迎光临",
        ):
            self.assertTrue(
                _smf.is_platform_or_system_message(text),
                msg=f"failed to match: {text!r}",
            )

    def test_customer_text_not_false_positive(self) -> None:
        # Real customer questions that contain neutral words like "欢迎"
        # but don't form the store-greeting pattern must NOT match.
        safe_customer_texts = [
            "你们家衣服质量怎么样？",
            "包邮吗？",
            "可以退货吗？",
            "我想咨询一下尺码",
            "欢迎介绍下你们的产品",  # contains 欢迎 but not store pattern
            "本店有团购吗？",  # contains 本店 but not 欢迎光临本店
            "Hi，请问发什么快递？",  # Hi greeting but no 欢迎光临
        ]
        for text in safe_customer_texts:
            self.assertFalse(
                _smf.is_platform_or_system_message(text),
                msg=f"false positive: {text!r}",
            )

    def test_first_system_row_match_finds_it_in_last_message(self) -> None:
        item = {
            "customer_name": "陆地飞鱼",
            "last_message": "Hi，欢迎光临本店，请问有什么可以帮助您?",
        }
        hit = _smf.first_system_row_match(item)
        self.assertEqual("system_message:last_message:store_auto_greeting", hit)

    def test_existing_patterns_still_work(self) -> None:
        # Don't accidentally break the existing filters when adding the
        # new pattern.  Spot-check one of each type.
        self.assertTrue(_smf.is_platform_or_system_message("当前会话已长时间未回复"))
        self.assertTrue(_smf.is_platform_or_system_message("亲亲，在哒~"))
        self.assertTrue(_smf.is_platform_or_system_message("现在是人工客服为您服务"))


if __name__ == "__main__":
    unittest.main()
