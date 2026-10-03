"""The periodic conversation-list check: a store whose socket carries nothing
(2026-10-02: observer attached mid-load, never got a frame, DOM monitor stood
down) must still answer a waiting customer, and must hand detection back to the
page monitor when the list cannot be read."""

import asyncio
import json
import unittest

from agent.ec_skills.browser_use_extension.hooks.external.pdd_chat import dom, ws_observer, ws_session


class FakeClient:
    def __init__(self, rows):
        self.rows = rows
        self.fail = False

    async def send_raw(self, method, params=None, session_id=None):
        if self.fail:
            raise ConnectionError("client is not started")
        return {"result": {"value": json.dumps(self.rows, ensure_ascii=False)}}


class ListCheckTests(unittest.TestCase):
    def setUp(self):
        self._old = ws_observer.LIST_CHECK_S
        ws_observer.LIST_CHECK_S = 0.01

    def tearDown(self):
        ws_observer.LIST_CHECK_S = self._old

    def test_waiting_customer_is_dispatched_once_without_any_frame(self):
        got = []
        state = ws_observer._State(got.append, "新消息")
        client = FakeClient([{"uid": "U1", "name": "S*n", "last_message": "有更多折扣吗？", "waiting": True}])
        shop = object()

        async def main():
            ws_session.set_dispatch_live(True, shop)
            task = asyncio.get_running_loop().create_task(ws_observer._watch_list(client, "s", state, shop))
            await asyncio.sleep(0.1)                      # several checks, same waiting text
            state.last_dispatch_at["U1"] = 0.0           # long ago: a new text may go out
            client.rows = [{"uid": "U1", "last_message": "有更多折扣吗？", "waiting": True},
                           {"uid": "U2", "last_message": "在吗", "group": "unTimeout"}]
            await asyncio.sleep(0.1)
            task.cancel()
        asyncio.run(main())
        self.assertEqual([i["last_message"] for i in got], ["有更多折扣吗？", "在吗"])

    def test_a_conversation_just_dispatched_by_the_socket_is_left_alone(self):
        got = []
        state = ws_observer._State(got.append, "新消息")
        state.last_text["U1"] = "[商品卡片] 睡衣 ¥59.9"           # what the socket dispatched
        state.last_dispatch_at["U1"] = __import__("time").time()
        client = FakeClient([{"uid": "U1", "last_message": "[商品]", "waiting": True}])
        shop = object()

        async def main():
            task = asyncio.get_running_loop().create_task(ws_observer._watch_list(client, "s", state, shop))
            await asyncio.sleep(0.05)
            task.cancel()
        asyncio.run(main())
        self.assertEqual(got, [])

    def test_unreadable_list_hands_detection_back_to_the_page_monitor(self):
        state = ws_observer._State(lambda item: None, "新消息")
        client = FakeClient([])
        client.fail = True
        shop = object()

        async def main():
            ws_session.set_dispatch_live(True, shop)
            await asyncio.wait_for(ws_observer._watch_list(client, "s", state, shop), 2)
        asyncio.run(main())
        self.assertFalse(ws_session.is_dispatch_live(shop))


class FakeBrowser:
    """Targets + one chat page that may be kicked out until it is reloaded."""

    def __init__(self, kicked=False):
        self.targets = [
            {"targetId": "OURS", "type": "page", "url": "https://mms.pinduoduo.com/chat-merchant/index.html#/"},
            {"targetId": "DUP", "type": "page", "url": "https://mms.pinduoduo.com/chat-merchant/index.html?r=1#/"},
            {"targetId": "OTHER", "type": "page", "url": "https://mms.pinduoduo.com/goods/list"},
        ]
        self.kicked = kicked
        self.closed, self.reloads = [], 0

    async def send_raw(self, method, params=None, session_id=None):
        params = params or {}
        if method == "Target.getTargets":
            return {"targetInfos": list(self.targets)}
        if method == "Target.closeTarget":
            self.closed.append(params["targetId"])
            self.targets = [t for t in self.targets if t["targetId"] != params["targetId"]]
            return {}
        if method == "Page.reload":
            self.reloads += 1
            self.kicked = False
            return {}
        expr = params.get("expression", "")
        if dom.KICKED_TEXT in expr:
            return {"result": {"value": json.dumps({"kicked": self.kicked})}}
        return {"result": {"value": json.dumps([{"uid": "U1", "last_message": "hi"}])}}


class SingleSessionTests(unittest.TestCase):
    def setUp(self):
        self._wait = ws_observer.RECLAIM_WAIT_S
        ws_observer.RECLAIM_WAIT_S = 0.0

    def tearDown(self):
        ws_observer.RECLAIM_WAIT_S = self._wait

    def test_extra_chat_tabs_are_closed_and_others_left_alone(self):
        b = FakeBrowser()
        state = ws_observer._State(lambda item: None, "新消息")
        asyncio.run(ws_observer._ensure_single_session(b, "s", "OURS", state))
        self.assertEqual(b.closed, ["DUP"])
        self.assertEqual(b.reloads, 0)

    def test_kicked_page_is_reloaded_once_per_cooldown(self):
        b = FakeBrowser(kicked=True)
        state = ws_observer._State(lambda item: None, "新消息")

        async def main():
            await ws_observer._ensure_single_session(b, "s", "OURS", state)
            b.kicked = True                       # kicked again right away
            await ws_observer._ensure_single_session(b, "s", "OURS", state)
        asyncio.run(main())
        self.assertEqual(b.reloads, 1)
        self.assertTrue(state.kicked_since)

    def test_send_refuses_a_kicked_page(self):
        async def evaluate(js):
            if dom.KICKED_TEXT in js:
                return json.dumps({"kicked": True})
            raise AssertionError("nothing else may run on a kicked page")

        async def cdp(method, params):
            raise AssertionError("no input into a kicked page")
        out = asyncio.run(dom.send_text(evaluate, "U1", "hi", cdp=cdp))
        self.assertFalse(out["ok"])
        self.assertIn("账户在别处登录", out["error"])


if __name__ == "__main__":
    unittest.main()
