"""
Unit tests for CloudBase authentication service.

覆盖：
1. 验证码存储（生成、验证、过期、冷却、重用）
2. CloudBase 配置加载与状态检查
3. 认证方法参数校验（密码强度、必填参数）
"""

import time
import pytest

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

        新设计（2026-07）：私密字段（SECRET_*/WECHAT_APP_SECRET）仅从环境变量读取，
        公开字段（SMS_*/WECHAT_*/CLOUDBASE.ENV_ID）从 auth_config.yml 读取。
        """
        monkeypatch.setenv("ECAN_APP_ID", "cn")
        # 私密字段通过环境变量注入
        monkeypatch.setenv("ECAN_TENCENT_SECRET_ID", "test-secret-id")
        monkeypatch.setenv("ECAN_TENCENT_SECRET_KEY", "test-secret-key")

        c = CloudBaseConfig.from_env()

        # 私密字段断言
        assert c.secret_id == "test-secret-id"
        assert c.secret_key == "test-secret-key"

        # 公开字段断言（来自 apps/cn/config/auth_config.yml）
        assert c.env_id == "sccb0-d0gc5398xf028be6a"
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
# CloudBaseAuthService - Input Validation Tests
# ============================================================

class TestCloudBaseAuthServiceValidation:
    """输入校验测试(标准 API)"""

    def test_signup_disabled(self, service):
        """注册被禁用时拒绝"""
        service.config.enable_signup = False
        result = service.sign_up_with_otp(
            email="test@example.com", verification_token="123456",
        )
        assert not result.success
        assert result.error_code == "DISABLED"

    def test_signup_no_verification_token(self, service):
        """缺 verification_token 被拒绝"""
        result = service.sign_up_with_otp(email="test@example.com", verification_token="")
        assert not result.success
        assert result.error_code == "INVALID_INPUT"

    def test_signup_no_email_or_phone(self, service):
        """既无 email 也无 phone 被拒绝"""
        result = service.sign_up_with_otp(verification_token="123456")
        assert not result.success
        assert result.error_code == "INVALID_INPUT"

    def test_email_login_disabled(self, service):
        """邮箱登录被禁用"""
        service.config.enable_email_login = False
        result = service.sign_in_with_password("test@example.com", "pass")
        assert not result.success
        assert "Username/password login is disabled" in result.error

    def test_phone_login_disabled(self, service):
        """手机号登录被禁用"""
        service.config.enable_phone_login = False
        result = service.sign_in_with_otp(
            phone_number="13800138000", verification_token="123456",
        )
        assert not result.success

    def test_phone_login_no_verification_token(self, service):
        """手机号登录：缺 verification_token 被拒绝"""
        result = service.sign_in_with_otp(
            phone_number="13800138000", verification_token="",
        )
        assert not result.success

    def test_reset_password_weak_rejected(self, service):
        """弱密码重置拒绝"""
        result = service.reset_password(
            phone_number="13800138000", code="123456", new_password="short",
        )
        assert not result.success
        assert result.error_code == "WEAK_PASSWORD"

    def test_reset_password_no_code(self, service):
        """重置密码：缺 code 被拒绝"""
        result = service.reset_password(
            phone_number="13800138000", code="", new_password="validpass123",
        )
        assert not result.success


# ============================================================
# CloudBaseAuthService - Reset Password Full Flow
# ============================================================

class TestResetPasswordFlow:
    """密码重置完整流程测试(标准 API)"""

    def test_full_reset_password_flow(self, service):
        """完整重置密码流程(不含 API 调用)"""
        store = get_code_store()
        code = store.generate_code("13800138000", purpose="reset_password")

        # 错误 code 被拒绝
        r1 = service.reset_password(
            phone_number="13800138000", code="wrongcode", new_password="newpassword123",
        )
        assert not r1.success

        # 正确 code 通过校验(API 调用会失败因未配置,但错误应该是 NOT_CONFIGURED)
        r2 = service.reset_password(
            phone_number="13800138000", code=code, new_password="newpassword123",
        )
        assert not r2.success


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
            sub="user-1",
            email="a@b.com",
            phone_number="13800138000",
            nickname="tester",
            login_type="email",
        )
        d = u.to_dict()

        assert d["sub"] == "user-1"
        assert d["email"] == "a@b.com"
        assert d["phone_number"] == "13800138000"
        assert d["nickname"] == "tester"
        assert d["login_type"] == "email"

    def test_default_values(self):
        """默认值"""
        u = CloudBaseUserInfo(sub="x")
        assert u.email is None
        assert u.phone_number is None
        assert u.nickname is None
        assert u.avatar_url is None
        assert u.login_type == "password"
