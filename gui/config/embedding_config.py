"""
Embedding Configuration Management

This module manages Embedding model configurations including:
- Embedding provider definitions and metadata
- Model configurations and parameters
- API key requirements
- Default settings

Configuration is loaded from embedding_providers.json for easy modification and extension.
"""

import os
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from utils.logger_helper import logger_helper as logger


class EmbeddingProvider(Enum):
    """Embedding Provider enumeration"""
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    HUGGINGFACE = "huggingface"
    COHERE = "cohere"
    VOYAGEAI = "voyageai"
    GOOGLE = "google"
    BAIDU_QIANFAN = "baidu_qianfan"
    ALIBABA_QWEN = "alibaba_qwen"
    DOUBAO = "doubao"
    JINA = "jina"
    OLLAMA = "ollama"


@dataclass
class EmbeddingModelConfig:
    """Configuration for a specific embedding model"""
    name: str
    display_name: str
    model_id: str
    dimensions: Optional[int] = None
    max_tokens: Optional[int] = None
    description: str = ""


@dataclass
class EmbeddingProviderConfig:
    """Configuration for an embedding provider"""
    name: str
    display_name: str
    provider: EmbeddingProvider
    class_name: str
    api_key_env_vars: List[str]
    base_url: Optional[str] = None
    default_model: Optional[str] = None
    supported_models: List[EmbeddingModelConfig] = field(default_factory=list)
    description: str = ""
    documentation_url: str = ""
    is_local: bool = False


class EmbeddingConfig:
    """Main Embedding configuration manager"""

    def __init__(self, config_file_path: Optional[str] = None):
        """
        Initialize Embedding configuration

        Args:
            config_file_path: Path to the JSON configuration file.
                            If None, uses default path.
        """
        if config_file_path is None:
            # Default path relative to this file
            config_file_path = os.path.join(os.path.dirname(__file__), 'embedding_providers.json')

        self.config_file_path = config_file_path
        self._config_data = self._load_config()
        self._providers = self._initialize_providers()
        self._models = self._initialize_models()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file"""
        try:
            with open(self.config_file_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            logger.info(f"Loaded Embedding configuration from {self.config_file_path}")
            return config_data

        except FileNotFoundError:
            logger.error(f"Embedding configuration file not found: {self.config_file_path}")
            return {"providers": {}, "metadata": {}}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in embedding configuration file: {e}")
            return {"providers": {}, "metadata": {}}

    def _initialize_providers(self) -> Dict[str, EmbeddingProviderConfig]:
        """Initialize provider configurations from loaded data"""
        providers = {}
        providers_data = self._config_data.get("providers", {})

        for provider_name, provider_data in providers_data.items():
            try:
                # Map provider string to enum
                provider_str = provider_data.get("provider", "").lower()
                provider_enum = EmbeddingProvider(provider_str)
            except ValueError:
                logger.warning(f"Unknown provider type: {provider_data.get('provider')} for {provider_name}. Allowing to continue with string value.")
                # Create a temporary enum-like value for unknown providers
                # This allows the system to continue working with new providers
                # that haven't been added to the enum yet
                from types import SimpleNamespace
                provider_enum = SimpleNamespace(value=provider_str)

            # Parse supported models
            supported_models = []
            for model_data in provider_data.get("supported_models", []):
                model_config = EmbeddingModelConfig(
                    name=model_data.get("name", ""),
                    display_name=model_data.get("display_name", ""),
                    model_id=model_data.get("model_id", ""),
                    dimensions=model_data.get("dimensions"),
                    max_tokens=model_data.get("max_tokens"),
                    description=model_data.get("description", "")
                )
                supported_models.append(model_config)

            provider_config = EmbeddingProviderConfig(
                name=provider_data.get("name", provider_name),
                display_name=provider_data.get("display_name", provider_name),
                provider=provider_enum,
                class_name=provider_data.get("class_name", ""),
                api_key_env_vars=provider_data.get("api_key_env_vars", []),
                base_url=provider_data.get("base_url"),
                default_model=provider_data.get("default_model"),
                supported_models=supported_models,
                description=provider_data.get("description", ""),
                documentation_url=provider_data.get("documentation_url", ""),
                is_local=provider_data.get("is_local", False)
            )

            providers[provider_name] = provider_config

        logger.info(f"Initialized {len(providers)} embedding providers")
        return providers

    def _initialize_models(self) -> Dict[str, EmbeddingModelConfig]:
        """Initialize model configurations from all providers"""
        models = {}
        for provider_config in self._providers.values():
            for model_config in provider_config.supported_models:
                models[model_config.name] = model_config
        return models

    def get_all_providers(self) -> Dict[str, EmbeddingProviderConfig]:
        """Get all provider configurations"""
        return self._providers

    def get_provider(self, provider_name: str) -> Optional[EmbeddingProviderConfig]:
        """Get a specific provider configuration"""
        return self._providers.get(provider_name)

    def get_provider_summary(self) -> Dict[str, Any]:
        """Get summary of all providers"""
        return {
            "total_providers": len(self._providers),
            "providers": [p.name for p in self._providers.values()]
        }

    def validate_provider_config(self, provider_name: str) -> Dict[str, Any]:
        """Validate a provider's configuration"""
        provider = self.get_provider(provider_name)
        if not provider:
            return {"valid": False, "error": f"Provider {provider_name} not found"}

        # Check required fields
        if not provider.class_name:
            return {"valid": False, "error": "Missing class_name"}
        if not provider.api_key_env_vars:
            return {"valid": False, "error": "Missing api_key_env_vars"}

        return {"valid": True}


# Global instance
embedding_config = EmbeddingConfig()


