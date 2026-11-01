"""A reply with reasoning but no JSON is asked once more for the JSON alone,
instead of failing the step (claude-opus-4-8 escalation, 拼多多 run 87, KEN 11-01)."""
import asyncio

import httpx
import pytest
from pydantic import BaseModel

from agent.ec_skills.browser_use_extension import lambda_proxy_llm as m

HOST = "https://example.invalid/api/llm-proxy"


class Out(BaseModel):
    memory: str


def _run(replies):
    llm = m.ChatLambdaProxy(model="claude-opus-4-8", provider_name="eCanAI", user_id="u",
                            lambda_endpoint=HOST, auth_token="t", max_retries=1)
    sent = []

    def handler(request):
        import json
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": replies[len(sent) - 1]}}]})

    real = httpx.AsyncClient
    m.httpx.AsyncClient = lambda **kw: real(transport=httpx.MockTransport(handler))
    try:
        out = asyncio.run(llm._do_request(HOST, {}, {"model": llm.model, "messages": [{"role": "user", "content": "go"}]}, Out))
    finally:
        m.httpx.AsyncClient = real
    return out, sent


def test_reasoning_only_reply_is_asked_again_for_the_json():
    out, sent = _run(["<think>\nThe dropdown is open at [15066]. Let me click it.", '{"memory": "m"}'])
    assert out.completion.memory == "m"
    assert len(sent) == 2
    assert sent[1]["messages"][-2]["role"] == "assistant"
    assert sent[1]["messages"][-1]["content"] == m._JSON_ONLY_ASK


def test_asks_only_once():
    with pytest.raises(ValueError):
        _run(["still thinking", "still no json"])


def test_prose_around_json_is_repaired_without_a_second_call():
    out, sent = _run(['All 3 images uploaded.\n{"memory": "m"}'])
    assert out.completion.memory == "m" and len(sent) == 1
