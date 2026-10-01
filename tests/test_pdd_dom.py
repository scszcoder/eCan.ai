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


# A page that, like the real one, ignores synthetic events: rows switch the
# conversation and 发送 sends ONLY for trusted input (first live run 2026-10-01:
# row .click() never switched, .send-btn .click() never sent).
TRUSTED_ONLY_PAGE = """<html><body style="margin:0">
<ul class="chat-list" style="height:120px;overflow:auto">
 <li class="chat-item"><div data-random="U1-0-unTimeout" class="chat-item-box" style="height:60px">U1</div></li>
 <li class="chat-item"><div data-random="U2-0-unTimeout" class="chat-item-box" style="height:60px">U2</div></li>
 <li class="chat-item"><div data-random="U3-0-unTimeout" class="chat-item-box" style="height:60px">U3</div></li>
</ul>
<div id="msgListContainer"><ul class="msg-list"></ul></div>
<div class="reply-box"><textarea id="replyTextarea"></textarea><div class="send-btn" style="width:80px;height:30px">发送</div></div>
<script>
 let current = 'U1', n = 0;
 function render() {
   document.querySelectorAll('#msgListContainer li').forEach(li => li.remove());
   const li = document.createElement('li');
   li.className = 'onemsg'; li.id = 'middlePanel_list_0';
   li.innerHTML = '<div class="buyer-item"><div currentuid="' + current + '"><p class="msg-content-box">hello</p></div></div>';
   document.querySelector('#msgListContainer ul').appendChild(li);
 }
 render();
 document.querySelectorAll('.chat-item-box').forEach(box => {
   let down = false;
   box.addEventListener('mousedown', e => { down = e.isTrusted; });
   box.addEventListener('mouseup', e => {
     if (down && e.isTrusted) { current = box.getAttribute('data-random').split('-')[0]; render(); }
     down = false;
   });
 });
 document.querySelector('.send-btn').addEventListener('click', e => {
   if (!e.isTrusted) return;
   const ta = document.querySelector('#replyTextarea');
   const li = document.createElement('li');
   li.className = 'onemsg'; li.id = 'middlePanel_list_' + (++n);
   li.innerHTML = '<div class="cs-item"><div currentuid="' + current + '"><p class="msg-content-box">' + ta.value + '</p></div></div>';
   document.querySelector('#msgListContainer ul').appendChild(li);
   ta.value = '';
 });
</script></body></html>"""


# The customer's store Chrome: our mouse events never count, keys and text do.
NO_MOUSE_PAGE = TRUSTED_ONLY_PAGE.replace(
    "document.querySelector('.send-btn').addEventListener('click', e => {",
    "document.querySelector('#replyTextarea').addEventListener('keydown', e => {\n   if (e.key !== 'Enter') return;"
).replace("box.addEventListener('mouseup'", "box.addEventListener('ecan-never'")


class TrustedInputTests(unittest.TestCase):
    """Real Chromium: the CDP send path works where synthetic events do not."""

    def _run(self, coro_fn, page_html=None):
        async def main():
            try:
                from playwright.async_api import async_playwright
            except Exception as exc:
                raise unittest.SkipTest(f"no playwright: {exc}")
            async with async_playwright() as pw:
                try:
                    browser = await pw.chromium.launch()
                except Exception as exc:
                    raise unittest.SkipTest(f"no Chromium: {exc}")
                page = await browser.new_page()
                await page.set_content(page_html or TRUSTED_ONLY_PAGE)
                session = await page.context.new_cdp_session(page)

                async def evaluate(js):
                    return await page.evaluate(js)

                async def cdp(method, params):
                    return await session.send(method, params)

                async def settle():
                    await asyncio.sleep(0.05)
                try:
                    return await coro_fn(page, evaluate, cdp, settle)
                finally:
                    await browser.close()
        return asyncio.run(main())

    def test_synthetic_send_is_ignored_like_the_real_page(self):
        async def go(page, evaluate, cdp, settle):
            return await dom.send_text(evaluate, "U2", "你好", settle=settle)       # no cdp
        out = self._run(go)
        self.assertFalse(out["ok"])
        self.assertIn("did not open", out["error"])

    def test_trusted_send_switches_types_and_sends(self):
        async def go(page, evaluate, cdp, settle):
            out = await dom.send_text(evaluate, "U3", '亲，在的哈 "quoted"', settle=settle, cdp=cdp)
            thread = json.loads(await evaluate(dom.THREAD_JS))
            return out, thread
        out, thread = self._run(go)
        self.assertTrue(out["ok"], out)
        self.assertTrue(out["cleared"])
        self.assertEqual(thread["uid"], "U3")
        self.assertEqual(thread["messages"][-1]["who"], "agent")
        self.assertEqual(thread["messages"][-1]["text"], '亲，在的哈 "quoted"')

    def test_trusted_send_clears_leftover_text(self):
        async def go(page, evaluate, cdp, settle):
            await page.fill("#replyTextarea", "old draft ")
            out = await dom.send_text(evaluate, "U1", "新回复", settle=settle, cdp=cdp)
            thread = json.loads(await evaluate(dom.THREAD_JS))
            return out, thread
        out, thread = self._run(go)
        self.assertTrue(out["ok"], out)
        self.assertEqual(thread["messages"][-1]["text"], "新回复")

class NoMouseTests(TrustedInputTests):
    """Clicks do nothing: the box is focused by script and Enter sends."""

    def test_trusted_send_switches_types_and_sends(self):
        pass

    def test_trusted_send_clears_leftover_text(self):
        pass

    def test_synthetic_send_is_ignored_like_the_real_page(self):
        pass

    def test_enter_sends_when_clicks_are_ignored(self):
        async def go(page, evaluate, cdp, settle):
            await evaluate("document.activeElement && document.activeElement.blur()")
            out = await dom.send_text(evaluate, "U1", "国庆有活动哦", settle=settle, cdp=cdp)
            thread = json.loads(await evaluate(dom.THREAD_JS))
            return out, thread
        out, thread = self._run(go, NO_MOUSE_PAGE)
        self.assertTrue(out["ok"], out)
        self.assertTrue(out["cleared"], out)
        self.assertEqual(thread["messages"][-1]["text"], "国庆有活动哦")
        self.assertNotIn("Enter did not send", out["diag"])

    def test_unopenable_conversation_reports_where_the_click_went(self):
        async def go(page, evaluate, cdp, settle):
            return await dom.send_text(evaluate, "U2", "x", settle=settle, cdp=cdp)
        out = self._run(go, NO_MOUSE_PAGE)
        self.assertFalse(out["ok"])
        self.assertIn("landed at", out["error"])

