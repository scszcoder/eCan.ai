"""CN network guard for direct LLM calls (build_node).

95z live incident (2026-08-28): the QA skill's LLM node was configured
openai/gpt-4o-mini; the customer machine resolved a key, so the missing-key
proxy fallback did not engage, and the direct call to api.openai.com timed out
after 45s (unreachable from mainland China) — the customer turn died.

_cn_blocked_direct_llm decides when a CN build must route through the
llm-proxy instead of calling the provider's default endpoint directly.
"""

from unittest.mock import patch

from agent.ec_skills import build_node as bn


def _cn(value):
    return patch("utils.app_env.is_cn", return_value=value)


def test_blocked_default_provider_on_cn():
    with _cn(True):
        assert bn._cn_blocked_direct_llm("openai", "")
        assert bn._cn_blocked_direct_llm("anthropic", None)
        assert bn._cn_blocked_direct_llm("gemini", "")


def test_blocked_explicit_host_on_cn():
    with _cn(True):
        assert bn._cn_blocked_direct_llm("openai", "https://api.openai.com/v1")
        assert bn._cn_blocked_direct_llm("custom", "https://api.anthropic.com")


def test_reachable_providers_stay_direct_on_cn():
    with _cn(True):
        assert not bn._cn_blocked_direct_llm("deepseek", "https://api.deepseek.com")
        assert not bn._cn_blocked_direct_llm("qwen", "")
        assert not bn._cn_blocked_direct_llm("ollama", "http://localhost:11434")


def test_custom_relay_base_url_stays_direct_on_cn():
    # A user-configured relay for an openai-compatible provider is respected.
    with _cn(True):
        assert not bn._cn_blocked_direct_llm("openai", "https://my-relay.example.cn/v1")


def test_intl_builds_never_blocked():
    with _cn(False):
        assert not bn._cn_blocked_direct_llm("openai", "")
        assert not bn._cn_blocked_direct_llm("openai", "https://api.openai.com/v1")
