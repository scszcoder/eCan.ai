#!/usr/bin/env python3
"""
ecan-websocket WebSocket 触发器补全脚本 (dry-run)

背景:
    当前 ecan-websocket 部署为 Event 类型 (ProtocolType=""), 不支持 WebSocket 长连接.
    必须通过以下 5 步切换到真正的 WS 函数:

      1. 备份现有函数 (环境变量 + 代码)
      2. 删除现有函数 (SCF 不支持原地改 ProtocolType, 必须重建)
      3. 重新部署为 WS 类型: tcb fn deploy ecan-websocket --ws --force
      4. 创建 API Gateway WebSocket API (指向 ecan-websocket)
      5. 给 ecan-websocket 挂 apigw 触发器

使用方式:
    # 仅检查当前状态 (推荐先跑)
    python3 scripts/ws-trigger-setup.py --status

    # Dry-run: 打印会执行的命令, 但不执行破坏性操作
    python3 scripts/ws-trigger-setup.py --dry-run

    # 实际执行 (会删除并重建函数!)
    python3 scripts/ws-trigger-setup.py --apply

前置条件:
    - tcb CLI 已登录 (tcb login)
    - 已安装 Python 3.7+
"""

import json
import os
import sys
import argparse
import subprocess
from pathlib import Path
from typing import Optional, List, Tuple

# ============================================================================
# 配置
# ============================================================================

SCRIPT_DIR = Path(__file__).parent.resolve()
CLOUDBASE_DIR = SCRIPT_DIR.parent

ENV_ID = "sccb0-d0gc5398xf028be6a"
REGION = "ap-shanghai"

WS_FUNCTION = "ecan-websocket"
GRAPHQL_FUNCTION = "ecan-graphql-api"
WS_DOMAIN = f"{ENV_ID}.service.tcloudbase.com"
WS_PATH = "/ws"
WS_ENDPOINT = f"wss://{WS_DOMAIN}{WS_PATH}"


# ============================================================================
# 工具函数
# ============================================================================

def run(cmd: List[str], dry_run: bool = False, check: bool = True) -> Tuple[int, str, str]:
    """执行命令, dry_run 模式下只打印"""
    print(f"  $ {' '.join(cmd)}")
    if dry_run:
        return 0, "", "(dry-run, not executed)"
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if check and result.returncode != 0:
        print(f"    ✖ exit={result.returncode}")
        if result.stderr:
            print(f"    stderr: {result.stderr[:200]}")
    return result.returncode, result.stdout, result.stderr


def parse_json_output(stdout: str) -> dict:
    """从 tcb api 的输出中提取 JSON. tcb cli 会先打印 'ℹ → SERVICE.Action' 一行,
    然后才是 JSON. JSON 也可能被包装成 {"data": {...}, "requestId": "..."}.

    返回 {"data": ..., "requestId": ...} 形式 (如果有外层包装, 解包到第一层).
    """
    # 找第一个 { 或 [
    s = stdout.strip()
    for i, ch in enumerate(s):
        if ch in "{[":
            s = s[i:]
            break
    return json.loads(s)


def header(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def ok(msg: str):
    print(f"  ✅ {msg}")


def warn(msg: str):
    print(f"  ⚠️  {msg}")


def err(msg: str):
    print(f"  ❌ {msg}")


# ============================================================================
# 检查当前状态
# ============================================================================

def check_status():
    """查询并打印 ecan-websocket 当前状态"""
    header(f"[Status] 当前 {WS_FUNCTION} 状态")

    code, stdout, _ = run([
        "tcb", "api", "scf", "GetFunction", "--json",
        "--body", json.dumps({
            "FunctionName": WS_FUNCTION,
            "Namespace": ENV_ID,
        })
    ], check=False)

    if code != 0:
        err(f"无法获取函数信息: {stdout}")
        return

    resp = parse_json_output(stdout)
    func = resp.get("data", resp)
    proto = func.get("ProtocolType", "")
    ftype = func.get("Type", "")
    status = func.get("Status", "")
    pub_net = func.get("PublicNetConfig", {}) or func.get("EipConfig", {}) or {}
    eip_status = pub_net.get("PublicNetStatus") or pub_net.get("EipStatus")
    eips = pub_net.get("Eips", [])
    eip_display = eip_status or (", ".join(eips) if eips else "-")

    print(f"  FunctionName : {func.get('FunctionName')}")
    print(f"  Type         : {ftype}")
    print(f"  ProtocolType : '{proto}' {'✅ 是 WS' if proto == 'WS' else '❌ 不是 WS (HTTP only)'}")
    print(f"  Status       : {status}")
    print(f"  EIP          : {eip_display}")

    # 触发器
    code, stdout, _ = run([
        "tcb", "api", "scf", "ListTriggers", "--json",
        "--body", json.dumps({
            "FunctionName": WS_FUNCTION,
            "Namespace": ENV_ID,
        })
    ], check=False)

    if code == 0:
        trig = parse_json_output(stdout)
        trig = trig.get("data", trig)
        print(f"  Triggers     : {trig.get('TotalCount', 0)} 个")
        for t in trig.get("Triggers", []):
            print(f"                  - {t.get('TriggerName')} (Type={t.get('Type')}, Enable={t.get('Enable')})")

    # 环境变量
    print(f"\n  当前环境变量:")
    vars_list = (func.get("Environment", {}) or {}).get("Variables", []) or []
    for v in vars_list:
        k = v.get("Key", "")
        val = v.get("Value", "")
        # 隐藏敏感值
        display = val if "SECRET" not in k.upper() and "PASSWORD" not in k.upper() else ("***" + val[-4:] if len(val) > 4 else "***")
        print(f"    {k} = {display}")

    # 路由
    code, stdout, _ = run([
        "tcb", "routes", "list", "-e", ENV_ID, "-r", REGION,
    ], check=False)

    if code == 0:
        print(f"\n  当前 TCB 路由 (domain: {WS_DOMAIN}):")
        in_domain = False
        for line in stdout.splitlines():
            if WS_DOMAIN in line:
                in_domain = True
            if in_domain and "/ws" in line:
                # 简化打印
                cols = [c.strip() for c in line.split("│") if c.strip()]
                if len(cols) >= 5:
                    print(f"    {cols[1]} → {cols[4]} ({cols[5] if len(cols) > 5 else ''})")
            if in_domain and "ap-shanghai.app.tcloudbase.com" in line:
                in_domain = False  # 切到旧域名, 停止

    # 总结
    header("诊断结论")
    if proto == "WS":
        ok(f"{WS_FUNCTION} 已经是 WebSocket 函数")
    else:
        warn(f"{WS_FUNCTION} 当前为 {ftype} 类型, ProtocolType='{proto}'")
        print("""
    含义: 客户端连 wss://.../ws 时, 网关把它当 HTTP 转发给 SCF,
          SCF 收到 event.action=undefined, 走 websocket.js default 分支返回 400.

    修复: 重新部署为 --ws 类型 + 创建 API Gateway WebSocket API + 挂触发器.
    """)


# ============================================================================
# 备份 / 恢复
# ============================================================================

def backup_function_state(dry_run: bool) -> dict:
    """备份现有函数的环境变量和元数据"""
    header("[1/5] 备份当前函数状态")

    if dry_run:
        # dry-run 模式下仍要打印会备份哪些内容, 但允许命令跑 (GetFunction 只读安全)
        print("  (dry-run: 以下为预演, 备份到磁盘这一步不会真执行)")
    code, stdout, _ = run([
        "tcb", "api", "scf", "GetFunction", "--json",
        "--body", json.dumps({
            "FunctionName": WS_FUNCTION,
            "Namespace": ENV_ID,
        })
    ], dry_run=False, check=False)  # 强制真实调用, dry-run 也要看到当前数据

    if code != 0:
        print(f"  ✖ 无法获取函数信息")
        return {}

    try:
        resp = parse_json_output(stdout)
        func = resp.get("data", resp)
    except Exception:
        func = {}

    env_vars = {v["Key"]: v["Value"] for v in func.get("Environment", {}).get("Variables", [])}
    backup = {
        "FunctionName": func.get("FunctionName"),
        "Description": func.get("Description", ""),
        "MemorySize": func.get("MemorySize"),
        "Timeout": func.get("Timeout"),
        "Runtime": func.get("Runtime"),
        "Handler": func.get("Handler"),
        "Environment": env_vars,
        "VpcConfig": func.get("VpcConfig", {}),
        "EipConfig": func.get("EipConfig", {}),
    }

    if dry_run:
        print(f"  (dry-run) 将保存到 {WS_FUNCTION}.bak.json:")
        # 隐藏敏感值
        display_backup = json.loads(json.dumps(backup))
        for k in list(display_backup.get("Environment", {}).keys()):
            if "SECRET" in k.upper() or "PASSWORD" in k.upper():
                v = display_backup["Environment"][k]
                display_backup["Environment"][k] = f"***{v[-4:] if len(v) > 4 else '***'}"
        print(json.dumps(display_backup, indent=2, ensure_ascii=False))
        return backup

    backup_file = CLOUDBASE_DIR / f"{WS_FUNCTION}.bak.json"
    backup_file.write_text(json.dumps(backup, indent=2))
    ok(f"备份已写入 {backup_file}")
    return backup


# ============================================================================
# Step 2: 删除函数
# ============================================================================

def delete_function(dry_run: bool):
    """删除现有函数 (SCF 不支持改 ProtocolType, 必须重建)"""
    header("[2/5] 删除现有函数")

    warn("此操作会删除 ecan-websocket, 现有连接会断开!")

    code, _, _ = run([
        "tcb", "fn", "delete", WS_FUNCTION,
        "-e", ENV_ID, "-r", REGION, "--force",
    ], dry_run, check=False)

    if code == 0 or dry_run:
        ok(f"删除 {WS_FUNCTION} 成功" if not dry_run else f"(dry-run) 将删除 {WS_FUNCTION}")
    else:
        err(f"删除失败")


# ============================================================================
# Step 3: 重新部署为 WS 类型
# ============================================================================

def redeploy_as_ws(dry_run: bool):
    """用 --ws 重新部署"""
    header("[3/5] 重新部署为 WebSocket 函数")

    deploy_dir = CLOUDBASE_DIR / "functions" / WS_FUNCTION

    cmd = [
        "tcb", "fn", "deploy", WS_FUNCTION,
        "-e", ENV_ID, "-r", REGION,
        "--dir", str(deploy_dir),
        "--force",
        "--ws",  # 关键: 声明这是 WebSocket 函数
    ]
    code, _, _ = run(cmd, dry_run, check=False)

    if code == 0 or dry_run:
        ok(f"重新部署 {WS_FUNCTION} (ProtocolType=WS)" if not dry_run else f"(dry-run) 将以 --ws 部署")


def restore_env_vars(dry_run: bool, backup: dict):
    """恢复环境变量 (部署 --ws 后会自动同步 cloudbaserc.json 中的, 但 WEBSOCKET_PUSH_SECRET 可能丢失)"""
    header("[3.5/5] 恢复敏感环境变量")

    env_vars = backup.get("Environment", {}) if backup else {}
    # cloudbaserc.json 里已有的 (会被 --ws 部署自动同步), 不需要手工恢复
    managed = {"NODE_ENV", "TCB_REGION", "COS_REGION", "COS_BUCKET"}
    to_restore = {k: v for k, v in env_vars.items() if k not in managed}

    if not to_restore:
        print("  没有需要手工恢复的环境变量 (cloudbaserc.json 已覆盖全部受管项).")
        return

    print(f"  将恢复 {len(to_restore)} 个非受管环境变量:")
    for key, value in to_restore.items():
        is_sensitive = "SECRET" in key.upper() or "PASSWORD" in key.upper()
        display_value = f"***{value[-4:] if len(value) > 4 else '***'}" if is_sensitive else value
        print(f"    {key} = {display_value}")

        if dry_run:
            continue

        cmd = [
            "tcb", "env", "update", WS_FUNCTION,
            "-e", ENV_ID,
        ]
        env_key = key.lower().replace("_", "-")
        cmd += [f"--{env_key}", value]
        code, _, _ = run(cmd, check=False)
        if code != 0:
            err(f"恢复 {key} 失败")


# ============================================================================
# Step 4 & 5: API Gateway WebSocket API + SCF 触发器
# ============================================================================

def create_apigw_websocket(dry_run: bool) -> Optional[str]:
    """创建 API Gateway WebSocket API. 返回 ServiceId 和 ApiId (若 dry-run 返回 None)"""
    header("[4/5] 创建 API Gateway WebSocket API")

    warn("此步通过腾讯云 API 网关服务创建独立的 WebSocket API.")
    print("""
    ⚠️  注意: 这是另一套网关系统 (apigateway), 与 TCB 自带网关 (service.tcloudbase.com) 不同.
        创建后会得到形如 service-xxxxxx-xxxx.gz.apigw.tencentcs.com 的域名.
        需要客户端代码额外连接这个新域名, 而非 wss://...service.tcloudbase.com/ws.

        如果想让原 wss://...service.tcloudbase.com/ws 也能通 WS,
        还需要在 TCB 控制台创建 WS API 后端 (这条路径 tcb CLI 不直接支持,
        只能用 API Gateway 手动创建, 或使用腾讯云 API 网关控制台).

        本脚本采用: 创建 API Gateway WS API + 给函数挂 apigw 触发器.
        客户端 WS 连接地址会变为新的独立域名 (脚本结束时打印).
    """)

    if dry_run:
        print("  (dry-run) 将执行以下 API 调用:\n")

        print("  [4a] CreateService:")
        print(json.dumps({
            "ServiceName": f"ecan-ws-{ENV_ID[:8]}",
            "Protocol": "WEBSOCKET",
            "ServiceDesc": "eCan WebSocket Service",
            "Region": REGION,
        }, indent=4))
        print()

        print("  [4b] CreateApi:")
        print(json.dumps({
            "ServiceId": "<from 4a>",
            "ApiName": "ecan-ws-handler",
            "Protocol": "WEBSOCKET",
            "Path": WS_PATH,
            "Method": "ANY",
            "ServiceTimeout": 60,
            "ServiceType": "SCF",
            "ServiceConfig": json.dumps({
                "ScfFunctionName": WS_FUNCTION,
                "ScfFunctionNamespace": ENV_ID,
                "IsIntegratedResponse": "FALSE",
            }, indent=2),
            "Region": REGION,
        }, indent=4))
        print()

        print("  [4c] ReleaseService: 把 API 网关服务发布到 release 环境.")
        return None

    # Step 4a: Create service
    code, stdout, _ = run([
        "tcb", "api", "apigateway", "CreateService", "--json",
        "--body", json.dumps({
            "ServiceName": f"ecan-ws-{ENV_ID[:8]}",
            "Protocol": "WEBSOCKET",
            "ServiceDesc": "eCan WebSocket Service",
            "Region": REGION,
        })
    ], check=False)

    if code != 0:
        err("CreateService 失败")
        return None
    service_resp = parse_json_output(stdout)
    service_resp = service_resp.get("data", service_resp)
    service_id = service_resp.get("ServiceId")
    ok(f"ServiceId = {service_id}")

    # Step 4b: Create WebSocket API
    code, stdout, _ = run([
        "tcb", "api", "apigateway", "CreateApi", "--json",
        "--body", json.dumps({
            "ServiceId": service_id,
            "ApiName": "ecan-ws-handler",
            "ApiDesc": "eCan WebSocket Handler",
            "Protocol": "WEBSOCKET",
            "Path": "/ws",
            "Method": "ANY",
            "ServiceTimeout": 60,
            "ServiceType": "SCF",
            "ServiceConfig": json.dumps({
                "ScfFunctionName": WS_FUNCTION,
                "ScfFunctionNamespace": ENV_ID,
                "IsIntegratedResponse": "FALSE",
            }),
            "Region": REGION,
        })
    ], check=False)

    if code != 0:
        err("CreateApi 失败")
        return None
    api_resp = parse_json_output(stdout)
    api_resp = api_resp.get("data", api_resp)
    api_id = api_resp.get("ApiId")
    ok(f"ApiId = {api_id}")

    # Step 4c: 发布服务到环境
    code, _, _ = run([
        "tcb", "api", "apigateway", "ReleaseService", "--json",
        "--body", json.dumps({
            "ServiceId": service_id,
            "EnvironmentName": "release",
            "Region": REGION,
        })
    ], check=False)

    if code == 0:
        ok("ReleaseService 成功")
    else:
        warn("ReleaseService 失败 (可手动在控制台发布)")

    return f"{service_id}:{api_id}"


def create_scf_trigger(dry_run: bool, apigw_ref: Optional[str]):
    """为 ecan-websocket 创建 SCF apigw 触发器"""
    header("[5/5] 创建 SCF 触发器 (Type=apigw)")

    if not apigw_ref and not dry_run:
        err("缺少 API Gateway serviceId:apiId")
        return

    if dry_run:
        trigger_desc = {
            "ServiceId": "<serviceId from step 4>",
            "ApiId": "<apiId from step 4>",
            "Region": REGION,
            "ServiceTimeout": 60,
        }
        print(f"  (dry-run) 将创建触发器:")
        print(json.dumps({
            "FunctionName": WS_FUNCTION,
            "Namespace": ENV_ID,
            "TriggerName": "ws-apigw-trigger",
            "Type": "apigw",
            "TriggerDesc": json.dumps(trigger_desc),
        }, indent=2))
        return

    service_id, api_id = apigw_ref.split(":")
    trigger_desc = {
        "ServiceId": service_id,
        "ApiId": api_id,
        "Region": REGION,
        "ServiceTimeout": 60,
    }
    code, _, _ = run([
        "tcb", "api", "scf", "CreateTrigger",
        "--body", json.dumps({
            "FunctionName": WS_FUNCTION,
            "Namespace": ENV_ID,
            "TriggerName": "ws-apigw-trigger",
            "Type": "apigw",
            "TriggerDesc": json.dumps(trigger_desc),
            "Enable": "OPEN",
        })
    ], check=False)

    if code == 0:
        ok("触发器创建成功")


# ============================================================================
# 路由调整
# ============================================================================

def adjust_routes(dry_run: bool):
    """提示删除 /ws 的 HTTP 路由, 避免双协议冲突"""
    header("[Bonus] 路由调整 (可选)")

    print(f"""
  当前的 TCB 路由 /ws 是 HTTP 触发, 会和新的 WebSocket API 冲突.
  建议删除 {WS_DOMAIN} 上的 /ws HTTP 路由, 保留 /ws/push 和 /ws/status (它们继续走 HTTP).

  命令 (dry-run 时不执行):
    tcb routes delete -e {ENV_ID} -r {REGION} \\
        {WS_DOMAIN} -p {WS_PATH}
""")
    if not dry_run:
        warn("请手动确认后执行上面的命令")


# ============================================================================
# 验证
# ============================================================================

def verify(dry_run: bool):
    """验证 WebSocket 连接"""
    header("[Verify] 测试 wss 连接")

    print(f"  端点: {WS_ENDPOINT}")
    if dry_run:
        print(f"  (dry-run) 将执行:")
        print(f'    python3 -c "import asyncio, websockets; '
              f'async def t(): async with websockets.connect(\\"{WS_ENDPOINT}\\", ping_interval=None) as ws: return \\"OK\\"; print(asyncio.run(t()))"')
    else:
        code, stdout, stderr = run([
            "python3", "-c",
            f"import asyncio, websockets; "
            f"async def t(): "
            f"  async with websockets.connect('{WS_ENDPOINT}', ping_interval=None) as ws: "
            f"    print(await ws.recv()); "
            f"asyncio.run(t())"
        ], check=False)
        if "OK" in stdout or "1009" in stdout:  # 1009 = normal close
            ok(f"WebSocket 可用: {stdout[:100]}")
        else:
            warn(f"WebSocket 未通: {stderr[:200]}")


# ============================================================================
# 主流程
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="ecan-websocket WebSocket 触发器补全脚本")
    parser.add_argument("--status", action="store_true", help="查询当前状态 (推荐先跑)")
    parser.add_argument("--dry-run", action="store_true", help="打印所有命令, 不执行")
    parser.add_argument("--apply", action="store_true", help="实际执行 (会删除并重建函数!)")
    args = parser.parse_args()

    if not any([args.status, args.dry_run, args.apply]):
        args.status = True  # 默认行为

    if args.status:
        check_status()
        print(f"\n💡 推荐先跑 `--dry-run` 预览计划, 确认后再 `--apply`.")
        return

    if args.dry_run:
        print("\n" + "="*60)
        print("  DRY-RUN MODE - 仅打印, 不实际执行")
        print("="*60)
        check_status()
        backup = backup_function_state(dry_run=True)
        delete_function(dry_run=True)
        redeploy_as_ws(dry_run=True)
        restore_env_vars(dry_run=True, backup=backup)
        apigw_ref = create_apigw_websocket(dry_run=True)
        create_scf_trigger(dry_run=True, apigw_ref=apigw_ref)
        adjust_routes(dry_run=True)
        verify(dry_run=True)
        print(f"\n✅ Dry-run 完成. 确认无误后跑 --apply.")
        return

    if args.apply:
        print("\n" + "!"*60)
        print("  APPLY MODE - 将修改生产环境!")
        print("!"*60)
        check_status()
        backup = backup_function_state(dry_run=False)
        delete_function(dry_run=False)
        redeploy_as_ws(dry_run=False)
        restore_env_vars(dry_run=False, backup=backup)
        apigw_ref = create_apigw_websocket(dry_run=False)
        create_scf_trigger(dry_run=False, apigw_ref=apigw_ref)
        adjust_routes(dry_run=False)
        verify(dry_run=False)
        print(f"\n✅ 完成. WebSocket 端点: {WS_ENDPOINT}")
        return


if __name__ == "__main__":
    main()