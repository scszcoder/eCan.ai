#!/usr/bin/env python3
"""
回写 CloudBase 部署后的端点信息到 auth_config.yml

使用方式:
    python3 scripts/update_auth_config.py

部署成功后调用,将以下端点写入 apps/cn/config/auth_config.yml:
    - GRAPHQL_ENDPOINT  (GraphQL HTTP)
    - SSE_ENDPOINT       (SSE 订阅; 与 Intl (AWS AppSync realtime) 对等)

端点格式基于 TCB_ENV_ID 和 TCB_REGION,遵循腾讯云云开发标准域名规则。
"""

import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
while os.path.basename(PROJECT_ROOT) != "eCan.ai" and os.path.dirname(PROJECT_ROOT) != PROJECT_ROOT:
    PROJECT_ROOT = os.path.dirname(PROJECT_ROOT)
# PROJECT_ROOT is now the eCan.ai repo root
AUTH_CONFIG_PATH = os.path.join(PROJECT_ROOT, "apps", "cn", "config", "auth_config.yml")


def load_env():
    """从 .env.local 加载 TCB 配置(与 deploy.sh 同目录)"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(script_dir, "..", ".env.local")
    env_path = os.path.normpath(env_path)

    if not os.path.exists(env_path):
        print(f"[update_auth_config] ⚠️  .env.local not found at {env_path}")
        # 从环境变量读取
        return {
            "TCB_ENV_ID": os.getenv("TCB_ENV_ID", ""),
            "TCB_REGION": os.getenv("TCB_REGION", "ap-shanghai"),
            "GRAPHQL_ENDPOINT": os.getenv("GRAPHQL_ENDPOINT", ""),
            "SSE_ENDPOINT": os.getenv("SSE_ENDPOINT", ""),
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

    CN realtime 是 SSE — 经由 `ecan-graphql-sse` 云函数走 HTTP /api/events。
    """
    env_id = env.get("TCB_ENV_ID", "").strip()
    region = env.get("TCB_REGION", "ap-shanghai").strip()

    if not env_id:
        print("[update_auth_config] ⚠️  TCB_ENV_ID is empty, cannot build endpoints")
        return {}

    # 优先使用 .env.local 中明确指定的端点
    graphql = env.get("GRAPHQL_ENDPOINT", "").strip()
    sse = env.get("SSE_ENDPOINT", "").strip()

    # 如果环境变量中没有指定,则根据 env_id 推导
    if not graphql:
        graphql = f"https://{env_id}.service.tcloudbase.com/api/graphql"
    if not sse:
        sse = f"https://{env_id}.service.tcloudbase.com/api/events"

    return {
        "GRAPHQL_ENDPOINT": graphql,
        "SSE_ENDPOINT": sse,
    }


def update_yaml_field(content: str, field: str, value: str) -> str:
    """将 content 中指定 field 的值替换为 value,保留注释和格式"""
    # 匹配 field: "xxx" 或 field: 'xxx' 或 field: xxx (无引号)
    # 使用 multi-line 模式,支持跨行 YAML
    pattern = rf'^(\s*{re.escape(field)}:\s*)["\']?[^\"\'#\n]*["\']?\s*(#.*)?$'
    replacement = rf'\1"{value}"'
    result, count = re.subn(pattern, replacement, content, flags=re.MULTILINE)
    if count == 0:
        print(f"[update_auth_config] ⚠️  Field '{field}' not found in auth_config.yml, skipping")
        return content
    return result


def update_auth_config(endpoints: dict):
    """将端点信息写入 auth_config.yml"""
    if not endpoints:
        print("[update_auth_config] ⚠️  No endpoints to write")
        return False

    if not os.path.exists(AUTH_CONFIG_PATH):
        print(f"[update_auth_config] ⚠️  auth_config.yml not found at {AUTH_CONFIG_PATH}")
        return False

    with open(AUTH_CONFIG_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    original = content
    for field, value in endpoints.items():
        content = update_yaml_field(content, field, value)
        if value != original:
            print(f"[update_auth_config] ✅ Updated {field}: {value}")

    if content == original:
        print("[update_auth_config] ⚠️  No changes made to auth_config.yml")
        return False

    with open(AUTH_CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[update_auth_config] ✅ auth_config.yml updated successfully")
    return True


def main():
    print("=" * 60)
    print("  eCan.ai — Update auth_config.yml with deployed endpoints")
    print("=" * 60)

    env = load_env()
    if not env.get("TCB_ENV_ID"):
        print("[update_auth_config] ❌ TCB_ENV_ID is required but not found")
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
        print("✅ Done! Deploy endpoints have been written to auth_config.yml.")
        print("   CN app will now use these endpoints directly from config.")
    else:
        print()
        print("⚠️  No changes made (endpoints may already be up to date)")
        sys.exit(1)


if __name__ == "__main__":
    main()
