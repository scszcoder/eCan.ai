#!/usr/bin/env python3
"""
CloudBase 手机号 OTP 完整链路 Mock 测试 (不连真实 CloudBase)

目的:
  - 验证前端→后端→CloudBaseAuthService 三层语义链路完好
  - 测试 6 种场景: 用户不存在/已存在 × login/signup × 错码/对码
  - 不受 CloudBase 平台 1分钟限制影响

原理: monkeypatch CloudBaseAuthService._post 直接返回预设响应
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

_script_path = Path(__file__).resolve()
_project_root = _script_path
for _ in range(4):
    _project_root = _project_root.parent
sys.path.insert(0, str(_project_root))


def scenario_user_not_exist_wrong_code():
    """场景1: 用户不存在,验证码错误 (纯外层)"""
    print("\n--- 场景1: send_code → 用户不存在 → verify 错码 ---")
    fake_vid = "FAKE_VID_USER_NOT_EXIST"

    fake_send_resp = {
        "_http_status": 200,
        "verification_id": fake_vid,
        "expires_in": 300,
        "is_user": False,  # 平台判断: 不存在
    }
    fake_verify_wrong_resp = {
        "_http_status": 400,
        "error": "Invalid verification code",
        "error_code": "INVALID_ARGUMENT",
    }

    from auth.tencent.cloudbase_auth import CloudBaseAuthService

    svc = CloudBaseAuthService()
    with patch.object(svc, "_post") as m:
        m.side_effect = [fake_send_resp, fake_verify_wrong_resp]
        send = svc.send_verification_code(phone_number="13800138000")
        print(f"  Step 1 (send): success={send.success}, is_user={send.data.get('is_user')}")
        assert send.success, "Step 1 should succeed"
        assert send.data["is_user"] is False, "Should detect user doesn't exist"

        v = svc.verify_verification_code(send.data["verification_id"], "000000")
        print(f"  Step 2 (verify wrong code): success={v.success}, err={v.error}")
        assert not v.success
        assert v.error_code == "INVALID_ARGUMENT"
    print("  ✓ PASS")


def scenario_user_not_exist_correct_code():
    """场景2: 用户不存在,验证码正确 → 走 signup"""
    print("\n--- 场景2: send_code → 用户不存在 → verify 对码 → signup ---")
    fake_vid = "FAKE_VID_NEW_USER"
    fake_token = "FAKE_VERIF_TOKEN_NEW"

    fake_send_resp = {"_http_status": 200, "verification_id": fake_vid,
                      "expires_in": 300, "is_user": False}
    fake_verify_ok_resp = {"_http_status": 200, "verification_token": fake_token,
                           "expires_in": 600}
    fake_signup_ok_resp = {
        "_http_status": 200,
        "access_token": "AT_NEW_USER",
        "refresh_token": "RT_NEW_USER",
        "token_type": "Bearer",
        "expires_in": 7200,
        "user_info": {"uid": "UID_NEW", "phone_number": "+86 13800138000"},
    }

    from auth.tencent.cloudbase_auth import CloudBaseAuthService
    svc = CloudBaseAuthService()

    with patch.object(svc, "_post") as m:
        m.side_effect = [fake_send_resp, fake_verify_ok_resp, fake_signup_ok_resp]
        send = svc.send_verification_code(phone_number="13800138000")
        assert send.success

        v = svc.verify_verification_code(send.data["verification_id"], "123456")
        assert v.success, f"verify failed: {v.error}"
        token = v.data["verification_token"]

        signup = svc.sign_up_with_otp(
            phone_number="13800138000",
            verification_token=token,
            password="TestPass123!",
        )
        print(f"  Step 3 (signup): success={signup.success}")
        if signup.success:
            print(f"    user_info: {signup.data.get('user_info')}")
        assert signup.success, f"signup failed: {signup.error}"
        # 注意: CloudBase 返回的 phone_number 不含 +86 前缀
        assert signup.data["user_info"]["phone_number"] == "13800138000"
    print("  ✓ PASS")


def scenario_user_exists_login_correct_code():
    """场景3: 用户已存在,验证码正确 → login"""
    print("\n--- 场景3: send_code → 用户已存在 → verify 对码 → login ---")
    fake_vid = "FAKE_VID_EXIST"
    fake_token = "FAKE_VERIF_TOKEN_EXIST"

    fake_send_resp = {"_http_status": 200, "verification_id": fake_vid,
                      "expires_in": 300, "is_user": True}
    fake_verify_ok_resp = {"_http_status": 200, "verification_token": fake_token,
                           "expires_in": 600}
    fake_signin_ok_resp = {
        "_http_status": 200,
        "access_token": "AT_EXIST",
        "refresh_token": "RT_EXIST",
        "token_type": "Bearer",
        "expires_in": 7200,
        "user_info": {"uid": "UID_EXIST", "phone_number": "+86 13800138000"},
    }

    from auth.tencent.cloudbase_auth import CloudBaseAuthService
    svc = CloudBaseAuthService()
    with patch.object(svc, "_post") as m:
        m.side_effect = [fake_send_resp, fake_verify_ok_resp, fake_signin_ok_resp]
        send = svc.send_verification_code(phone_number="13800138000")
        assert send.success
        assert send.data["is_user"] is True

        v = svc.verify_verification_code(send.data["verification_id"], "654321")
        assert v.success

        signin = svc.sign_in_with_otp(
            phone_number="13800138000",
            verification_token=v.data["verification_token"],
        )
        print(f"  Step 3 (signin): success={signin.success}")
        assert signin.success
    print("  ✓ PASS")


def scenario_login_user_not_exist():
    """场景4: 用户不存在却尝试 login → login 应该失败 (CloudBase 返回 INVALID_ARGUMENT)"""
    print("\n--- 场景4: 用户不存在却调 login → 应失败 ---")
    fake_vid = "FAKE_VID"
    fake_token = "FAKE_TOKEN"

    fake_send_resp = {"_http_status": 200, "verification_id": fake_vid,
                      "expires_in": 300, "is_user": False}
    fake_verify_ok_resp = {"_http_status": 200, "verification_token": fake_token,
                           "expires_in": 600}
    fake_login_fail_resp = {
        "_http_status": 400,
        "error": "User not exist",
        "error_code": "INVALID_ARGUMENT",
    }

    from auth.tencent.cloudbase_auth import CloudBaseAuthService
    svc = CloudBaseAuthService()
    with patch.object(svc, "_post") as m:
        m.side_effect = [fake_send_resp, fake_verify_ok_resp, fake_login_fail_resp]
        send = svc.send_verification_code(phone_number="13800138000")
        v = svc.verify_verification_code(send.data["verification_id"], "111111")
        signin = svc.sign_in_with_otp(
            phone_number="13800138000", verification_token=v.data["verification_token"],
        )
        print(f"  login (user not exists): success={signin.success}, err={signin.error_code}")
        assert not signin.success
    print("  ✓ PASS")


def scenario_signup_user_exists():
    """场景5: 用户已存在却尝试 signup → signup 应该失败 (PHONE_EXISTS)"""
    print("\n--- 场景5: 用户已存在却调 signup → 应失败 ---")
    fake_vid = "FAKE_VID"
    fake_token = "FAKE_TOKEN"

    fake_send_resp = {"_http_status": 200, "verification_id": fake_vid,
                      "expires_in": 300, "is_user": True}
    fake_verify_ok_resp = {"_http_status": 200, "verification_token": fake_token,
                           "expires_in": 600}
    fake_signup_fail_resp = {
        "_http_status": 400,
        "error": "Phone number already registered",
        "error_code": "PHONE_NUMBER_EXISTS",
    }

    from auth.tencent.cloudbase_auth import CloudBaseAuthService
    svc = CloudBaseAuthService()
    with patch.object(svc, "_post") as m:
        m.side_effect = [fake_send_resp, fake_verify_ok_resp, fake_signup_fail_resp]
        send = svc.send_verification_code(phone_number="13800138000")
        v = svc.verify_verification_code(send.data["verification_id"], "111111")
        signup = svc.sign_up_with_otp(
            phone_number="13800138000", verification_token=v.data["verification_token"],
        )
        print(f"  signup (user exists): success={signup.success}, err={signup.error_code}")
        assert not signup.success
        assert signup.error_code == "PHONE_NUMBER_EXISTS"
    print("  ✓ PASS")


def scenario_rate_limited():
    """场景6: 限流 RESOURCE_EXHAUSTED"""
    print("\n--- 场景6: 限流 RESOURCE_EXHAUSTED (1分钟1条) ---")
    fake_resp = {
        "_http_status": 429,
        "error": "Your phone can receive up to 1 text message per minute.",
        "error_code": "RESOURCE_EXHAUSTED",
    }
    from auth.tencent.cloudbase_auth import CloudBaseAuthService
    svc = CloudBaseAuthService()
    with patch.object(svc, "_post", return_value=fake_resp):
        send = svc.send_verification_code(phone_number="13800138000")
        print(f"  rate-limited send: success={send.success}, err_code={send.error_code}")
        assert not send.success
        assert send.error_code == "RESOURCE_EXHAUSTED"
    print("  ✓ PASS")


def main():
    print("=" * 60)
    print(" CloudBase 手机号 OTP 完整链路 Mock 测试")
    print("=" * 60)
    passed = []
    failed = []
    for fn in [
        scenario_user_not_exist_wrong_code,
        scenario_user_not_exist_correct_code,
        scenario_user_exists_login_correct_code,
        scenario_login_user_not_exist,
        scenario_signup_user_exists,
        scenario_rate_limited,
    ]:
        try:
            fn()
            passed.append(fn.__name__)
        except AssertionError as e:
            failed.append((fn.__name__, str(e)))
            import traceback
            traceback.print_exc()
        except Exception as e:
            failed.append((fn.__name__, repr(e)))
            import traceback
            traceback.print_exc()

    print()
    print("=" * 60)
    print(f" 通过 {len(passed)}/{len(passed) + len(failed)}")
    for name in passed:
        print(f"   ✓ {name}")
    for name, err in failed:
        print(f"   ✗ {name}: {err}")
    print("=" * 60)


if __name__ == "__main__":
    main()
