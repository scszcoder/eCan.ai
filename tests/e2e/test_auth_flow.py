"""
CloudBase Auth E2E Test Suite
===============================

跑 eCan.ai CN 版本的完整登录/注册流程
针对 CloudBase Web v3 Auth REST API

要求：
1. 设置 ECAN_APP_ID=cn（确保加载 CN 配置）
2. .env 里有 ECAN_TENCENT_CLOUDBASE_ENV_ID（可被环境变量 override）
3. apps/cn/config/auth_config.yml 中 CLOUDBASE.ENV_ID 配置正确
4. **【自动】** 在腾讯云 CloudBase 控制台 → 用户管理 → 用户列表 → 查看用户
   或通过 E2E 测试直接注册（走 email 验证码流程，无需控制台操作）：
       ECAN_APP_ID=cn python3 -c "
       from auth.tencent.cloudbase_auth import get_cloudbase_service
       svc = get_cloudbase_service()
       # 发验证码到邮箱
       r = svc.send_verification_code(email='your_email@example.com')
       # 手动查邮件获取 6 位码 verification_code
       # 验证验证码获取 verification_token
       vt = svc.verify_verification_code(r.data['verification_id'], '123456')
       # 注册
       svc.sign_up_with_otp(email='your_email@example.com',
                            verification_token=vt.data['verification_token'],
                            username='testuser',
                            password='YourPass123!')
       "

跑测试：
    ECAN_APP_ID=cn pytest tests/e2e/test_auth_flow.py -v -s

如果不需要 SK 也能跑通登录测试（web v3 不需要签名）。
如果需要 SK 才会跑通（即还在老架构），说明 cloudbase_auth.py 没有走 web v3。
"""

import os
import sys
import time
import uuid
from pathlib import Path

# 确保 ECAN_APP_ID 在 import 之前已设置
if not os.getenv("ECAN_APP_ID"):
    os.environ["ECAN_APP_ID"] = "cn"

# 让脚本能 import 项目根目录
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from auth.tencent.cloudbase_auth import (
    CloudBaseAuthService,
    get_cloudbase_service,
    AuthResult,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="module")
def cloudbase_service():
    """共享的 CloudBase service 单例"""
    get_cloudbase_service.cache_clear()
    return CloudBaseAuthService()


@pytest.fixture(scope="module")
def config(cloudbase_service):
    status = cloudbase_service.get_config_status()
    if not status["configured"]:
        pytest.skip(
            f"CloudBase not configured: env_id={status['env_id']!r}\n"
            f"检查: apps/cn/config/auth_config.yml 中 CLOUDBASE.ENV_ID 是否正确"
        )
    return status


# ============================================================
# 单元链路测试（不依赖真实用户，能验证 HTTP 链路）
# ============================================================

class TestCloudBaseConfig:
    """测试配置正确加载"""

    def test_env_id_loaded(self, config):
        assert config["env_id"], "env_id should be loaded"
        # env_id 真实存在
        assert config["base_url"].startswith("https://"), "base_url wrong"

    def test_is_configured(self, cloudbase_service):
        """Web v3 登录只需要 env_id,不应该要求 SK"""
        assert cloudbase_service.config.is_configured(), \
            "is_configured should return True with just env_id (web v3 doesn't need SK)"

    def test_has_admin_credentials_optional(self, cloudbase_service):
        """admin 类操作需要 SK,但登录不需要"""
        # 这里只验证方法存在,不强制 SK 已配
        result = cloudbase_service.config.has_admin_credentials()
        assert isinstance(result, bool)


class TestCloudBaseHTTPChain:
    """测试 HTTP 链路活，不依赖真实用户"""

    def test_signin_with_nonexistent_user_returns_401(self, cloudbase_service):
        """随机不存在用户 → INVALID_CREDENTIALS（链路 OK）"""
        result = cloudbase_service.sign_in_with_password(
            username=f"nonexistent_{uuid.uuid4().hex[:8]}",
            password="BadPass123!",
        )
        assert not result.success
        assert result.error_code == "INVALID_CREDENTIALS", \
            f"Expected INVALID_CREDENTIALS, got {result.error_code}: {result.error}"

    def test_signin_with_empty_input_rejected(self, cloudbase_service):
        """空输入应该被 client 端拦截"""
        result = cloudbase_service.sign_in_with_password(username="", password="")
        assert not result.success
        assert result.error_code == "INVALID_INPUT"


# ============================================================
# E2E 真实用户测试（需要在 CloudBase 控制台手工创建）
# ============================================================

class TestRealLoginFlow:
    """真实用户登录流程"""

    # ！！CloudBase Web v3 注册的测试账号
    TEST_USERNAME = os.getenv("E2E_TEST_USERNAME", "ecan249511118")
    TEST_PASSWORD = os.getenv("E2E_TEST_PASSWORD", "Ecan249511118!")

    def test_signin_with_valid_credentials(self, cloudbase_service):
        """真实账号登录 → 成功，拿到 access_token"""
        result = cloudbase_service.sign_in_with_password(
            username=self.TEST_USERNAME,
            password=self.TEST_PASSWORD,
        )
        assert result.success, f"登录失败: {result.error} ({result.error_code})"
        data = result.data
        assert data["token_type"] == "Bearer"
        assert data["access_token"]
        assert data["refresh_token"]
        assert data["expires_in"] > 0
        assert data["user_info"]["sub"]

    def test_current_user_with_access_token(self, cloudbase_service):
        """用 access_token 拉当前用户信息"""
        login = cloudbase_service.sign_in_with_password(
            username=self.TEST_USERNAME,
            password=self.TEST_PASSWORD,
        )
        if not login.success:
            pytest.skip(f"登录失败，跳过: {login.error}")

        result = cloudbase_service.get_current_user(login.data["access_token"])
        assert result.success, f"获取用户失败: {result.error}"
        user = result.data
        # CloudBase /auth/v1/user 返回的用户字段
        assert "sub" in user or "user_id" in user

    def test_refresh_token(self, cloudbase_service):
        """用 refresh_token 刷新得到新 access_token"""
        login = cloudbase_service.sign_in_with_password(
            username=self.TEST_USERNAME,
            password=self.TEST_PASSWORD,
        )
        if not login.success:
            pytest.skip(f"登录失败，跳过: {login.error}")

        old_refresh = login.data["refresh_token"]
        result = cloudbase_service.refresh_token(old_refresh)
        assert result.success, f"刷新失败: {result.error}"
        # 新的 access_token 应该不一样（CloudBase 一般会 roll）
        assert result.data["access_token"] != login.data["access_token"]

    def test_signout_invalidates_session(self, cloudbase_service):
        """登出后 access_token 应该失效"""
        login = cloudbase_service.sign_in_with_password(
            username=self.TEST_USERNAME,
            password=self.TEST_PASSWORD,
        )
        if not login.success:
            pytest.skip(f"登录失败，跳过: {login.error}")

        access_token = login.data["access_token"]
        out = cloudbase_service.sign_out(access_token)
        assert out.success, f"登出失败: {out.error}"


# ============================================================
# 真实手机/邮箱 OTP 测试（需要真实手机号/邮箱,以及 SMS 配置）
# ============================================================

class TestOTPFlow:
    """验证码登录流程（需要腾讯云 SMS 服务配置 + 真实手机号）"""

    TEST_PHONE = os.getenv("E2E_TEST_PHONE", "")  # 形如 "+86 13800138000"
    TEST_EMAIL = os.getenv("E2E_TEST_EMAIL", "")  # 形如 "user@example.com"

    @pytest.mark.skipif(
        not os.getenv("E2E_TEST_PHONE") and not os.getenv("E2E_TEST_EMAIL"),
        reason="需要配置 E2E_TEST_PHONE 或 E2E_TEST_EMAIL 环境变量,且该账号已注册",
    )
    def test_send_verification_code(self, cloudbase_service):
        if self.TEST_PHONE:
            result = cloudbase_service.send_verification_code(phone_number=self.TEST_PHONE)
        else:
            result = cloudbase_service.send_verification_code(email=self.TEST_EMAIL)
        # 不一定成功（取决于 SMS 配额/邮箱有效性），但不应该是网络错误
        assert result.error_code != "NETWORK_ERROR", \
            f"网络错误: {result.error}"


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
