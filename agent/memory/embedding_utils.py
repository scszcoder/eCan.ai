"""
Embedding Utils for Memory Service

This module provides embedding creation functionality for memory service,
similar to how LLM is managed. It handles all embedding provider initialization
and configuration.
"""

import os
from typing import Optional

from langchain_core.embeddings import Embeddings, FakeEmbeddings
from langchain_community.embeddings import (
    AzureOpenAIEmbeddings,
    HuggingFaceEmbeddings,
    CohereEmbeddings,
    VoyageEmbeddings,
    VertexAIEmbeddings,
    QianfanEmbeddingsEndpoint,
    DashScopeEmbeddings,
)
from langchain_openai import OpenAIEmbeddings

from utils.logger_helper import logger_helper as logger


class EmbeddingFactory:
    """Factory for creating embedding instances for memory service."""
    
    @staticmethod
    def create_embeddings(
        provider_name: str = "OpenAI",
        model_name: str = "text-embedding-3-small"
    ) -> Embeddings:
        """Create embeddings instance based on provider and model.
        
        Args:
            provider_name: Name of the embedding provider (OpenAI, Azure OpenAI, HuggingFace, etc.)
            model_name: Model name to use
        
        Returns:
            Embeddings instance
        """
        try:
            from utils.env.secure_store import secure_store
            from gui.config.embedding_config import embedding_config
            
            # Get provider configuration to determine provider enum value
            # provider_name can be: provider identifier (e.g., "openai"), name (e.g., "OpenAI"), or display_name
            provider_config = None
            provider_enum_value = None
            
            # First try: match by provider identifier (canonical)
            all_providers = embedding_config.get_all_providers()
            provider_name_lower = (provider_name or "").lower()
            for provider_key, config in all_providers.items():
                # Match by provider identifier (canonical)
                if config.provider.value.lower() == provider_name_lower:
                    provider_config = config
                    provider_enum_value = config.provider.value.lower()
                    break
                # Match by name
                if config.name.lower() == provider_name_lower:
                    provider_config = config
                    provider_enum_value = config.provider.value.lower()
                    break
                # Match by display_name
                if config.display_name.lower() == provider_name_lower:
                    provider_config = config
                    provider_enum_value = config.provider.value.lower()
                    break
                # Match by provider_key (e.g., "百度千帆")
                if provider_key.lower() == provider_name_lower:
                    provider_config = config
                    provider_enum_value = config.provider.value.lower()
                    break
            
            # Special handling for common provider name variants
            if provider_enum_value is None:
                # Map "dashscope" to "alibaba_qwen" (DashScope is the API name for Alibaba Qwen)
                if provider_name_lower == "dashscope" or provider_name_lower == "qwen":
                    provider_enum_value = "alibaba_qwen"
                else:
                    # Last resort: use provider_name as fallback
                    provider_enum_value = provider_name_lower
                    logger.warning(f"[EmbeddingFactory] Provider '{provider_name}' not found in config, using name as fallback")
            
            logger.debug(f"[EmbeddingFactory] Creating embeddings: provider_name={provider_name}, provider_enum_value={provider_enum_value}, model_name={model_name}")
            
            # Get current username for user isolation
            from utils.env.secure_store import get_current_username
            username = get_current_username()
            
            if provider_enum_value == "openai":
                api_key = secure_store.get("OPENAI_API_KEY", username=username)
                if api_key:
                    return OpenAIEmbeddings(model=model_name, api_key=api_key)
                else:
                    logger.debug(f"[EmbeddingFactory] OPENAI_API_KEY not found, using FakeEmbeddings (memory features will be limited)")
                    return FakeEmbeddings(size=1536)  # OpenAI default dimension
                    
            elif provider_enum_value == "azure_openai":
                azure_endpoint = secure_store.get("AZURE_ENDPOINT", username=username)
                api_key = secure_store.get("AZURE_OPENAI_API_KEY", username=username)
                if azure_endpoint and api_key:
                    return AzureOpenAIEmbeddings(
                        model=model_name,
                        azure_endpoint=azure_endpoint,
                        api_key=api_key
                    )
                else:
                    logger.warning(f"[EmbeddingFactory] Azure OpenAI credentials not found, using FakeEmbeddings")
                    return FakeEmbeddings(size=1536)  # Azure OpenAI default dimension
                    
            elif provider_enum_value == "huggingface":
                api_key = secure_store.get("HUGGINGFACE_API_KEY", username=username)
                return HuggingFaceEmbeddings(
                    model_name=model_name,
                    model_kwargs={"device": "cpu"},
                    encode_kwargs={"normalize_embeddings": True}
                )
                
            elif provider_enum_value == "cohere":
                api_key = secure_store.get("COHERE_API_KEY", username=username)
                if api_key:
                    # CohereEmbeddings uses 'cohere_api_key' parameter
                    return CohereEmbeddings(model=model_name, cohere_api_key=api_key)
                else:
                    logger.warning(f"[EmbeddingFactory] COHERE_API_KEY not found")
                    return FakeEmbeddings(size=1024)  # Cohere default dimension
                    
            elif provider_enum_value == "voyageai":
                api_key = secure_store.get("VOYAGE_API_KEY", username=username)
                if api_key:
                    # VoyageEmbeddings uses 'voyage_api_key' parameter
                    return VoyageEmbeddings(model=model_name, voyage_api_key=api_key)
                else:
                    logger.warning(f"[EmbeddingFactory] VOYAGE_API_KEY not found")
                    return FakeEmbeddings(size=1024)  # Voyage default dimension
                    
            elif provider_enum_value == "google":
                # Google Vertex AI requires credentials file or environment variable
                credentials_path = secure_store.get("GOOGLE_APPLICATION_CREDENTIALS", username=username)
                api_key = secure_store.get("GOOGLE_API_KEY", username=username)
                try:
                    if credentials_path:
                        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
                    # Use langchain_community version
                    return VertexAIEmbeddings(model_name=model_name)
                except Exception as e:
                    logger.error(f"[EmbeddingFactory] Google Vertex AI setup failed: {e}")
                    return FakeEmbeddings(size=768)  # Google default dimension
            
            elif provider_enum_value == "baidu_qianfan":
                # Baidu Qianfan embeddings - use V2 OpenAI-compatible API (same as LLM)
                # Only requires API Key, passed as Bearer token
                api_key = secure_store.get("BAIDU_API_KEY", username=username)
                
                if api_key:
                    try:
                        # Create no-proxy httpx client for Baidu Qianfan (domestic API, bypass proxy)
                        from agent.ec_skills.llm_utils.llm_utils import _create_no_proxy_http_client
                        sync_client, async_client = _create_no_proxy_http_client()
                        
                        # Use OpenAIEmbeddings with Baidu's V2 API endpoint
                        # API key is automatically passed as Bearer token
                        # IMPORTANT: OpenAIEmbeddings requires BOTH http_client (sync) and http_async_client (async)
                        # If you provide a custom client, you must provide both
                        if sync_client and async_client:
                            logger.debug(f"[EmbeddingFactory] Baidu Qianfan using no-proxy clients (domestic API)")
                            return OpenAIEmbeddings(
                                model=model_name or "bge-large-zh",
                                api_key=api_key,
                                base_url="https://qianfan.baidubce.com/v2",
                                http_client=sync_client,
                                http_async_client=async_client
                            )
                        else:
                            logger.debug(f"[EmbeddingFactory] Baidu Qianfan using default client (no proxy configured)")
                            return OpenAIEmbeddings(
                                model=model_name or "bge-large-zh",
                                api_key=api_key,
                                base_url="https://qianfan.baidubce.com/v2"
                            )
                    except Exception as e:
                        logger.error(f"[EmbeddingFactory] Baidu Qianfan OpenAI-compatible embeddings failed: {e}")
                        return FakeEmbeddings(size=1024)  # Baidu default dimension
                else:
                    logger.warning(f"[EmbeddingFactory] Baidu API key not found")
                    return FakeEmbeddings(size=1024)
                    
            elif provider_enum_value == "alibaba_qwen":
                # Alibaba Qwen embeddings (DashScope API)
                api_key = secure_store.get("DASHSCOPE_API_KEY", username=username)
                if api_key:
                    try:
                        logger.debug(f"[EmbeddingFactory] Creating DashScopeEmbeddings with model={model_name}")
                        return DashScopeEmbeddings(
                            dashscope_api_key=api_key,
                            model=model_name
                        )
                    except ImportError as e:
                        logger.error(f"[EmbeddingFactory] DashScopeEmbeddings failed: Missing 'dashscope' module. Please install it with: pip install dashscope")
                        return FakeEmbeddings(size=1536)  # Qwen default dimension
                    except Exception as e:
                        logger.error(f"[EmbeddingFactory] DashScopeEmbeddings failed: {e}")
                        return FakeEmbeddings(size=1536)  # Qwen default dimension
                else:
                    logger.warning(f"[EmbeddingFactory] DashScope API key not found")
                    return FakeEmbeddings(size=1536)
                    
            elif provider_enum_value == "doubao" or provider_enum_value == "bytedance":
                # Bytedance Doubao embeddings - use OpenAI-compatible API (Volcano Engine)
                # Doubao provides OpenAI-compatible embedding API
                api_key = secure_store.get("ARK_API_KEY", username=username)
                
                if api_key:
                    try:
                        # Create no-proxy httpx client for Bytedance (domestic API, bypass proxy)
                        from agent.ec_skills.llm_utils.llm_utils import _create_no_proxy_http_client
                        sync_client, async_client = _create_no_proxy_http_client()
                        
                        # Use OpenAIEmbeddings with Bytedance's OpenAI-compatible endpoint
                        # API key is automatically passed as Bearer token
                        # IMPORTANT: OpenAIEmbeddings requires BOTH http_client (sync) and http_async_client (async)
                        # If you provide a custom client, you must provide both
                        if sync_client and async_client:
                            logger.debug(f"[EmbeddingFactory] Bytedance Doubao using no-proxy clients (domestic API)")
                            return OpenAIEmbeddings(
                                model=model_name or "doubao-embedding",
                                api_key=api_key,
                                base_url="https://ark.cn-beijing.volces.com/api/v3",
                                http_client=sync_client,
                                http_async_client=async_client
                            )
                        else:
                            logger.debug(f"[EmbeddingFactory] Bytedance Doubao using default client (no proxy configured)")
                            return OpenAIEmbeddings(
                                model=model_name or "doubao-embedding",
                                api_key=api_key,
                                base_url="https://ark.cn-beijing.volces.com/api/v3"
                            )
                    except Exception as e:
                        logger.error(f"[EmbeddingFactory] Bytedance Doubao OpenAI-compatible embeddings failed: {e}")
                        return FakeEmbeddings(size=1024)  # Doubao default dimension
                else:
                    logger.warning(f"[EmbeddingFactory] Bytedance ARK_API_KEY not found")
                    return FakeEmbeddings(size=1024)
                
            elif provider_enum_value == "ollama":
                # Ollama embeddings (uses OpenAI-compatible API)
                try:
                    # Get base_url and API key using common helper functions
                    from gui.manager.provider_settings_helper import get_ollama_base_url, get_ollama_api_key
                    
                    # Convert provider_config to dict if it's an object
                    provider_config_dict = None
                    if provider_config:
                        try:
                            # If it's an EmbeddingProviderConfig object, extract base_url
                            if hasattr(provider_config, 'base_url'):
                                provider_config_dict = {'base_url': provider_config.base_url}
                        except Exception:
                            pass
                    
                    base_url = get_ollama_base_url('embedding', provider_config_dict)
                    ollama_api_key = get_ollama_api_key('embedding')
                    
                    # Convert native Ollama URL to OpenAI-compatible endpoint
                    # Settings stores native URL (http://localhost:11434) for LightRAG compatibility
                    # OpenAIEmbeddings needs OpenAI-compatible endpoint (http://localhost:11434/v1)
                    base_url = base_url.rstrip('/')
                    if not base_url.endswith('/v1'):
                        base_url = f"{base_url}/v1"
                    
                    logger.debug(f"[EmbeddingFactory] Creating Ollama embeddings with model={model_name}, base_url={base_url}")
                    return OpenAIEmbeddings(
                        model=model_name or "nomic-embed-text",
                        api_key=ollama_api_key,
                        base_url=base_url
                    )
                except Exception as e:
                    logger.error(f"[EmbeddingFactory] Ollama embeddings failed: {e}")
                    return FakeEmbeddings(size=768)  # Ollama default dimension
                
            else:
                # Default to FakeEmbeddings for unknown providers
                logger.warning(f"[EmbeddingFactory] Unknown provider {provider_name}, using FakeEmbeddings")
                return FakeEmbeddings(size=1536)
                    
        except Exception as e:
            logger.error(f"[EmbeddingFactory] Error creating embeddings: {e}", exc_info=True)
            # Fallback to FakeEmbeddings to ensure system continues working
            return FakeEmbeddings(size=1536)

