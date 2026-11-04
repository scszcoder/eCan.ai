"""prompt_refs.start_clicks: texts clicked once the start page shows them
(抖店 返回旧版, KEN 11-02 runs 90/94)."""
import asyncio

from browser_use.agent.views import ActionResult

from agent.ec_skills.browser_node import runner
from agent.ec_skills.browser_use_extension import extension_tools_service as ets


def _run(monkeypatch, state, replies):
    calls = []

    async def fake(session, text, nth=0):
        calls.append(text)
        return replies.pop(0) if replies else ActionResult(extracted_content="Clicked")

    async def no_sleep(_):
        return None
    monkeypatch.setattr(ets, "click_by_text", fake)
    monkeypatch.setattr(runner.asyncio, "sleep", no_sleep)
    asyncio.run(runner.run_start_clicks(object(), state, wait_s=5))
    return calls


def test_nothing_to_click_without_start_clicks(monkeypatch):
    assert _run(monkeypatch, {"prompt_refs": {"start_url": "x"}}, []) == []


def test_waits_until_the_text_shows(monkeypatch):
    replies = [ActionResult(error="click_text: no visible element"), ActionResult(extracted_content="Clicked")]
    calls = _run(monkeypatch, {"prompt_refs": {"start_clicks": ["返回旧版"]}}, replies)
    assert calls == ["返回旧版", "返回旧版"]


def test_gives_up_when_the_text_never_shows(monkeypatch):
    t = iter(range(0, 1000, 3))
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(t))
    calls = _run(monkeypatch, {"prompt_refs": {"start_clicks": ["返回旧版"]}},
                 [ActionResult(error="no visible element")] * 50)
    assert 1 < len(calls) < 5
