#!/usr/bin/env python3
"""
CloudBase 手机号验证码 登录/注册 完整流程测试

测试覆盖:
  Step 1: send_verification_code (发短信)
  Step 2: verify_verification_code (验证,需真实验证码)
  Step 3: sign_in_with_otp  / sign_up_with_otp (登录/注册)

Usage:
    ECAN_APP_ID=cn python tests/integration/auth/test_phone_otp_flow.py
    ECAN_APP_ID=cn python tests/integration/auth/test_phone_otp_flow.py --signup
    ECAN_APP_ID=cn python tests/integration/auth/test_phone_otp_flow.py --phone 13880917374 --code 123456
"""
import argparse
import os
import sys
from pathlib import Path

_script_path = Path(__file__).resolve()
_project_root = _script_path
for _ in range(4):
    _project_root = _project_root.parent
sys.path.insert(0, str(_project_root))
os.chdir(_project_root)


def hr(title: str):
    print()
    print("=" * 60)
    print(f" {title}")
    print("=" * 60)


def test_step1_send_code(phone: str) -> str | None:
    hr("Step 1: send_verification_code (发验证码)")
    from auth.tencent.cloudbase_auth import CloudBaseAuthService
    svc = CloudBaseAuthService()
    status = svc.get_config_status()
    print(f"  configured: {status['configured']}")
    print(f"  env_id: {status['env_id']}")
    print(f"  phone_login_enabled: {status['phone_login_enabled']}")
    print(f"  signup_enabled: {status['signup_enabled']}")

    if not status["configured"]:
        print("\n❌ CloudBase 未配置,无法继续")
        return None

    print(f"\n  → 发送验证码到: {phone}")
    result = svc.send_verification_code(phone_number=phone)
    if not result.success:
        print(f"\n❌ 发送失败:")
        print(f"  error: {result.error}")
        print(f"  error_code: {result.error_code}")
        return None

    vid = result.data.get("verification_id")
    is_user = result.data.get("is_user")
    print(f"\n✓ 验证码已发送")
    print(f"  verification_id: {vid[:40]}..." if vid else "  verification_id: <empty>")
    print(f"  is_user (平台判断): {is_user}")
    print(f"  expires_in: {result.data.get('expires_in')}s")
    return vid


def test_step2_verify_code(verification_id: str, code: str) -> str | None:
    hr("Step 2: verify_verification_code (验证码 → verification_token)")
    from auth.tencent.cloudbase_auth import CloudBaseAuthService
    svc = CloudBaseAuthService()
    print(f"  → 用 verification_id + code 换 token")
    result = svc.verify_verification_code(verification_id, code)
    if not result.success:
        print(f"\n❌ 验证失败:")
        print(f"  error: {result.error}")
        print(f"  error_code: {result.error_code}")
        return None

    token = result.data.get("verification_token")
    print(f"\n✓ 验证成功")
    print(f"  verification_token: {token[:40]}..." if token else "  verification_token: <empty>")
    return token


def test_step3_signin(phone: str, verification_token: str) -> bool:
    hr("Step 3a: sign_in_with_otp (登录 - 用户必须已存在)")
    from auth.tencent.cloudbase_auth import CloudBaseAuthService
    svc = CloudBaseAuthService()
    print(f"  → 用 phone + verification_token 登录")
    result = svc.sign_in_with_otp(phone_number=phone, verification_token=verification_token)
    if not result.success:
        print(f"\n❌ 登录失败:")
        print(f"  error: {result.error}")
        print(f"  error_code: {result.error_code}")
        return False

    print(f"\n✓ 登录成功")
    print(f"  token_type: {result.data.get('token_type')}")
    print(f"  expires_in: {result.data.get('expires_in')}s")
    print(f"  user_info: {result.data.get('user_info')}")
    return True


def test_step3_signup(phone: str, verification_token: str, password: str | None = None) -> bool:
    hr("Step 3b: sign_up_with_otp (注册 - 创建新用户)")
    from auth.tencent.cloudbase_auth import CloudBaseAuthService
    svc = CloudBaseAuthService()
    print(f"  → 用 phone + verification_token 注册")
    print(f"     password: {'<set>' if password else '<not set>'}")
    result = svc.sign_up_with_otp(
        phone_number=phone,
        verification_token=verification_token,
        password=password,
    )
    if not result.success:
        print(f"\n❌ 注册失败:")
        print(f"  error: {result.error}")
        print(f"  error_code: {result.error_code}")
        return False

    print(f"\n✓ 注册成功")
    print(f"  token_type: {result.data.get('token_type')}")
    print(f"  expires_in: {result.data.get('expires_in')}s")
    print(f"  user_info: {result.data.get('user_info')}")
    return True


def main():
    p = argparse.ArgumentParser(description="Test CloudBase phone OTP flow")
    p.add_argument("--phone", default="13880917374", help="手机号")
    p.add_argument("--code", default=None, help="验证码 (默认需要交互式输入)")
    p.add_argument("--password", default=None, help="注册时密码")
    p.add_argument("--signup", action="store_true", help="走注册流程 (默认走登录)")
    args = p.parse_args()

    print("\n🚀 CloudBase 手机号 OTP 流程测试")
    print(f"   phone: {args.phone}")
    print(f"   mode: {'signup' if args.signup else 'login'}")

    # Step 1
    vid = test_step1_send_code(args.phone)
    if not vid:
        print("\n⛔ Step 1 失败,流程终止")
        sys.exit(1)

    # Step 2 — 需要真实验证码
    if not args.code:
        print(f"\n⚠️  Step 2 需要真实验证码")
        print(f"   请检查手机 {args.phone} 收到的短信验证码")
        code = input("   请输入验证码: ").strip()
        if not code:
            print("\n⛔ 未输入验证码,流程终止")
            sys.exit(1)
    else:
        code = args.code

    token = test_step2_verify_code(vid, code)
    if not token:
        print("\n⛔ Step 2 失败,流程终止")
        sys.exit(2)

    # Step 3
    if args.signup:
        ok = test_step3_signup(args.phone, token, args.password)
    else:
        ok = test_step3_signin(args.phone, token)
    if not ok:
        print(f"\n⛔ Step 3 失败,流程终止")
        sys.exit(3)

    print("\n" + "=" * 60)
    print(" ✅ 完整流程通过!")
    print("=" * 60)


if __name__ == "__main__":
    main()
