#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM Provider Types - 简化的数据结构
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class LLMProvider:
    """LLM Provider数据结构 - 简化版"""
    name: str
    display_name: str
    api_key: Optional[str]  # 直接存储API key值，从环境变量获取

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'name': self.name,
            'display_name': self.display_name,
            'api_key': self.api_key,
            'is_configured': bool(self.api_key)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LLMProvider':
        """从字典创建实例"""
        return cls(
            name=data['name'],
            display_name=data['display_name'],
            api_key=data.get('api_key')
        )


class LLMProviderManager:
    """LLM Provider管理器 - 简化版"""

    @staticmethod
    def mask_api_key(api_key: Optional[str]) -> str:
        """掩码显示API key"""
        if not api_key:
            return ''
        if len(api_key) <= 10:
            return '*' * len(api_key)
        return f"{api_key[:6]}{'*' * 10}{api_key[-4:]}"

    @staticmethod
    def providers_to_dict_list(providers: List[LLMProvider]) -> List[Dict[str, Any]]:
        """将providers列表转换为字典列表"""
        return [provider.to_dict() for provider in providers]

    @staticmethod
    def providers_from_dict_list(data: List[Dict[str, Any]]) -> List[LLMProvider]:
        """从字典列表创建providers列表"""
        return [LLMProvider.from_dict(item) for item in data]
