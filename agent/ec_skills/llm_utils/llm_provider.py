"""
LLM Provider Model

This module provides a class-based model for LLM provider configuration,
replacing dict-based configurations with a more structured and maintainable approach.
"""

import os
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from utils.env.secure_store import secure_store


class ProviderType(Enum):
    """Enum for LLM provider types"""
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    CLAUDE = "claude"
    GOOGLE = "google"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    QWQ = "qwq"
    DASHSCOPE = "dashscope"
    BEDROCK = "bedrock"
    OLLAMA = "ollama"
    UNKNOWN = "unknown"
    
    @classmethod
    def from_string(cls, value: str) -> 'ProviderType':
        """Convert string to ProviderType enum"""
        value_lower = value.lower()
        for provider_type in cls:
            if provider_type.value == value_lower:
                return provider_type
        return cls.UNKNOWN


@dataclass
class LLMModel:
    """Model configuration for a specific LLM model"""
    name: str
    display_name: str
    model_id: str
    default_temperature: float = 0.7
    max_tokens: Optional[int] = None
    supports_streaming: bool = True
    supports_function_calling: bool = False
    supports_vision: bool = False
    cost_per_1k_tokens: Optional[float] = None
    description: str = ""
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LLMModel':
        """Create LLMModel from dictionary"""
        return cls(
            name=data.get('name', ''),
            display_name=data.get('display_name', ''),
            model_id=data.get('model_id', ''),
            default_temperature=data.get('default_temperature', 0.7),
            max_tokens=data.get('max_tokens'),
            supports_streaming=data.get('supports_streaming', True),
            supports_function_calling=data.get('supports_function_calling', False),
            supports_vision=data.get('supports_vision', False),
            cost_per_1k_tokens=data.get('cost_per_1k_tokens'),
            description=data.get('description', '')
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


@dataclass
class LLMProvider:
    """
    LLM Provider configuration class.
    
    This class provides a structured way to manage LLM provider configurations,
    replacing dict-based configurations with a type-safe, IDE-friendly approach.
    
    Attributes:
        name: Provider name (e.g., "OpenAI", "DeepSeek")
        display_name: Human-readable display name
        provider_type: Type of provider (ProviderType enum)
        class_name: LangChain class name (e.g., "ChatOpenAI")
        api_key_env_vars: List of environment variable names for API keys
        base_url: Base URL for API (optional)
        default_model: Default model to use
        preferred_model: Preferred model (overrides default_model if set)
        supported_models: List of supported models
        description: Provider description
        documentation_url: URL to provider documentation
        is_local: Whether this is a local provider (e.g., Ollama)
        api_key_configured: Whether API key is configured
        temperature: Default temperature
    """
    name: str
    display_name: str
    provider_type: ProviderType
    class_name: str
    api_key_env_vars: List[str] = field(default_factory=list)
    base_url: Optional[str] = None
    default_model: Optional[str] = None
    preferred_model: Optional[str] = None
    supported_models: List[LLMModel] = field(default_factory=list)
    description: str = ""
    documentation_url: str = ""
    is_local: bool = False
    api_key_configured: bool = False
    temperature: float = 0.7
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LLMProvider':
        """
        Create LLMProvider from dictionary.
        
        Args:
            data: Dictionary containing provider configuration
            
        Returns:
            LLMProvider instance
        """
        # Parse provider type
        provider_type_str = data.get('provider', 'unknown')
        provider_type = ProviderType.from_string(provider_type_str)
        
        # Parse supported models
        supported_models = []
        models_data = data.get('supported_models', [])
        if isinstance(models_data, list):
            for model_data in models_data:
                if isinstance(model_data, dict):
                    supported_models.append(LLMModel.from_dict(model_data))
        
        return cls(
            name=data.get('name', ''),
            display_name=data.get('display_name', ''),
            provider_type=provider_type,
            class_name=data.get('class_name', ''),
            api_key_env_vars=data.get('api_key_env_vars', []),
            base_url=data.get('base_url'),
            default_model=data.get('default_model'),
            preferred_model=data.get('preferred_model'),
            supported_models=supported_models,
            description=data.get('description', ''),
            documentation_url=data.get('documentation_url', ''),
            is_local=data.get('is_local', False),
            api_key_configured=data.get('api_key_configured', False),
            temperature=data.get('temperature', 0.7)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for backward compatibility.
        
        Returns:
            Dictionary representation
        """
        result = {
            'name': self.name,
            'display_name': self.display_name,
            'provider': self.provider_type.value,
            'class_name': self.class_name,
            'api_key_env_vars': self.api_key_env_vars,
            'base_url': self.base_url,
            'default_model': self.default_model,
            'preferred_model': self.preferred_model,
            'supported_models': [model.to_dict() for model in self.supported_models],
            'description': self.description,
            'documentation_url': self.documentation_url,
            'is_local': self.is_local,
            'api_key_configured': self.api_key_configured,
            'temperature': self.temperature
        }
        return result
    
    def get_model_name(self) -> Optional[str]:
        """
        Get the model name to use, prioritizing preferred_model over default_model.
        
        Returns:
            Model name or None
        """
        if self.preferred_model:
            return self.preferred_model
        elif self.default_model:
            return self.default_model
        elif self.supported_models:
            # Use the first supported model's model_id
            first_model = self.supported_models[0]
            return first_model.model_id
        return None
    
    def get_api_key(self) -> Optional[str]:
        """
        Get API key from secure store with user isolation (no env fallback).
        """
        try:
            # Get current username for user isolation
            from utils.env.secure_store import get_current_username
            username = get_current_username()
            
            for env_var in self.api_key_env_vars:
                api_key = secure_store.get(env_var, username=username)
                if api_key and api_key.strip():
                    return api_key
            return None
        except Exception:
            return None
    
    def is_openai_compatible(self) -> bool:
        """
        Check if provider is OpenAI-compatible.
        
        Returns:
            True if provider uses OpenAI-compatible API
        """
        openai_compatible_types = [
            ProviderType.OPENAI,
            ProviderType.AZURE_OPENAI,
            ProviderType.DEEPSEEK,
            ProviderType.QWEN,
            ProviderType.QWQ,
            ProviderType.DASHSCOPE,
            ProviderType.OLLAMA
        ]
        return self.provider_type in openai_compatible_types or 'openai' in self.class_name.lower()
    
    def is_browser_use_compatible(self) -> bool:
        """
        Check if provider is compatible with browser_use.
        
        browser_use primarily supports OpenAI-compatible APIs.
        
        Returns:
            True if provider can be used with browser_use
        """
        return self.is_openai_compatible()
    
    def supports_streaming(self) -> bool:
        """
        Check if provider supports streaming.
        
        Returns:
            True if streaming is supported
        """
        if self.supported_models:
            # Check if at least one model supports streaming
            return any(model.supports_streaming for model in self.supported_models)
        # Default to True for OpenAI-compatible providers
        return self.is_openai_compatible()
    
    def supports_function_calling(self) -> bool:
        """
        Check if provider supports function calling.
        
        Returns:
            True if function calling is supported
        """
        if self.supported_models:
            return any(model.supports_function_calling for model in self.supported_models)
        # OpenAI, Anthropic, Google support function calling
        return self.provider_type in [
            ProviderType.OPENAI,
            ProviderType.AZURE_OPENAI,
            ProviderType.ANTHROPIC,
            ProviderType.CLAUDE,
            ProviderType.GOOGLE,
            ProviderType.GEMINI
        ]
    
    def __str__(self) -> str:
        """String representation"""
        return f"LLMProvider(name={self.name}, type={self.provider_type.value}, model={self.get_model_name()})"
    
    def __repr__(self) -> str:
        """Detailed representation"""
        return (f"LLMProvider(name={self.name!r}, display_name={self.display_name!r}, "
                f"provider_type={self.provider_type}, class_name={self.class_name!r}, "
                f"model={self.get_model_name()!r})")


def create_provider_from_dict(data: Dict[str, Any]) -> LLMProvider:
    """
    Convenience function to create LLMProvider from dictionary.
    
    Args:
        data: Dictionary containing provider configuration
        
    Returns:
        LLMProvider instance
    """
    return LLMProvider.from_dict(data)


def create_providers_from_dict(providers_dict: Dict[str, Dict[str, Any]]) -> Dict[str, LLMProvider]:
    """
    Create multiple LLMProvider instances from a dictionary of providers.
    
    Args:
        providers_dict: Dictionary mapping provider names to their configurations
        
    Returns:
        Dictionary mapping provider names to LLMProvider instances
    """
    return {
        name: LLMProvider.from_dict(config)
        for name, config in providers_dict.items()
    }

