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
    OpenAIEmbeddings,
    AzureOpenAIEmbeddings,
    HuggingFaceEmbeddings,
    CohereEmbeddings,
    VoyageEmbeddings,
    VertexAIEmbeddings,
    QianfanEmbeddingsEndpoint,
    DashScopeEmbeddings,
)

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
            provider_config = embedding_config.get_provider(provider_name)
            if provider_config:
                provider_enum_value = provider_config.provider.value.lower()
            else:
                # Fallback: search all providers by name or display_name to find matching config
                # This handles cases where provider_name might be a display name or variant
                provider_enum_value = None
                all_providers = embedding_config.get_all_providers()
                for provider_key, config in all_providers.items():
                    # Match by provider key (e.g., "百度千帆"), name, or display_name
                    if (provider_key == provider_name or 
                        config.name == provider_name or 
                        config.display_name == provider_name):
                        provider_enum_value = config.provider.value.lower()
                        break
                
                # Special handling for common provider name variants
                if provider_enum_value is None:
                    provider_lower = provider_name.lower()
                    # Map "dashscope" to "alibaba_qwen" (DashScope is the API name for Alibaba Qwen)
                    if provider_lower == "dashscope" or provider_lower == "qwen":
                        provider_enum_value = "alibaba_qwen"
                    else:
                        # Last resort: use provider_name as fallback
                        provider_enum_value = provider_lower
                        logger.warning(f"[EmbeddingFactory] Provider {provider_name} not found in config, using name as fallback")
            
            logger.debug(f"[EmbeddingFactory] Creating embeddings: provider_name={provider_name}, provider_enum_value={provider_enum_value}, model_name={model_name}")
            
            if provider_enum_value == "openai":
                api_key = secure_store.get("OPENAI_API_KEY")
                if api_key:
                    return OpenAIEmbeddings(model=model_name, openai_api_key=api_key)
                else:
                    logger.warning(f"[EmbeddingFactory] OPENAI_API_KEY not found, using FakeEmbeddings")
                    return FakeEmbeddings(size=1536)  # OpenAI default dimension
                    
            elif provider_enum_value == "azure_openai":
                azure_endpoint = secure_store.get("AZURE_ENDPOINT")
                api_key = secure_store.get("AZURE_OPENAI_API_KEY")
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
                api_key = secure_store.get("HUGGINGFACE_API_KEY")
                return HuggingFaceEmbeddings(
                    model_name=model_name,
                    model_kwargs={"device": "cpu"},
                    encode_kwargs={"normalize_embeddings": True}
                )
                
            elif provider_enum_value == "cohere":
                api_key = secure_store.get("COHERE_API_KEY")
                if api_key:
                    # CohereEmbeddings uses 'cohere_api_key' parameter
                    return CohereEmbeddings(model=model_name, cohere_api_key=api_key)
                else:
                    logger.warning(f"[EmbeddingFactory] COHERE_API_KEY not found")
                    return FakeEmbeddings(size=1024)  # Cohere default dimension
                    
            elif provider_enum_value == "voyageai":
                api_key = secure_store.get("VOYAGE_API_KEY")
                if api_key:
                    # VoyageEmbeddings uses 'voyage_api_key' parameter
                    return VoyageEmbeddings(model=model_name, voyage_api_key=api_key)
                else:
                    logger.warning(f"[EmbeddingFactory] VOYAGE_API_KEY not found")
                    return FakeEmbeddings(size=1024)  # Voyage default dimension
                    
            elif provider_enum_value == "google":
                # Google Vertex AI requires credentials file or environment variable
                credentials_path = secure_store.get("GOOGLE_APPLICATION_CREDENTIALS")
                api_key = secure_store.get("GOOGLE_API_KEY")
                try:
                    if credentials_path:
                        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
                    # Use langchain_community version
                    return VertexAIEmbeddings(model_name=model_name)
                except Exception as e:
                    logger.error(f"[EmbeddingFactory] Google Vertex AI setup failed: {e}")
                    return FakeEmbeddings(size=768)  # Google default dimension
            
            elif provider_enum_value == "baidu_qianfan":
                # Baidu Qianfan embeddings
                api_key = secure_store.get("BAIDU_API_KEY")
                secret_key = secure_store.get("BAIDU_SECRET_KEY")
                if api_key and secret_key:
                    try:
                        return QianfanEmbeddingsEndpoint(
                            qianfan_ak=api_key,
                            qianfan_sk=secret_key,
                            model=model_name
                        )
                    except Exception as e:
                        logger.error(f"[EmbeddingFactory] QianfanEmbeddingsEndpoint failed: {e}")
                        return FakeEmbeddings(size=1024)  # Baidu default dimension
                else:
                    logger.warning(f"[EmbeddingFactory] Baidu API keys not found")
                    return FakeEmbeddings(size=1024)
                    
            elif provider_enum_value == "alibaba_qwen":
                # Alibaba Qwen embeddings (DashScope API)
                api_key = secure_store.get("DASHSCOPE_API_KEY")
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
                    
            elif provider_enum_value == "doubao":
                # Doubao embeddings
                # Note: Doubao is not directly supported in langchain_community.embeddings
                # If it becomes available, implement it here
                api_key = secure_store.get("DOUBAO_API_KEY")
                if api_key:
                    logger.warning(f"[EmbeddingFactory] Doubao embeddings not yet implemented in langchain_community")
                    return FakeEmbeddings(size=1024)  # Doubao default dimension
                else:
                    logger.warning(f"[EmbeddingFactory] Doubao API key not found")
                    return FakeEmbeddings(size=1024)
                
            else:
                # Default to FakeEmbeddings for unknown providers
                logger.warning(f"[EmbeddingFactory] Unknown provider {provider_name}, using FakeEmbeddings")
                return FakeEmbeddings(size=1536)
                    
        except Exception as e:
            logger.error(f"[EmbeddingFactory] Error creating embeddings: {e}", exc_info=True)
            # Fallback to FakeEmbeddings to ensure system continues working
            return FakeEmbeddings(size=1536)

