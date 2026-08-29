from unittest.mock import MagicMock, patch

from knowledge.lightrag_config_manager import LightRAGConfigManager


def test_empty_embedding_model_uses_selected_provider_model():
    provider = {
        "name": "RyoAIS",
        "base_url": "https://example.test/v1",
        "preferred_model": "bge-m3",
        "api_key_env_vars": [],
        "supported_models": [{
            "name": "bge-m3",
            "model_id": "bge-m3",
            "dimensions": 1024,
            "max_tokens": 8192,
        }],
    }
    main_window = MagicMock()
    main_window.config_manager.llm_manager.get_provider.return_value = None
    main_window.config_manager.embedding_manager.get_provider.return_value = provider
    main_window.config_manager.rerank_manager.get_provider.return_value = None
    main_window.config_manager.general_settings.default_embedding_model = "bge-m3"
    main_window.config_manager.general_settings.lambda_proxy_endpoint = ""

    fake_self = MagicMock()
    fake_self.read_config.return_value = {
        "EMBEDDING_BINDING": "ryoais",
        "EMBEDDING_MODEL": "",
    }
    with patch("app_context.AppContext.get_main_window", return_value=main_window):
        keys = LightRAGConfigManager._compute_system_api_keys(fake_self)

    assert keys["EMBEDDING_MODEL"] == "bge-m3"
    assert keys["EMBEDDING_DIM"] == "1024"
    assert keys["EMBEDDING_TOKEN_LIMIT"] == "8192"
