"""ws197: llm_proxy calls carry X-Ecan-* attribution (agent/task/skill/vehicle)
read from the log scope AT REQUEST TIME (race-safe for the cached, shared LLM
instance), as HEADERS (never body, so they can't leak to a model vendor)."""

from utils import log_scope as ls


def test_attribution_headers_from_scope():
    with ls.scope(agent_id="agent_abc", agent_name="前台小张", task_id="t1",
                  skill_name="飞鸽客服问答00", skill_id="pr-287230", vehicle_id="SCHOME:win"):
        h = ls.attribution_headers()
    assert h["X-Ecan-Agent-Id"] == "agent_abc"
    assert h["X-Ecan-Task-Id"] == "t1"
    assert h["X-Ecan-Skill-Id"] == "pr-287230"     # raw, exact-matchable
    assert h["X-Ecan-Vehicle-Id"] == "SCHOME:win"  # colon kept (valid header value)
    assert h["X-Ecan-Source"].startswith("%")      # non-latin-1 name percent-encoded
    # every value must be a valid latin-1 HTTP header value (won't crash httpx)
    for v in h.values():
        v.encode("latin-1")


def test_no_scope_no_headers():
    assert ls.attribution_headers() == {}


def test_partial_scope_only_present_ids():
    with ls.scope(agent_id="agent_x"):
        h = ls.attribution_headers()
    assert h == {"X-Ecan-Agent-Id": "agent_x"}


def test_openai_proxy_build_headers_includes_attribution():
    from agent.ec_skills.browser_use_extension.lambda_proxy_llm import ChatLambdaProxy
    c = ChatLambdaProxy.__new__(ChatLambdaProxy)   # skip heavy __init__
    c.user_id = "u1"
    c.auth_token = "tok"
    c._token_refresh_fn = None
    with ls.scope(agent_id="agent_abc", task_id="t1", skill_id="pr-1"):
        hdrs = c._build_headers()
    assert hdrs["X-User-Id"] == "u1"
    assert hdrs["X-Ecan-Agent-Id"] == "agent_abc"
    assert hdrs["X-Ecan-Task-Id"] == "t1"
    assert hdrs["X-Ecan-Skill-Id"] == "pr-1"


def test_langchain_request_hook_injects_headers():
    import httpx
    from agent.ec_skills.lambda_proxy_langchain import _apply_attribution_headers
    req = httpx.Request("POST", "https://x/v1/chat/completions")
    with ls.scope(agent_id="agent_abc", skill_id="pr-1"):
        _apply_attribution_headers(req)
    assert req.headers["X-Ecan-Agent-Id"] == "agent_abc"
    assert req.headers["X-Ecan-Skill-Id"] == "pr-1"
