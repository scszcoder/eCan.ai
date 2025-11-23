"""
LLM Configuration Management

This module manages LLM (Large Language Model) configurations including:
- LLM provider definitions and metadata
- Model configurations and parameters
- API key requirements
- Default settings and supported features

Configuration is loaded from llm_providers.json for easy modification and extension.
"""

import os
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from agent.models import REQUIRED_LLM_API_ENV_VARS
from utils.logger_helper import logger_helper as logger


class LLMProvider(Enum):
    """LLM Provider enumeration"""
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    BEDROCK = "bedrock"
    GOOGLE = "google"
    DEEPSEEK = "deepseek"
    DASHSCOPE = "dashscope"
    BYTEDANCE = "bytedance"
    BAIDU_QIANFAN = "baidu_qianfan"
    OLLAMA = "ollama"


@dataclass
class LLMModelConfig:
    """Configuration for a specific LLM model"""
    name: str
    display_name: str
    provider: LLMProvider
    model_id: str
    default_temperature: float = 0.7
    max_tokens: Optional[int] = None
    supports_streaming: bool = True
    supports_function_calling: bool = False
    supports_vision: bool = False
    cost_per_1k_tokens: Optional[float] = None
    description: str = ""


@dataclass
class LLMProviderConfig:
    """Configuration for an LLM provider"""
    name: str
    display_name: str
    provider: LLMProvider
    class_name: str
    api_key_env_vars: List[str]
    base_url: Optional[str] = None
    default_model: Optional[str] = None
    supported_models: List[LLMModelConfig] = field(default_factory=list)
    description: str = ""
    documentation_url: str = ""
    is_local: bool = False


class LLMConfig:
    """Main LLM configuration manager"""

    def __init__(self, config_file_path: Optional[str] = None):
        """
        Initialize LLM configuration

        Args:
            config_file_path: Path to the JSON configuration file.
                            If None, uses default path.
        """
        if config_file_path is None:
            # Default path relative to this file
            config_file_path = os.path.join(os.path.dirname(__file__), 'llm_providers.json')

        self.config_file_path = config_file_path
        self._config_data = self._load_config()
        self._providers = self._initialize_providers()
        self._models = self._initialize_models()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file"""
        try:
            with open(self.config_file_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            logger.info(f"Loaded LLM configuration from {self.config_file_path}")
            return config_data

        except FileNotFoundError:
            logger.error(f"LLM configuration file not found: {self.config_file_path}")
            return {"providers": {}, "metadata": {}}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in LLM configuration file: {e}")
            return {"providers": {}, "metadata": {}}
        except Exception as e:
            logger.error(f"Error loading LLM configuration: {e}")
            return {"providers": {}, "metadata": {}}
    
    def _initialize_providers(self) -> Dict[str, LLMProviderConfig]:
        """Initialize LLM provider configurations from JSON data"""
        providers = {}

        providers_data = self._config_data.get("providers", {})

        for provider_name, provider_data in providers_data.items():
            try:
                # Convert provider string to enum
                provider_enum = LLMProvider(provider_data.get("provider", "openai"))

                # Create provider config
                provider_config = LLMProviderConfig(
                    name=provider_data.get("name", provider_name),
                    display_name=provider_data.get("display_name", provider_name),
                    provider=provider_enum,
                    class_name=provider_data.get("class_name", provider_name),
                    api_key_env_vars=provider_data.get("api_key_env_vars", []),
                    base_url=provider_data.get("base_url"),
                    default_model=provider_data.get("default_model"),
                    description=provider_data.get("description", ""),
                    documentation_url=provider_data.get("documentation_url", ""),
                    is_local=provider_data.get("is_local", False)
                )

                providers[provider_name] = provider_config

            except ValueError as e:
                logger.warning(f"Invalid provider enum value for {provider_name}: {e}")
                continue
            except Exception as e:
                logger.error(f"Error initializing provider {provider_name}: {e}")
                continue

        logger.info(f"Initialized {len(providers)} LLM providers from configuration")
        return providers

    def _initialize_models(self) -> Dict[str, List[LLMModelConfig]]:
        """Initialize model configurations for each provider from JSON data"""
        models = {}

        providers_data = self._config_data.get("providers", {})

        for provider_name, provider_data in providers_data.items():
            provider_models = []

            supported_models = provider_data.get("supported_models", [])

            # Get provider enum for models
            provider_enum = None
            try:
                provider_enum = LLMProvider(provider_data.get("provider", "openai"))
            except ValueError:
                logger.warning(f"Invalid provider enum for {provider_name}, using OPENAI as default")
                provider_enum = LLMProvider.OPENAI

            for model_data in supported_models:
                try:
                    model_config = LLMModelConfig(
                        name=model_data.get("name", ""),
                        display_name=model_data.get("display_name", ""),
                        provider=provider_enum,
                        model_id=model_data.get("model_id", ""),
                        default_temperature=model_data.get("default_temperature", 0.7),
                        max_tokens=model_data.get("max_tokens", 4096),
                        supports_streaming=model_data.get("supports_streaming", True),
                        supports_function_calling=model_data.get("supports_function_calling", False),
                        supports_vision=model_data.get("supports_vision", False),
                        cost_per_1k_tokens=model_data.get("cost_per_1k_tokens", 0.0),
                        description=model_data.get("description", "")
                    )

                    provider_models.append(model_config)

                except Exception as e:
                    logger.error(f"Error initializing model {model_data.get('name', 'unknown')} for provider {provider_name}: {e}")
                    continue

            if provider_models:
                models[provider_name] = provider_models

        # Set supported models for each provider
        for provider_name, provider_models in models.items():
            if provider_name in self._providers:
                self._providers[provider_name].supported_models = provider_models

        logger.info(f"Initialized models for {len(models)} providers from configuration")
        return models

    # Public API methods
    def get_all_providers(self) -> Dict[str, LLMProviderConfig]:
        """Get all LLM provider configurations"""
        return self._providers.copy()

    def get_provider(self, provider_name: str) -> Optional[LLMProviderConfig]:
        """Get a specific provider configuration"""
        return self._providers.get(provider_name)

    def get_provider_by_class_name(self, class_name: str) -> Optional[LLMProviderConfig]:
        """Get provider configuration by class name"""
        for provider in self._providers.values():
            if provider.class_name == class_name:
                return provider
        return None

    def get_models_for_provider(self, provider_name: str) -> List[LLMModelConfig]:
        """Get all models for a specific provider"""
        return self._models.get(provider_name, [])

    def get_model(self, provider_name: str, model_name: str) -> Optional[LLMModelConfig]:
        """Get a specific model configuration"""
        models = self.get_models_for_provider(provider_name)
        for model in models:
            if model.name == model_name:
                return model
        return None

    def get_required_env_vars(self, provider_name: str) -> List[str]:
        """Get required environment variables for a provider"""
        provider = self.get_provider(provider_name)
        return provider.api_key_env_vars if provider else []

    def get_all_required_env_vars(self) -> Dict[str, List[str]]:
        """Get all required environment variables for all providers"""
        return REQUIRED_LLM_API_ENV_VARS.copy()

    def get_providers_by_env_var(self, env_var: str) -> List[LLMProviderConfig]:
        """Get all providers that use a specific environment variable"""
        providers = []
        for provider in self._providers.values():
            if env_var in provider.api_key_env_vars:
                providers.append(provider)
        return providers

    def is_provider_local(self, provider_name: str) -> bool:
        """Check if a provider is local (doesn't require API keys)"""
        provider = self.get_provider(provider_name)
        return provider.is_local if provider else False

    def get_default_model_for_provider(self, provider_name: str) -> Optional[str]:
        """Get the default model for a provider"""
        provider = self.get_provider(provider_name)
        return provider.default_model if provider else None

    def validate_provider_config(self, provider_name: str) -> Dict[str, Any]:
        """Validate provider configuration and return status"""
        provider = self.get_provider(provider_name)
        if not provider:
            return {
                'valid': False,
                'error': f'Provider {provider_name} not found'
            }

        result = {
            'valid': True,
            'provider': provider.display_name,
            'requires_api_key': len(provider.api_key_env_vars) > 0,
            'is_local': provider.is_local,
            'missing_env_vars': []
        }

        # Check for missing environment variables
        if not provider.is_local:
            for env_var in provider.api_key_env_vars:
                if not os.getenv(env_var):
                    result['missing_env_vars'].append(env_var)

            if result['missing_env_vars']:
                result['valid'] = False
                result['error'] = f"Missing environment variables: {', '.join(result['missing_env_vars'])}"

        return result

    def get_max_tokens(self, provider_identifier: str, model_name: str) -> int:
        """
        Get max tokens for a specific provider (by canonical identifier) and model.
        
        Args:
            provider_identifier: Canonical provider identifier (e.g., "baidu_qianfan", "openai")
            model_name: Model name/ID
            
        Returns:
            Max tokens limit, or a default safe value (25536) if not found
        """
        try:
            provider_id_lower = (provider_identifier or "").strip().lower()
            target_provider_config = None
            
            # Find provider config by matching canonical identifier
            for p_name, p_conf in self._providers.items():
                if p_conf.provider.value == provider_id_lower:
                    target_provider_config = p_conf
                    break
            
            if not target_provider_config:
                return 25536  # Default
                
            target_model = model_name or target_provider_config.default_model
            if not target_model:
                return 25536

            # Look up model config using provider's lookup name (p_conf.name)
            # Since _models is keyed by provider name (e.g. "百度千帆")
            model_conf = self.get_model(target_provider_config.name, target_model)
            
            if model_conf and model_conf.max_tokens:
                return model_conf.max_tokens
                
            # Fallback for specific providers if model config missing
            if provider_id_lower in ("baidu", "qianfan", "baidu_qianfan"):
                return 4000
                
            return 25536
        except Exception as e:
            logger.error(f"Error getting max tokens: {e}")
            return 25536

    def get_provider_summary(self) -> Dict[str, Any]:
        """Get a summary of all providers and their status"""
        summary = {
            'total_providers': len(self._providers),
            'local_providers': 0,
            'cloud_providers': 0,
            'configured_providers': 0,
            'providers': {}
        }

        for name, provider in self._providers.items():
            validation = self.validate_provider_config(name)

            if provider.is_local:
                summary['local_providers'] += 1
            else:
                summary['cloud_providers'] += 1

            if validation['valid']:
                summary['configured_providers'] += 1

            summary['providers'][name] = {
                'display_name': provider.display_name,
                'is_local': provider.is_local,
                'configured': validation['valid'],
                'model_count': len(provider.supported_models),
                'default_model': provider.default_model
            }

        return summary

    def save_config(self) -> bool:
        """Save current configuration to JSON file"""
        try:
            # Update metadata
            self._config_data["metadata"]["last_updated"] = "2025-01-16"

            with open(self.config_file_path, 'w', encoding='utf-8') as f:
                json.dump(self._config_data, f, indent=2, ensure_ascii=False)

            logger.info(f"LLM configuration saved to {self.config_file_path}")
            return True

        except Exception as e:
            logger.error(f"Error saving LLM configuration: {e}")
            return False

    def reload_config(self) -> bool:
        """Reload configuration from JSON file"""
        try:
            self._config_data = self._load_config()
            self._providers = self._initialize_providers()
            self._models = self._initialize_models()

            logger.info("LLM configuration reloaded successfully")
            return True

        except Exception as e:
            logger.error(f"Error reloading LLM configuration: {e}")
            return False

    def add_provider(self, provider_data: Dict[str, Any]) -> bool:
        """Add a new provider to the configuration"""
        try:
            provider_name = provider_data.get("name")
            if not provider_name:
                logger.error("Provider name is required")
                return False

            if provider_name in self._config_data["providers"]:
                logger.warning(f"Provider {provider_name} already exists")
                return False

            self._config_data["providers"][provider_name] = provider_data

            # Reinitialize providers and models
            self._providers = self._initialize_providers()
            self._models = self._initialize_models()

            logger.info(f"Added new provider: {provider_name}")
            return True

        except Exception as e:
            logger.error(f"Error adding provider: {e}")
            return False

    def update_provider(self, provider_name: str, provider_data: Dict[str, Any]) -> bool:
        """Update an existing provider configuration"""
        try:
            if provider_name not in self._config_data["providers"]:
                logger.error(f"Provider {provider_name} not found")
                return False

            self._config_data["providers"][provider_name].update(provider_data)

            # Reinitialize providers and models
            self._providers = self._initialize_providers()
            self._models = self._initialize_models()

            logger.info(f"Updated provider: {provider_name}")
            return True

        except Exception as e:
            logger.error(f"Error updating provider {provider_name}: {e}")
            return False

    def remove_provider(self, provider_name: str) -> bool:
        """Remove a provider from the configuration"""
        try:
            if provider_name not in self._config_data["providers"]:
                logger.error(f"Provider {provider_name} not found")
                return False

            del self._config_data["providers"][provider_name]

            # Reinitialize providers and models
            self._providers = self._initialize_providers()
            self._models = self._initialize_models()

            logger.info(f"Removed provider: {provider_name}")
            return True

        except Exception as e:
            logger.error(f"Error removing provider {provider_name}: {e}")
            return False

    def get_config_metadata(self) -> Dict[str, Any]:
        """Get configuration metadata"""
        return self._config_data.get("metadata", {})


# Global instance
llm_config = LLMConfig()
