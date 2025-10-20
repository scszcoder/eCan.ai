"""
Authentication Performance Configuration
Manages performance optimization settings for authentication
"""

import os
from typing import Dict, Any

class AuthPerformanceConfig:
    """Authentication performance configuration class"""

    # Default configuration
    DEFAULT_CONFIG = {
        # Cognito client configuration
        'cognito': {
            'connect_timeout': 15,      # Connection timeout (seconds) - increased for stability
            'read_timeout': 20,        # Read timeout (seconds) - increased for slow responses
            'max_attempts': 3,         # Maximum retry attempts - increased for reliability
            'max_pool_connections': 10, # Connection pool size
        },

        # Authentication flow configuration
        'auth_flow': {
            'total_timeout': 30,       # Total authentication timeout (seconds) - increased for stability
        },

        # Performance monitoring configuration
        'monitoring': {
            'log_timing': True,        # Whether to log timing
            'alert_threshold': 5.0,    # Performance alert threshold (seconds)
        }
    }
    
    @classmethod
    def get_config(cls) -> Dict[str, Any]:
        """Get current configuration"""
        config = cls.DEFAULT_CONFIG.copy()

        # Override from environment variables
        config = cls._override_from_env(config)

        # Auto-adjust based on environment
        config = cls._auto_adjust_for_environment(config)

        return config

    @classmethod
    def _override_from_env(cls, config: Dict[str, Any]) -> Dict[str, Any]:
        """Override configuration from environment variables"""

        # Cognito configuration
        if os.getenv('COGNITO_CONNECT_TIMEOUT'):
            config['cognito']['connect_timeout'] = int(os.getenv('COGNITO_CONNECT_TIMEOUT'))

        if os.getenv('COGNITO_READ_TIMEOUT'):
            config['cognito']['read_timeout'] = int(os.getenv('COGNITO_READ_TIMEOUT'))

        if os.getenv('COGNITO_MAX_ATTEMPTS'):
            config['cognito']['max_attempts'] = int(os.getenv('COGNITO_MAX_ATTEMPTS'))

        # Authentication flow configuration
        if os.getenv('AUTH_TOTAL_TIMEOUT'):
            config['auth_flow']['total_timeout'] = int(os.getenv('AUTH_TOTAL_TIMEOUT'))

        return config
    
    @classmethod
    def _auto_adjust_for_environment(cls, config: Dict[str, Any]) -> Dict[str, Any]:
        """Auto-adjust configuration based on environment"""

        # Detect development environment
        is_dev = (
            os.getenv('ENVIRONMENT', '').lower() in ['dev', 'development'] or
            os.getenv('DEBUG', '').lower() == 'true'
        )

        if is_dev:
            # Development environment - use same stable timeouts as production
            # (Removed shorter timeouts to improve stability)
            pass

        # Detect network environment
        region = os.getenv('AWS_REGION', 'us-east-1')
        if region.startswith('cn-'):
            # China region, increase timeout
            config['cognito']['connect_timeout'] += 2
            config['cognito']['read_timeout'] += 5
            config['auth_flow']['total_timeout'] += 5

        return config
    
    @classmethod
    def get_cognito_config(cls) -> Dict[str, Any]:
        """Get Cognito client configuration"""
        return cls.get_config()['cognito']

    @classmethod
    def get_auth_flow_config(cls) -> Dict[str, Any]:
        """Get authentication flow configuration"""
        return cls.get_config()['auth_flow']

    @classmethod
    def get_monitoring_config(cls) -> Dict[str, Any]:
        """Get monitoring configuration"""
        return cls.get_config()['monitoring']

    @classmethod
    def should_log_timing(cls) -> bool:
        """Check if timing should be logged"""
        return cls.get_monitoring_config()['log_timing']

    @classmethod
    def get_alert_threshold(cls) -> float:
        """Get performance alert threshold"""
        return cls.get_monitoring_config()['alert_threshold']

# Convenient access instance
perf_config = AuthPerformanceConfig()
