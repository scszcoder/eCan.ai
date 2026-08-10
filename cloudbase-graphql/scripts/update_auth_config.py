#!/usr/bin/env python3
"""
回写 CloudBase 部署后的端点信息到 auth_config.yml

使用方式:
    python3 scripts/update_auth_config.py

部署成功后调用,将以下端点写入 apps/cn/config/auth_config.yml:
    - GRAPHQL_ENDPOINT  (GraphQL HTTP)
    - WS_ENDPOINT       (WebSocket 实时推送; graphql-ws / AppSync 兼容)

WS_ENDPOINT 指向 TCB 云托管 (TCS) 中部署的 ecan-graphql-ws 服务。
"""

import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
while os.path.basename(PROJECT_ROOT) != "eCan.ai" and os.path.dirname(PROJECT_ROOT) != PROJECT_ROOT:
    PROJECT_ROOT = os.path.dirname(PROJECT_ROOT)
AUTH_CONFIG_PATH = os.path.join(PROJECT_ROOT, "apps", "cn", "config", "auth_config.yml")


def load_env():
    """从 .env.local 加载 TCB 配置(与 deploy.sh 同目录)"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(script_dir, "..", ".env.local")
    env_path = os.path.normpath(env_path)

    if not os.path.exists(env_path):
        print(f"[update_auth_config] .env.local not found at {env_path}")
        return {
            "TCB_ENV_ID": os.getenv("TCB_ENV_ID", ""),
            "TCB_REGION": os.getenv("TCB_REGION", "ap-shanghai"),
            "GRAPHQL_ENDPOINT": os.getenv("GRAPHQL_ENDPOINT", ""),
            "WS_ENDPOINT": os.getenv("WS_ENDPOINT", ""),
            "WS_TCS_URL": os.getenv("WS_TCS_URL", ""),
        }

    env = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()
    return env


def build_endpoints(env: dict) -> dict:
    """根据 env_id 和 region 构建标准 TCB 端点

    CN realtime 是自建 WebSocket 服务 — 部署在 TCB 云托管 (TCS) 中,
    由 ecan-graphql-ws 容器服务提供,走 graphql-ws / AppSync 兼容协议.
    """
    env_id = env.get("TCB_ENV_ID", "").strip()
    region = env.get("TCB_REGION", "ap-shanghai").strip()

    if not env_id:
        print("[update_auth_config] TCB_ENV_ID is empty, cannot build endpoints")
        return {}

    # WS_ENDPOINT: 优先使用 .env.local 中的 WS_ENDPOINT (CBR 直接域名)
    # 或从 WS_TCS_URL (TCS 部署后返回的访问地址) 转换而来
    ws = env.get("WS_ENDPOINT", "").strip()
    ws_tcs = env.get("WS_TCS_URL", "").strip()
    if not ws and ws_tcs:
        # WS_TCS_URL 是完整的 https://... URL，转换为 wss://
        if ws_tcs.startswith("https://"):
            ws = ws_tcs.replace("https://", "wss://")
        elif ws_tcs.startswith("http://"):
            ws = ws_tcs.replace("http://", "wss://")
        else:
            ws = "wss://" + ws_tcs

    # 如果环境变量中没有指定,则根据 env_id 推导
    if not graphql:
        graphql = f"https://{env_id}.service.tcloudbase.com/api/graphql"
    # WS_ENDPOINT 必须由 TCS 部署后回写,无法自动推导

    result = {"GRAPHQL_ENDPOINT": graphql}
    if ws:
        result["WS_ENDPOINT"] = ws
    return result


def update_yaml_field(content: str, field: str, value: str) -> str:
    """将 content 中指定 field 的值替换为 value,保留注释和格式"""
    pattern = rf'^(\s*{re.escape(field)}:\s*)["\']?[^\"\'#\n]*["\']?\s*(#.*)?$'
    replacement = rf'\1"{value}"'
    result, count = re.subn(pattern, replacement, content, flags=re.MULTILINE)
    if count == 0:
        print(f"[update_auth_config] Field '{field}' not found in auth_config.yml, skipping")
        return content
    return result


def update_auth_config(endpoints: dict):
    """将端点信息写入 auth_config.yml"""
    if not endpoints:
        print("[update_auth_config] No endpoints to write")
        return False

    if not os.path.exists(AUTH_CONFIG_PATH):
        print(f"[update_auth_config] auth_config.yml not found at {AUTH_CONFIG_PATH}")
        return False

    with open(AUTH_CONFIG_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    original = content
    for field, value in endpoints.items():
        content = update_yaml_field(content, field, value)
        if value != original:
            print(f"[update_auth_config] Updated {field}: {value}")

    if content == original:
        print("[update_auth_config] No changes made to auth_config.yml")
        return False

    with open(AUTH_CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[update_auth_config] auth_config.yml updated successfully")
    return True


def main():
    print("=" * 60)
    print("  eCan.ai - Update auth_config.yml with deployed endpoints")
    print("=" * 60)

    env = load_env()
    if not env.get("TCB_ENV_ID"):
        print("[update_auth_config] TCB_ENV_ID is required but not found")
        print("  Set it in .env.local or as an environment variable")
        sys.exit(1)

    print(f"  TCB_ENV_ID: {env.get('TCB_ENV_ID')}")
    print(f"  TCB_REGION: {env.get('TCB_REGION', 'ap-shanghai')}")
    print()

    endpoints = build_endpoints(env)
    for name, url in endpoints.items():
        print(f"  {name}: {url}")
    print()

    success = update_auth_config(endpoints)
    if success:
        print()
        print("Done! Deploy endpoints have been written to auth_config.yml.")
    else:
        print()
        print("No changes made (endpoints may already be up to date)")
        sys.exit(1)


if __name__ == "__main__":
    main()
