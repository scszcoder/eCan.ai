"""Pinduoduo titan push decoding. Frames are built here with the real layout
(header, protobuf-ish envelope, gzip(inner + JSON)); real captures hold customer
messages and stay out of the repo."""

import base64
import gzip
import json
import unittest

from agent.ec_skills.browser_use_extension.hooks.external.pdd_chat import ws_protocol as wp


def frame(obj=None, raw_inner=b""):
    inner = b"\n\t100000001\x18\x05 \xa8\x9c\x01* 1790317002793#100000001#0abcdef01\xd8\x03"
    body = inner + (json.dumps(obj, ensure_ascii=False).encode("utf-8") if obj is not None else raw_inner)
    head = bytes.fromhex("000a0066") + b"\x00" * 10 + b"\x01\x6d" + bytes.fromhex("689ec4d0f2071001") + b"R\xc8\x02"
    return base64.b64encode(head + gzip.compress(body) + b"\x00titan.notifyDataLite").decode()


def chat(*messages):
    return frame({"push_type": 2, "target_id": 100000001,
                  "push_data": {"seq_type": 1, "seq_id": 22,
                                "data": [{"message": m, "chat_type_id": 1} for m in messages]}})


BUYER = {"role": "user", "uid": "1000000000001"}
SHOP = {"role": "mall_cs", "uid": "200000002"}


class DecodeTests(unittest.TestCase):
    def test_buyer_text(self):
        [e] = wp.decode_events(chat({"from": BUYER, "to": SHOP, "content": "这款买三套有打折吗？", "type": 0,
                                     "msg_id": "1790317002572", "pre_msg_id": "1790316982665",
                                     "ts": "1790317002", "nickname": "S*******n"}))
        self.assertEqual((e["conversation_id"], e["kind"], e["text"]), ("1000000000001", "text", "这款买三套有打折吗？"))
        self.assertTrue(e["from_customer"] and e["needs_reply"])
        self.assertEqual((e["customer_name"], e["msg_id"], e["ts"]), ("S*******n", "1790317002572", 1790317002))

    def test_our_own_reply_is_not_input(self):
        [e] = wp.decode_events(chat({"from": {**SHOP, "csid": "Agent1"}, "to": BUYER, "content": "在的", "type": 0}))
        self.assertFalse(e["from_customer"] or e["needs_reply"])
        self.assertEqual((e["conversation_id"], e["agent_account"]), ("1000000000001", "Agent1"))

    def test_a_push_can_carry_several_messages(self):
        evs = wp.decode_events(chat({"from": {**SHOP}, "to": BUYER, "content": "a", "type": 0},
                                    {"from": BUYER, "to": SHOP, "content": "b", "type": 0}))
        self.assertEqual([e["from_customer"] for e in evs], [False, True])

    def test_image(self):
        [e] = wp.decode_events(chat({"from": BUYER, "to": SHOP, "type": 1, "content": "https://chat-img/x.jpeg",
                                     "info": {"image_url": "https://chat-img/x.jpeg", "width": 1, "height": 2}}))
        self.assertEqual((e["kind"], e["image_url"], e["text"]), ("image", "https://chat-img/x.jpeg", ""))
        self.assertTrue(e["needs_reply"])

    def test_goods_card(self):
        [e] = wp.decode_events(chat({"from": BUYER, "to": SHOP, "type": 0, "template_name": "user_goods_card",
                                     "content": "https://mobile.yangkeduo.com/goods.html?goods_id=1",
                                     "info": {"goodsID": 300000000003, "goodsName": "睡衣", "goodsPrice": "59.9",
                                              "goodsThumbUrl": "t", "linkUrl": "u"}}))
        self.assertEqual(e["kind"], "goods_card")
        self.assertEqual(e["goods"], {"goods_id": "300000000003", "name": "睡衣", "price": 59.9, "thumb": "t", "url": "u"})

    def test_source_card_is_context_not_a_question(self):
        [e] = wp.decode_events(chat({"from": BUYER, "to": SHOP, "type": 41, "template_name": "user_source",
                                     "content": "[当前用户来自 商品详情页]", "no_unreply_hint": 1,
                                     "info": {"goods_info": {"goods_id": 1, "goods_name": "睡衣", "total_amount": 5990}}}))
        self.assertEqual((e["kind"], e["needs_reply"], e["goods"]["price"]), ("source", False, 59.9))

    def test_remind(self):
        [e] = wp.decode_events(chat({"from": BUYER, "to": SHOP, "type": 31,
                                     "template_name": "remind_customer_service_mall",
                                     "content": "消费者催促您，请尽快回复！\n"}))
        self.assertEqual((e["kind"], e["text"], e["needs_reply"]), ("remind", "消费者催促您，请尽快回复！", True))

    def test_system_pushes(self):
        f = frame({"response": "mall_system_msg", "message": {"type": 20, "data": {
            "user_id": "1000000000001", "user_last_read": "1790316865843"}}})
        self.assertEqual(wp.decode_events(f), [])
        s = wp.system_event(wp.decode_frame(f))
        self.assertEqual((s["type"], s["conversation_id"]), (20, "1000000000001"))

    def test_control_and_protobuf_only_frames_are_skipped(self):
        self.assertIsNone(wp.decode_frame(base64.b64encode(bytes.fromhex("00000000000000690000000100000000"))))
        self.assertIsNone(wp.decode_frame(frame(raw_inner=b"\nu\n\x0eclient_ip_info\x12c")))
        self.assertIsNone(wp.decode_frame("not base64 !!"))

    def test_titan_url(self):
        self.assertTrue(wp.is_titan_url("wss://titan-ws.pinduoduo.com/"))
        self.assertFalse(wp.is_titan_url("wss://m-ws.pinduoduo.com/?access_token=x"))


if __name__ == "__main__":
    unittest.main()
