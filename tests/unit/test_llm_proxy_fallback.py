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

    def test_healthy_node_llm_untouched_intl(self):
        # Intl builds: a healthy local node LLM is used directly. (On CN builds
        # the 2026-08-28 default-routing policy sends it to the proxy instead —
        # see test_cn_default_routes_healthy_node_llm_to_proxy.)
        sentinel = object()
        with patch("utils.app_env.is_cn", return_value=False), \
             patch.object(br, "_should_use_proxy", return_value=False), \
             patch.object(br, "_get_proxy_config", return_value=PROXY_CFG), \
             patch.object(br, "_build_local_llm_from_node_config_impl", return_value=sentinel):
            llm = br.build_local_llm(
                MagicMock(), llm_provider="openai", llm_model_name="gpt-4o", raw_inputs={},
            )
        assert llm is sentinel  # proxy NOT used when local config works

    def test_cn_default_routes_healthy_node_llm_to_proxy(self, _fake_proxy_class):
        sentinel = object()
        with patch("utils.app_env.is_cn", return_value=True), \
             patch.object(br, "_should_use_proxy", return_value=False), \
             patch.object(br, "_get_proxy_config", return_value=PROXY_CFG), \
             patch.object(br, "_build_local_llm_from_node_config_impl", return_value=sentinel):
            llm = br.build_local_llm(
                MagicMock(), llm_provider="openai", llm_model_name="gpt-4o", raw_inputs={},
            )
        assert isinstance(llm, _FakeProxyLLM)

    def test_cn_default_leaves_ollama_direct(self):
        sentinel = object()
        with patch("utils.app_env.is_cn", return_value=True), \
             patch.object(br, "_should_use_proxy", return_value=False), \
             patch.object(br, "_get_proxy_config", return_value=PROXY_CFG), \
             patch.object(br, "_build_local_llm_from_node_config_impl", return_value=sentinel):
            llm = br.build_local_llm(
                MagicMock(), llm_provider="ollama", llm_model_name="qwen3:14b", raw_inputs={},
            )
        assert llm is sentinel


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


class TestLightragMissingKeyFallback:
    """RAG side: _compute_system_api_keys reroutes key-less LLM/EMBEDDING
    bindings to the OpenAI-compatible proxy (endpoint + /v1)."""

    def _compute(self, env_config, proxy_endpoint="https://tcb.example/api/llm-proxy"):
        from knowledge.lightrag_config_manager import LightRAGConfigManager

        main_window = MagicMock()
        # No provider rows → sections 1-3 resolve no keys
        main_window.config_manager.llm_manager.get_provider.return_value = None
        main_window.config_manager.embedding_manager.get_provider.return_value = None
        main_window.config_manager.rerank_manager.get_provider.return_value = None
        main_window.config_manager.general_settings.lambda_proxy_endpoint = proxy_endpoint
        main_window.get_auth_token.return_value = "session-token"

        fake_self = MagicMock()
        fake_self.read_config.return_value = dict(env_config)
        with patch("app_context.AppContext.get_main_window", return_value=main_window):
            return LightRAGConfigManager._compute_system_api_keys(fake_self)

    def test_keyless_bindings_reroute_to_proxy(self):
        keys = self._compute({"LLM_BINDING": "deepseek", "EMBEDDING_BINDING": "qwen"})
        for kind in ("LLM", "EMBEDDING"):
            assert keys[f"{kind}_BINDING"] == "openai"
            assert keys[f"{kind}_BINDING_HOST"] == "https://tcb.example/api/llm-proxy/v1"
            assert keys[f"{kind}_BINDING_API_KEY"] == "session-token"

    def test_ollama_binding_left_alone(self):
        keys = self._compute({"LLM_BINDING": "ollama", "EMBEDDING_BINDING": "ollama"})
        assert "LLM_BINDING_HOST" not in keys and "EMBEDDING_BINDING_HOST" not in keys

    def test_env_key_present_not_overridden(self):
        keys = self._compute({"LLM_BINDING": "deepseek", "LLM_BINDING_API_KEY": "sk-x"})
        assert keys.get("LLM_BINDING") != "openai"
        assert "LLM_BINDING_HOST" not in keys

    def test_no_proxy_endpoint_no_override(self):
        keys = self._compute({"LLM_BINDING": "deepseek"}, proxy_endpoint="")
        assert "LLM_BINDING_HOST" not in keys

class TestCnDefaultProxyEndpoint:
    def _gs(self, data):
        from gui.config.general_settings import GeneralSettings
        gs = object.__new__(GeneralSettings)
        gs._data = data
        return gs

    def test_cn_default_when_unset(self):
        with patch("utils.app_env.is_cn", return_value=True):
            ep = self._gs({}).lambda_proxy_endpoint
        assert ep == ("https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com"
                      "/api/llm-proxy")

    def test_intl_stays_empty(self):
        with patch("utils.app_env.is_cn", return_value=False):
            assert self._gs({}).lambda_proxy_endpoint == ""

    def test_user_value_wins(self):
        with patch("utils.app_env.is_cn", return_value=True):
            ep = self._gs({"lambda_proxy_endpoint": "https://mine.example"}).lambda_proxy_endpoint
        assert ep == "https://mine.example"


class TestUserNotRegisteredMapping:
    """The CN proxy's 403 user_not_registered maps to an actionable
    bilingual message instead of raw proxy JSON (live-tested 2026-08-27)."""

    PROXY_JSON = ('{"error":{"message":"user_not_registered",'
                  '"type":"access_denied","code":"user_not_registered"}}')

    def test_friendly_message_for_code(self):
        from agent.ec_skills.llm_utils.proxy_errors import friendly_proxy_error_message
        msg = friendly_proxy_error_message(self.PROXY_JSON)
        assert msg and "注册" in msg and "Settings > LLM Management" in msg

    def test_other_errors_untouched(self):
        from agent.ec_skills.llm_utils.proxy_errors import (
            friendly_proxy_error_message, translate_proxy_exception)
        assert friendly_proxy_error_message('{"error":{"code":"rate_limited"}}') is None
        assert translate_proxy_exception(RuntimeError("boom")) is None

    def test_langchain_proxy_generate_raises_friendly(self, _fake_proxy_class):
        from langchain_openai import ChatOpenAI
        from agent.ec_skills.lambda_proxy_langchain import create_lambda_proxy_langchain

        llm = create_lambda_proxy_langchain(
            provider="openai", model="gpt-4o", user_id="u@x",
            lambda_endpoint="https://tcb.example/api/llm-proxy", auth_token="tok",
        )
        with patch.object(ChatOpenAI, "_generate",
                          side_effect=RuntimeError(f"Error code: 403 - {self.PROXY_JSON}")):
            with pytest.raises(PermissionError, match="注册"):
                llm._generate([])

    def test_langchain_proxy_other_error_passthrough(self, _fake_proxy_class):
        from langchain_openai import ChatOpenAI
        from agent.ec_skills.lambda_proxy_langchain import create_lambda_proxy_langchain

        llm = create_lambda_proxy_langchain(
            provider="openai", model="gpt-4o", user_id="u@x",
            lambda_endpoint="https://tcb.example/api/llm-proxy", auth_token="tok",
        )
        with patch.object(ChatOpenAI, "_generate", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                llm._generate([])

    def test_chat_lambda_proxy_body_error_friendly(self):
        from agent.ec_skills.browser_use_extension.lambda_proxy_llm import ChatLambdaProxy
        data = {"error": {"message": "user_not_registered",
                          "type": "access_denied", "code": "user_not_registered"}}
        with pytest.raises(ValueError, match="注册"):
            ChatLambdaProxy._extract_completion(data)


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


class TestCnAwsEndpointGuard:
    def _gs(self, data):
        from gui.config.general_settings import GeneralSettings
        gs = object.__new__(GeneralSettings)
        gs._data = data
        return gs

    def test_stale_aws_url_ignored_on_cn(self):
        gs = self._gs({"lambda_proxy_endpoint":
                       "https://abc.lambda-url.us-east-1.on.aws"})
        with patch("utils.app_env.is_cn", return_value=True):
            assert "tcloudbase.com" in gs.lambda_proxy_endpoint

    def test_custom_tcb_url_kept_on_cn(self):
        gs = self._gs({"lambda_proxy_endpoint": "https://my.tcb.example/llm"})
        with patch("utils.app_env.is_cn", return_value=True):
            assert gs.lambda_proxy_endpoint == "https://my.tcb.example/llm"

    def test_aws_url_kept_on_intl(self):
        gs = self._gs({"lambda_proxy_endpoint":
                       "https://abc.lambda-url.us-east-1.on.aws"})
        with patch("utils.app_env.is_cn", return_value=False):
            assert gs.lambda_proxy_endpoint == "https://abc.lambda-url.us-east-1.on.aws"


class TestEcanaiDefaultProvider:
    """eCanAI is the out-of-the-box provider for llm/embedding/rerank
    (2026-08-30): unset profiles resolve to ecanai + role model defaults;
    an explicit stored choice always wins."""

    def _gs(self, data):
        from gui.config.general_settings import GeneralSettings
        gs = object.__new__(GeneralSettings)
        gs._data = data
        return gs

    def test_unset_profile_defaults_to_ecanai(self):
        gs = self._gs({})
        assert gs.default_llm == "ecanai" and gs.default_llm_model == "qwen-plus"
        assert gs.default_embedding == "ecanai"
        assert gs.default_embedding_model == "text-embedding-v3"
        assert gs.default_rerank == "ecanai" and gs.default_rerank_model == "gte-rerank"

    def test_explicit_choice_wins_and_model_not_polluted(self):
        gs = self._gs({"default_llm": "deepseek", "default_llm_model": ""})
        assert gs.default_llm == "deepseek"
        assert gs.default_llm_model == ""

    def test_ecanai_with_empty_model_gets_role_default(self):
        gs = self._gs({"default_embedding": "ecanai", "default_embedding_model": ""})
        assert gs.default_embedding_model == "text-embedding-v3"


class TestEcanaiEmbeddingModelPriority:
    """2026-08-30 ingest 404 incident: the ecanai overlay set
    EMBEDDING_MODEL=text-embedding-v3 from Settings, but the stale
    lightrag.env value (text-embedding-3-small) overwrote it three lines
    later. The Settings-resolved model must win over the .env value."""

    def test_settings_model_beats_stale_env_model(self):
        from knowledge.lightrag_config_manager import LightRAGConfigManager

        main_window = MagicMock()
        gs = main_window.config_manager.general_settings
        gs.default_llm = 'ecanai'
        gs.default_llm_model = 'qwen-plus'
        gs.default_embedding = 'ecanai'
        gs.default_embedding_model = 'text-embedding-v3'
        gs.default_rerank = ''
        gs.lambda_proxy_endpoint = 'https://tcb.example/api/llm-proxy'

        provider = {
            'name': 'eCanAI', 'provider': 'ecanai',
            'base_url': 'https://tcb.example/api/llm-proxy/v1',
            'api_key_env_vars': ['ECANAI_EMBEDDING_API_KEY'],
            'supported_models': [],
        }
        main_window.config_manager.llm_manager.get_provider.return_value = provider
        main_window.config_manager.llm_manager.retrieve_api_key.return_value = 'KEY'
        main_window.config_manager.embedding_manager.get_provider.return_value = provider
        main_window.config_manager.embedding_manager.retrieve_api_key.return_value = 'KEY'
        main_window.config_manager.rerank_manager.get_provider.return_value = None
        main_window.get_auth_token.return_value = 'tok'

        fake_self = MagicMock()
        fake_self.read_config.return_value = {
            'LLM_BINDING': 'openai',
            'EMBEDDING_BINDING': 'openai',
            'EMBEDDING_MODEL': 'text-embedding-3-small',   # stale .env value
        }
        with patch('app_context.AppContext.get_main_window', return_value=main_window):
            keys = LightRAGConfigManager._compute_system_api_keys(fake_self)
        assert keys['EMBEDDING_MODEL'] == 'text-embedding-v3'
        assert keys['EMBEDDING_BINDING'] == 'ecanai'
