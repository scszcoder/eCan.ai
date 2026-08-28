#!/usr/bin/env python3
"""
CloudBase 微信扫码登录 API 测试脚本
用于验证 CloudBase 配置和扫码登录 API 是否正常工作
"""

import sys
import os
from pathlib import Path

# 计算项目根目录 (tests/integration/auth -> 项目根目录，需要向上4层)
_script_path = Path(__file__).resolve()
_project_root = _script_path
for _ in range(4):
    _project_root = _project_root.parent
sys.path.insert(0, str(_project_root))
os.chdir(_project_root)

import yaml


def load_auth_config():
    """直接加载 auth_config.yml"""
    config_path = _project_root / 'apps' / 'cn' / 'config' / 'auth_config.yml'

    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}


def test_cloudbase_config():
    """测试 CloudBase 配置"""
    print("=" * 60)
    print("测试 CloudBase 配置")
    print("=" * 60)

    config = load_auth_config()
    cloudbase_cfg = config.get('CLOUDBASE', {})
    wechat_cfg = config.get('WECHAT', {})

    env_id = cloudbase_cfg.get('ENV_ID', '')
    wechat_app_id = wechat_cfg.get('APP_ID', '')

    print(f"env_id: {env_id or '(未配置)'}")
    print(f"region: {cloudbase_cfg.get('REGION', 'ap-shanghai')}")
    print(f"wechat_app_id: {wechat_app_id or '(未配置)'}")
    print(f"enable_wechat_login: {cloudbase_cfg.get('ENABLE_WECHAT_LOGIN', True)}")
    print()

    if not env_id:
        print("❌ CloudBase 未配置 (env_id 为空)")
        return False

    if not wechat_app_id:
        print("⚠️  微信登录未配置 (wechat_app_id 为空)")
        print("   请在 CloudBase 控制台配置微信登录")
        return False

    print("✓ CloudBase 配置检查通过")
    return True, env_id


def test_get_qrcode(env_id: str):
    """测试获取微信二维码"""
    print("=" * 60)
    print("测试获取微信登录二维码")
    print("=" * 60)

    try:
        from auth.tencent.cloudbase_auth import CloudBaseAuthService
        from auth.tencent.cloudbase_config import CloudBaseConfig

        config = CloudBaseConfig(
            env_id=env_id,
            wechat_app_id=load_auth_config().get('WECHAT', {}).get('APP_ID', ''),
            enable_wechat_login=True,
        )
        service = CloudBaseAuthService(config=config)
        result = service.get_wechat_qrcode_link()

        if result.success:
            print(f"✓ 成功获取二维码")
            uri = result.data.get('uri', '')
            session_id = result.data.get('session_id', '')
            print(f"  session_id: {session_id}")
            if len(uri) > 80:
                print(f"  uri: {uri[:80]}...")
            else:
                print(f"  uri: {uri}")
            print(f"  expires_in: {result.data.get('expires_in')}s")
            print(f"\n📱 二维码内容: {uri}")
            print(f"   (请用二维码生成工具生成二维码，或直接在浏览器打开此链接)")
            return True, uri
        else:
            print(f"❌ 获取二维码失败")
            print(f"  error: {result.error}")
            print(f"  error_code: {result.error_code}")
            return False, None

    except Exception as e:
        print(f"❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def test_poll_qrcode(uri: str):
    """测试轮询二维码状态"""
    print("=" * 60)
    print(f"测试轮询二维码状态")
    print("=" * 60)

    if not uri:
        print("⚠️  无 uri，跳过轮询测试")
        return

    print("微信扫码登录使用 OAuth 回调模式：")
    print(f"1. 打开授权链接: {uri[:60]}...")
    print("2. 用微信扫码授权")
    print("3. 微信回调带 code")
    print("4. 用 code 调用 sign_in_with_wechat_qrcode() 完成登录")
    print("\n注意：实际使用时后端应启动本地服务器捕获回调")


def main():
    print("\n🔍 CloudBase 微信扫码登录 API 测试\n")

    # 测试 1: 配置检查
    result = test_cloudbase_config()
    if not result:
        print("\n请先配置 CloudBase 环境变量后重试")
        sys.exit(1)

    _, env_id = result

    # 测试 2: 获取二维码
    success, uri = test_get_qrcode(env_id)

    if success:
        # 测试 3: 显示扫码说明
        test_poll_qrcode(uri)

        print("\n" + "=" * 60)
        print("✅ API 调用测试通过!")
        print("=" * 60)
        print("\n📱 请打开下方链接进行实际扫码测试：")
        print(f"\n{uri}")
    else:
        print("\n❌ 测试失败，请检查 CloudBase 配置")


if __name__ == "__main__":
    main()
