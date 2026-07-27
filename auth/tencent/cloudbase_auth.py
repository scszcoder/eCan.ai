"""
CloudBase Authentication Service (Web v3 REST API)
腾讯云云开发 v3 认证服务 — 客户端 REST 接入

[2026-07 重写] 使用 CloudBase web v3 Auth HTTP API:
  https://{env_id}.api.tcloudbasegateway.com/auth/v1/...

之前的实现错误地使用 TC3 签名调 tcb-admin.tencentcloudapi.com
(Web v3 的 Auth API 不需要 SK 签名,直接用 Bearer token 鉴权)

支持：
1. 用户名+密码登录（POST /auth/v1/signin）
2. 手机号 / 邮箱 验证码登录（POST /auth/v1/signin + verification_token）
3. 第三方 OAuth 登录（微信、GitHub 等）
4. Token 刷新（POST /auth/v1/token grant_type=refresh_token）
5. 匿名登录（POST /auth/v1/signin/anonymously）
6. 登出（POST /auth/v1/logout）

注意：
- 客户端不允许纯 username+password 注册（腾讯云策略：注册必须有验证码或第三方授权）
- 用户必须从 CloudBase 控制台或服务端 SDK 创建
- 客户端只负责登录 / 用 access_token 调其他 API
"""

import os
import time
import json
import uuid
from dataclasses import dataclass, asdict
from functools import lru_cache
from typing import Any, Dict, Optional

import requests

from auth.tencent.cloudbase_config import CloudBaseConfig
from utils.logger_helper import logger_helper as logger


# ============================================================
# Data Models
# ============================================================

@dataclass
class CloudBaseUserInfo:
    """CloudBase 用户信息（标准 OAuth 2.0 sub 字段）"""
    sub: str  # 用户唯一标识 (CloudBase 标准)
    email: Optional[str] = None
    phone_number: Optional[str] = None
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    username: Optional[str] = None
    login_type: str = "password"

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
# CloudBase Web v3 Auth Service
# ============================================================

class CloudBaseAuthService:
    """
    腾讯云 CloudBase Web v3 认证服务

    Auth REST API 文档:
      https://docs.cloudbase.net/http-api/auth
    端点格式:
      https://{env_id}.api.tcloudbasegateway.com/auth/v1/{endpoint}
    """

    def __init__(self, config: Optional[CloudBaseConfig] = None, *,
                 device_id: Optional[str] = None):
        self.config = config or CloudBaseConfig.from_env()
        # device_id 单例兜底值（向后兼容旧 IPC handler）
        # 新 REST 路径通过 per-request device_id 参数透传,优先于单例值
        self._device_id: str = device_id or _load_or_create_device_id()

        if not self.config.is_configured():
            logger.warning("[CloudBaseAuth] Not configured - env_id is empty")

    @property
    def base_url(self) -> str:
        if not self.config.env_id:
            return ""
        return f"https://{self.config.env_id}.api.tcloudbasegateway.com"

    def _headers(self, with_auth: bool = False, access_token: Optional[str] = None,
                 device_id: Optional[str] = None) -> Dict[str, str]:
        # 优先顺序: 参数 > 实例属性
        h = {
            "Content-Type": "application/json",
            "x-device-id": device_id or self._device_id,
        }
        if with_auth and access_token:
            h["Authorization"] = f"Bearer {access_token}"
        return h

    def _post(self, endpoint: str, payload: Dict[str, Any],
              timeout: int = 30,
              device_id: Optional[str] = None) -> Dict[str, Any]:
        """POST 到 CloudBase Auth API

        Args:
            device_id: per-request device_id,优先于实例单例值
        """
        if not self.config.env_id:
            return {"_configured": False, "error": "CloudBase env_id not configured"}

        url = f"{self.base_url}{endpoint}"
        try:
            r = requests.post(url, json=payload,
                              headers=self._headers(device_id=device_id),
                              timeout=timeout)
            body = r.json() if r.text else {}

            if r.status_code >= 400:
                err_code = body.get("code", f"HTTP_{r.status_code}")
                err_msg = body.get("error_description") or body.get("error") or body.get("message") or r.text
                return {"_http_status": r.status_code, "error": err_msg, "error_code": err_code, "_raw": body}

            return {"_http_status": r.status_code, **body}
        except requests.RequestException as e:
            logger.error(f"[CloudBaseAuth] Request error: {e}")
            return {"_http_status": 0, "error": str(e), "error_code": "NETWORK_ERROR"}

    def _is_dev_mode(self) -> bool:
        return os.getenv("DEBUG_MODE", "false").lower() == "true"

    # ============================================================
    # Public: 登录
    # ============================================================

    def sign_in_with_password(self, username: str, password: str, *,
                                device_id: Optional[str] = None) -> AuthResult:
        """
        用户名+密码登录

        POST /auth/v1/signin
        文档: https://docs.cloudbase.net/http-api/auth/auth-sign-in

        Required:
          - 用户已通过 CloudBase 控制台或服务端 SDK 创建
          - env 中"用户名密码登录"已开启

        Returns:
          AuthResult with access_token / refresh_token
        """
        if not self.config.enable_email_login:
            return AuthResult.fail("Username/password login is disabled", "DISABLED")

        if not username or not password:
            return AuthResult.fail("Username and password are required", "INVALID_INPUT")

        result = self._post("/auth/v1/signin", {
            "username": username,
            "password": password,
        }, device_id=device_id)

        if "error" in result:
            code = result.get("error_code", "LOGIN_FAILED")
            if code in ("INVALID_USERNAME_OR_PASSWORD", "UserNotFound", "AuthFailure"):
                return AuthResult.fail("Invalid username or password", "INVALID_CREDENTIALS")
            return AuthResult.fail(result["error"], code)

        return _wrap_token_response(
            result, username=username,
            login_type="password",
        )

    def sign_in_anonymously(self, *, device_id: Optional[str] = None) -> AuthResult:
        """匿名登录（需先在控制台开启“允许匿名登录”）"""
        result = self._post("/auth/v1/signin/anonymously", {}, device_id=device_id)
        if "error" in result:
            return AuthResult.fail(result["error"], result.get("error_code"))
        return _wrap_token_response(result, login_type="anonymous")

    @staticmethod
    def _format_phone_e164_with_space(phone_number: str) -> str:
        """规范化手机号到 CloudBase 要求格式: "+86 13880917374"

        支持输入:
          "13880917374"        → "+86 13880917374"
          "+8613880917374"     → "+86 13880917374"
          "+86 13880917374"    → "+86 13880917374"
          " 13880917374 "      → "+86 13880917374"
        """
        digits = phone_number.strip().replace(" ", "").lstrip("+")
        return f"+86 {digits}"

    def sign_in_with_otp(self, *, phone_number: Optional[str] = None,
                         email: Optional[str] = None,
                         verification_token: str,
                         device_id: Optional[str] = None) -> AuthResult:
        """
        验证码登录（手机/邮箱，需要先调 /auth/v1/verification/{phone,email} 获取 verification_token）

        POST /auth/v1/signin
        Body: {phone_number|email, verification_token}
        """
        if not self.config.enable_phone_login and phone_number:
            return AuthResult.fail("Phone login is disabled", "DISABLED")

        if not verification_token:
            return AuthResult.fail("verification_token is required", "INVALID_INPUT")

        payload: Dict[str, Any] = {"verification_token": verification_token}
        if phone_number:
            payload["phone_number"] = self._format_phone_e164_with_space(phone_number)
        elif email:
            payload["email"] = email
        else:
            return AuthResult.fail("Either phone_number or email required", "INVALID_INPUT")

        result = self._post("/auth/v1/signin", payload, device_id=device_id)
        if "error" in result:
            return AuthResult.fail(result["error"], result.get("error_code"))

        return _wrap_token_response(
            result, phone=phone_number, email=email, login_type="otp",
        )

    # ============================================================
    # Public: 注册
    # ============================================================

    def sign_up_with_otp(self, *, phone_number: Optional[str] = None,
                         email: Optional[str] = None,
                         verification_token: str,
                         username: Optional[str] = None,
                         password: Optional[str] = None,
                         device_id: Optional[str] = None) -> AuthResult:
        """
        验证码注册（手机/邮箱）

        文档: https://docs.cloudbase.net/http-api/auth/auth-sign-up
        说明：客户端不能纯 username+password 注册（CloudBase 策略：必须验证码或第三方授权）
        """
        if not self.config.enable_signup:
            return AuthResult.fail("Signup is disabled", "DISABLED")

        if not verification_token:
            return AuthResult.fail("verification_token is required", "INVALID_INPUT")

        payload: Dict[str, Any] = {"verification_token": verification_token}
        if phone_number:
            payload["phone_number"] = self._format_phone_e164_with_space(phone_number)
            if not self.config.enable_phone_login:
                return AuthResult.fail("Phone login is disabled", "DISABLED")
        elif email:
            payload["email"] = email
        else:
            return AuthResult.fail("Either phone_number or email required", "INVALID_INPUT")

        if username:
            payload["username"] = username
        if password:
            payload["password"] = password

        result = self._post("/auth/v1/signup", payload, device_id=device_id)
        if "error" in result:
            return AuthResult.fail(result["error"], result.get("error_code"))

        return _wrap_token_response(
            result, phone=phone_number, email=email,
            username=username, login_type="signup",
        )

    def send_verification_code(self, *, phone_number: Optional[str] = None,
                               email: Optional[str] = None,
                               device_id: Optional[str] = None) -> AuthResult:
        """
        触发验证码发送

        POST /auth/v1/verification/{phone|email}
        Body: {phone_number | email}

        对邮箱: target=ANY,返回 is_user 字段指示用户是否已注册。
        """
        if phone_number:
            return self._send_phone_code(phone_number)
        if email:
            return self._send_email_code(email, device_id=device_id)
        return AuthResult.fail("Either phone_number or email required", "INVALID_INPUT")

    def _send_phone_code(self, phone_number: str) -> AuthResult:
        """触发 CloudBase 内置手机验证码。

        CloudBase 平台内置 SMS 发送能力，不需要自己配置腾讯云短信服务。
        端点: POST /auth/v1/verification
        Body: {target: "ANY|USER", phone_number: "+86 xxxxxxxxxxx"}
        返回: {verification_id, expires_in, is_user}
        """
        # 确保手机号格式正确: CloudBase 要求 "+86 13880917374" (加号、国家码、空格、号码)
        phone = phone_number.strip().replace(" ", "")
        if phone.startswith("+"):
            phone = phone[1:]  # 去掉现有 + 号
        phone = f"+86 {phone}"  # 重新格式化为 "+86 13880917374"

        result = self._post("/auth/v1/verification", {
            "target": "ANY",
            "phone_number": phone,
        })
        if "error" in result:
            return AuthResult.fail(result["error"], result.get("error_code"))
        return AuthResult.ok({
            "message": "Verification code sent",
            "verification_id": result.get("verification_id"),
            "expires_in": result.get("expires_in", 600),
            "is_user": result.get("is_user"),
        })

    def _send_email_code(self, email: str, *, device_id: Optional[str] = None) -> AuthResult:
        """触发 CloudBase 邮箱验证码。

        正确端点: POST /auth/v1/verification
        Body: {target: "ANY", email: "..."}
        返回: {verification_id, expires_in, is_user}
        - is_user=true:  邮箱已注册
        - is_user=false: 邮箱未注册（可用于注册）
        """
        result = self._post("/auth/v1/verification", {
            "target": "ANY",
            "email": email,
        }, device_id=device_id)
        if "error" in result:
            return AuthResult.fail(result["error"], result.get("error_code"))
        return AuthResult.ok({
            "message": "Verification code sent",
            "verification_id": result.get("verification_id"),
            "expires_in": result.get("expires_in", 600),
            "is_user": result.get("is_user"),
        })

    # ============================================================
    # Public: Token 操作
    # ============================================================

    def verify_verification_code(self, verification_id: str,
                                 verification_code: str, *,
                                 device_id: Optional[str] = None) -> AuthResult:
        """
        校验验证码，获取 verification_token（用于后续登录/注册）

        POST /auth/v1/verification/verify
        Body: {verification_id, verification_code}

        文档: https://docs.cloudbase.net/http-api/auth/auth-verify-verification
        """
        if not verification_id:
            return AuthResult.fail("verification_id is required", "INVALID_INPUT")
        if not verification_code:
            return AuthResult.fail("verification_code is required", "INVALID_INPUT")

        result = self._post("/auth/v1/verification/verify", {
            "verification_id": verification_id,
            "verification_code": verification_code,
        }, device_id=device_id)
        if "error" in result:
            return AuthResult.fail(result["error"], result.get("error_code"))

        token = result.get("verification_token")
        if not token:
            return AuthResult.fail("No verification_token in response", "NO_TOKEN")

        return AuthResult.ok({
            "verification_token": token,
            "expires_in": result.get("expires_in", 600),
        })

    def refresh_token(self, refresh_token: str, *,
                      device_id: Optional[str] = None) -> AuthResult:
        """
        刷新 access_token

        POST /auth/v1/token
        Body: {grant_type: "refresh_token", refresh_token: "..."}
        """
        if not refresh_token:
            return AuthResult.fail("refresh_token is required", "INVALID_INPUT")

        result = self._post("/auth/v1/token", {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }, device_id=device_id)
        if "error" in result:
            return AuthResult.fail(result["error"], result.get("error_code"))

        return _wrap_token_response(result, login_type="refresh")

    def sign_out(self, access_token: str) -> AuthResult:
        """
        登出（清除服务端 session）

        POST /auth/v1/user/signout
        Headers: Authorization: Bearer <access_token>
        """
        if not access_token:
            return AuthResult.fail("access_token is required", "INVALID_INPUT")

        url = f"{self.base_url}/auth/v1/user/signout"
        try:
            r = requests.post(url, headers=self._headers(with_auth=True, access_token=access_token),
                              timeout=15)
            if r.status_code >= 400:
                body = r.json() if r.text else {}
                return AuthResult.fail(
                    body.get("error_description") or body.get("message") or "Logout failed",
                    body.get("code", "LOGOUT_FAILED"),
                )
            return AuthResult.ok({"message": "Logout successful"})
        except requests.RequestException as e:
            logger.error(f"[CloudBaseAuth] Logout error: {e}")
            return AuthResult.fail(str(e), "NETWORK_ERROR")

    # ============================================================
    # Public: 当前用户
    # ============================================================

    def get_current_user(self, access_token: str) -> AuthResult:
        """获取当前登录用户信息（用 access_token）"""
        if not access_token:
            return AuthResult.fail("access_token is required", "INVALID_INPUT")

        url = f"{self.base_url}/auth/v1/user/me"
        try:
            r = requests.get(url, headers=self._headers(with_auth=True, access_token=access_token),
                             timeout=15)
            if r.status_code == 401:
                return AuthResult.fail("Invalid or expired access_token", "UNAUTHORIZED")
            if r.status_code >= 400:
                body = r.json() if r.text else {}
                return AuthResult.fail(
                    body.get("error_description") or body.get("message") or "Request failed",
                    body.get("code", "REQUEST_FAILED"),
                )
            return AuthResult.ok(r.json())
        except requests.RequestException as e:
            logger.error(f"[CloudBaseAuth] get_current_user error: {e}")
            return AuthResult.fail(str(e), "NETWORK_ERROR")

    def reset_password(self, *, phone_number: Optional[str] = None,
                       email: Optional[str] = None,
                       new_password: str, verification_id: str,
                       verification_code: str,
                       device_id: Optional[str] = None) -> AuthResult:
        """通过手机/邮箱验证码重置密码（三步流程）。

        流程：
        1. send_verification_code → 获取 verification_id
        2. verify_verification_code(verification_id, code) → 获取 verification_token
        3. 本方法用 verification_token 调用 /auth/v1/recover

        POST /auth/v1/recover
        Body: { phone_number, verification_token, new_password, email? }
        """
        if not verification_code:
            return AuthResult.fail("verification_code is required", "INVALID_INPUT")
        if not verification_id:
            return AuthResult.fail("verification_id is required", "INVALID_INPUT")
        if not phone_number and not email:
            return AuthResult.fail("Either phone_number or email required", "INVALID_INPUT")
        if not new_password or len(new_password) < 8:
            return AuthResult.fail("Password must be at least 8 characters", "WEAK_PASSWORD")

        # Step 1: 验证验证码获取 verification_token
        verify_result = self.verify_verification_code(verification_id, verification_code, device_id=device_id)
        if not verify_result.success:
            return AuthResult.fail(verify_result.error, verify_result.error_code)

        verification_token = verify_result.data.get("verification_token", "")

        # Step 2: 用 verification_token 重置密码
        payload: Dict[str, Any] = {
            "verification_token": verification_token,
            "new_password": new_password,
        }
        if phone_number:
            payload["phone_number"] = self._format_phone_e164_with_space(phone_number)
        if email:
            payload["email"] = email

        result = self._post("/auth/v1/recover", payload, device_id=device_id)
        if "error" in result:
            return AuthResult.fail(result["error"], result.get("error_code", "RESET_FAILED"))
        return AuthResult.ok({"message": "Password reset successful"})

    # ============================================================
    # Public: 微信扫码登录（QR Code）
    # ============================================================

    def get_wechat_qrcode_link(self, *, device_id: Optional[str] = None, state: Optional[str] = None,
                           redirect_uri: Optional[str] = None) -> AuthResult:
        """
        获取微信扫码 / 网页授权登录链接

        根据 cloudbase_config.wechat_login_type 切换两种模式：

          - open_platform: 开放平台网站应用 → CloudBase provider_id=wx_open
            URL: https://open.weixin.qq.com/connect/qrconnect?scope=snsapi_login
                 适用：PC 浏览器，弹出二维码让用户用手机微信扫

          - mp_official:   公众号 H5 网页授权 → CloudBase provider_id=wx_mp
            URL: https://open.weixin.qq.com/connect/oauth2/authorize?scope=snsapi_userinfo
                 适用：用户已在微信内打开 H5 页面（公众号菜单/客服消息等），点确认

        GET /auth/v1/provider/uri?provider_id=...&redirect_uri=...&scope=...
        返回: uri（可直接跳转或生成二维码）

        Args:
            state:        防 CSRF 的状态标识，会传给 CloudBase
            redirect_uri: 微信回调地址（必须与微信后台配置的回调域一致），
                          一般传前端登录页 URL。
        """
        if not self.config.enable_wechat_login:
            return AuthResult.fail("WeChat login is disabled", "DISABLED")

        if not self.config.is_wechat_configured():
            return AuthResult.fail("WeChat not configured (APP_ID missing)", "NOT_CONFIGURED")

        if not self.config.env_id:
            return AuthResult.fail("CloudBase env_id not configured", "NOT_CONFIGURED")

        # 根据 LOGIN_TYPE 选择 CloudBase provider_id 和默认 scope
        login_type = (self.config.wechat_login_type or "open_platform").lower()
        if login_type == "mp_official":
            provider_id = "wx_mp"
            default_scope = "snsapi_userinfo"
        else:  # 默认 / open_platform
            provider_id = "wx_open"
            default_scope = "snsapi_login"

        try:
            # 使用 GET 请求获取授权 URI
            url = f"{self.base_url}/auth/v1/provider/uri"
            params = {
                "provider_id": provider_id,
                "state": state or f"wechat_qr_{uuid.uuid4().hex[:16]}",
            }
            # redirect_uri 必须传给 CloudBase（微信会回调到这个地址）
            if redirect_uri:
                params["redirect_uri"] = redirect_uri
            # 把配置里的 scope 透传给 CloudBase；未填则用本模式默认值
            scope_to_send = self.config.wechat_scope or default_scope
            params["scope"] = scope_to_send

            headers = self._headers(device_id=device_id)

            r = requests.get(url, params=params, headers=headers, timeout=30)
            body = r.json() if r.text else {}

            if r.status_code >= 400:
                err_code = body.get("code", f"HTTP_{r.status_code}")
                err_msg = body.get("error_description") or body.get("error") or r.text
                return AuthResult.fail(err_msg, err_code)

            uri = body.get("uri")
            if not uri:
                return AuthResult.fail("No uri in response", "NO_DATA")

            # 生成唯一 ID 用于追踪本次登录会话
            session_id = uuid.uuid4().hex

            logger.info(
                f"[get_wechat_qrcode_link] mode={login_type} provider_id={provider_id} "
                f"scope={scope_to_send} session_id={session_id}"
            )
            return AuthResult.ok({
                "uri": uri,
                "session_id": session_id,
                "expires_in": 300,
                "login_type": login_type,
                "provider_id": provider_id,
            })
        except requests.RequestException as e:
            logger.error(f"[get_wechat_qrcode_link] Error: {e}")
            return AuthResult.fail(str(e), "NETWORK_ERROR")
        except Exception as e:
            logger.error(f"[get_wechat_qrcode_link] Error: {e}")
            return AuthResult.fail(str(e), "UNKNOWN_ERROR")

    # ============================================================
    # Public: 配置状态
    # ============================================================

    def get_config_status(self) -> Dict[str, Any]:
        return {
            "configured": self.config.is_configured(),
            "env_id": self.config.env_id,
            "region": self.config.region,
            "device_id": self._device_id,
            "email_login_enabled": self.config.enable_email_login,
            "phone_login_enabled": self.config.enable_phone_login,
            "wechat_login_enabled": self.config.enable_wechat_login,
            "wechat_configured": self.config.is_wechat_configured(),
            "signup_enabled": self.config.enable_signup,
            "base_url": self.base_url,
        }


@lru_cache(maxsize=1)
def get_cloudbase_service() -> CloudBaseAuthService:
    """获取 CloudBase 认证服务单例"""
    return CloudBaseAuthService()


# ============================================================
# Module-level helpers(提取出来避免 CloudBaseAuthService 超过 300 行)
# ============================================================

def _load_or_create_device_id(device_file: str = "~/.eCan.cn/device_id") -> str:
    """读取持久化 device_id,缺失则生成新 UUID。"""
    path = os.path.expanduser(device_file)
    try:
        if os.path.exists(path):
            with open(path, "r") as f:
                did = f.read().strip()
                if did:
                    return did
    except OSError:
        pass
    did = str(uuid.uuid4())
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(did)
    except OSError:
        pass
    return did


def _build_user_info(body: Dict[str, Any], *,
                     email: Optional[str] = None,
                     phone: Optional[str] = None,
                     username: Optional[str] = None,
                     nickname: Optional[str] = None,
                     avatar_url: Optional[str] = None,
                     login_type: str = "password") -> CloudBaseUserInfo:
    """从 API 响应构造 UserInfo。sub 是 CloudBase 标准 OAuth 2.0 用户字段。"""
    return CloudBaseUserInfo(
        sub=str(body.get("sub") or body.get("user_id") or uuid.uuid4()),
        email=email or body.get("email"),
        phone_number=phone or body.get("phone_number"),
        username=username or body.get("username"),
        nickname=nickname or body.get("name") or body.get("nickname"),
        avatar_url=avatar_url or body.get("picture"),
        login_type=login_type,
    )


def _wrap_token_response(body: Dict[str, Any], *,
                         email: Optional[str] = None,
                         phone: Optional[str] = None,
                         username: Optional[str] = None,
                         login_type: str = "password") -> AuthResult:
    """包装 token 响应成标准 AuthResult。"""
    access_token = body.get("access_token")
    if not access_token:
        return AuthResult.fail(
            body.get("error") or "No access_token in response",
            body.get("error_code") or "NO_TOKEN",
        )
    user_info = _build_user_info(
        body, email=email, phone=phone, username=username, login_type=login_type,
    )
    return AuthResult.ok({
        "token_type": body.get("token_type", "Bearer"),
        "access_token": access_token,
        "refresh_token": body.get("refresh_token"),
        "expires_in": body.get("expires_in", 7200),
        "user_info": user_info.to_dict(),
    })
