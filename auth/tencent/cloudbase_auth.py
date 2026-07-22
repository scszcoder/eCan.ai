"""
CloudBase Authentication Service
腾讯云云开发认证服务封装

支持以下登录方式：
1. 邮箱密码登录/注册
2. 手机号 + 验证码登录
3. 微信登录（通过微信开放平台）
4. 自定义登录（用于无密码场景）

CloudBase SDK 文档: https://cloud.tencent.com/document/product/876/34656
"""

import json
import time
import hashlib
import hmac
import base64
import urllib.parse
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, asdict

import requests
from utils.logger_helper import logger_helper as logger
from auth.auth_config import AuthConfig


@dataclass
class CloudBaseUserInfo:
    """CloudBase 用户信息结构"""
    uuid: str           # 用户唯一标识
    wx_open_id: Optional[str] = None    # 微信 OpenID
    phone_number: Optional[str] = None   # 手机号
    email: Optional[str] = None          # 邮箱
    nickname: Optional[str] = None       # 昵称
    avatar_url: Optional[str] = None     # 头像
    custom_user_id: Optional[str] = None  # 自定义用户ID
    login_type: str = "unknown"          # 登录类型


@dataclass
class CloudBaseAuthResult:
    """CloudBase 认证结果"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_code: Optional[str] = None


class CloudBaseAuthService:
    """
    腾讯云 CloudBase 认证服务

    使用腾讯云开发的认证服务，支持：
    - 邮箱密码登录
    - 手机号验证码登录
    - 微信登录
    - 自定义登录 Ticket
    """

    def __init__(self):
        self._config = self._load_config()
        self._jwt_secret = self._get_jwt_secret()
        self._access_token_cache: Optional[Dict[str, Any]] = None

    def _load_config(self) -> Dict[str, Any]:
        """加载 CloudBase 配置"""
        config = {}

        # CloudBase 配置
        if hasattr(AuthConfig, 'CLOUDBASE'):
            cloudbase_config = AuthConfig.CLOUDBASE
            config['env_id'] = str(cloudbase_config.ENV_ID) if cloudbase_config.ENV_ID else ''
            config['secret_id'] = str(cloudbase_config.SECRET_ID) if cloudbase_config.SECRET_ID else ''
            config['secret_key'] = str(cloudbase_config.SECRET_KEY) if cloudbase_config.SECRET_KEY else ''
            config['region'] = str(cloudbase_config.REGION) if hasattr(cloudbase_config, 'REGION') else 'ap-guangzhou'

        # JWT 配置
        if hasattr(AuthConfig, 'JWT'):
            jwt_config = AuthConfig.JWT
            config['jwt_secret'] = str(jwt_config.secret) if jwt_config.secret else ''
            config['jwt_expires_in'] = int(jwt_config.expires_in) if jwt_config.expires_in else 86400

        # 微信配置
        if hasattr(AuthConfig, 'WECHAT'):
            wechat_config = AuthConfig.WECHAT
            config['wechat_enabled'] = wechat_config.enabled if hasattr(wechat_config, 'enabled') else False
            config['wechat_app_id'] = str(wechat_config.APP_ID) if wechat_config.APP_ID else ''
            config['wechat_app_secret'] = str(wechat_config.APP_SECRET) if wechat_config.APP_SECRET else ''

        logger.info(f"[CloudBaseAuth] Loaded config: env_id={config.get('env_id', 'N/A')}, "
                   f"region={config.get('region', 'N/A')}")

        return config

    def _get_jwt_secret(self) -> str:
        """获取 JWT 密钥"""
        secret = self._config.get('jwt_secret', '')
        if not secret:
            # 使用默认密钥（生产环境应配置环境变量）
            secret = 'ecan-cn-default-jwt-secret-change-in-production'
            logger.warning("[CloudBaseAuth] Using default JWT secret - configure ECAN_JWT_SECRET in production!")
        return secret

    def _get_access_token(self, force_refresh: bool = False) -> Optional[str]:
        """
        获取 CloudBase 访问令牌

        使用腾讯云 API 密钥获取 CloudBase 环境访问令牌
        """
        if not force_refresh and self._access_token_cache:
            # 检查缓存是否过期（提前5分钟刷新）
            if time.time() < self._access_token_cache.get('expires_at', 0) - 300:
                return self._access_token_cache.get('token')

        env_id = self._config.get('env_id')
        secret_id = self._config.get('secret_id')
        secret_key = self._config.get('secret_key')

        if not all([env_id, secret_id, secret_key]):
            logger.error("[CloudBaseAuth] Missing CloudBase credentials")
            return None

        try:
            # 腾讯云 CAM 获取临时凭证
            # 文档: https://cloud.tencent.com/document/product/1312/82465
            timestamp = int(time.time())
            expired = timestamp + 3600  # 1小时有效期

            # 构造签名
            sign_str = f"a21{env_id}{timestamp}{expired}"
            signature = hmac.new(
                secret_key.encode('utf-8'),
                sign_str.encode('utf-8'),
                hashlib.sha1
            ).hexdigest()

            # 请求获取凭证
            url = f"https://tcb-admin.{self._config.get('region', 'ap-guangzhou')}.tencentcloudapi.com/admin/loginBySelf"
            headers = {
                'Content-Type': 'application/json',
                'X-TC-Action': 'CreateAuthToken',
                'X-TC-Version': '2020-02-27',
                'X-TC-Timestamp': str(timestamp),
                'X-TC-Region': self._config.get('region', 'ap-guangzhou'),
            }

            # 实际使用腾讯云 CAM 获取访问令牌
            # 这里使用简化的方法 - 通过云开发控制台 API
            # 生产环境应使用腾讯云 SDK

            # 获取腾讯云访问令牌
            cam_token = self._get_cam_token()
            if not cam_token:
                logger.error("[CloudBaseAuth] Failed to get CAM token")
                return None

            # 通过 CAM token 获取 CloudBase 访问令牌
            tcb_url = f"https://tcb-admin.{self._config.get('region', 'ap-guangzhou')}.tencentcloudapi.com/admin/loginBySelf"
            payload = {
                "EnvId": env_id,
                "CamToken": cam_token
            }

            response = requests.post(
                tcb_url,
                headers=headers,
                json=payload,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                if result.get('Response', {}).get('Error') is None:
                    data = result.get('Response', {})
                    token = data.get('LoginSessionKey')
                    if token:
                        self._access_token_cache = {
                            'token': token,
                            'expires_at': time.time() + 3500  # 约1小时后过期
                        }
                        return token

            logger.error(f"[CloudBaseAuth] Failed to get access token: {response.text}")
            return None

        except Exception as e:
            logger.error(f"[CloudBaseAuth] Exception getting access token: {e}")
            return None

    def _get_cam_token(self) -> Optional[str]:
        """
        通过腾讯云 CAM 获取访问令牌

        使用永久密钥获取临时访问凭证
        """
        import boto3
        from botocore.config import Config

        secret_id = self._config.get('secret_id')
        secret_key = self._config.get('secret_key')
        region = self._config.get('region', 'ap-guangzhou')

        if not all([secret_id, secret_key]):
            return None

        try:
            # 使用 STS 获取临时凭证
            sts_client = boto3.client(
                'sts',
                region_name=region,
                aws_access_key_id=secret_id,
                aws_secret_access_key=secret_key
            )

            # 调用 GetFederationToken 获取联合令牌
            # 该令牌可以用于 CloudBase 认证
            response = sts_client.get_federation_token(
                Name=f"ecan-cloudbase-{int(time.time())}",
                Policy=json.dumps({
                    "Version": "2.0",
                    "Statement": [{
                        "Effect": "Allow",
                        "Action": ["tcb:*"],
                        "Resource": ["*"]
                    }]
                }),
                DurationSeconds=3600
            )

            credentials = response['Credentials']

            # 构造 CloudBase 兼容的令牌
            token_data = {
                'TmpSecretId': credentials['AccessKeyId'],
                'TmpSecretKey': credentials['SecretAccessKey'],
                'Token': credentials['SessionToken'],
                'ExpiredTime': int(credentials['Expiration'].timestamp())
            }

            # 返回 base64 编码的令牌
            return base64.b64encode(json.dumps(token_data).encode()).decode()

        except Exception as e:
            logger.error(f"[CloudBaseAuth] CAM token error: {e}")
            return None

    def _call_cloudbase_auth(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用 CloudBase 认证 API

        Args:
            action: API 动作名称
            payload: 请求参数

        Returns:
            API 响应
        """
        env_id = self._config.get('env_id')
        access_token = self._get_access_token()

        if not access_token:
            return {'error': 'Failed to get access token'}

        region = self._config.get('region', 'ap-guangzhou')
        url = f"https://tcb-admin.{region}.tencentcloudapi.com/"

        headers = {
            'Content-Type': 'application/json',
            'X-TC-Action': action,
            'X-TC-Version': '2020-02-27',
            'X-TC-Timestamp': str(int(time.time())),
            'X-TC-Region': region,
        }

        try:
            response = requests.post(
                url,
                headers=headers,
                json={
                    'EnvironmentId': env_id,
                    'LoginSessionKey': access_token,
                    **payload
                },
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                resp = result.get('Response', {})
                if resp.get('Error'):
                    return {'error': resp['Error'].get('Message', 'Unknown error')}
                return resp

            return {'error': f'HTTP {response.status_code}: {response.text}'}

        except Exception as e:
            logger.error(f"[CloudBaseAuth] API call error: {e}")
            return {'error': str(e)}

    # ==================== 认证方法 ====================

    def sign_in_with_email_and_password(self, email: str, password: str) -> CloudBaseAuthResult:
        """
        邮箱密码登录

        Args:
            email: 邮箱地址
            password: 密码

        Returns:
            CloudBaseAuthResult
        """
        try:
            # CloudBase 邮箱登录 API
            result = self._call_cloudbase_auth('auth.signInWithEmailAndPassword', {
                'Email': email,
                'Password': password
            })

            if 'error' in result:
                return CloudBaseAuthResult(success=False, error=result['error'])

            # 解析用户信息
            user_info = self._parse_user_info(result)
            custom_token = self._generate_custom_token(user_info)

            return CloudBaseAuthResult(
                success=True,
                data={
                    'user_info': user_info,
                    'token': custom_token,
                    'refresh_token': custom_token
                }
            )

        except Exception as e:
            logger.error(f"[CloudBaseAuth] Email login error: {e}")
            return CloudBaseAuthResult(success=False, error=str(e))

    def sign_up_with_email_and_password(self, email: str, password: str) -> CloudBaseAuthResult:
        """
        邮箱注册

        Args:
            email: 邮箱地址
            password: 密码

        Returns:
            CloudBaseAuthResult
        """
        try:
            # CloudBase 邮箱注册 API
            result = self._call_cloudbase_auth('auth.signUpWithEmailAndPassword', {
                'Email': email,
                'Password': password
            })

            if 'error' in result:
                return CloudBaseAuthResult(success=False, error=result['error'])

            return CloudBaseAuthResult(
                success=True,
                data={'message': 'Registration successful. Please verify your email.'}
            )

        except Exception as e:
            logger.error(f"[CloudBaseAuth] Email signup error: {e}")
            return CloudBaseAuthResult(success=False, error=str(e))

    def sign_in_with_phone_number(self, phone: str, code: str) -> CloudBaseAuthResult:
        """
        手机号验证码登录

        Args:
            phone: 手机号
            code: 验证码

        Returns:
            CloudBaseAuthResult
        """
        try:
            # CloudBase 手机号登录 API
            result = self._call_cloudbase_auth('auth.signInWithPhoneAndCode', {
                'PhoneNumber': phone,
                'Code': code
            })

            if 'error' in result:
                return CloudBaseAuthResult(success=False, error=result['error'])

            # 解析用户信息
            user_info = self._parse_user_info(result)
            custom_token = self._generate_custom_token(user_info)

            return CloudBaseAuthResult(
                success=True,
                data={
                    'user_info': user_info,
                    'token': custom_token,
                    'refresh_token': custom_token
                }
            )

        except Exception as e:
            logger.error(f"[CloudBaseAuth] Phone login error: {e}")
            return CloudBaseAuthResult(success=False, error=str(e))

    def send_phone_verification_code(self, phone: str, purpose: str = 'login') -> CloudBaseAuthResult:
        """
        发送手机验证码

        Args:
            phone: 手机号
            purpose: 用途 (login, register, reset_password)

        Returns:
            CloudBaseAuthResult
        """
        try:
            result = self._call_cloudbase_auth('auth.sendPhoneVerificationCode', {
                'PhoneNumber': phone,
                'Purpose': purpose
            })

            if 'error' in result:
                return CloudBaseAuthResult(success=False, error=result['error'])

            return CloudBaseAuthResult(
                success=True,
                data={'message': 'Verification code sent'}
            )

        except Exception as e:
            logger.error(f"[CloudBaseAuth] Send phone code error: {e}")
            return CloudBaseAuthResult(success=False, error=str(e))

    def sign_in_with_wechat(self, code: str) -> CloudBaseAuthResult:
        """
        微信登录

        通过微信授权码获取用户信息并登录

        Args:
            code: 微信授权码

        Returns:
            CloudBaseAuthResult
        """
        try:
            wechat_config = self._config.get('wechat_app_id', '')

            if not wechat_config:
                return CloudBaseAuthResult(
                    success=False,
                    error='WeChat login not configured'
                )

            # 通过 code 获取微信 OpenID
            wechat_result = self._get_wechat_session(code)
            if not wechat_result:
                return CloudBaseAuthResult(
                    success=False,
                    error='Failed to get WeChat session'
                )

            openid = wechat_result.get('openid')
            session_key = wechat_result.get('session_key')

            # CloudBase 微信登录
            result = self._call_cloudbase_auth('auth.signInWithWechat', {
                'WxOpenId': openid,
                'WxSessionKey': session_key
            })

            if 'error' in result:
                return CloudBaseAuthResult(success=False, error=result['error'])

            # 解析用户信息
            user_info = self._parse_user_info(result)
            user_info.wx_open_id = openid
            user_info.login_type = 'wechat'

            custom_token = self._generate_custom_token(user_info)

            return CloudBaseAuthResult(
                success=True,
                data={
                    'user_info': user_info,
                    'token': custom_token,
                    'refresh_token': custom_token
                }
            )

        except Exception as e:
            logger.error(f"[CloudBaseAuth] WeChat login error: {e}")
            return CloudBaseAuthResult(success=False, error=str(e))

    def sign_in_with_custom_token(self, custom_token: str) -> CloudBaseAuthResult:
        """
        自定义登录（使用 Ticket）

        用于后端生成了自定义登录凭证的场景

        Args:
            custom_token: 自定义登录 Ticket

        Returns:
            CloudBaseAuthResult
        """
        try:
            result = self._call_cloudbase_auth('auth.signInWithTicket', {
                'Ticket': custom_token
            })

            if 'error' in result:
                return CloudBaseAuthResult(success=False, error=result['error'])

            # 解析用户信息
            user_info = self._parse_user_info(result)
            new_token = self._generate_custom_token(user_info)

            return CloudBaseAuthResult(
                success=True,
                data={
                    'user_info': user_info,
                    'token': new_token,
                    'refresh_token': new_token
                }
            )

        except Exception as e:
            logger.error(f"[CloudBaseAuth] Custom token login error: {e}")
            return CloudBaseAuthResult(success=False, error=str(e))

    def get_user_info(self, refresh_token: str) -> CloudBaseAuthResult:
        """
        获取用户信息

        Args:
            refresh_token: 刷新令牌

        Returns:
            CloudBaseAuthResult
        """
        try:
            result = self._call_cloudbase_auth('auth.getUserInfo', {
                'RefreshToken': refresh_token
            })

            if 'error' in result:
                return CloudBaseAuthResult(success=False, error=result['error'])

            user_info = self._parse_user_info(result)

            return CloudBaseAuthResult(
                success=True,
                data={'user_info': user_info}
            )

        except Exception as e:
            logger.error(f"[CloudBaseAuth] Get user info error: {e}")
            return CloudBaseAuthResult(success=False, error=str(e))

    def sign_out(self, refresh_token: str) -> CloudBaseAuthResult:
        """
        用户登出

        Args:
            refresh_token: 刷新令牌

        Returns:
            CloudBaseAuthResult
        """
        try:
            result = self._call_cloudbase_auth('auth.signOut', {
                'RefreshToken': refresh_token
            })

            if 'error' in result:
                return CloudBaseAuthResult(success=False, error=result['error'])

            return CloudBaseAuthResult(success=True)

        except Exception as e:
            logger.error(f"[CloudBaseAuth] Sign out error: {e}")
            return CloudBaseAuthResult(success=False, error=str(e))

    # ==================== 辅助方法 ====================

    def _get_wechat_session(self, code: str) -> Optional[Dict[str, Any]]:
        """
        通过微信授权码获取微信会话信息

        Args:
            code: 微信授权码

        Returns:
            微信会话信息 {openid, session_key}
        """
        wechat_app_id = self._config.get('wechat_app_id', '')
        wechat_app_secret = self._config.get('wechat_app_secret', '')

        if not wechat_app_id or not wechat_app_secret:
            logger.error("[CloudBaseAuth] WeChat credentials not configured")
            return None

        try:
            url = "https://api.weixin.qq.com/sns/jscode2session"
            params = {
                'appid': wechat_app_id,
                'secret': wechat_app_secret,
                'js_code': code,
                'grant_type': 'authorization_code'
            }

            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            if 'errcode' in data and data['errcode'] != 0:
                logger.error(f"[CloudBaseAuth] WeChat API error: {data}")
                return None

            return {
                'openid': data.get('openid'),
                'session_key': data.get('session_key'),
                'unionid': data.get('unionid')
            }

        except Exception as e:
            logger.error(f"[CloudBaseAuth] WeChat session error: {e}")
            return None

    def _parse_user_info(self, result: Dict[str, Any]) -> CloudBaseUserInfo:
        """
        解析 CloudBase 返回的用户信息

        Args:
            result: CloudBase API 响应

        Returns:
            CloudBaseUserInfo
        """
        data = result.get('Data', {})

        return CloudBaseUserInfo(
            uuid=data.get('uuid', ''),
            wx_open_id=data.get('wxOpenId'),
            phone_number=data.get('phoneNumber'),
            email=data.get('email'),
            nickname=data.get('nickName'),
            avatar_url=data.get('avatarUrl'),
            custom_user_id=data.get('customUserId'),
            login_type=data.get('loginType', 'unknown')
        )

    def _generate_custom_token(self, user_info: CloudBaseUserInfo) -> str:
        """
        生成自定义 JWT Token

        用于应用内部的会话管理

        Args:
            user_info: 用户信息

        Returns:
            JWT Token 字符串
        """
        import jwt as pyjwt

        now = int(time.time())
        expires_in = self._config.get('jwt_expires_in', 86400)

        payload = {
            'iss': 'ecan-cn',
            'sub': user_info.uuid,
            'iat': now,
            'exp': now + expires_in,
            'user': {
                'uuid': user_info.uuid,
                'email': user_info.email,
                'phone': user_info.phone_number,
                'nickname': user_info.nickname,
                'login_type': user_info.login_type
            }
        }

        return pyjwt.encode(payload, self._jwt_secret, algorithm='HS256')

    def verify_token(self, token: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        验证 JWT Token

        Args:
            token: JWT Token

        Returns:
            (是否有效, 用户信息字典)
        """
        import jwt as pyjwt

        try:
            payload = pyjwt.decode(token, self._jwt_secret, algorithms=['HS256'])
            return True, payload
        except pyjwt.ExpiredSignatureError:
            logger.warning("[CloudBaseAuth] Token expired")
            return False, None
        except pyjwt.InvalidTokenError as e:
            logger.warning(f"[CloudBaseAuth] Invalid token: {e}")
            return False, None

    def refresh_token(self, refresh_token: str) -> CloudBaseAuthResult:
        """
        刷新访问令牌

        Args:
            refresh_token: 刷新令牌

        Returns:
            CloudBaseAuthResult
        """
        try:
            # 验证刷新令牌
            valid, payload = self.verify_token(refresh_token)
            if not valid:
                return CloudBaseAuthResult(success=False, error='Invalid refresh token')

            # 重新获取 CloudBase 会话
            result = self._call_cloudbase_auth('auth.accurateQuery', {
                'RefreshToken': refresh_token
            })

            if 'error' in result:
                return CloudBaseAuthResult(success=False, error=result['error'])

            user_info = self._parse_user_info(result)
            new_token = self._generate_custom_token(user_info)

            return CloudBaseAuthResult(
                success=True,
                data={
                    'token': new_token,
                    'refresh_token': new_token
                }
            )

        except Exception as e:
            logger.error(f"[CloudBaseAuth] Token refresh error: {e}")
            return CloudBaseAuthResult(success=False, error=str(e))
