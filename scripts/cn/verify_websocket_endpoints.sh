#!/usr/bin/env bash
# ============================================================
# eCan.ai · WS service smoke test (CN)
# ============================================================
#
# 用法:
#   ./scripts/cn/verify_websocket_endpoints.sh
#
# 检查项 (新拓扑: 独立 graphql-ws TCS 服务 + ws-bridge-push.js):
#   1. GET  {WS_TCS_URL}/healthz   → 返回 { status:'ok', service:'ecan-graphql-ws' }
#   2. POST {WS_TCS_URL}/publish   → 鉴权 + 跨实例推送 (X-WS-Push-Secret header)
#   3. WS end-to-end (graphql-ws subprotocol) → 客户端订阅 + 服务端 push + 收到 data frame
#
# 前提 (cloudbase-graphql/.env.local):
#   - WS_TCS_URL     # TCS cloudrun 服务地址 (http(s)://...), 由 bin/deploy-ws.sh 回写
#   - WS_PUSH_SECRET # SCF → WS 推送密钥
#
# 失败处理:
#   - 任一步骤返回非 200 → 退出码 1
#   - 打印完整响应体, 便于定位

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CB_ENV_FILE="$ROOT/cloudbase-graphql/.env.local"

if [[ ! -f "$CB_ENV_FILE" ]]; then
  echo -e "${RED}❌ $CB_ENV_FILE not found${NC}"
  exit 1
fi

# shellcheck disable=SC1090
set -a; source "$CB_ENV_FILE"; set +a

# WS endpoint: 独立 TCS cloudrun 服务, 由 bin/deploy-ws.sh 部署后写入 .env.local
# 注意: WS_TCS_URL 是 TCB 内网域名 (只有 VPC/SCF 能解析), 本地机器跑这个脚本
# 拿不到内网 DNS, 用 WS_PUBLIC_URL (公网) 替代做 verify, 两者走同一服务。
WS_TCS_URL="${WS_TCS_URL:-${CLOUDBASE_API_BASE:-}}"
WS_PUBLIC_URL="${WS_PUBLIC_URL:-https://ecan-graphql-ws-288118-5-1251680599.sh.run.tcloudbase.com}"
if [[ -z "$WS_TCS_URL" ]]; then
  echo -e "${RED}❌ WS_TCS_URL (or CLOUDBASE_API_BASE) missing in $CB_ENV_FILE${NC}"
  echo "  跑 cloudbase-graphql/bin/deploy-ws.sh 完成 WS 部署,会自动写入 WS_TCS_URL"
  exit 1
fi

if [[ -z "${WS_PUSH_SECRET:-}" ]]; then
  echo -e "${RED}� WS_PUSH_SECRET missing in $CB_ENV_FILE${NC}"
  exit 1
fi

# verify 用公网 URL (本地机器能访问); WS_TCS_URL 保留用于显示/部署记录
echo -e "${YELLOW}ℹ️  WS_TCS_URL (内网, SCF/VPC 专用): $WS_TCS_URL${NC}"
echo -e "${YELLOW}ℹ️  WS_PUBLIC_URL (公网, 本地 verify 用): $WS_PUBLIC_URL${NC}"
URL_BASE="$WS_PUBLIC_URL"
URL_HEALTHZ="$URL_BASE/healthz"
URL_PUBLISH="$URL_BASE/publish"

# ---- Step 1: GET /healthz ----
echo -e "${YELLOW}→ GET $URL_HEALTHZ${NC}"
RESP=$(curl -fsS -w "\nHTTP_CODE=%{http_code}" "$URL_HEALTHZ" || true)
HTTP_CODE=$(echo "$RESP" | grep -o 'HTTP_CODE=[0-9]*' | cut -d= -f2)
BODY=$(echo "$RESP" | grep -v 'HTTP_CODE=')
echo "   HTTP $HTTP_CODE"
echo "   body: $BODY"

if [[ "$HTTP_CODE" != "200" ]]; then
  echo -e "${RED}❌ /healthz returned HTTP $HTTP_CODE${NC}"
  exit 1
fi

if ! echo "$BODY" | grep -q '"service":"ecan-graphql-ws"'; then
  echo -e "${RED}❌ /healthz missing service:ecan-graphql-ws field (拓扑不对,确认是 TCS 服务而不是 SCF)${NC}"
  exit 1
fi

echo -e "${GREEN}   ✓ /healthz OK${NC}"
echo

# ---- Step 2: POST /publish (with X-WS-Push-Secret auth header) ----
echo -e "${YELLOW}→ POST $URL_PUBLISH (no subscriber → 200 ok:true no-op)${NC}"
PAYLOAD='{"topic":"onTaskStatus","target":"verify-smoke-no-sub","payload":{"smoke":true}}'
RESP=$(curl -fsS -w "\nHTTP_CODE=%{http_code}" \
  -X POST \
  -H "Content-Type: application/json" \
  -H "X-WS-Push-Secret: $WS_PUSH_SECRET" \
  -d "$PAYLOAD" \
  "$URL_PUBLISH" || true)
HTTP_CODE=$(echo "$RESP" | grep -o 'HTTP_CODE=[0-9]*' | cut -d= -f2)
BODY=$(echo "$RESP" | grep -v 'HTTP_CODE=')
echo "   HTTP $HTTP_CODE"
echo "   body: $BODY"

if [[ "$HTTP_CODE" != "200" ]]; then
  echo -e "${RED}❌ /publish returned HTTP $HTTP_CODE (no-subscriber 应仍 200)${NC}"
  exit 1
fi

if ! echo "$BODY" | grep -q '"ok":true'; then
  echo -e "${RED}❌ /publish missing ok:true field${NC}"
  exit 1
fi

echo -e "${GREEN}   ✓ /publish OK (no-op,无订阅者)${NC}"
echo

# ---- Step 3: /publish wrong secret → 401 ----
echo -e "${YELLOW}→ POST $URL_PUBLISH with WRONG secret (应 401)${NC}"
RESP=$(curl -fsS -w "\nHTTP_CODE=%{http_code}" \
  -X POST \
  -H "Content-Type: application/json" \
  -H "X-WS-Push-Secret: wrong-secret-on-purpose" \
  -d "$PAYLOAD" \
  "$URL_PUBLISH" || true)
HTTP_CODE=$(echo "$RESP" | grep -o 'HTTP_CODE=[0-9]*' | cut -d= -f2)
BODY=$(echo "$RESP" | grep -v 'HTTP_CODE=')
echo "   HTTP $HTTP_CODE"
echo "   body: $BODY"

if [[ "$HTTP_CODE" != "401" ]]; then
  echo -e "${RED}❌ /publish wrong-secret 应返回 401, 实际 $HTTP_CODE${NC}"
  exit 1
fi
echo -e "${GREEN}   ✓ /publish 鉴权正确${NC}"
echo

# ---- Step 4: WebSocket end-to-end (subscribe + push + receive) ----
# 验证 graphql-ws 协议端到端:
#   1. 用 graphql-ws subprotocol 连上 WS 服务 (wss://{WS_TCS_URL}/...)
#   2. 订阅 onTaskStatus(runID=verify-e2e)
#   3. POST /publish 推一条消息
#   4. 客户端在 5 秒内收到 → 证明 WS 服务自己处理 publish (in-process bus)
echo -e "${YELLOW}→ WebSocket end-to-end (connect + subscribe + push + receive)${NC}"

cd "$ROOT"
WS_EXIT=0
# WS e2e 也走公网 (本地机器不能解析内网域名); 公网 ws URL + 公网 push URL 走同一服务。
WS_PUBLIC_URL="$WS_PUBLIC_URL" WS_PUSH_SECRET="$WS_PUSH_SECRET" python3 - <<'PYEOF' || WS_EXIT=$?
import asyncio
import json
import os
import sys
import urllib.request
import urllib.error
import websockets

ws_base = os.environ["WS_PUBLIC_URL"]
push_secret = os.environ["WS_PUSH_SECRET"]

# WS URL: 把 http(s):// → ws(s)://, 后面带 /?token=... 让 server 走 ALLOW_INSECURE 路径
ws_url = ws_base.replace("http://", "ws://").replace("https://", "wss://").rstrip("/")
push_url = ws_base.rstrip("/") + "/publish"

print(f"   WS URL:   {ws_url}/?token=verify")
print(f"   push URL: {push_url}")

async def main():
    received = []
    try:
        async with websockets.connect(
            ws_url + "/?token=verify",
            subprotocols=["graphql-ws"],
            open_timeout=10,
            close_timeout=5,
        ) as ws:
            # 1. connection_init
            await ws.send(json.dumps({"type": "connection_init"}))
            ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            assert ack.get("type") == "connection_ack", f"expected connection_ack, got {ack}"
            print(f"   ✓ connection_ack")

            # 2. start subscription (AppSync-style: payload.data is JSON-stringified)
            sub_id = "verify-e2e-1"
            start_data = {
                "query": "subscription { onTaskStatus(runID: \"verify-e2e\") { runID status } }",
                "variables": {"runID": "verify-e2e"},
            }
            await ws.send(json.dumps({
                "id": sub_id,
                "type": "start",
                "payload": {"data": json.dumps(start_data)},
            }))
            await asyncio.sleep(0.5)

            # 3. POST /publish (同进程 bus 投递)
            req = urllib.request.Request(
                push_url,
                data=json.dumps({
                    "topic": "onTaskStatus",
                    "target": "verify-e2e",
                    "payload": {"runID": "verify-e2e", "status": "ok"}
                }).encode(),
                headers={
                    "Content-Type": "application/json",
                    "X-WS-Push-Secret": push_secret,
                },
                method="POST",
            )
            try:
                resp = urllib.request.urlopen(req, timeout=10)
                push_result = json.loads(resp.read())
                print(f"   push_result: {json.dumps(push_result)}")
            except urllib.error.HTTPError as e:
                print(f"   /publish → HTTP {e.code}: {e.read().decode()}")
                return False

            # 4. 等客户端收到推送 (loop recv, 跳过 start_ack / ping / ka 等控制帧)
            deadline = asyncio.get_event_loop().time() + 5
            try:
                while True:
                    remaining = deadline - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        raise asyncio.TimeoutError()
                    msg = await asyncio.wait_for(ws.recv(), timeout=remaining)
                    frame = json.loads(msg)
                    if frame.get("type") == "data":
                        received.append(frame)
                        break
                    # 跳过 start_ack / ka / ping 等
                    # print(f"   (skip frame: {frame.get('type')})")
            except asyncio.TimeoutError:
                received.append({"error": "timeout"})

    except Exception as e:
        print(f"   WS error: {type(e).__name__}: {e}")
        return False

    print(f"   client received: {json.dumps(received)}")
    if not received:
        return False
    if "error" in received[0]:
        return False
    if received[0].get("type") != "data":
        return False
    payload = received[0].get("payload", {}).get("data", {}).get("onTaskStatus")
    return payload is not None

sys.exit(0 if asyncio.run(main()) else 1)
PYEOF

if [[ $WS_EXIT -eq 0 ]]; then
  echo -e "${GREEN}   ✓ WS end-to-end OK (客户端成功收到推送)${NC}"
else
  echo -e "${RED}❌ WS end-to-end FAILED${NC}"
  echo "   客户端没收到推送 — 可能是:"
  echo "   1. WS_TCS_URL 不是独立 cloudrun service (确认是 TCS 默认域名)"
  echo "   2. ALLOW_INSECURE_AUTH 未在 WS 服务环境变量启用 (生产模式默认 false, verify 用 ?token= 需要 true)"
  echo "   3. subprotocol 不匹配 (服务只接受 'graphql-ws')"
  echo "   4. WS_PUSH_SECRET 不匹配"
  echo ""
  echo -e "${YELLOW}ℹ️  WS end-to-end 步骤依赖 ?token=<any> 走 ALLOW_INSECURE_AUTH 路径,${NC}"
  echo -e "${YELLOW}   生产模式这个开关应保持 false (避免接受任意 token). 如果要跑这个 step,${NC}"
  echo -e "${YELLOW}   临时把 WS 容器 EnvParams 的 ALLOW_INSECURE_AUTH 改成 'true', 跑完 verify 改回.${NC}"
  echo -e "${YELLOW}   或者用真实 JWT (通过 e2e_full_stack_test.sh 自动 mint).${NC}"
  exit 1
fi

echo
echo -e "${GREEN}✅ WS service + push auth + e2e all healthy${NC}"