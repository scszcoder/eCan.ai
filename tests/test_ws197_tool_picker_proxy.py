"""ws197: the tool picker LLM (_get_chat_llm) routes through the llm-proxy when
enabled, so its spend is tracked + attributed (previously it hit OpenAI directly
with the user's own key — invisible to billing)."""

import agent.ec_skills.build_node as bn
import agent.ec_skills.lambda_proxy_langchain as lpl


def test_tool_picker_uses_proxy_when_enabled(monkeypatch):
    monkeypatch.setattr(bn, "_should_use_proxy", lambda *a, **k: True)
    monkeypatch.setattr(bn, "_cn_llm_proxy_by_default", lambda *a, **k: False)
    monkeypatch.setattr(bn, "_get_proxy_config",
                        lambda: {"user_id": "u1", "endpoint": "https://x", "auth_token": "tok"})
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return "PROXY_LLM"

    monkeypatch.setattr(lpl, "create_lambda_proxy_langchain", fake_create)
    llm = bn._get_chat_llm("gpt-4o-mini", 0.0)
    assert llm == "PROXY_LLM"
    assert captured["provider"] == "openai"
    assert captured["model"] == "gpt-4o-mini"
    assert captured["user_id"] == "u1"
    assert captured["lambda_endpoint"] == "https://x"


def test_tool_picker_falls_back_to_direct_when_proxy_off(monkeypatch):
    monkeypatch.setattr(bn, "_should_use_proxy", lambda *a, **k: False)
    monkeypatch.setattr(bn, "_cn_llm_proxy_by_default", lambda *a, **k: False)
    monkeypatch.setattr(bn, "get_current_username", lambda: "user1")
    # no key in secure store -> raises (proves it took the direct branch, not proxy)
    monkeypatch.setattr(bn.secure_store, "get", lambda *a, **k: "")
    import pytest
    with pytest.raises(Exception):
        bn._get_chat_llm("gpt-4o-mini", 0.0)
