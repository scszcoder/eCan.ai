"""
CloudBase Authentication Service
腾讯云云开发认证服务

支持以下登录方式：
1. 邮箱密码登录/注册
2. 手机号 + 验证码登录/注册
3. JWT Token 生成与验证

使用腾讯云 CloudBase Auth REST API。
"""

import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple

import jwt as pyjwt
import requests

from auth.tencent.cloudbase_config import CloudBaseConfig
from utils.logger_helper import logger_helper as logger


# ============================================================
# 数据模型
# ============================================================

@dataclass
class CloudBaseUserInfo:
    """CloudBase 用户信息"""
    uuid: str
    email: Optional[str] = None
    phone_number: Optional[str] = None
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    login_type: str = "email"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AuthResult:
    """认证结果"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_code: Optional[str] = None

    @classmethod
    def ok(cls, data: Dict[str, Any]) -> "AuthResult":
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: str, code: str = None) -> "AuthResult":
        return cls(success=False, error=error, error_code=code)


# ============================================================
# CloudBase Auth Service
# ============================================================

class CloudBaseAuthService:
    """
    腾讯云 CloudBase 认证服务

    使用 CloudBase 提供的 REST API 进行用户认证。
    """

    BASE_URL = "https://tcb-admin.tencentcloudapi.com"

    def __init__(self, config: Optional[CloudBaseConfig] = None):
        self.config = config or CloudBaseConfig.from_env()
        self._access_token: Optional[str] = None
        self._access_token_expires: float = 0

        if not self.config.is_configured():
            logger.warning("[CloudBaseAuth] Not configured - missing credentials")

    # ============================================================
    # 访问令牌管理
    # ============================================================

    def _sign_tc3(self, action: str, payload: Dict[str, Any],
                  service: str = "tcb", version: str = "2018-04-26") -> Tuple[Dict[str, str], str]:
        """
        构造腾讯云 API v3 签名（严格按官方 TC3 规范）

        参考文档：
        https://cloud.tencent.com/document/api/172/1278

        签名流程：
          1. 构造规范请求串 canonical_request
          2. 构造待签名字符串 string_to_sign
          3. 用 secret_key 派生三级密钥 → 计算 Signature
          4. 组装 Authorization 头
        """
        timestamp = int(time.time())
        date = time.strftime("%Y-%m-%d", time.gmtime(timestamp))

        body = json.dumps(payload, separators=(",", ":"))

        # ========== Step 1: CanonicalRequest ==========
        # 格式：HTTPMethod\nCanonicalURI\nCanonicalQueryString\nCanonicalHeaders\nSignedHeaders\nHashedRequestPayload
        canonical_uri = "/"
        canonical_querystring = ""
        content_type = "application/json; charset=utf-8"
        host = "tcb-admin.tencentcloudapi.com"

        canonical_headers = (
            f"content-type:{content_type}\n"
            f"host:{host}\n"
        )
        signed_headers = "content-type;host"
        hashed_request_payload = hashlib.sha256(body.encode("utf-8")).hexdigest()

        canonical_request = (
            f"POST\n"
            f"{canonical_uri}\n"
            f"{canonical_querystring}\n"
            f"{canonical_headers}\n"
            f"{signed_headers}\n"
            f"{hashed_request_payload}"
        )

        # ========== Step 2: StringToSign ==========
        credential_scope = f"{date}/{service}/tc3_request"
        string_to_sign = (
            f"TC3-HMAC-SHA256\n"
            f"{timestamp}\n"
            f"{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )

        # ========== Step 3: 计算 Signature ==========
        secret_date = hmac.new(
            f"TC3{self.config.secret_key}".encode("utf-8"),
            date.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        secret_service = hmac.new(
            secret_date, service.encode("utf-8"), hashlib.sha256
        ).digest()
        signature = hmac.new(
            secret_service,
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        # ========== Step 4: Authorization ==========
        authorization = (
            f"TC3-HMAC-SHA256 "
            f"Credential={self.config.secret_id}/{date}/{service}/tc3_request, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )

        headers = {
            "Authorization": authorization,
            "Content-Type": content_type,
            "Host": host,
            "X-TC-Action": action,
            "X-TC-Version": version,
            "X-TC-Timestamp": str(timestamp),
        }

        return headers, body

    def _call_cloudbase_api(self, action: str, payload: Dict[str, Any],
                            version: str = "2018-04-26") -> Dict[str, Any]:
        """调用 CloudBase Auth API"""
        if not self.config.is_configured():
            return {"error": "CloudBase not configured", "_configured": False}

        # 注入 EnvId
        if "EnvId" not in payload:
            payload["EnvId"] = self.config.env_id

        try:
            headers, body = self._sign_tc3(action, payload, version=version)

            response = requests.post(
                self.BASE_URL,
                headers=headers,
                data=body,
                timeout=30,
            )

            result = response.json()

            if "Response" in result:
                resp = result["Response"]
                if resp.get("Error"):
                    error_msg = resp["Error"].get("Message", "Unknown error")
                    return {
                        "error": error_msg,
                        "error_code": resp["Error"].get("Code", ""),
                    }
                return resp

            return {"error": f"HTTP {response.status_code}: {response.text}"}

        except Exception as e:
            logger.error(f"[CloudBaseAuth] API call error: {e}")
            return {"error": str(e)}

    # ============================================================
    # JWT Token
    # ============================================================

    def _generate_jwt(self, user_info: CloudBaseUserInfo) -> str:
        """生成 JWT Token"""
        now = int(time.time())
        jwt_secret = self.config.get_jwt_secret()

        payload = {
            "iss": "ecan-cn",
            "sub": user_info.uuid,
            "iat": now,
            "exp": now + self.config.jwt_expires_in,
            "user": {
                "uuid": user_info.uuid,
                "email": user_info.email,
                "phone": user_info.phone_number,
                "nickname": user_info.nickname,
                "login_type": user_info.login_type,
            },
        }

        return pyjwt.encode(payload, jwt_secret, algorithm="HS256")

    def verify_token(self, token: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """验证 JWT Token"""
        try:
            jwt_secret = self.config.get_jwt_secret()
            payload = pyjwt.decode(token, jwt_secret, algorithms=["HS256"])
            return True, payload
        except pyjwt.ExpiredSignatureError:
            logger.warning("[CloudBaseAuth] Token expired")
            return False, None
        except pyjwt.InvalidTokenError as e:
            logger.warning(f"[CloudBaseAuth] Invalid token: {e}")
            return False, None

    # ============================================================
    # 用户注册
    # ============================================================

    def sign_up_with_email(self, email: str, password: str) -> AuthResult:
        """邮箱注册"""
        if not self.config.enable_signup:
            return AuthResult.fail("Signup is disabled")

        if not email or not password:
            return AuthResult.fail("Email and password are required")

        if len(password) < 8:
            return AuthResult.fail("Password must be at least 8 characters", "WEAK_PASSWORD")

        result = self._call_cloudbase_api("CreateUser", {
            "EnvId": self.config.env_id,
            "Email": email,
            "Password": password,
        })

        if "error" in result and not result.get("_configured"):
            return AuthResult.fail(result["error"], "NOT_CONFIGURED")

        if "error" in result:
            return AuthResult.fail(result["error"], result.get("error_code", "SIGNUP_FAILED"))

        user_uuid = result.get("UserId") or result.get("Uuid") or str(uuid.uuid4())

        return AuthResult.ok({
            "message": "Registration successful. Please verify your email.",
            "user_id": user_uuid,
        })

    # ============================================================
    # 邮箱登录
    # ============================================================

    def sign_in_with_email(self, email: str, password: str) -> AuthResult:
        """邮箱登录"""
        if not self.config.enable_email_login:
            return AuthResult.fail("Email login is disabled")

        if not email or not password:
            return AuthResult.fail("Email and password are required")

        result = self._call_cloudbase_api("LoginUser", {
            "EnvId": self.config.env_id,
            "Email": email,
            "Password": password,
        })

        if "error" in result:
            err_code = result.get("error_code", "LOGIN_FAILED")
            if "UserNotFound" in err_code or "AuthFailure" in err_code:
                return AuthResult.fail("Invalid email or password", "INVALID_CREDENTIALS")
            return AuthResult.fail(result["error"], err_code)

        user_uuid = result.get("UserId") or result.get("Uuid") or str(uuid.uuid4())

        user_info = CloudBaseUserInfo(
            uuid=user_uuid,
            email=email,
            login_type="email",
        )

        token = self._generate_jwt(user_info)
        refresh_token = self._generate_jwt(user_info)

        return AuthResult.ok({
            "token": token,
            "refresh_token": refresh_token,
            "user_info": user_info.to_dict(),
        })

    # ============================================================
    # 手机号登录（验证码由本地发送，本地校验）
    # ============================================================

    def sign_in_with_phone(self, phone: str, code: str) -> AuthResult:
        """
        手机号验证码登录

        流程：
        1. 验证本地存储的验证码
        2. 调用 CloudBase API 检查/创建用户
        3. 生成 JWT Token
        """
        if not self.config.enable_phone_login:
            return AuthResult.fail("Phone login is disabled")

        from auth.tencent.code_store import get_code_store
        code_store = get_code_store()

        # 验证验证码
        if not code_store.verify_code(phone, code, purpose="login"):
            return AuthResult.fail("Invalid or expired verification code", "INVALID_CODE")

        # 查询/创建用户
        result = self._call_cloudbase_api("GetUserByPhone", {
            "EnvId": self.config.env_id,
            "PhoneNumber": phone,
        })

        user_uuid = None
        if "error" not in result:
            user_uuid = result.get("UserId") or result.get("Uuid")

        if not user_uuid:
            # 自动创建用户
            create_result = self._call_cloudbase_api("CreateUser", {
                "EnvId": self.config.env_id,
                "PhoneNumber": phone,
            })

            if "error" in create_result:
                # 用户可能已存在，继续登录
                logger.warning(f"[CloudBaseAuth] User may already exist: {create_result.get('error')}")

            user_uuid = str(uuid.uuid4())

        user_info = CloudBaseUserInfo(
            uuid=user_uuid,
            phone_number=phone,
            login_type="phone",
        )

        token = self._generate_jwt(user_info)
        refresh_token = self._generate_jwt(user_info)

        return AuthResult.ok({
            "token": token,
            "refresh_token": refresh_token,
            "user_info": user_info.to_dict(),
        })

    def send_phone_verification_code(self, phone: str,
                                     purpose: str = "login") -> AuthResult:
        """
        发送手机验证码

        流程：
        1. 检查发送冷却
        2. 生成 6 位验证码
        3. 通过腾讯云短信发送
        """
        from auth.tencent.code_store import get_code_store, CooldownError
        from auth.tencent.sms_service import get_sms_service

        code_store = get_code_store()

        # 生成验证码
        try:
            code = code_store.generate_code(phone, purpose=purpose)
        except CooldownError as e:
            return AuthResult.fail(str(e), "COOLDOWN")

        if not code:
            return AuthResult.fail("Failed to generate code", "GENERATE_FAILED")

        # 发送短信
        sms_service = get_sms_service()
        sms_result = sms_service.send_verification_code(phone, code)

        if not sms_result.success:
            return AuthResult.fail(
                sms_result.error or "Failed to send SMS",
                "SMS_SEND_FAILED"
            )

        return AuthResult.ok({
            "message": "Verification code sent",
            # 开发环境返回验证码（生产环境应删除）
            "dev_code": code if self._is_dev_mode() else None,
        })

    def _is_dev_mode(self) -> bool:
        """是否为开发模式（用于在响应中返回验证码方便测试）"""
        import os
        debug = os.getenv("DEBUG_MODE", "false").lower() == "true"
        return debug

    # ============================================================
    # Token 操作
    # ============================================================

    def sign_out(self, token: str) -> AuthResult:
        """登出"""
        # 验证 token 以确认有效性
        valid, _ = self.verify_token(token)
        if not valid:
            return AuthResult.fail("Invalid token", "INVALID_TOKEN")
        return AuthResult.ok({"message": "Logout successful"})

    def refresh_token(self, refresh_token: str) -> AuthResult:
        """刷新 Token"""
        valid, payload = self.verify_token(refresh_token)
        if not valid:
            return AuthResult.fail("Invalid refresh token", "INVALID_TOKEN")

        user_data = payload.get("user", {})
        user_info = CloudBaseUserInfo(
            uuid=user_data.get("uuid", ""),
            email=user_data.get("email"),
            phone_number=user_data.get("phone"),
            nickname=user_data.get("nickname"),
            login_type=user_data.get("login_type", "email"),
        )

        new_token = self._generate_jwt(user_info)
        new_refresh = self._generate_jwt(user_info)

        return AuthResult.ok({
            "token": new_token,
            "refresh_token": new_refresh,
            "user_info": user_info.to_dict(),
        })

    # ============================================================
    # 密码重置（使用手机验证码）
    # ============================================================

    def forgot_password_with_phone(self, phone: str) -> AuthResult:
        """
        发起密码重置（发送验证码到手机）

        流程：
        1. 生成 6 位验证码
        2. 发送短信
        3. 存储验证码（purpose=reset_password）
        """
        if not self.config.enable_phone_login:
            return AuthResult.fail("Phone login is disabled")

        from auth.tencent.code_store import get_code_store, CooldownError
        from auth.tencent.sms_service import get_sms_service

        code_store = get_code_store()

        try:
            code = code_store.generate_code(phone, purpose="reset_password")
        except CooldownError as e:
            return AuthResult.fail(str(e), "COOLDOWN")

        if not code:
            return AuthResult.fail("Failed to generate code", "GENERATE_FAILED")

        sms_service = get_sms_service()
        sms_result = sms_service.send_verification_code(phone, code)

        if not sms_result.success:
            return AuthResult.fail(
                sms_result.error or "Failed to send SMS",
                "SMS_SEND_FAILED",
            )

        return AuthResult.ok({
            "message": "Verification code sent",
            "dev_code": code if self._is_dev_mode() else None,
        })

    def reset_password_with_phone(self, phone: str, code: str,
                                  new_password: str) -> AuthResult:
        """
        重置密码（通过手机验证码）

        流程：
        1. 验证验证码
        2. 调用 CloudBase API 重置密码
        3. 返回结果
        """
        if not new_password or len(new_password) < 8:
            return AuthResult.fail("Password must be at least 8 characters", "WEAK_PASSWORD")

        from auth.tencent.code_store import get_code_store

        code_store = get_code_store()
        if not code_store.verify_code(phone, code, purpose="reset_password"):
            return AuthResult.fail("Invalid or expired verification code", "INVALID_CODE")

        # 调用 CloudBase API 重置密码
        result = self._call_cloudbase_api("ResetPasswordByPhone", {
            "EnvId": self.config.env_id,
            "PhoneNumber": phone,
            "NewPassword": new_password,
        })

        if "error" in result:
            err_code = result.get("error_code", "RESET_FAILED")
            return AuthResult.fail(result["error"], err_code)

        return AuthResult.ok({
            "message": "Password reset successful. Please login with your new password.",
        })

    def sign_up_with_phone(self, phone: str, code: str,
                           password: str = None) -> AuthResult:
        """
        手机号注册

        流程：
        1. 验证验证码
        2. 调用 CloudBase API 创建用户
        3. 返回 JWT Token
        """
        if not self.config.enable_signup:
            return AuthResult.fail("Signup is disabled")

        from auth.tencent.code_store import get_code_store

        code_store = get_code_store()
        if not code_store.verify_code(phone, code, purpose="register"):
            return AuthResult.fail("Invalid or expired verification code", "INVALID_CODE")

        import uuid as uuidlib

        # 创建用户
        payload = {
            "EnvId": self.config.env_id,
            "PhoneNumber": phone,
        }
        if password:
            payload["Password"] = password

        result = self._call_cloudbase_api("CreateUser", payload)

        if "error" in result:
            err_code = result.get("error_code", "SIGNUP_FAILED")
            if "AlreadyExists" in err_code or "UserExists" in err_code:
                return AuthResult.fail("Phone number already registered", "USER_EXISTS")
            return AuthResult.fail(result["error"], err_code)

        user_uuid = result.get("UserId") or result.get("Uuid") or str(uuidlib.uuid4())

        user_info = CloudBaseUserInfo(
            uuid=user_uuid,
            phone_number=phone,
            login_type="phone",
        )

        token = self._generate_jwt(user_info)
        refresh_token = self._generate_jwt(user_info)

        return AuthResult.ok({
            "token": token,
            "refresh_token": refresh_token,
            "user_info": user_info.to_dict(),
        })

    # ============================================================
    # 微信登录（OAuth 2.0 code 换用户信息）
    # ============================================================

    def login_with_wechat(self, code: str) -> AuthResult:
        """
        微信 OAuth 登录

        流程：
        1. 使用 code 换取 access_token 和 openid
        2. 使用 access_token + openid 获取用户信息
        3. 在 CloudBase 中查找/创建用户
        4. 返回 JWT Token
        """
        if not code:
            return AuthResult.fail("WeChat code is required", "INVALID_CODE")

        # 从配置读取微信 AppID/AppSecret（公开字段来自 yml，私密字段来自环境变量）
        wechat_app_id = self.config.wechat_app_id
        wechat_app_secret = self.config.wechat_app_secret

        if not wechat_app_id or not wechat_app_secret:
            return AuthResult.fail(
                "WeChat is not configured. Set WECHAT.APP_ID in auth_config.yml and "
                "ECAN_WECHAT_APP_SECRET in environment.",
                "WECHAT_NOT_CONFIGURED",
            )

        try:
            # Step 1: code 换 access_token
            token_url = "https://api.weixin.qq.com/sns/oauth2/access_token"
            token_params = {
                "appid": wechat_app_id,
                "secret": wechat_app_secret,
                "code": code,
                "grant_type": "authorization_code",
            }
            token_resp = requests.get(token_url, params=token_params, timeout=15)
            token_data = token_resp.json()

            if "errcode" in token_data and token_data["errcode"] != 0:
                return AuthResult.fail(
                    f"WeChat token error: {token_data.get('errmsg', 'unknown')}",
                    "WECHAT_TOKEN_FAILED",
                )

            access_token = token_data.get("access_token")
            openid = token_data.get("openid")
            unionid = token_data.get("unionid")

            if not access_token or not openid:
                return AuthResult.fail(
                    "Invalid WeChat token response",
                    "WECHAT_INVALID_RESPONSE",
                )

            # Step 2: 获取用户信息（scope=snsapi_userinfo 时才有）
            user_info_data = {}
            try:
                user_url = "https://api.weixin.qq.com/sns/userinfo"
                user_params = {
                    "access_token": access_token,
                    "openid": openid,
                }
                user_resp = requests.get(user_url, params=user_params, timeout=15)
                user_info_data = user_resp.json()
            except Exception as e:
                logger.warning(f"[CloudBaseAuth] Failed to fetch WeChat user info: {e}")

            nickname = user_info_data.get("nickname", "")
            avatar_url = user_info_data.get("headimgurl", "")

            # Step 3: 在 CloudBase 中查找/创建用户
            user_uuid = self._find_or_create_wechat_user(openid, unionid, nickname, avatar_url)

            user_info = CloudBaseUserInfo(
                uuid=user_uuid,
                nickname=nickname,
                avatar_url=avatar_url,
                login_type="wechat",
            )

            token = self._generate_jwt(user_info)
            refresh_token = self._generate_jwt(user_info)

            return AuthResult.ok({
                "token": token,
                "refresh_token": refresh_token,
                "user_info": {
                    **user_info.to_dict(),
                    "openid": openid,
                    "unionid": unionid,
                },
            })

        except Exception as e:
            logger.error(f"[CloudBaseAuth] WeChat login error: {e}")
            return AuthResult.fail(str(e), "WECHAT_LOGIN_FAILED")

    def _find_or_create_wechat_user(self, openid: str, unionid: Optional[str],
                                    nickname: str, avatar_url: str) -> str:
        """查找或创建微信用户"""
        import uuid as uuidlib

        # 查询用户
        payload = {
            "EnvId": self.config.env_id,
            "OpenId": openid,
        }
        if unionid:
            payload["UnionId"] = unionid

        result = self._call_cloudbase_api("GetUserByOpenId", payload)

        if "error" not in result:
            user_uuid = result.get("UserId") or result.get("Uuid")
            if user_uuid:
                return user_uuid

        # 创建用户
        create_payload = {
            "EnvId": self.config.env_id,
            "OpenId": openid,
            "Nickname": nickname,
            "AvatarUrl": avatar_url,
        }
        if unionid:
            create_payload["UnionId"] = unionid

        create_result = self._call_cloudbase_api("CreateUser", create_payload)

        if "error" not in create_result:
            return create_result.get("UserId") or create_result.get("Uuid") or str(uuidlib.uuid4())

        # 创建失败时（用户可能已存在）使用 fallback UUID
        logger.warning(f"[CloudBaseAuth] WeChat user create fallback: {create_result.get('error')}")
        return str(uuidlib.uuid4())

    # ============================================================
    # 配置检查
    # ============================================================

    def get_config_status(self) -> Dict[str, Any]:
        """获取配置状态"""
        return {
            "configured": self.config.is_configured(),
            "email_login_enabled": self.config.enable_email_login,
            "phone_login_enabled": self.config.enable_phone_login,
            "signup_enabled": self.config.enable_signup,
            "sms_configured": self.config.is_sms_configured(),
            "region": self.config.region,
        }


@lru_cache(maxsize=1)
def get_cloudbase_service() -> CloudBaseAuthService:
    """获取 CloudBase 认证服务单例"""
    return CloudBaseAuthService()
