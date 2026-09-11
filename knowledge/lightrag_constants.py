"""
LightRAG Constants

Centralized constants for LightRAG configuration and provider management.
"""

import json
import os
from typing import List, Set

# Default rerank binding format for proxy providers
DEFAULT_PROXY_RERANK_BINDING = 'jina'

# Cache for provider lists
_native_providers_cache: Set[str] = None
_proxy_providers_cache: Set[str] = None


def _load_rerank_providers_config() -> dict:
    """Load rerank providers configuration from JSON file."""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'gui', 'config', 'rerank_providers.json'
    )
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        # Fallback to hardcoded values if file not found
        return {
            'providers': {
                'Cohere': {'provider': 'cohere', 'is_local': False},
                'Jina AI': {'provider': 'jina', 'is_local': False},
                'Alibaba Qwen': {'provider': 'aliyun', 'is_local': False},
            }
        }


def get_lightrag_native_rerank_providers() -> Set[str]:
    """
    Get list of LightRAG native rerank providers.
    
    Native providers are those directly supported by LightRAG core without proxy.
    Currently LightRAG natively supports: cohere, jina, aliyun
    
    Returns:
        Set of native provider names (lowercase)
    """
    # LightRAG core natively supports these providers
    # See: https://github.com/HKUDS/LightRAG/blob/main/lightrag/rerank.py
    return {'cohere', 'jina', 'aliyun'}


def get_lightrag_proxy_rerank_providers() -> Set[str]:
    """
    Get list of rerank providers that require proxy routing.
    
    Proxy providers are local providers (Ollama, RyoAIS, etc.) that need
    to be routed through the local rerank proxy.
    
    Returns:
        Set of proxy provider names (lowercase)
    """
    global _proxy_providers_cache
    
    if _proxy_providers_cache is None:
        config = _load_rerank_providers_config()
        _proxy_providers_cache = set()
        
        for provider_config in config.get('providers', {}).values():
            # Proxy providers are local providers
            if provider_config.get('is_local', False):
                provider_name = provider_config.get('provider', '').lower()
                if provider_name:
                    _proxy_providers_cache.add(provider_name)
    
    return _proxy_providers_cache


def is_native_rerank_provider(provider: str) -> bool:
    """Check if a provider is a native LightRAG rerank provider."""
    return provider.lower() in get_lightrag_native_rerank_providers()


def is_proxy_rerank_provider(provider: str) -> bool:
    """Check if a provider requires proxy routing."""
    return provider.lower() in get_lightrag_proxy_rerank_providers()


# ── Shared disable sentinels ─────────────────────────────────────────────
# Used by both the UI disable path and the server/proxy passthrough paths.
# Centralizing here ensures all three layers agree on what "rerank disabled" means.
# The proxy additionally checks ``not binding`` (empty string) to cover the case
# where RERANK_BINDING is absent from lightrag.env entirely.
RERANK_DISABLE_SENTINELS: frozenset = frozenset({
    '', 'null', 'none', 'disabled', 'off', 'false', '0',
})


def is_rerank_disabled(binding: str) -> bool:
    """Return True when ``binding`` represents a disabled rerank state."""
    return not binding or binding.lower() in RERANK_DISABLE_SENTINELS
