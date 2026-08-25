"""Missing-local-API-key → cloud LLM proxy fallback (2026-08-27).

Previously the proxy was used only when explicitly enabled
(ECAN_FORCE_LAMBDA_PROXY / node useProxy / global use_lambda_proxy);
a missing local key raised "<provider> requires an API key" even when a
proxy endpoint was configured. Now every LLM-construction path falls
back to the proxy when the local key/config is missing AND a proxy
endpoint is configured; without one, the original error still raises.
"""

from unittest.mock import MagicMock, patch

import pytest

import agent.ec_tasks  # noqa: F401  (import-order guard)
from agent.ec_skills.browser_node import runner as br


PROXY_CFG = {"endpoint": "https://proxy.example/llm", "auth_token": "tok", "user_id": "u@x"}


class _FakeProxyLLM:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


@pytest.fixture()
def _fake_proxy_class():
    import agent.ec_skills.browser_use_extension.lambda_proxy_llm as lpl
    with patch.object(lpl, "ChatLambdaProxy", _FakeProxyLLM):
        yield


class TestBuildLocalLlmFallback:
    def _call(self, proxy_cfg, node_exc=ValueError("openai requires an API key")):
        with patch.object(br, "_should_use_proxy", return_value=False), \
             patch.object(br, "_get_proxy_config", return_value=proxy_cfg), \
             patch.object(br, "_build_local_llm_from_node_config_impl", side_effect=node_exc):
            return br.build_local_llm(
                MagicMock(), llm_provider="openai", llm_model_name="gpt-4o", raw_inputs={},
            )

    def test_missing_key_falls_back_to_proxy(self, _fake_proxy_class):
        llm = self._call(PROXY_CFG)
        assert isinstance(llm, _FakeProxyLLM)
        assert llm.kwargs["lambda_endpoint"] == PROXY_CFG["endpoint"]
        assert llm.kwargs["provider_name"] == "openai"

    def test_no_proxy_configured_reraises(self):
        with pytest.raises(ValueError, match="requires an API key"):
            self._call({})

    def test_healthy_node_llm_untouched(self):
        sentinel = object()
        with patch.object(br, "_should_use_proxy", return_value=False), \
             patch.object(br, "_get_proxy_config", return_value=PROXY_CFG), \
             patch.object(br, "_build_local_llm_from_node_config_impl", return_value=sentinel):
            llm = br.build_local_llm(
                MagicMock(), llm_provider="openai", llm_model_name="gpt-4o", raw_inputs={},
            )
        assert llm is sentinel  # proxy NOT used when local config works


class TestBuildCloudLlmFallback:
    def test_node_branch_runtime_error_falls_back(self, _fake_proxy_class):
        with patch.object(br, "_should_use_proxy", return_value=False), \
             patch.object(br, "_get_proxy_config", return_value=PROXY_CFG), \
             patch.object(br, "_build_cloud_llm_from_node_config_impl",
                          side_effect=RuntimeError("No API key configured")):
            llm = br._build_cloud_llm_impl(
                llm_provider="deepseek", llm_model_name="deepseek-chat", raw_inputs={},
            )
        assert isinstance(llm, _FakeProxyLLM)
        assert llm.kwargs["provider_name"] == "deepseek"

    def test_node_branch_no_proxy_reraises(self):
        with patch.object(br, "_should_use_proxy", return_value=False), \
             patch.object(br, "_get_proxy_config", return_value={}), \
             patch.object(br, "_build_cloud_llm_from_node_config_impl",
                          side_effect=RuntimeError("No API key configured")):
            with pytest.raises(RuntimeError, match="No API key"):
                br._build_cloud_llm_impl(
                    llm_provider="deepseek", llm_model_name="deepseek-chat", raw_inputs={},
                )


class TestBuildNodeSourceContract:
    """build_node's _build_runtime_llm is a deep closure — assert the
    missing-key branch tries the proxy before raising, at source level."""

    def test_missing_key_branch_tries_proxy_first(self):
        from pathlib import Path
        src = Path("agent/ec_skills/build_node.py").read_text(encoding="utf-8")
        idx = src.find('requires_api_key") and not api_key_value')
        assert idx != -1
        window = src[idx:idx + 600]
        proxy_pos = window.find('_make_proxy_llm("no local API key")')
        raise_pos = window.find("raise ValueError")
        assert proxy_pos != -1, "missing-key branch no longer tries the proxy"
        assert raise_pos != -1 and proxy_pos < raise_pos, \
            "proxy fallback must be attempted BEFORE raising the missing-key error"
