"""Pinduoduo chat page helpers: the selectors (run in Chromium against a small
page with the real structure) and the send guard (never type into the wrong
conversation)."""

import asyncio
import json
import unittest

from agent.ec_skills.browser_use_extension.hooks.external.pdd_chat import dom

PAGE = """<html><body>
<ul class="already-unreply">
 <li class="chat-item"><div data-random="1000000000001-0-unTimeout" class="chat-item-box transition active">
  <div class="chat-detail"><div class="chat-nickname"><span class="nickname-span">S*******n</span></div>
  <div class="bottom-message"><p class="chat-message-content">你好,在吗?</p></div></div>
  <div class="chat-time"><p class="item-note"> 12:40 </p><div class="chat-unreply-over-time">已等待1小时</div></div></div></li>
 <li class="chat-item"><div data-random="1000000000002-0-reply" class="chat-item-box transition">
  <div class="chat-detail"><div class="chat-nickname"><span class="nickname-span">X*K</span></div>
  <div class="bottom-message"><p class="chat-message-content">这件有货</p></div></div>
  <div class="chat-time"><p class="item-note">13:09</p></div></div></li>
 <li class="chat-item"><div data-random="1000000000002-0-all" class="chat-item-box transition"></div></li>
</ul>
<div class="chatWindowHeader"><div class="base-info"><span class="name">S*******n</span></div></div>
<div id="msgListContainer"><ul class="msg-list">
 <li id="middlePanel_list_1790317002572" class="clearfix onemsg"><div class="merchantMessage">
  <div class="buyer-item"><div currentuid="1000000000001"><div class="msg-content"><p class="msg-content-box">这款买三套有打折吗？</p></div></div></div></div></li>
 <li id="middlePanel_list_1790317011086" class="clearfix onemsg"><div class="merchantMessage">
  <div class="cs-item isread"><div currentuid="1000000000001"><div class="msg-content"><p class="msg-content-box">没有哦</p></div></div></div></div></li>
 <li id="middlePanel_list_1790317002863" class="clearfix onemsg"><div class="merchantMessage">
  <div class="buyer-item"><div currentuid="1000000000001"><div class="msg-content good-card"><p class="good-name">睡衣</p><img src="https://img/thumb.jpeg"></div></div></div></div></li>
</ul></div>
<div class="reply-box"><textarea id="replyTextarea"></textarea><div class="send-btn">发送</div></div>
</body></html>"""


class SelectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
            cls._pw = sync_playwright().start()
            cls._browser = cls._pw.chromium.launch()
        except Exception as exc:
            raise unittest.SkipTest(f"no Chromium for the selector tests: {exc}")
        cls.page = cls._browser.new_page()
        cls.page.set_content(PAGE)

    @classmethod
    def tearDownClass(cls):
        cls._browser.close()
        cls._pw.stop()

    def run_js(self, js):
        return json.loads(self.page.evaluate(js))

    def test_sessions_by_uid_one_row_each(self):
        rows = self.run_js(dom.LIST_SESSIONS_JS)
        self.assertEqual([r["uid"] for r in rows], ["1000000000001", "1000000000002"])
        first = rows[0]
        self.assertEqual((first["name"], first["waiting"], first["active"], first["group"]),
                         ("S*******n", "已等待1小时", True, "unTimeout"))

    def test_thread_knows_whose_it_is_and_who_said_what(self):
        t = self.run_js(dom.THREAD_JS)
        self.assertEqual((t["uid"], t["name"]), ("1000000000001", "S*******n"))
        self.assertEqual([(m["msg_id"], m["who"]) for m in t["messages"]],
                         [("1790317002572", "customer"), ("1790317011086", "agent"), ("1790317002863", "customer")])
        self.assertEqual(t["messages"][0]["text"], "这款买三套有打折吗？")
        self.assertEqual(t["messages"][2]["image"], "", "a card's thumbnail is not a picture")

    def test_typing_reaches_the_reply_box(self):
        self.assertTrue(self.run_js(dom.type_reply_js('亲，有的哈 "quoted"'))["ok"])
        self.assertEqual(self.page.eval_on_selector("#replyTextarea", "e => e.value"), '亲，有的哈 "quoted"')


class SendGuardTests(unittest.TestCase):
    def _fake(self, showing, opens_to):
        state = {"uid": showing, "typed": None, "clicked": False}

        async def evaluate(js):
            if js == dom.THREAD_JS:
                return json.dumps({"uid": state["uid"], "messages": []})
            if "data-random" in js and "click()" in js:
                state["uid"] = opens_to
                return json.dumps({"ok": True})
            if "#replyTextarea" in js and "setter" in js:
                state["typed"] = js
                return json.dumps({"ok": True})
            if js == dom.CLICK_SEND_JS:
                state["clicked"] = True
                return json.dumps({"ok": True, "cleared": True})
            raise AssertionError(js[:60])
        return evaluate, state

    async def _noop(self):
        return None

    def test_sends_into_the_right_conversation(self):
        ev, st = self._fake(showing="A", opens_to="B")
        out = asyncio.run(dom.send_text(ev, "B", "hi", settle=self._noop))
        self.assertTrue(out["ok"] and st["clicked"])

    def test_refuses_when_the_conversation_does_not_open(self):
        ev, st = self._fake(showing="A", opens_to="A")      # the click did not switch
        out = asyncio.run(dom.send_text(ev, "B", "hi", settle=self._noop))
        self.assertFalse(out["ok"])
        self.assertIsNone(st["typed"], "nothing typed into A's conversation")
        self.assertFalse(st["clicked"])


if __name__ == "__main__":
    unittest.main()
