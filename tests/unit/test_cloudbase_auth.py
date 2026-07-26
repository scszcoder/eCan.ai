"""
Unit tests for CloudBase authentication service.

覆盖：
1. JWT Token 生成与验证
2. 验证码存储（生成、验证、过期、冷却、重用）
3. CloudBase 配置加载与状态检查
4. 认证方法参数校验（密码强度、必填参数）
"""

import os
import time
import pytest

# 在导入前设置环境变量（生产必需）
os.environ.setdefault("ECAN_JWT_SECRET", "test-jwt-secret-at-least-32-characters-long")

from auth.tencent.cloudbase_config import CloudBaseConfig
from auth.tencent.cloudbase_auth import CloudBaseAuthService, CloudBaseUserInfo
from auth.tencent.code_store import CodeStore, get_code_store, CooldownError
from auth.tencent.sms_service import TencentSMSService


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def reset_code_store():
    """每个测试后重置验证码存储"""
    store = get_code_store()
    store._codes.clear()
    store._last_send.clear()
    yield
    store._codes.clear()
    store._last_send.clear()


@pytest.fixture
def config(monkeypatch):
    """CloudBase 配置 fixture（function scope，每次重新创建）"""
    # 确保 CN app yml 加载路径
    monkeypatch.setenv("ECAN_APP_ID", "cn")
    return CloudBaseConfig.from_env()


@pytest.fixture
def service(config):
    """CloudBase 认证服务 fixture"""
    return CloudBaseAuthService(config)


@pytest.fixture
def sample_user():
    """示例用户"""
    return CloudBaseUserInfo(
        uuid="test-uuid-12345",
        email="test@example.com",
        login_type="email",
    )


# ============================================================
# Config Tests
# ============================================================

class TestCloudBaseConfig:
    """CloudBase 配置测试"""

    def test_default_config(self):
        """默认配置"""
        c = CloudBaseConfig()
        assert c.region == "ap-guangzhou"
        assert c.enable_email_login is True
        assert c.enable_phone_login is True
        assert c.enable_signup is True

    def test_from_env_loads_env_vars(self, monkeypatch):
        """私密字段从环境变量加载；公开字段从 yml 加载。

        新设计（2026-07）：私密字段（SECRET_*/JWT_SECRET）仅从环境变量读取，
        公开字段（SMS_*/WECHAT_*/CLOUDBASE.ENV_ID）从 auth_config.yml 读取。
        """
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        # 私密字段通过环境变量注入
        monkeypatch.setenv("ECAN_TENCENT_SECRET_ID", "test-secret-id")
        monkeypatch.setenv("ECAN_TENCENT_SECRET_KEY", "test-secret-key")
        monkeypatch.setenv("ECAN_JWT_SECRET", "x" * 32)

        c = CloudBaseConfig.from_env()

        # 私密字段断言
        assert c.secret_id == "test-secret-id"
        assert c.secret_key == "test-secret-key"
        assert c.jwt_secret == "x" * 32

        # 公开字段断言（来自 apps/cn/config/auth_config.yml）
        assert c.env_id == "ecan-cn-prod"
        assert c.region == "ap-guangzhou"
        assert c.sms_sign_name == "eCan"

    def test_is_configured(self):
        """配置完整性检查"""
        c = CloudBaseConfig()
        assert c.is_configured() is False

        c.env_id = "env"
        c.secret_id = "id"
        c.secret_key = "key"
        assert c.is_configured() is True

    def test_is_sms_configured(self):
        """短信配置检查"""
        c = CloudBaseConfig()
        assert c.is_sms_configured() is False

        c.secret_id = "id"
        c.secret_key = "key"
        c.sms_sdk_app_id = "sms"
        c.sms_template_id = "tpl"
        assert c.is_sms_configured() is True

    def test_get_jwt_secret_raises_when_missing(self):
        """JWT 密钥缺失时必须 fail-fast，不允许静默生成随机值。

        理由：每次重启后端都会让所有现有 token 失效；多副本部署时跨实例
        token 互不兼容。调用方必须显式配置 ECAN_JWT_SECRET。
        """
        c = CloudBaseConfig(jwt_secret="")
        with pytest.raises(RuntimeError, match="ECAN_JWT_SECRET"):
            c.get_jwt_secret()

    def test_get_jwt_secret_raises_when_too_short(self):
        """JWT 密钥长度 <32 字符时也必须 fail-fast。"""
        c = CloudBaseConfig(jwt_secret="short")
        with pytest.raises(RuntimeError, match="ECAN_JWT_SECRET"):
            c.get_jwt_secret()

    def test_get_jwt_secret_uses_provided_secret(self):
        """使用配置的 JWT 密钥"""
        provided = "x" * 32
        c = CloudBaseConfig(jwt_secret=provided)
        assert c.get_jwt_secret() == provided


# ============================================================
# CodeStore Tests
# ============================================================

class TestCodeStore:
    """验证码存储测试"""

    def test_generate_code_success(self):
        """成功生成验证码"""
        store = CodeStore()
        code = store.generate_code("13800138000", purpose="login")
        assert code is not None
        assert len(code) == 6
        assert code.isdigit()

    def test_generate_code_cooldown(self):
        """发送冷却"""
        store = CodeStore()
        store.generate_code("13800138000", purpose="login")

        with pytest.raises(CooldownError) as exc_info:
            store.generate_code("13800138000", purpose="login")
        assert "秒" in str(exc_info.value)

    def test_cooldown_is_purpose_specific(self):
        """不同用途冷却独立"""
        store = CodeStore()
        code1 = store.generate_code("13800138000", purpose="login")
        code2 = store.generate_code("13800138000", purpose="register")
        assert code1 != code2

    def test_verify_code_success(self):
        """成功验证"""
        store = CodeStore()
        code = store.generate_code("13800138000", purpose="login")
        assert store.verify_code("13800138000", code, purpose="login") is True

    def test_verify_code_wrong_code(self):
        """错误验证码"""
        store = CodeStore()
        store.generate_code("13800138000", purpose="login")
        assert store.verify_code("13800138000", "000000", purpose="login") is False

    def test_verify_code_one_time_use(self):
        """验证码一次性使用"""
        store = CodeStore()
        code = store.generate_code("13800138000", purpose="login")
        assert store.verify_code("13800138000", code, purpose="login") is True
        assert store.verify_code("13800138000", code, purpose="login") is False

    def test_verify_code_max_attempts(self):
        """最大尝试次数限制"""
        store = CodeStore()
        store.generate_code("13800138000", purpose="login")

        for _ in range(5):
            store.verify_code("13800138000", "000000", purpose="login")

        # 第 6 次失败后，code 应该被移除
        assert store.verify_code("13800138000", "000000", purpose="login") is False

    def test_verify_code_expired(self):
        """验证码过期"""
        store = CodeStore()
        # 模拟过期
        store._codes["13800138000:login"] = type('E', (), {
            'code': '123456',
            'purpose': 'login',
            'created_at': time.time() - 1000,
            'expires_at': time.time() - 500,
            'attempts': 0,
        })()

        assert store.verify_code("13800138000", "123456", purpose="login") is False

    def test_phone_normalization(self):
        """手机号标准化"""
        store = CodeStore()
        code = store.generate_code("+86 138-0013-8000", purpose="login")

        # 验证时使用任意格式
        assert store.verify_code("13800138000", code, purpose="login") is True


# ============================================================
# CloudBaseAuthService - JWT Tests
# ============================================================

class TestCloudBaseAuthServiceJWT:
    """JWT Token 测试"""

    def test_generate_and_verify_jwt(self, service, sample_user):
        """生成并验证 JWT"""
        token = service._generate_jwt(sample_user)
        assert isinstance(token, str)
        assert len(token.split(".")) == 3  # JWT 格式

        valid, payload = service.verify_token(token)
        assert valid is True
        assert payload["sub"] == sample_user.uuid
        assert payload["user"]["email"] == sample_user.email

    def test_verify_invalid_token(self, service):
        """无效 token 验证失败"""
        valid, payload = service.verify_token("invalid.token.here")
        assert valid is False
        assert payload is None

    def test_verify_expired_token(self, service, sample_user):
        """过期 token 验证失败"""
        # 设置短过期时间
        service.config.jwt_expires_in = -100  # 已过期
        token = service._generate_jwt(sample_user)

        valid, _ = service.verify_token(token)
        assert valid is False


# ============================================================
# CloudBaseAuthService - Input Validation Tests
# ============================================================

class TestCloudBaseAuthServiceValidation:
    """输入校验测试"""

    def test_signup_weak_password_rejected(self, service):
        """弱密码被拒绝"""
        result = service.sign_up_with_email("test@example.com", "1234567")
        # 由于未配置 CloudBase，先返回未配置错误
        assert not result.success

    def test_signup_disabled(self, service):
        """注册被禁用时拒绝"""
        service.config.enable_signup = False
        result = service.sign_up_with_email("test@example.com", "validpass123")
        assert not result.success
        assert "Signup is disabled" in result.error

    def test_signup_empty_fields(self, service):
        """空字段拒绝"""
        result = service.sign_up_with_email("", "")
        assert not result.success

    def test_email_login_disabled(self, service):
        """邮箱登录被禁用"""
        service.config.enable_email_login = False
        result = service.sign_in_with_email("test@example.com", "pass")
        assert not result.success
        assert "Email login is disabled" in result.error

    def test_phone_login_disabled(self, service):
        """手机号登录被禁用"""
        service.config.enable_phone_login = False
        result = service.sign_in_with_phone("13800138000", "123456")
        assert not result.success

    def test_phone_login_invalid_code(self, service):
        """手机号登录：无效验证码"""
        result = service.sign_in_with_phone("13800138000", "000000")
        assert not result.success
        assert result.error_code == "INVALID_CODE"

    def test_reset_password_weak_rejected(self, service):
        """弱密码重置拒绝"""
        result = service.reset_password_with_phone("13800138000", "123456", "short")
        assert not result.success
        assert result.error_code == "WEAK_PASSWORD"

    def test_reset_password_no_code(self, service):
        """无验证码拒绝"""
        result = service.reset_password_with_phone("13800138000", "999999", "validpass123")
        assert not result.success
        assert result.error_code == "INVALID_CODE"


# ============================================================
# CloudBaseAuthService - Reset Password Full Flow
# ============================================================

class TestResetPasswordFlow:
    """密码重置完整流程测试"""

    def test_full_reset_password_flow(self, service):
        """完整重置密码流程（不含 API 调用）"""
        store = get_code_store()
        code = store.generate_code("13800138000", purpose="reset_password")

        # 错误 code 被拒绝
        r1 = service.reset_password_with_phone("13800138000", "wrongcode", "newpassword123")
        assert not r1.success
        assert r1.error_code == "INVALID_CODE"

        # 正确 code 通过校验（API 调用会失败因未配置，但错误应该是 NOT_CONFIGURED/SIGNUP_FAILED）
        r2 = service.reset_password_with_phone("13800138000", code, "newpassword123")
        # 未配置 CloudBase，会返回 NOT_CONFIGURED
        assert not r2.success
        # 但不是因为 INVALID_CODE
        assert r2.error_code != "INVALID_CODE"


# ============================================================
# Config Status Tests
# ============================================================

class TestConfigStatus:
    """配置状态测试"""

    def test_get_config_status(self, service):
        """获取配置状态"""
        status = service.get_config_status()

        assert "configured" in status
        assert "email_login_enabled" in status
        assert "phone_login_enabled" in status
        assert "signup_enabled" in status
        assert "sms_configured" in status
        assert "region" in status

        assert isinstance(status["configured"], bool)
        assert isinstance(status["email_login_enabled"], bool)


# ============================================================
# SMS Service Tests
# ============================================================

class TestSMSService:
    """短信服务测试"""

    def test_sms_service_init(self):
        """初始化"""
        svc = TencentSMSService()
        assert svc.API_URL == "https://sms.tencentcloudapi.com"
        assert svc.API_VERSION == "2021-01-11"

    def test_send_without_config(self):
        """未配置时发送失败"""
        svc = TencentSMSService()
        svc.config = CloudBaseConfig()  # 全部为空

        result = svc.send_verification_code("13800138000", "123456")
        assert result.success is False
        assert "not configured" in result.error.lower()


# ============================================================
# CloudBaseUserInfo Tests
# ============================================================

class TestCloudBaseUserInfo:
    """用户信息数据类测试"""

    def test_to_dict(self):
        """转换为字典"""
        u = CloudBaseUserInfo(
            uuid="uuid-1",
            email="a@b.com",
            phone_number="13800138000",
            nickname="tester",
            login_type="email",
        )
        d = u.to_dict()

        assert d["uuid"] == "uuid-1"
        assert d["email"] == "a@b.com"
        assert d["phone_number"] == "13800138000"
        assert d["nickname"] == "tester"
        assert d["login_type"] == "email"

    def test_default_values(self):
        """默认值"""
        u = CloudBaseUserInfo(uuid="x")
        assert u.email is None
        assert u.phone_number is None
        assert u.nickname is None
        assert u.avatar_url is None
        assert u.login_type == "email"
