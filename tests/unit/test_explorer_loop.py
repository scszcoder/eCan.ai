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
