"""evaluate_to_file: page-script results go straight to disk, not through the model.

2026-10-12: the crawl planner paged Microchip's 766-part 8-bit PIC table one
screen at a time (~34 s per browser-use step, 5-10 min per 40 parts) and had to
retype every row into its replies, which broke its JSON.
"""
import asyncio
import json
from types import SimpleNamespace

from agent.ec_skills.browser_use_extension import extension_tools_service as svc
from agent.ec_skills.browser_use_extension.extension_tools_views import EvaluateToFileAction


def _session(result):
    calls = []

    async def evaluate(params, session_id):
        calls.append(params)
        return result

    cdp = SimpleNamespace(cdp_client=SimpleNamespace(send=SimpleNamespace(Runtime=SimpleNamespace(evaluate=evaluate))),
                          session_id="s1")

    async def get_or_create_cdp_session():
        return cdp

    return SimpleNamespace(get_or_create_cdp_session=get_or_create_cdp_session), calls


def _run(result, tmp_path, **kw):
    session, calls = _session(result)
    params = EvaluateToFileAction(code="(async () => [])()", path=str(tmp_path / "out" / "parts.json"), **kw)
    return asyncio.run(svc.evaluate_to_file(params=params, browser_session=session)), calls


def test_list_result_is_written_as_json(tmp_path):
    out, calls = _run({"result": {"value": ["PIC16F13214", "PIC16F13254"]}}, tmp_path)
    assert out.error is None
    assert "2 items" in out.extracted_content
    assert json.loads((tmp_path / "out" / "parts.json").read_text(encoding="utf-8")) == ["PIC16F13214", "PIC16F13254"]
    assert calls[0]["awaitPromise"] and calls[0]["returnByValue"]


def test_append_adds_one_entry_per_call(tmp_path):
    _run({"result": {"value": "a,b"}}, tmp_path)
    _run({"result": {"value": "c,d"}}, tmp_path, append=True)
    assert (tmp_path / "out" / "parts.json").read_text(encoding="utf-8") == "a,b\nc,d"


def test_js_error_writes_nothing(tmp_path):
    out, _ = _run({"exceptionDetails": {"text": "Uncaught", "exception": {"description": "TypeError: x is null"}}},
                  tmp_path)
    assert "TypeError: x is null" in out.error
    assert not (tmp_path / "out" / "parts.json").exists()


def test_relative_path_is_rejected(tmp_path):
    session, _ = _session({"result": {"value": "x"}})
    params = EvaluateToFileAction(code="1", path="parts.json")
    out = asyncio.run(svc.evaluate_to_file(params=params, browser_session=session))
    assert "absolute" in out.error
