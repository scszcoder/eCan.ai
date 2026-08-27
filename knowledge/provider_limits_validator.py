"""
Provider Limits Validator

智能配置验证系统，根据不同 embedding provider 的 API 限制自动调整配置值。

功能：
1. 从 embedding_providers.json 读取各 provider 的 API 限制
2. 验证配置值是否超过限制
3. 自动调整超限配置为最大允许值
4. 提供配置建议和警告信息
"""

import os
import sys
import json
from typing import Dict, Any, Optional, Tuple
from utils.logger_helper import logger_helper as logger


class ProviderLimitsValidator:
    """Provider 配置限制验证器"""
    
    def __init__(self):
        """初始化验证器，加载 provider 配置"""
        self.providers_config = self._load_providers_config()
        self.default_limits = {
            'max_batch_size': 128,  # 默认最大批量大小
            'rate_limit_rpm': None,
            'rate_limit_tpm': None
        }
    
    def _load_providers_config(self) -> Dict[str, Any]:
        """加载 embedding_providers.json 配置文件"""
        try:
            # 获取配置文件路径
            if getattr(sys, 'frozen', False):
                # PyInstaller 打包环境
                base_path = sys._MEIPASS
            else:
                # 开发环境
                base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            
            config_path = os.path.join(base_path, 'gui', 'config', 'embedding_providers.json')
            
            if not os.path.exists(config_path):
                logger.warning(f"[ProviderLimitsValidator] Config file not found: {config_path}")
                return {}
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            logger.info(f"[ProviderLimitsValidator] Loaded {len(config.get('providers', {}))} provider configurations")
            return config.get('providers', {})
            
        except Exception as e:
            logger.error(f"[ProviderLimitsValidator] Failed to load providers config: {e}")
            return {}
    
    def get_provider_limits(self, provider_name: str) -> Dict[str, Any]:
        """
        获取指定 provider 的 API 限制
        
        Args:
            provider_name: Provider 名称（如 'openai', 'alibaba_qwen', 'ryoais'）
        
        Returns:
            包含 API 限制的字典，如果找不到则返回默认限制
        """
        # 标准化 provider 名称（小写）
        provider_key = provider_name.lower().strip()
        
        # 尝试精确匹配
        for key, config in self.providers_config.items():
            if config.get('provider', '').lower() == provider_key:
                limits = config.get('api_limits', self.default_limits.copy())
                logger.debug(f"[ProviderLimitsValidator] Found limits for {provider_name}: {limits}")
                return limits
        
        # 尝试模糊匹配（display_name）
        for key, config in self.providers_config.items():
            if provider_key in key.lower():
                limits = config.get('api_limits', self.default_limits.copy())
                logger.debug(f"[ProviderLimitsValidator] Found limits for {provider_name} (fuzzy match): {limits}")
                return limits
        
        logger.warning(f"[ProviderLimitsValidator] No limits found for {provider_name}, using defaults")
        return self.default_limits.copy()
    
    def validate_batch_size(self, provider_name: str, batch_size: int) -> Tuple[bool, int, Optional[str]]:
        """
        验证批量大小是否符合 provider 限制
        
        Args:
            provider_name: Provider 名称
            batch_size: 配置的批量大小
        
        Returns:
            (is_valid, adjusted_value, warning_message)
            - is_valid: 是否有效（未超限）
            - adjusted_value: 调整后的值（如果超限则为最大允许值）
            - warning_message: 警告信息（如果有）
        """
        limits = self.get_provider_limits(provider_name)
        max_batch_size = limits.get('max_batch_size')
        
        # 如果没有限制，返回原值
        if max_batch_size is None:
            return True, batch_size, None
        
        # 检查是否超限
        if batch_size > max_batch_size:
            warning = (
                f"⚠️  EMBEDDING_BATCH_NUM ({batch_size}) exceeds {provider_name} limit ({max_batch_size}). "
                f"Auto-adjusted to {max_batch_size}."
            )
            logger.warning(f"[ProviderLimitsValidator] {warning}")
            return False, max_batch_size, warning
        
        # 未超限
        return True, batch_size, None
    
    def validate_and_adjust_config(self, provider_name: str, config: Dict[str, Any]) -> Tuple[Dict[str, Any], list]:
        """
        验证并调整配置，确保所有值符合 provider 限制。

        Args:
            provider_name: Provider 名称
            config: 配置字典（包含 EMBEDDING_BATCH_NUM 等）

        Returns:
            (adjusted_config, warnings)
            - adjusted_config: 调整后的配置字典（缺失字段会自动填入安全默认值）
            - warnings: 警告信息列表
        """
        adjusted_config = config.copy()
        warnings = []

        limits = self.get_provider_limits(provider_name)
        max_batch_size = limits.get('max_batch_size', 128)

        # --- EMBEDDING_BATCH_NUM: 用户未配置时自动填入安全默认值 ---
        if 'EMBEDDING_BATCH_NUM' not in config:
            safe_batch = min(max_batch_size, 64)
            adjusted_config['EMBEDDING_BATCH_NUM'] = safe_batch
            warnings.append(
                f"EMBEDDING_BATCH_NUM not set; auto-configured to {safe_batch} for {provider_name}."
            )
        else:
            try:
                batch_size = int(config['EMBEDDING_BATCH_NUM'])
                is_valid, adjusted_value, warning = self.validate_batch_size(provider_name, batch_size)
                if not is_valid:
                    adjusted_config['EMBEDDING_BATCH_NUM'] = adjusted_value
                    warnings.append(warning)
            except (ValueError, TypeError) as e:
                logger.error(f"[ProviderLimitsValidator] Invalid EMBEDDING_BATCH_NUM value: {config['EMBEDDING_BATCH_NUM']}")

        # --- EMBEDDING_FUNC_MAX_ASYNC: 用户未配置时自动填入安全默认值 ---
        if 'EMBEDDING_FUNC_MAX_ASYNC' not in config:
            is_local = self._is_local_provider(provider_name)
            safe_async = 8 if is_local else 16
            adjusted_config['EMBEDDING_FUNC_MAX_ASYNC'] = safe_async
            warnings.append(
                f"EMBEDDING_FUNC_MAX_ASYNC not set; auto-configured to {safe_async} for {provider_name}."
            )

        # --- MAX_PARALLEL_INSERT: 用户未配置时自动填入安全默认值 ---
        if 'MAX_PARALLEL_INSERT' not in config:
            is_local = self._is_local_provider(provider_name)
            safe_insert = 4 if is_local else 8
            adjusted_config['MAX_PARALLEL_INSERT'] = safe_insert
            warnings.append(
                f"MAX_PARALLEL_INSERT not set; auto-configured to {safe_insert}."
            )

        # --- MAX_GLEANING: LightRAG 每 chunk 的 gleaning LLM 调用次数。
        # 0 砍掉每 chunk 第 2 次 LLM round-trip，单文档总耗时直接减半。
        # 短 chunk 检索质量几乎不变；长 chunk 会少抓 5-10% 隐藏 entity。
        # 用户可在 LightRAG Settings UI 自由调整，所以"用户没设"才自动填。
        if 'MAX_GLEANING' not in config:
            adjusted_config['MAX_GLEANING'] = 0
            warnings.append(
                "MAX_GLEANING not set; auto-configured to 0 (skips second entity "
                "extraction pass — ~50% speedup, may miss 5-10% entities on "
                "long chunks)."
            )

        # --- MAX_ASYNC_LLM: LightRAG 1.5.6 优先读此 env，没有则回退 MAX_ASYNC。
        # 默认 2（云端/本地统一）。原因：
        #   - chunk LLM 并发过高时，一旦某次 LLM 卡住（云端超时可达 240s），
        #     cancel 请求要等所有 in-flight LLM 返回才能结束，
        #     stop 延迟会被卡死的 LLM 拖到分钟级。
        #   - 2 并发下 stop 最坏延迟 ≈ 2 × 5s（正常 chunk）≈ 10s；
        #   6 并发下 stop 最坏延迟 ≈ 6 × 30s（卡死 chunk）≈ 3 分钟。
        # 用户 GUI 里调过 MAX_ASYNC_LLM 的会通过 config_manager 写到 env，
        # 所以这里只在"完全没设"时生效——用户手动设的值不会被覆盖。
        if 'MAX_ASYNC_LLM' not in config:
            adjusted_config['MAX_ASYNC_LLM'] = 2
            warnings.append(
                "MAX_ASYNC_LLM not set; auto-configured to 2 (uniform default — "
                "balances stop latency vs throughput)."
            )

        return adjusted_config, warnings
    
    def get_recommended_config(self, provider_name: str) -> Dict[str, Any]:
        """
        获取指定 provider 的推荐配置
        
        Args:
            provider_name: Provider 名称
        
        Returns:
            推荐配置字典
        """
        limits = self.get_provider_limits(provider_name)
        max_batch_size = limits.get('max_batch_size', 128)
        
        # 根据 provider 类型给出不同的推荐配置
        is_local = self._is_local_provider(provider_name)
        
        if is_local:
            # 本地 provider（Ollama, RyoAIS）- 更保守的配置
            recommended = {
                'EMBEDDING_BATCH_NUM': min(max_batch_size, 32),
                'EMBEDDING_FUNC_MAX_ASYNC': 8,
                'MAX_PARALLEL_INSERT': 4,
                'MAX_GLEANING': 0,
                'MAX_ASYNC_LLM': 2,
            }
        else:
            # 云端 provider - 可以更激进
            recommended = {
                'EMBEDDING_BATCH_NUM': min(max_batch_size, 64),
                'EMBEDDING_FUNC_MAX_ASYNC': 16,
                'MAX_PARALLEL_INSERT': 8,
                'MAX_GLEANING': 0,
                'MAX_ASYNC_LLM': 2,
            }
        
        logger.info(f"[ProviderLimitsValidator] Recommended config for {provider_name}: {recommended}")
        return recommended
    
    def _is_local_provider(self, provider_name: str) -> bool:
        """判断是否为本地 provider"""
        local_providers = ['ollama', 'ryoais']
        return provider_name.lower() in local_providers
    
    def get_all_provider_limits(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有 provider 的限制信息
        
        Returns:
            {provider_name: limits} 字典
        """
        all_limits = {}
        for key, config in self.providers_config.items():
            provider_name = config.get('provider', key)
            limits = config.get('api_limits', self.default_limits.copy())
            all_limits[provider_name] = limits
        
        return all_limits


# 全局单例
_validator_instance = None


def get_validator() -> ProviderLimitsValidator:
    """获取全局验证器实例"""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = ProviderLimitsValidator()
    return _validator_instance


def validate_lightrag_config(provider_name: str, config: Dict[str, Any]) -> Tuple[Dict[str, Any], list]:
    """
    便捷函数：验证并调整 LightRAG 配置
    
    Args:
        provider_name: Embedding provider 名称
        config: 配置字典
    
    Returns:
        (adjusted_config, warnings)
    """
    validator = get_validator()
    return validator.validate_and_adjust_config(provider_name, config)


if __name__ == '__main__':
    # 测试代码
    import sys
    
    validator = ProviderLimitsValidator()
    
    # 测试各个 provider
    test_providers = [
        ('openai', 2048),
        ('alibaba_qwen', 10),
        ('ryoais', 10),
        ('azure_openai', 16),
        ('ollama', 128),
    ]
    
    print("\n=== Provider Limits Test ===\n")
    for provider, expected_limit in test_providers:
        limits = validator.get_provider_limits(provider)
        print(f"{provider:20} -> max_batch_size: {limits.get('max_batch_size')}")
        assert limits.get('max_batch_size') == expected_limit, f"Expected {expected_limit}, got {limits.get('max_batch_size')}"
    
    print("\n=== Batch Size Validation Test ===\n")
    # 测试超限情况
    is_valid, adjusted, warning = validator.validate_batch_size('alibaba_qwen', 128)
    print(f"alibaba_qwen with 128: valid={is_valid}, adjusted={adjusted}")
    assert not is_valid and adjusted == 10, "Should adjust to 10"
    
    # 测试正常情况
    is_valid, adjusted, warning = validator.validate_batch_size('openai', 128)
    print(f"openai with 128: valid={is_valid}, adjusted={adjusted}")
    assert is_valid and adjusted == 128, "Should keep 128"
    
    print("\n=== Config Adjustment Test ===\n")
    test_config = {
        'EMBEDDING_BATCH_NUM': 128,
        'EMBEDDING_FUNC_MAX_ASYNC': 16
    }
    
    adjusted_config, warnings = validator.validate_and_adjust_config('alibaba_qwen', test_config)
    print(f"Adjusted config: {adjusted_config}")
    print(f"Warnings: {warnings}")
    assert adjusted_config['EMBEDDING_BATCH_NUM'] == 10, "Should adjust to 10"
    
    print("\n✅ All tests passed!")
