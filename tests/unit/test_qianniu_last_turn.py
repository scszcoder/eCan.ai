"""千牛 cold-start/backstop 'who spoke last' on real screens (alpha 2026-10-20,
cs_stress_bot OCR history: the exact OCR output the sweep decided on)."""
import json
import os
import time

from agent.mcp.server.qianniu import qianniu_ocr
from agent.ec_skills.browser_use_extension.hooks.external.qianniu_chat import observer

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _screen(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return [{"text": l["text"], "loc": l["loc"]} for l in json.load(f)["lines"]]


def test_the_sellers_turn_is_seen_whatever_nickname_the_agent_shows():
    # Seller bubbles are labelled 客服小A (agent nickname), not the window's store
    # label 'shopA71'; read as "buyer last: 确认好了吗客服小A" and answered again.
    assert qianniu_ocr.last_turn(_screen("qianniu_ocr_seller_last.json"),
                                 "买家熊猫", "shopA71") == ("store", "")


def test_the_customer_panel_is_not_part_of_the_buyers_message():
    # The panel's '医全' tag on the bubble's row was read as '医全有蓝深色海军衫吗？'.
    assert qianniu_ocr.last_turn(_screen("qianniu_ocr_buyers1_panel_tag.json"),
                                 "buyers1", "shopA71") == ("buyer", "有蓝深色海军衫吗？")


def test_a_screen_read_with_extra_words_is_still_already_handled():
    obs = observer.QianniuMemObserver(dispatch_fn=lambda item: 1)
    obs._dispatched_texts.append(("有蓝深色海军衫吗？", time.time()))
    assert obs._already_handled("buyers1", "医全有蓝深色海军衫吗？")
    obs._dispatched_texts.append(("在吗", time.time()))
    assert not obs._already_handled("tb1", "我在吗你看下尺码")       # a short text matches only from the start
