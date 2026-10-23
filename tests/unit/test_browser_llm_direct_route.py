"""Browser-agent steps over the gateway's ~100 KB limit go on the direct route
(2026-10-23 KEN: every 抖店商品导出 step carried a screenshot -> 413
EXCEED_MAX_PAYLOAD_SIZE, the export never ran)."""
import asyncio

from browser_use.llm.messages import UserMessage

from agent.ec_skills.browser_use_extension.lambda_proxy_llm import ChatLambdaProxy

HOST = "https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/api/llm-proxy"


def _urls(text):
    llm = ChatLambdaProxy(model="gpt-5.4", provider_name="openai", user_id="u", lambda_endpoint=HOST,
                          auth_token="t", max_retries=1)
    seen = []

    async def fake(url, headers, payload, output_format):
        seen.append(url)
        return "ok"
    llm._do_request = fake
    asyncio.run(llm.ainvoke([UserMessage(content=text)]))
    return seen


def test_a_screenshot_sized_step_goes_on_the_direct_route():
    assert _urls("x" * (200 * 1024)) == [HOST + "-b/v1/chat/completions"]


def test_a_small_step_stays_on_the_normal_route():
    assert _urls("点击商品管理") == [HOST + "/v1/chat/completions"]
