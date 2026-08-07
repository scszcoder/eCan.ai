#!/usr/bin/env python3
"""
TCB 云函数部署和 WebSocket 触发器配置脚本

使用方式:
    python3 scripts/setup-tcb-websocket.py          # 完整流程
    python3 scripts/setup-tcb-websocket.py --status   # 检查状态
    python3 scripts/setup-tcb-websocket.py --deploy   # 仅部署云函数

前置条件:
    - TCB CLI 已登录 (tcb login)
    - npm 已安装
"""

import json
import os
import sys
import argparse
import subprocess
import shutil
from pathlib import Path
from typing import Optional, List

# ============================================================================
# 配置
# ============================================================================

SCRIPT_DIR = Path(__file__).parent.resolve()
CLOUDBASE_DIR = SCRIPT_DIR.parent
DEFAULT_ENV_ID = "sccb0-d0gc5398xf028be6a"
DEFAULT_REGION = "ap-shanghai"

# ============================================================================
# 工具函数
# ============================================================================

def run_cmd(cmd: List[str], cwd: Optional[Path] = None, timeout: int = 300) -> tuple:
    """运行命令并返回 (returncode, stdout, stderr)"""
    print(f"  $ {' '.join(cmd[:5])}...")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, cwd=str(cwd) if cwd else None
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Timeout after {timeout}s"
    except Exception as e:
        return 1, "", str(e)


def check_login() -> bool:
    code, _, _ = run_cmd(["tcb", "env", "list"])
    return code == 0


def header(step: int, total: int, title: str):
    print(f"\n{'='*60}")
    print(f"[{step}/{total}] {title}")
    print('='*60)


def ok(msg): print(f"  ✅ {msg}")
def err(msg): print(f"  ❌ {msg}")
def warn(msg): print(f"  ⚠️  {msg}")
def info(msg): print(f"  ℹ️  {msg}")


# ============================================================================
# 部署云函数
# ============================================================================

def deploy_function(env_id: str, region: str, name: str, handler: str, timeout: int, ws: bool = False) -> bool:
    """部署单个云函数"""
    info(f"部署 {name} (ws={ws})")

    # 准备部署目录
    deploy_dir = CLOUDBASE_DIR / f".deploy_tmp/{name}"
    deploy_dir.mkdir(parents=True, exist_ok=True)

    # 复制文件
    for f in ["index.js", "websocket.js", "package.json", "package-lock.json"]:
        src = CLOUDBASE_DIR / f
        if src.exists():
            shutil.copy2(src, deploy_dir / f)

    # 复制 node_modules
    node_modules = CLOUDBASE_DIR / "node_modules"
    if node_modules.exists():
        info("复制 node_modules...")
        shutil.copytree(
            node_modules, deploy_dir / "node_modules",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".bin", "*.md", "*.txt", ".git*")
        )

    # 部署 - handler 从 cloudbaserc.json 读取,不需要 --handler 参数
    cmd = [
        "tcb", "fn", "deploy", name,
        "-e", env_id,
        "--dir", str(deploy_dir),
        "--timeout", str(timeout),
        "--force",
    ]
    if ws:
        cmd.append("--ws")
    else:
        cmd.append("--httpFn")

    code, stdout, stderr = run_cmd(cmd, cwd=deploy_dir, timeout=timeout + 120)

    if code == 0:
        ok(f"{name} 部署成功")
        return True
    else:
        err(f"{name} 部署失败: {stderr[:200]}")
        return False


def deploy_all(env_id: str, region: str) -> bool:
    """部署所有云函数"""
    header(1, 3, "部署云函数")

    if not check_login():
        err("TCB CLI 未登录,请先执行: tcb login")
        return False

    funcs = [
        ("ecan-graphql-api", "index.main", 60, False),  # (name, handler, timeout, is_websocket)
        ("ecan-websocket", "websocket.main", 300, True),
    ]

    success = True
    for name, handler, timeout, is_ws in funcs:
        if not deploy_function(env_id, region, name, handler, timeout, is_ws):
            success = False
            warn(f"{name} 部署失败,继续...")

    return success


# ============================================================================
# 配置 HTTP 触发器
# ============================================================================

def setup_http(env_id: str) -> bool:
    """配置 HTTP 触发器"""
    header(2, 3, "配置 HTTP 触发器")

    code, stdout, stderr = run_cmd([
        "tcb", "fn", "trigger", "create", "ecan-graphql-api",
        "-e", env_id,
        "--trigger-name", "http-trigger",
        "--type", "http",
        "--method", "GET,POST",
        "--path", "/graphql",
    ])

    if code == 0:
        ok("HTTP 触发器配置成功")
    elif "already" in stderr or "已存在" in stderr:
        info("HTTP 触发器已存在")
    else:
        warn(f"HTTP 触发器配置: {stderr[:150]}")
    return True


# ============================================================================
# 配置 WebSocket 触发器
# ============================================================================

def setup_websocket(env_id: str, region: str) -> bool:
    """配置 WebSocket 触发器"""
    header(3, 3, "配置 WebSocket 触发器")

    info("WebSocket 触发器需要通过 TCB 控制台手动配置")
    print()
    info("请在 TCB 控制台完成以下操作:")
    print()
    print("  1. 进入 API 网关控制台")
    print("     https://console.cloud.tencent.com/apigateway")
    print()
    print("  2. 创建或选择 API 网关服务")
    print()
    print("  3. 创建 WebSocket API:")
    print(f"     - 路径: /ws")
    print(f"     - 云函数: ecan-websocket")
    print("     - 协议: WEBSOCKET")
    print("     - 认证: 无")
    print()
    print("  4. 发布 API")
    print()
    print(f"  控制台链接: https://console.cloud.tencent.com/tcb/scf/index?envId={env_id}&region={region}")
    print()

    # 尝试部署 WebSocket 函数
    info("尝试部署 ecan-websocket 函数...")
    deploy_function(env_id, region, "ecan-websocket", "websocket.main", 300)

    return True


# ============================================================================
# 状态检查
# ============================================================================

def check_status(env_id: str, region: str):
    """检查云函数状态"""
    print(f"\n{'='*60}")
    print(f"[状态检查] 环境: {env_id} / {region}")
    print('='*60)

    if not check_login():
        err("TCB CLI 未登录")
        return

    # 云函数列表
    info("云函数列表:")
    code, stdout, _ = run_cmd([
        "tcb", "api", "scf", "ListFunctions",
        "-e", env_id,
        "--body", '{"Namespace":"default"}',
        "--json",
    ])

    if code == 0:
        try:
            # 解析 JSON (可能有前缀)
            resp = json.loads(stdout)
            if "data" in resp:
                resp = resp["data"]
            funcs = resp.get("Response", {}).get("Functions", [])
            print(f"  共 {len(funcs)} 个:")
            for f in funcs:
                print(f"    - {f.get('FunctionName')} ({f.get('Runtime')}) - {f.get('Status')}")
        except:
            print(f"  解析失败: {stdout[:200]}")
    else:
        err(f"无法获取云函数列表")

    # GraphQL HTTP 测试
    print()
    info("GraphQL HTTP 端点:")
    code, stdout, _ = run_cmd([
        "curl", "-s", "-X", "POST",
        f"https://{env_id}.service.tcloudbase.com/api/graphql",
        "-H", "Content-Type: application/json",
        "-d", '{"query":"{ __typename }"}',
        "--max-time", "10",
    ])

    if "UNAUTHENTICATED" in stdout or "errors" in stdout:
        ok("可访问 (需要认证)")
    elif "FUNCTIONS_INVOCATION_FAILED" in stdout:
        err("函数执行失败 (检查环境变量配置)")
    elif code != 0:
        err("不可用")
    else:
        info(f"响应: {stdout[:100]}")

    # WebSocket 测试
    print()
    info("WebSocket 端点:")
    code, stdout, _ = run_cmd([
        "python3", "-c",
        f"import asyncio; import websockets; "
        f"async def t(): "
        f"  async with websockets.connect('wss://{env_id}.service.tcloudbase.com/ws', ping_interval=None) as ws: "
        f"    return 'OK'; "
        f"asyncio.run(t())"
    ])

    if "OK" in stdout:
        ok("可访问")
    else:
        err("不可用 (WebSocket 触发器可能未配置)")

    # 检查需要的环境变量
    print()
    info("需要配置的环境变量 (在 TCB 控制台):")
    print(f"  ecan-graphql-api:")
    print(f"    - DATABASE_URL: PostgreSQL 连接字符串")
    print(f"  ecan-websocket:")
    print(f"    - WEBSOCKET_PUSH_SECRET: HMAC 密钥")
    print()
    print(f"  控制台: https://console.cloud.tencent.com/tcb/scf/index?envId={env_id}&region={region}")


# ============================================================================
# 主流程
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="TCB 云函数部署和 WebSocket 配置")
    parser.add_argument("-e", "--env-id", default=DEFAULT_ENV_ID, help="TCB 环境 ID")
    parser.add_argument("-r", "--region", default=DEFAULT_REGION, help="区域")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--status", action="store_true", help="检查状态")
    group.add_argument("--deploy", action="store_true", help="仅部署")
    group.add_argument("--http", action="store_true", help="仅配置 HTTP")
    group.add_argument("--websocket", action="store_true", help="仅配置 WebSocket")
    args = parser.parse_args()

    env_id, region = args.env_id, args.region

    print(f"\n{'#'*60}")
    print(f"# TCB 云函数部署和 WebSocket 配置")
    print(f"# 环境: {env_id} / {region}")
    print(f"{'#'*60}")

    if args.status:
        check_status(env_id, region)
    elif args.deploy:
        deploy_all(env_id, region)
    elif args.http:
        setup_http(env_id)
    elif args.websocket:
        setup_websocket(env_id, region)
    else:
        # 完整流程
        deploy_all(env_id, region)
        setup_http(env_id)
        setup_websocket(env_id, region)
        print(f"\n{'#'*60}")
        print("✅ 完成!")
        print(f"WebSocket: wss://{env_id}.service.tcloudbase.com/ws")
        print(f"\n检查状态: python3 scripts/setup-tcb-websocket.py --status")


if __name__ == "__main__":
    main()
