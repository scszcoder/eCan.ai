"""
Tencent Cloud Authentication Module
腾讯云认证模块

提供基于腾讯云服务的认证功能，包括：
- CloudBase 认证服务
- 微信登录
- 手机号登录
"""

from auth.tencent.cloudbase_auth import (
    CloudBaseAuthService,
    CloudBaseUserInfo,
    CloudBaseAuthResult
)

__all__ = [
    'CloudBaseAuthService',
    'CloudBaseUserInfo',
    'CloudBaseAuthResult'
]
