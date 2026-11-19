"""A browser model reply that names an action the old way (go_to_url) or clicks by xpath is
repaired to the actions eCan registers, instead of failing validation until the agent gives
up (2026-11-18: a Shopify label run stopped one click short of "Create shipping label")."""
import json

from agent.ec_skills.browser_use_extension.action_repair import repair_actions


def _actions(text):
    return json.loads(text)["action"]


def test_legacy_names_become_registered_actions():
    reply = json.dumps({"memory": "m", "action": [{"go_to_url": {"url": "https://x.test/orders"}},
                                                  {"click_element": {"index": 7}},
                                                  {"input_text": {"index": 3, "text": "1001"}}]})
    assert _actions(repair_actions(reply)) == [{"navigate": {"url": "https://x.test/orders"}},
                                               {"click": {"index": 7}},
                                               {"input": {"index": 3, "text": "1001"}}]


def test_a_click_by_xpath_on_visible_text_becomes_click_text():
    for xp in ("//*[contains(text(),'Create shipping label')]",
               "//*[normalize-space()='Create shipping label']",
               '//button[contains(., "Create shipping label")]'):
        out = _actions(repair_actions(json.dumps({"action": [{"click": {"xpath": xp}}]})))
        assert out == [{"click_text": {"text": "Create shipping label"}}], xp
    out = _actions(repair_actions(json.dumps({"action": [{"click": {"text": "Buy shipping label"}}]})))
    assert out == [{"click_text": {"text": "Buy shipping label"}}]


def test_valid_or_unreadable_replies_are_left_alone():
    ok = json.dumps({"action": [{"click": {"index": 4}}, {"navigate": {"url": "u"}}]})
    assert repair_actions(ok) == ok
    css = json.dumps({"action": [{"click": {"selector": "#buy"}}]})       # no text to click by
    assert repair_actions(css) == css
    for text in ("not json", "[1, 2]", '{"no_action": 1}', ""):
        assert repair_actions(text) == text
