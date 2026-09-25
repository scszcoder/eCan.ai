"""The Pinduoduo bundle: opt-in registration, observer dispatch items, send retry rules."""

import os
import unittest
from unittest import mock

from agent.ec_skills import live_chat_dispatch as lcd
from agent.ec_skills.browser_use_extension.hooks.external import pdd_chat
from agent.ec_skills.browser_use_extension.hooks.external.pdd_chat import runner_bridge as rb
from agent.ec_skills.browser_use_extension.hooks.external.pdd_chat import ws_observer, ws_protocol
from tests.test_pdd_ws_protocol import BUYER, SHOP, chat


class RegistrationGateTests(unittest.TestCase):
    def setUp(self):
        self.saved = dict(lcd._BRIDGES)
        self.addCleanup(self._restore)
        self.feige = object()

    def _restore(self):
        lcd._BRIDGES.clear()
        lcd._BRIDGES.update(self.saved)
        pdd_chat._REGISTERED = False

    def test_not_named_means_not_registered_and_feige_unchanged(self):
        lcd._BRIDGES.clear()
        lcd.register_runner_bridge(self.feige, "feige_chat")
        pdd_chat._REGISTERED = False
        with mock.patch.dict(os.environ, {"ECAN_LIVE_CHAT_SITE": ""}):
            self.assertFalse(pdd_chat.register())
            self.assertEqual(lcd.bridge_sites(), ["feige_chat"])
            self.assertIs(lcd.runner_bridge(), self.feige, "the sole bridge still answers")

    def test_named_registers_and_is_the_default_outside_a_node(self):
        lcd._BRIDGES.clear()
        lcd.register_runner_bridge(self.feige, "feige_chat")
        pdd_chat._REGISTERED = False
        with mock.patch.dict(os.environ, {"ECAN_LIVE_CHAT_SITE": "pdd_chat"}):
            self.assertTrue(pdd_chat.register())
            self.assertIs(lcd.runner_bridge(), rb.get_bridge())
            self.assertIs(lcd.runner_bridge("feige_chat"), self.feige, "explicit still wins")
            token = lcd.set_active_site("feige_chat")
            try:
                self.assertIs(lcd.runner_bridge(), self.feige, "a running Feige node still gets Feige")
            finally:
                lcd.reset_active_site(token)

    def test_two_bridges_and_no_configuration_still_refuses_to_guess(self):
        lcd._BRIDGES.clear()
        lcd.register_runner_bridge(self.feige, "feige_chat")
        lcd.register_runner_bridge(rb.get_bridge(), "pdd_chat")
        with mock.patch.dict(os.environ, {"ECAN_LIVE_CHAT_SITE": ""}):
            self.assertIsNone(lcd.runner_bridge())

    def test_the_tools_exist_once_enabled(self):
        with mock.patch.dict(os.environ, {"ECAN_LIVE_CHAT_SITE": "pdd_chat"}):
            pdd_chat._REGISTERED = False
            pdd_chat.register()
        from agent.ec_skills.browser_use_extension.extension_tools_service import custom_controller
        actions = custom_controller.registry.registry.actions
        for name in ("pdd_list_sessions", "pdd_open_session", "pdd_get_chat_thread", "pdd_send_message"):
            self.assertIn(name, actions)


class ObserverItemTests(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.state = ws_observer._State(self.sent.append, "pdd")

    def test_a_buyer_message_becomes_a_front_desk_item_keyed_by_uid(self):
        self.state.on_frame(chat({"from": BUYER, "to": SHOP, "type": 0, "content": "有绿色的吗？",
                                  "msg_id": "m1", "nickname": "S*******n"}))
        [item] = self.sent
        self.assertEqual({item[k] for k in ("customer_name", "session_id", "customer_id", "talk_id")},
                         {"1000000000001"})
        self.assertEqual(item["customer_display_name"], "S*******n")
        self.assertEqual((item["last_message"], item["latest_message_msg_id"], item["unread_badge"], item["source"]),
                         ("有绿色的吗？", "m1", "1", "ws_frontier"))
        self.assertEqual(item["identity_key"], "1000000000001|m1")

    def test_same_message_twice_is_dispatched_once(self):
        f = chat({"from": BUYER, "to": SHOP, "type": 0, "content": "hi", "msg_id": "m1"})
        self.state.on_frame(f)
        self.state.on_frame(f)
        self.assertEqual(len(self.sent), 1)

    def test_our_replies_and_source_cards_are_not_dispatched_but_give_context(self):
        self.state.on_frame(chat({"from": {**SHOP, "csid": "x"}, "to": BUYER, "type": 0, "content": "在的", "msg_id": "a"}))
        self.state.on_frame(chat({"from": BUYER, "to": SHOP, "type": 41, "template_name": "user_source",
                                  "no_unreply_hint": 1, "msg_id": "s",
                                  "info": {"goods_info": {"goods_id": 9, "goods_name": "睡衣", "total_amount": 5990}}}))
        self.assertEqual(self.sent, [])
        self.state.on_frame(chat({"from": BUYER, "to": SHOP, "type": 0, "content": "尺码偏大吗", "msg_id": "q"}))
        [item] = self.sent
        self.assertEqual(item["product_context"]["name"], "睡衣")

    def test_an_image_travels_as_an_attachment(self):
        self.state.on_frame(chat({"from": BUYER, "to": SHOP, "type": 1, "content": "https://img/x.jpeg",
                                  "msg_id": "i", "info": {"image_url": "https://img/x.jpeg"}}))
        [item] = self.sent
        self.assertEqual(item["last_message"], "[图片]")
        self.assertEqual(item["last_message_attachments"][0]["url"], "https://img/x.jpeg")

    def test_a_dispatch_error_does_not_stop_the_observer(self):
        st = ws_observer._State(mock.Mock(side_effect=RuntimeError("boom")), "pdd")
        st.on_frame(chat({"from": BUYER, "to": SHOP, "type": 0, "content": "x", "msg_id": "1"}))
        self.assertEqual(st.stats["messages"], 1)


class SendRuleTests(unittest.TestCase):
    def test_an_unverified_send_is_never_retried(self):
        self.assertFalse(rb._is_retryable_send_error("pdd_send_unverified:no_bubble -- reply not seen"))
        self.assertEqual(rb.get_bridge().classify_send_error("pdd_send_unverified:no_bubble"),
                         "send_unverified_no_bubble")

    def test_failures_before_typing_are_retried(self):
        self.assertTrue(rb._is_retryable_send_error("pdd_send_not_typed: conversation 1 did not open"))
        self.assertTrue(rb._is_retryable_send_error("typing_lock_busy (holder='x')"))

    def test_the_typing_lock_is_one_sender_at_a_time(self):
        lock = rb.get_bridge().typing_lock
        self.assertTrue(lock.try_acquire("a"))
        try:
            self.assertFalse(lock.try_acquire("b"))
            self.assertEqual(lock.holder(), "a")
        finally:
            lock.release("a")
        self.assertTrue(lock.try_acquire("b"))
        lock.release("b")


if __name__ == "__main__":
    unittest.main()
