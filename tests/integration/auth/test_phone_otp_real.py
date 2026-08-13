#!/usr/bin/env python3
"""
分两步走的真实流程测试（避免 1 分钟限流互相干扰）

Usage:
  Step 1: ECAN_APP_ID=cn python tests/integration/auth/test_phone_otp_real.py send
          (会发送验证码到 --phone)
  Step 2: ECAN_APP_ID=cn python tests/integration/auth/test_phone_otp_real.py verify --code <code>
          (用最新验证码验证 + 走登录/注册)
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

_script_path = Path(__file__).resolve()
_project_root = _script_path
for _ in range(4):
    _project_root = _project_root.parent
sys.path.insert(0, str(_project_root))


STATE_FILE = Path("/tmp/eCan_phone_otp_state.json")


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(s: dict):
    STATE_FILE.write_text(json.dumps(s, indent=2))


def cmd_send(args):
    from auth.tencent.cloudbase_auth import CloudBaseAuthService

    svc = CloudBaseAuthService()
    st = load_state()
    last_phone = st.get("phone")
    if last_phone == args.phone and (time.time() - st.get("sent_at", 0)) < 60:
        wait = 60 - int(time.time() - st.get("sent_at", 0))
        print(f"⚠️  离上次发送给同号 {args.phone} 还不到 1 分钟")
        print(f"   还需要等 {wait} 秒")
        print(f"   或: 用 'verify --code <code>' 处理上次发的验证码")
        sys.exit(1)

    print(f"→ send_verification_code({args.phone})")
    r = svc.send_verification_code(phone_number=args.phone)
    if not r.success:
        print(f"❌ FAIL: {r.error_code} - {r.error}")
        sys.exit(1)

    save_state({
        "phone": args.phone,
        "vid": r.data["verification_id"],
        "sent_at": time.time(),
        "is_user": r.data.get("is_user"),
    })
    print(f"✓ 验证码已发送")
    print(f"  verification_id: {r.data['verification_id'][:40]}...")
    print(f"  platform is_user: {r.data.get('is_user')}")
    print(f"  state 已存到: {STATE_FILE}")
    print()
    print(f"📱 请查手机 {args.phone} 收到的新验证码")
    print(f"   然后跑: python {__file__} verify --code <新码>")


def cmd_verify(args):
    from auth.tencent.cloudbase_auth import CloudBaseAuthService

    svc = CloudBaseAuthService()
    st = load_state()
    if not st.get("vid"):
        print("❌ 没有 sent 状态, 请先跑 'send'")
        sys.exit(1)

    phone = st["phone"]
    vid = st["vid"]
    age = int(time.time() - st["sent_at"])
    print(f"使用 state: phone={phone}, vid={vid[:30]}..., age={age}s")
    if age > 300:
        print("⚠️  超过 5 分钟可能过期")

    print(f"\n→ verify_verification_code({vid[:20]}..., {args.code})")
    v = svc.verify_verification_code(vid, args.code)
    if not v.success:
        print(f"❌ FAIL: {v.error_code} - {v.error}")
        sys.exit(1)

    token = v.data["verification_token"]
    print(f"✓ Step 2 OK")
    print(f"  verification_token: {token[:40]}...")

    is_user = st.get("is_user")
    if is_user is False:
        print(f"\n→ sign_up_with_otp (平台判断 is_user=False → 应走 signup)")
        action = "signup"
    elif is_user is True:
        print(f"\n→ sign_in_with_otp (平台判断 is_user=True → 应走 signin)")
        action = "signin"
    else:
        print(f"\n→ 先试 signin (默认)")
        action = "signin"

    if action == "signin":
        result = svc.sign_in_with_otp(phone_number=phone, verification_token=token)
        if not result.success:
            print(f"❌ signin FAIL: {result.error_code} - {result.error}")
            print(f"   (新用户却用 signin → 可接受,重试 signup)")
            # 兜底: 试 signup
            print(f"\n→ fallback sign_up_with_otp")
            result = svc.sign_up_with_otp(
                phone_number=phone, verification_token=token, password="TestPass123!",
            )
            action = "signup"
    else:
        result = svc.sign_up_with_otp(
            phone_number=phone, verification_token=token, password="TestPass123!",
        )

    if not result.success:
        print(f"❌ {action} FAIL: {result.error_code} - {result.error}")
        sys.exit(1)

    print(f"\n✅ 完整链路通过! ({action})")
    print(f"  user_info: {result.data.get('user_info')}")
    save_state({})


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    send = sub.add_parser("send", help="发验证码")
    send.add_argument("--phone", default="13880917374")
    v = sub.add_parser("verify", help="验证码 + 登录/注册")
    v.add_argument("--code", required=True)
    v.add_argument("--phone", help="覆盖 phone (默认用 send 时的)")
    args = p.parse_args()

    if args.cmd == "send":
        cmd_send(args)
    elif args.cmd == "verify":
        if args.phone:
            st = load_state()
            st["phone"] = args.phone
            save_state(st)
        cmd_verify(args)


if __name__ == "__main__":
    main()
