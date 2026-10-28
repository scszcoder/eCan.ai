"""qwen runs in thinking mode on the llm-proxy unless the caller turns it off;
browser steps took 20-75 s each on KEN (10-27) from hidden reasoning."""
import asyncio

from browser_use.llm.messages import UserMessage

from agent.ec_skills.browser_use_extension.lambda_proxy_llm import ChatLambdaProxy

HOST = "https://example.invalid/api/llm-proxy"


def _payload(model):
    llm = ChatLambdaProxy(model=model, provider_name="eCanAI", user_id="u", lambda_endpoint=HOST,
                          auth_token="t", max_retries=1)
    seen = []

    async def fake(url, headers, payload, output_format):
        seen.append(payload)
        return "ok"
    llm._do_request = fake
    asyncio.run(llm.ainvoke([UserMessage(content="点击商品管理")]))
    return seen[0]


def test_qwen_calls_turn_thinking_off():
    assert _payload("qwen3.8-flash")["enable_thinking"] is False


def test_other_models_get_no_dashscope_field():
    assert "enable_thinking" not in _payload("gpt-5.4")
