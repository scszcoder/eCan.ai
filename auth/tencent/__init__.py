"""
Tencent Cloud Authentication Module
腾讯云认证模块

提供基于腾讯云服务的认证功能：
- CloudBase 认证服务（邮箱/手机号登录）
- 微信登录（规划中）
- 短信验证码
"""

from auth.tencent.cloudbase_config import CloudBaseConfig
from auth.tencent.cloudbase_auth import (
    CloudBaseAuthService,
    CloudBaseUserInfo,
    AuthResult,
    get_cloudbase_service,
)
from auth.tencent.code_store import CodeStore, get_code_store, CooldownError
from auth.tencent.sms_service import TencentSMSService, get_sms_service

__all__ = [
    "CloudBaseConfig",
    "CloudBaseAuthService",
    "CloudBaseUserInfo",
    "AuthResult",
    "get_cloudbase_service",
    "CodeStore",
    "get_code_store",
    "CooldownError",
    "TencentSMSService",
    "get_sms_service",
]
