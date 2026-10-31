"""The engineer-style explorer loop (agent/ec_skills/explorer)."""

import asyncio
import json

from agent.ec_skills.explorer import loop, tools


class FakePage:
    def __init__(self):
        self.network, self.closed, self.clicked = [], False, []

    async def url(self):
        return "https://fxg.jinritemai.com/ffa/g/create"

    async def evaluate(self, js, timeout=30):
        if "CLICK" in js or "scrollIntoView({ block: 'center' });\n  const r" in js:
            return {"x": 1, "y": 2, "label": "发布商品" if ("发布" in js or r"\u53d1\u5e03" in js) else "M", "tag": "button", "matches": 1}
        return {"ok": True}

    async def mouse_click(self, x, y):
        self.clicked.append((x, y))

    async def close(self):
        self.closed = True


class ScriptedLLM:
    def __init__(self, replies):
        self.replies, self.seen = list(replies), []

    async def ainvoke(self, messages):
        from langchain_core.messages import AIMessage
        self.seen.append(messages[-1].content)
        r = self.replies.pop(0)
        return AIMessage(content=r if isinstance(r, str) else json.dumps(r, ensure_ascii=False))


def _run(replies, monkeypatch, max_turns=6):
    page = FakePage()

    async def fake_open(port, start_url, reuse=""):
        return page
    monkeypatch.setattr(loop, "browser_port", lambda *a, **k: 9222)
    monkeypatch.setattr(loop.PageSession, "open", staticmethod(fake_open))
    llm = ScriptedLLM(replies)
    out = asyncio.run(loop.explore("task", start_url="https://x", domains=["jinritemai.com"], llm=llm,
                                   max_turns=max_turns))
    return out, llm, page


def test_done_ends_the_run_and_the_tab_is_closed(monkeypatch):
    out, llm, page = _run([{"thinking": "t", "calls": [], "done": {"part": "规格值", "script": ""}}], monkeypatch)
    assert json.loads(out["final"])["part"] == "规格值" and out["turns"] == 1 and page.closed


def test_a_reply_that_is_not_json_gets_a_retry(monkeypatch):
    out, llm, page = _run(["I think...", {"thinking": "t", "calls": [], "done": {"x": 1}}], monkeypatch)
    assert out["turns"] == 2 and "合法的 JSON 对象" in llm.seen[1]


def test_unknown_tools_and_publish_clicks_are_refused(monkeypatch):
    out, llm, page = _run([{"thinking": "t", "calls": [{"tool": "nope", "args": {}},
                                                       {"tool": "click", "args": {"text": "发布商品"}}]},
                           {"thinking": "t", "calls": [], "done": {"x": 1}}], monkeypatch)
    text = "\n".join(p["text"] for p in llm.seen[1] if p.get("type") == "text")
    assert "没有这个工具" in text and "拒绝" in text and page.clicked == []


def test_running_out_of_turns_is_reported(monkeypatch):
    out, llm, page = _run([{"thinking": "t", "calls": [{"tool": "wait", "args": {"seconds": 0}}]}] * 2,
                          monkeypatch, max_turns=2)
    assert out["final"] == "" and "without done" in out["error"]


def test_old_tool_results_are_elided_but_recent_ones_kept(monkeypatch):
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    monkeypatch.setattr(loop, "HISTORY_CHARS", 5000)
    msgs = [SystemMessage(content="s"), HumanMessage(content="task")]
    for k in range(20):
        msgs += [AIMessage(content=f"thinking {k}"), HumanMessage(content="x" * 1000)]
    loop._elide(msgs)
    assert msgs[1].content == "task" and msgs[-1].content == "x" * 1000
    assert any("已省略" in str(m.content) for m in msgs) and all("thinking" in m.content for m in msgs if isinstance(m, AIMessage))


def test_navigation_stays_on_the_platform():
    page = FakePage()
    text, _ = asyncio.run(tools.TOOLS["navigate"][1](page, {"url": "https://evil.example.com/"}, {"domains": ["jinritemai.com"]}))
    assert text.startswith("拒绝")


def test_scripts_that_click_publish_are_refused():
    text, _ = asyncio.run(tools.TOOLS["run_js"][1](FakePage(), {"code": "[...document.querySelectorAll('button')].find(b=>b.innerText==='发布商品').click()"}, {}))
    assert text.startswith("拒绝")


def test_a_turn_is_found_around_extra_text_and_second_objects():
    turn = {"thinking": "看一下", "calls": [{"tool": "snapshot", "args": {}}], "done": None}
    raw = json.dumps(turn, ensure_ascii=False)
    for text in (raw, "```json\n" + raw + "\n```", "好的。\n" + raw + "\n结果：{\"ok\": true}",
                 raw + "\n" + json.dumps({"thinking": "第二个", "calls": [], "done": None})):
        assert loop._parse(text)["thinking"] == "看一下", text
    assert loop._parse('{"type": "text"}') is None and loop._parse("没有 JSON") is None


def test_content_blocks_are_read_as_text():
    assert loop._text([{"type": "thinking", "thinking": "x"}, {"type": "text", "text": "{\"done\": 1}"}]) == '{"done": 1}'


def test_replies_outside_the_protocol_end_the_run_early(monkeypatch):
    out, llm, page = _run(["I think..."] * 10, monkeypatch, max_turns=60)
    assert out["turns"] == loop.MAX_BAD_REPLIES and "not a JSON turn" in out["error"] and page.closed


class JsPage(FakePage):
    """Statements in expression position are a SyntaxError, as in a browser."""
    def __init__(self):
        super().__init__()
        self.ran = []

    async def evaluate(self, js, timeout=30):
        self.ran.append(js)
        if js.startswith("(async()=>{ return (") and "const n" in js.split("return (", 1)[1].split("=>", 1)[0]:
            return "page error: SyntaxError: Unexpected token 'const'"
        return 8


def test_an_iife_with_an_inner_return_keeps_its_value():
    page = JsPage()
    text, _ = asyncio.run(tools.TOOLS["run_js"][1](page, {"code": "(() => { const r = 8; return r; })()"}, {}))
    assert text == "8" and len(page.ran) == 1 and page.ran[0].startswith("(async()=>{ return (")


def test_a_function_body_still_runs():
    page = JsPage()
    text, _ = asyncio.run(tools.TOOLS["run_js"][1](page, {"code": "const n = 8; return n;"}, {}))
    assert text == "8" and len(page.ran) == 2 and not page.ran[1].startswith("(async()=>{ return (")


def test_every_turn_is_a_sign_of_life_for_the_runner(monkeypatch):
    ticks = []
    monkeypatch.setattr(loop, "note_task_progress", lambda *a, **k: ticks.append(1))
    _run([{"thinking": "t", "calls": [{"tool": "wait", "args": {"seconds": 0}}]}] * 3, monkeypatch, max_turns=3)
    assert len(ticks) == 3


def test_a_page_that_stops_answering_does_not_end_the_run(monkeypatch):
    class Wedged(FakePage):
        n = 0

        async def url(self):
            self.n += 1
            if self.n > 1:                       # fine at the start, then stops answering
                raise asyncio.TimeoutError()
            return "https://x"
    page = Wedged()

    async def fake_open(port, start_url, reuse=""):
        return page
    monkeypatch.setattr(loop, "browser_port", lambda *a, **k: 9222)
    monkeypatch.setattr(loop.PageSession, "open", staticmethod(fake_open))
    llm = ScriptedLLM([{"thinking": "t", "calls": [{"tool": "wait", "args": {"seconds": 0}}]},
                       {"thinking": "t", "calls": [], "done": {"x": 1}}])
    out = asyncio.run(loop.explore("task", start_url="https://x", domains=["jinritemai.com"], llm=llm, max_turns=3))
    assert out["error"] == "" and "页面没有响应" in llm.seen[1][-1]["text"]


def test_other_records_are_never_opened():
    class P(FakePage):
        async def navigate(self, url):
            return url
    page = P()
    nav = lambda url, own=(): asyncio.run(tools.TOOLS["navigate"][1](page, {"url": url}, {"domains": ["jinritemai.com", "pinduoduo.com"], "own_ids": list(own)}))[0]
    assert nav("https://fxg.jinritemai.com/ffa/g/edit?product_id=3826533688146002286").startswith("拒绝")   # KEN run 72
    assert nav("https://mms.pinduoduo.com/goods/goods_list?goods_id=1023552315313").startswith("拒绝")
    assert not nav("https://fxg.jinritemai.com/ffa/g/create?product_id=3851155447138615457", own=["3851155447138615457"]).startswith("拒绝")
    assert not nav("https://fxg.jinritemai.com/ffa/g/create").startswith("拒绝")


def test_scripts_may_read_but_not_write_through_requests():
    w = tools.script_writes
    assert w("const r = await fetch('/product/tproduct/list', {method:'POST'}); return r.status") == ""
    assert w("await fetch('/product/tproduct/save', {method:'POST'})")
    assert w("await fetch('https://mms.pinduoduo.com/vodka/v2/mms/edit/commit')")
    assert w("await fetch(url)")                     # an address it cannot see is not trusted
    assert w("document.title") == "" and w("prefetchData()") == ""
    text, _ = asyncio.run(tools.TOOLS["run_js"][1](FakePage(), {"code": "await fetch('/product/save',{method:'POST'})"}, {}))
    assert text.startswith("拒绝")


def test_only_the_products_own_files_can_be_uploaded():
    class P(FakePage):
        async def set_files(self, selector, paths):
            self.set = (selector, paths)
            return {"files": len(paths)}
    page = P()
    ctx = {"files": {"main_1.png": r"C:\inbox\main_1.png"}}
    run = lambda names: asyncio.run(tools.TOOLS["upload"][1](page, {"selector": "input[type=file]", "names": names}, ctx))[0]
    assert run(["C:/Windows/win.ini"]).startswith("拒绝")
    assert '"files": 1' in run(["main_1.png"]) and page.set == ("input[type=file]", [r"C:\inbox\main_1.png"])


def _run_page(page, llm, monkeypatch, max_turns=3, **kw):
    async def fake_open(port, start_url, reuse=""):
        return page
    monkeypatch.setattr(loop, "browser_port", lambda *a, **k: 9222)
    monkeypatch.setattr(loop.PageSession, "open", staticmethod(fake_open))
    return asyncio.run(loop.explore("task", start_url="https://x", domains=["jinritemai.com"], llm=llm,
                                    max_turns=max_turns, **kw))


def test_a_click_that_lands_on_another_product_goes_straight_back(monkeypatch):
    class P(FakePage):
        where = "https://fxg.jinritemai.com/ffa/g/create"

        async def url(self):
            return self.where

        async def mouse_click(self, x, y):
            self.where = "https://fxg.jinritemai.com/ffa/g/edit?product_id=3826533688146002286"

        async def evaluate(self, js, timeout=30):
            if js == "history.back()":
                self.where = "https://fxg.jinritemai.com/ffa/g/create"
                return None
            return await super().evaluate(js, timeout)
    page = P()
    llm = ScriptedLLM([{"thinking": "t", "calls": [{"tool": "click", "args": {"text": "M"}}]},
                       {"thinking": "t", "calls": [], "done": {"x": 1}}])
    _run_page(page, llm, monkeypatch)
    text = "\n".join(p["text"] for p in llm.seen[1] if p.get("type") == "text")
    assert "3826533688146002286" in text and "退回" in text and page.where.endswith("/create")


def test_a_model_call_that_never_returns_does_not_hang_the_run(monkeypatch):
    class Silent:
        async def ainvoke(self, messages):
            await asyncio.sleep(10)
    monkeypatch.setattr(loop, "LLM_TIMEOUT_SEC", 0.05)
    out = _run_page(FakePage(), Silent(), monkeypatch, max_turns=5)
    assert "did not reply" in out["error"] and out["turns"] == loop.MAX_BAD_REPLIES


def test_screenshots_cost_what_the_model_pays_and_old_results_keep_a_gist():
    from langchain_core.messages import HumanMessage, SystemMessage
    shot = {"type": "image_url", "image_url": {"url": "data:image/png;base64," + "A" * 400_000}}
    assert loop._size([shot]) == loop.IMAGE_CHARS
    big = "[1] snapshot()\nbody 商品标题 输入框 " + "x" * 200_000
    msgs = [SystemMessage(content="s"), HumanMessage(content="task")] + \
           [HumanMessage(content=[{"type": "text", "text": big}, shot]) for _ in range(12)]
    loop._elide(msgs)
    first = msgs[2].content
    assert isinstance(first, str) and "商品标题" in first and len(first) < 2000
    assert isinstance(msgs[-1].content, list)            # the recent ones stay whole


def test_the_draft_list_is_not_a_forbidden_button():
    assert not tools.FORBIDDEN.search("草稿箱") and tools.FORBIDDEN.search("存草稿")


class CompactingLLM(ScriptedLLM):
    """Answers summary requests with a summary, everything else from the script."""
    def __init__(self, replies, summary="已确认：规格表在 form.spec_detail；尺码组开关会弹顺序对话框，点取消后开关不变。下一步：直接写 spec_detail。"):
        super().__init__(replies)
        self.summary, self.summaries = summary, 0

    async def ainvoke(self, messages):
        from langchain_core.messages import AIMessage
        if messages and loop.SUMMARY_SYSTEM in str(messages[0].content):
            self.summaries += 1
            self.summary_source = messages[-1].content
            return AIMessage(content=self.summary)
        return await super().ainvoke(messages)


def test_a_long_exploration_is_compacted_into_a_summary_the_model_wrote(monkeypatch):
    monkeypatch.setattr(loop, "COMPACT_AT_CHARS", 3_000)
    monkeypatch.setattr(loop, "KEEP_RECENT_TURNS", 2)

    class Big(FakePage):
        async def evaluate(self, js, timeout=30):
            return {"rows": "x" * 2_000}
    turn = {"thinking": "读一下", "calls": [{"tool": "run_js", "args": {"code": "1"}}]}
    llm = CompactingLLM([turn] * 6 + [{"thinking": "t", "calls": [], "done": {"x": 1}}])
    out = _run_page(Big(), llm, monkeypatch, max_turns=8)
    assert out["error"] == "" and llm.summaries >= 1
    last = llm.seen[-1]                                   # the model still sees the latest results whole
    assert isinstance(last, list)
    assert "【你】" in llm.summary_source and "【工具结果】" in llm.summary_source


def test_the_summary_lands_under_the_task_and_older_turns_go(monkeypatch):
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    monkeypatch.setattr(loop, "COMPACT_AT_CHARS", 1_000)
    monkeypatch.setattr(loop, "KEEP_RECENT_TURNS", 2)
    msgs = [SystemMessage(content="s"), HumanMessage(content="TASK")]
    for k in range(6):
        msgs += [AIMessage(content=f"turn {k}"), HumanMessage(content=[{"type": "text", "text": "r" * 500}])]
    llm = CompactingLLM([])
    state = {}
    assert asyncio.run(loop._compact(llm, msgs, "TASK", state))
    assert msgs[1].content.startswith("TASK") and llm.summary in msgs[1].content
    assert [m.content for m in msgs if isinstance(m, AIMessage)] == ["turn 4", "turn 5"]
    assert state["n"] == 1


def test_a_failed_summary_falls_back_to_eliding(monkeypatch):
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    monkeypatch.setattr(loop, "COMPACT_AT_CHARS", 1_000)
    msgs = [SystemMessage(content="s"), HumanMessage(content="TASK")]
    for k in range(10):
        msgs += [AIMessage(content=f"turn {k}"), HumanMessage(content=[{"type": "text", "text": "r" * 500}])]

    class Broken:
        async def ainvoke(self, messages):
            raise RuntimeError("proxy down")
    assert asyncio.run(loop._compact(Broken(), msgs, "TASK", {})) is False
    assert len(msgs) == 22                                # untouched; the caller elides


def _draft_page(created):
    class P(FakePage):
        where = "https://mms.pinduoduo.com/goods/category"

        def __init__(self):
            super().__init__()
            self.network = [{"id": "1", "url": "https://mms.pinduoduo.com/glide/v2/mms/edit/commit/create_new"}] if created else []

        async def response_body(self, rid):
            return '{"success":true,"result":{"goods_commit_id":205099994178}}'

        async def url(self):
            return self.where

        async def mouse_click(self, x, y):         # 下一步 opens the new draft
            self.where = "https://mms.pinduoduo.com/goods/goods_add/index?type=add&id=205099994178"

        async def evaluate(self, js, timeout=30):
            if js == "history.back()":
                self.where = "https://mms.pinduoduo.com/goods/category"
                return None
            return await super().evaluate(js, timeout)
    return P()


def test_a_draft_this_exploration_created_is_its_own(monkeypatch):
    # 拼多多 KEN 11-01: 下一步 creates a goods draft and opens it; the guard sent the
    # explorer back from its own draft every time, so step 2 was never reached.
    page = _draft_page(created=True)
    llm = ScriptedLLM([{"thinking": "t", "calls": [{"tool": "click", "args": {"text": "M"}}]},
                       {"thinking": "t", "calls": [], "done": {"x": 1}}])
    out = _run_page(page, llm, monkeypatch)
    assert out["created"] == ["205099994178"] and "goods_add" in page.where


def test_a_record_nobody_here_created_is_still_left(monkeypatch):
    page = _draft_page(created=False)
    llm = ScriptedLLM([{"thinking": "t", "calls": [{"tool": "click", "args": {"text": "M"}}]},
                       {"thinking": "t", "calls": [], "done": {"x": 1}}])
    out = _run_page(page, llm, monkeypatch)
    assert out["created"] == [] and page.where.endswith("/goods/category")
