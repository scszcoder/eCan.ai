#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM Provider Types - Simplified data structures
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class LLMProvider:
    """LLM Provider data structure - simplified version"""
    name: str
    display_name: str
    api_key: Optional[str]  # Store API key value directly, obtained from environment variables

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'name': self.name,
            'display_name': self.display_name,
            'api_key': self.api_key,
            'is_configured': bool(self.api_key)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LLMProvider':
        """Create instance from dictionary"""
        return cls(
            name=data['name'],
            display_name=data['display_name'],
            api_key=data.get('api_key')
        )


class LLMProviderManager:
    """LLM Provider manager - simplified version"""

    @staticmethod
    def mask_api_key(api_key: Optional[str]) -> str:
        """Mask display API key"""
        if not api_key:
            return ''
        if len(api_key) <= 10:
            return '*' * len(api_key)
        return f"{api_key[:6]}{'*' * 10}{api_key[-4:]}"

    @staticmethod
    def providers_to_dict_list(providers: List[LLMProvider]) -> List[Dict[str, Any]]:
        """Convert providers list to dictionary list"""
        return [provider.to_dict() for provider in providers]

    @staticmethod
    def providers_from_dict_list(data: List[Dict[str, Any]]) -> List[LLMProvider]:
        """Create providers list from dictionary list"""
        return [LLMProvider.from_dict(item) for item in data]
