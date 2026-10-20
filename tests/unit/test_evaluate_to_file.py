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


def test_uncalled_function_is_called(tmp_path):
    # 2026-10-12: the planner sent `async () => {...}` without `()`; the
    # function object serialized to {} and nothing was collected
    results = iter([{"result": {"type": "function", "value": {}}},
                    {"result": {"type": "object", "value": {"total": 1, "parts": ["PIC16F1509"]}}}])
    session, calls = _session(None)

    async def evaluate(params, session_id):
        calls.append(params)
        return next(results)

    session_cdp = asyncio.run(session.get_or_create_cdp_session())
    session_cdp.cdp_client.send.Runtime.evaluate = evaluate
    params = EvaluateToFileAction(code="async () => ({total: 1})", path=str(tmp_path / "p.json"))
    out = asyncio.run(svc.evaluate_to_file(params=params, browser_session=session))
    assert out.error is None
    assert calls[1]["expression"] == "(async () => ({total: 1}))()"
    assert json.loads((tmp_path / "p.json").read_text(encoding="utf-8"))["parts"] == ["PIC16F1509"]


def test_bare_function_body_is_wrapped(tmp_path):
    # the planner's retry: a body with a top-level `return`
    results = iter([{"exceptionDetails": {"exception": {"description": "SyntaxError: Illegal return statement"}}},
                    {"result": {"type": "object", "value": ["PIC16F1509"]}}])
    session, calls = _session(None)

    async def evaluate(params, session_id):
        calls.append(params)
        return next(results)

    asyncio.run(session.get_or_create_cdp_session()).cdp_client.send.Runtime.evaluate = evaluate
    params = EvaluateToFileAction(code="const p = []; return p;", path=str(tmp_path / "p.json"))
    out = asyncio.run(svc.evaluate_to_file(params=params, browser_session=session))
    assert out.error is None
    assert calls[1]["expression"] == "(async () => {\nconst p = []; return p;\n})()"


def test_saved_script_is_reused_via_code_file(tmp_path):
    # the next category reuses the working collection script instead of retyping it
    script = tmp_path / "raw" / "collect_table.js"
    session, calls = _session({"result": {"type": "object", "value": {"total": 2, "parts": ["A", "B"]}}})
    first = EvaluateToFileAction(code="(async () => ({}))()", path=str(tmp_path / "a.json"), save_code_to=str(script))
    out = asyncio.run(svc.evaluate_to_file(params=first, browser_session=session))
    assert "parts: 2 items" in out.extracted_content and "saved" in out.extracted_content
    assert script.read_text(encoding="utf-8") == "(async () => ({}))()"
    again = EvaluateToFileAction(code_file=str(script), path=str(tmp_path / "b.json"))
    asyncio.run(svc.evaluate_to_file(params=again, browser_session=session))
    assert calls[1]["expression"] == "(async () => ({}))()"


def test_missing_code_is_rejected(tmp_path):
    session, _ = _session({"result": {"value": "x"}})
    out = asyncio.run(svc.evaluate_to_file(params=EvaluateToFileAction(path=str(tmp_path / "a.json")),
                                           browser_session=session))
    assert "code" in out.error


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


def test_args_are_passed_to_a_saved_script(tmp_path):
    # 2026-10-18: Infineon part pages have ~40k elements; the worker stays on a tiny page
    # and calls the saved collector with each part's URL
    script = tmp_path / "collect_docs.js"
    script.write_text("async (arg) => [arg.url]", encoding="utf-8")
    session, calls = _session({"result": {"type": "object", "value": ["https://x/part/A"]}})
    params = EvaluateToFileAction(code_file=str(script), args='{"url": "https://x/part/A"}', path=str(tmp_path / "a.json"))
    out = asyncio.run(svc.evaluate_to_file(params=params, browser_session=session))
    assert out.error is None and len(calls) == 1
    assert calls[0]["expression"] == '(async (arg) => [arg.url])({"url": "https://x/part/A"})'


def test_invalid_args_are_rejected(tmp_path):
    out, calls = _run({"result": {"value": "x"}}, tmp_path, args="{url: x}")
    assert "args is not valid JSON" in out.error and not calls


def test_args_sent_as_an_object_are_accepted():
    # models often send {"url": ...} as an object, not a JSON string
    params = EvaluateToFileAction(code_file="c.js", args={"url": "https://x/part/A"}, path="a.json")
    assert params.args == '{"url": "https://x/part/A"}'
