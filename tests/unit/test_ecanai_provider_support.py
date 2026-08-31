import json
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent.ec_skills.llm_utils.llm_provider import LLMModel, LLMProvider as AgentLLMProvider
from agent.ec_skills.llm_utils.llm_provider import ProviderType
from agent.ec_skills.llm_utils import llm_utils
from gui.config.llm_config import LLMConfig, LLMModelConfig, LLMProvider, LLMProviderConfig
from gui.config.embedding_config import EmbeddingModelConfig, EmbeddingProviderConfig
from gui.config.rerank_config import RerankModelConfig, RerankProviderConfig
from knowledge.lightrag_config_manager import LightRAGConfigManager
from gui.manager import provider_settings_helper


ECANAI_URL = "https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/api/llm-proxy/v1"


def test_python_provider_models_cover_the_json_schema():
    config_path = Path(__file__).parents[2] / "gui/config/llm_providers.json"
    providers = json.loads(config_path.read_text(encoding="utf-8"))["providers"].values()
    provider_keys = {key for provider in providers for key in provider}
    model_keys = {
        key
        for provider in providers
        for model in provider.get("supported_models", [])
        for key in model
    }

    assert provider_keys <= {field.name for field in fields(LLMProviderConfig)}
    assert model_keys <= {field.name for field in fields(LLMModelConfig)}
    assert provider_keys - {"provider"} <= {field.name for field in fields(AgentLLMProvider)}
    assert model_keys <= {field.name for field in fields(LLMModel)}

    for filename, provider_class, model_class in (
        ("embedding_providers.json", EmbeddingProviderConfig, EmbeddingModelConfig),
        ("rerank_providers.json", RerankProviderConfig, RerankModelConfig),
    ):
        typed_providers = json.loads(
            (config_path.parent / filename).read_text(encoding="utf-8")
        )["providers"].values()
        typed_provider_keys = {key for provider in typed_providers for key in provider}
        typed_model_keys = {
            key
            for provider in typed_providers
            for model in provider.get("supported_models", [])
            for key in model
        }
        assert typed_provider_keys <= {field.name for field in fields(provider_class)}
        assert typed_model_keys <= {field.name for field in fields(model_class)}


def test_ecanai_is_registered_as_openai_compatible_provider():
    LLMConfig.clear_cache()
    provider = LLMConfig().get_provider("eCanAI")

    assert provider is not None
    assert provider.provider is LLMProvider.ECANAI
    assert provider.base_url == ECANAI_URL
    assert provider.runtime_kind == "openai_compatible"
    assert provider.special_features["dynamic_models"] is True
    assert provider.enable_thinking is False

    agent_provider = AgentLLMProvider.from_dict({
        "name": "eCanAI",
        "display_name": "eCanAI",
        "provider": "ecanai",
        "class_name": "ChatOpenAI",
        "base_url": ECANAI_URL,
    })
    assert agent_provider.provider_type is ProviderType.ECANAI
    assert agent_provider.is_openai_compatible()
    assert llm_utils.is_provider_browser_use_compatible("ecanai")


def test_ecanai_llm_uses_real_key_from_secure_store():
    sentinel = object()
    provider = {
        "name": "eCanAI",
        "display_name": "eCanAI",
        "provider": "ecanai",
        "class_name": "ChatOpenAI",
        "base_url": ECANAI_URL,
        "default_model": "test-model",
        "api_key_env_vars": ["ECANAI_LLM_API_KEY"],
        "supported_models": [],
    }

    with (
        patch.object(llm_utils.secure_store, "get", return_value="real-ecanai-key"),
        patch.object(llm_utils, "ChatOpenAI", return_value=sentinel) as chat_openai,
    ):
        result = llm_utils._create_llm_instance(provider)

    assert result is sentinel
    kwargs = chat_openai.call_args.kwargs
    assert kwargs["model"] == "test-model"
    assert kwargs["base_url"] == ECANAI_URL
    assert kwargs["api_key"] == "real-ecanai-key"


def test_ecanai_llm_rejects_missing_api_key():
    provider = {
        "name": "eCanAI",
        "provider": "ecanai",
        "class_name": "ChatOpenAI",
        "base_url": ECANAI_URL,
        "default_model": "test-model",
        "api_key_env_vars": ["ECANAI_LLM_API_KEY"],
    }
    with patch.object(llm_utils.secure_store, "get", return_value=None):
        assert llm_utils._create_llm_instance(provider, allow_no_api_key=True) is None


def test_lightrag_effective_env_follows_system_ecanai_defaults_and_keys():
    def manager(kind):
        return SimpleNamespace(
            get_provider=lambda _name: {
                "name": "eCanAI",
                "base_url": ECANAI_URL,
                "default_model": f"{kind}-default",
                "supported_models": [],
                "api_key_env_vars": [f"ECANAI_{kind.upper()}_API_KEY"],
            },
            retrieve_api_key=lambda env_var: f"secret-{env_var.lower()}",
        )

    config = SimpleNamespace(
        general_settings=SimpleNamespace(
            default_llm="ecanai",
            default_llm_model="chat-model",
            default_embedding="ecanai",
            default_embedding_model="embedding-model",
            default_rerank="ecanai",
            default_rerank_model="rerank-model",
            lambda_proxy_endpoint="",
        ),
        llm_manager=manager("llm"),
        embedding_manager=manager("embedding"),
        rerank_manager=manager("rerank"),
    )
    main_window = SimpleNamespace(config_manager=config)
    lightrag_config = LightRAGConfigManager()

    with (
        patch("app_context.AppContext.get_main_window", return_value=main_window),
        patch.object(lightrag_config, "read_config", return_value={
            "LLM_BINDING": "openai",
            "EMBEDDING_BINDING": "openai",
            "RERANK_BINDING": "jina",
        }),
    ):
        env = lightrag_config.get_system_api_keys(force_refresh=True)

    assert env["LLM_BINDING"] == "ecanai"
    assert env["LLM_MODEL"] == "chat-model"
    assert env["LLM_BINDING_HOST"] == ECANAI_URL
    assert env["LLM_BINDING_API_KEY"] == "secret-ecanai_llm_api_key"
    assert env["OPENAI_API_KEY"] == env["LLM_BINDING_API_KEY"]
    assert env["EMBEDDING_BINDING"] == "ecanai"
    assert env["EMBEDDING_MODEL"] == "embedding-model"
    assert env["EMBEDDING_BINDING_API_KEY"] == "secret-ecanai_embedding_api_key"
    assert env["RERANK_BINDING"] == "ecanai"
    assert env["RERANK_MODEL"] == "rerank-model"
    assert env["RERANK_BINDING_HOST"] == ECANAI_URL
    assert env["RERANK_BINDING_API_KEY"] == "secret-ecanai_rerank_api_key"


def test_account_api_key_syncs_all_ecanai_roles_and_invalidates_lightrag():
    stored = {}

    def manager():
        return SimpleNamespace(
            store_api_key=lambda env_var, value: (stored.__setitem__(env_var, value) is None, None),
        )

    config_manager = SimpleNamespace(
        llm_manager=manager(),
        embedding_manager=manager(),
        rerank_manager=manager(),
        general_settings=SimpleNamespace(
            default_llm="ecanai",
            default_llm_model="chat-model",
            default_embedding="ecanai",
            default_embedding_model="text-embedding-v3",
            default_rerank="ecanai",
            default_rerank_model="gte-rerank",
        ),
    )
    main_window = SimpleNamespace(
        config_manager=config_manager,
        agents=[],
        update_all_llms=lambda **_kwargs: True,
    )

    with patch.object(provider_settings_helper, "invalidate_lightrag_provider_cache") as invalidate:
        success, error = provider_settings_helper.sync_account_api_key_to_ecanai(
            "account-api-key-1234567890", main_window=main_window
        )

    assert success and error is None
    assert stored == {
        "ECANAI_LLM_API_KEY": "account-api-key-1234567890",
        "ECANAI_EMBEDDING_API_KEY": "account-api-key-1234567890",
        "ECANAI_RERANK_API_KEY": "account-api-key-1234567890",
    }
    invalidate.assert_called_once_with("llm", "ecanai")
