"""Agents must get a usable browser-use LLM on a machine with no local LLM key.

2026-10-09 (platoon machine): mainwin.browser_use_llm was None (default provider
'ecanai' = llm-proxy, no API key), browser-use turned llm=None into its own
cloud model and raised "set BROWSER_USE_API_KEY", and every agent was dropped.
"""
import agent.ec_skills.build_node as bn
from agent.ec_agents.agent_utils import _session_proxy_browser_llm
from agent.ec_skills.browser_use_extension.lambda_proxy_llm import ChatLambdaProxy


def test_proxy_fallback_built_from_session(monkeypatch):
    monkeypatch.setattr(bn, "_get_proxy_config", lambda: {
        "endpoint": "https://proxy.example", "auth_token": "tok", "user_id": "u@x"})
    llm = _session_proxy_browser_llm()
    assert isinstance(llm, ChatLambdaProxy)
    assert llm.lambda_endpoint == "https://proxy.example" and llm.user_id == "u@x"


def test_no_proxy_config_gives_none(monkeypatch):
    monkeypatch.setattr(bn, "_get_proxy_config", lambda: {})
    assert _session_proxy_browser_llm() is None
