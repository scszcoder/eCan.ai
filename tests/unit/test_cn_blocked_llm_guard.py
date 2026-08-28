"""CN default LLM routing policy (build_node._cn_llm_proxy_by_default).

2026-08-28 user decision after the 95z run (openai/gpt-4o-mini direct call from
the customer machine timed out on api.openai.com after 45s): on CN builds ALL
model providers route through the llm-proxy by default; the exceptions that
stay direct are ollama / private-server hosts and explicit node-level useProxy
values. Intl builds are unchanged.
"""

from unittest.mock import patch

from agent.ec_skills import build_node as bn


def _cn(value):
    return patch("utils.app_env.is_cn", return_value=value)


def test_all_cloud_providers_default_to_proxy_on_cn():
    with _cn(True):
        assert bn._cn_llm_proxy_by_default("openai", "")
        assert bn._cn_llm_proxy_by_default("anthropic", None)
        assert bn._cn_llm_proxy_by_default("gemini", "")
        assert bn._cn_llm_proxy_by_default("deepseek", "https://api.deepseek.com")
        assert bn._cn_llm_proxy_by_default("qwen", "")


def test_ollama_stays_direct_on_cn():
    with _cn(True):
        assert not bn._cn_llm_proxy_by_default("ollama", "")
        assert not bn._cn_llm_proxy_by_default("Ollama", "http://localhost:11434")


def test_private_server_hosts_stay_direct_on_cn():
    with _cn(True):
        assert not bn._cn_llm_proxy_by_default("openai", "http://localhost:8000/v1")
        assert not bn._cn_llm_proxy_by_default("openai", "http://127.0.0.1:1234/v1")
        assert not bn._cn_llm_proxy_by_default("openai", "http://192.168.1.20:8000/v1")
        assert not bn._cn_llm_proxy_by_default("openai", "http://10.0.0.5:8000")


def test_explicit_node_useproxy_value_respected():
    # useProxy=true is honored upstream by _should_use_proxy; =false is an
    # explicit opt-out. Either way, the default policy stands down.
    with _cn(True):
        off = {"useProxy": {"content": "false"}}
        on = {"useProxy": {"content": "true"}}
        assert not bn._cn_llm_proxy_by_default("openai", "", off)
        assert not bn._cn_llm_proxy_by_default("openai", "", on)
        assert bn._cn_llm_proxy_by_default("openai", "", {"useProxy": {"content": None}})


def test_intl_builds_unchanged():
    with _cn(False):
        assert not bn._cn_llm_proxy_by_default("openai", "")
        assert not bn._cn_llm_proxy_by_default("deepseek", "")
        assert not bn._cn_llm_proxy_by_default("openai", "https://api.openai.com/v1")
