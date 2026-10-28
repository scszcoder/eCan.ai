"""Prompt caching for browser steps: the run's task sits at the end of the system
message (the same on every step) instead of after the per-step history, the
system message is marked for the provider's explicit cache, and both can be
turned off; a rejected marker turns itself off and the call goes through."""
import asyncio
from types import SimpleNamespace

import httpx
from browser_use.llm.messages import SystemMessage, UserMessage

import agent.ec_skills.browser_use_extension.lambda_proxy_llm as lp
from agent.ec_skills.browser_node.agent import TASK_POINTER, pin_task_in_system_message
from agent.ec_skills.browser_use_extension.lambda_proxy_llm import ChatLambdaProxy

HOST = "https://example.invalid/api/llm-proxy"


def _agent(task, system="browser-use system prompt"):
    sys_msg = SimpleNamespace(content=system)
    return SimpleNamespace(_message_manager=SimpleNamespace(task=task, state=SimpleNamespace(
        history=SimpleNamespace(system_message=sys_msg))))


def test_the_task_moves_to_the_end_of_the_system_message():
    a = _agent("发布 ECC2610")
    assert pin_task_in_system_message(a) is True
    assert a._message_manager.state.history.system_message.content.endswith("<user_request>\n发布 ECC2610\n</user_request>")
    assert a._message_manager.task == TASK_POINTER


def test_a_reused_agent_carries_only_the_new_task():
    a = _agent("发布 ECC2610")
    pin_task_in_system_message(a)
    a._message_manager.task = "发布 ECS2611"          # reset_bu_agent_for_next_round sets the next run's task
    pin_task_in_system_message(a)
    content = a._message_manager.state.history.system_message.content
    assert "ECS2611" in content and "ECC2610" not in content


def test_the_pin_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("ECAN_BROWSER_TASK_IN_SYSTEM", "0")
    a = _agent("发布 ECC2610")
    assert pin_task_in_system_message(a) is False and a._message_manager.task == "发布 ECC2610"


def _call(model, fail_first=None):
    llm = ChatLambdaProxy(model=model, provider_name="eCanAI", user_id="u", lambda_endpoint=HOST,
                          auth_token="t", max_retries=1)
    sent = []

    async def fake(url, headers, payload, output_format):
        sent.append(repr(payload["messages"][0]["content"]))
        if fail_first and len(sent) == 1:
            req = httpx.Request("POST", url)
            raise httpx.HTTPStatusError("bad", request=req, response=httpx.Response(fail_first, request=req,
                                                                                     text="unknown field cache_control"))
        return "ok"
    llm._do_request = fake
    out = asyncio.run(llm.ainvoke([SystemMessage(content="system prompt + task"), UserMessage(content="page")]))
    return out, sent


def test_qwen_marks_the_system_message_for_the_cache(monkeypatch):
    monkeypatch.setattr(lp, "_explicit_cache_rejected", False)
    _, sent = _call("qwen3.8-flash")
    assert "cache_control" in sent[0] and "system prompt + task" in sent[0]


def test_other_models_and_the_off_switch_send_no_marker(monkeypatch):
    monkeypatch.setattr(lp, "_explicit_cache_rejected", False)
    assert "cache_control" not in _call("gpt-5.4")[1][0]
    monkeypatch.setenv("ECAN_LLM_EXPLICIT_CACHE", "0")
    assert "cache_control" not in _call("qwen3.8-flash")[1][0]


def test_a_rejected_marker_turns_itself_off_and_the_call_goes_through(monkeypatch):
    monkeypatch.setattr(lp, "_explicit_cache_rejected", False)
    out, sent = _call("qwen3.8-flash", fail_first=400)
    assert out == "ok" and "cache_control" in sent[0] and "cache_control" not in sent[1]
    assert lp._explicit_cache_rejected is True
    assert "cache_control" not in _call("qwen3.8-flash")[1][0]      # stays off for the session


def test_usage_reports_cache_reads_and_writes():
    u = ChatLambdaProxy._extract_usage({"usage": {"prompt_tokens": 24000, "completion_tokens": 400, "total_tokens": 24400,
                                                  "prompt_tokens_details": {"cached_tokens": 12000,
                                                                            "cache_creation_input_tokens": 0}}})
    assert u.prompt_cached_tokens == 12000 and u.prompt_cache_creation_tokens == 0
    assert ChatLambdaProxy._extract_usage({"usage": {"prompt_tokens": 1, "prompt_tokens_details": None}}).prompt_cached_tokens is None
