#!/usr/bin/env bash
# ============================================================
# eCan.ai · WS HTTP endpoint smoke test (CN)
# ============================================================
#
# 用法:
#   ./scripts/cn/verify_websocket_endpoints.sh
#
# 检查项:
#   1. GET  /ws/status → 返回连接统计
#   2. POST /ws/push   → 推送一条测试消息
#
# 前提:
#   - 根目录的 .env 里有 CLOUDBASE_API_BASE
#     格式: https://{env_id}.service.tcloudbase.com
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
ENV_FILE="$ROOT/.env"
CB_ENV_FILE="$ROOT/cloudbase-graphql/.env.local"

if [[ ! -f "$ENV_FILE" ]]; then
  echo -e "${RED}❌ $ENV_FILE not found${NC}"
  exit 1
fi
if [[ ! -f "$CB_ENV_FILE" ]]; then
  echo -e "${RED}❌ $CB_ENV_FILE not found${NC}"
  exit 1
fi

# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a
set -a; source "$CB_ENV_FILE"; set +a

if [[ -z "${CLOUDBASE_API_BASE:-}" ]]; then
  echo -e "${RED}❌ CLOUDBASE_API_BASE missing in $ENV_FILE${NC}"
  echo "  格式: https://{env_id}.service.tcloudbase.com"
  exit 1
fi

if [[ -z "${WEBSOCKET_PUSH_SECRET:-}" ]]; then
  echo -e "${RED}❌ WEBSOCKET_PUSH_SECRET missing in $CB_ENV_FILE${NC}"
  exit 1
fi

BASE="$CLOUDBASE_API_BASE"
URL_STATUS="$BASE/ws/status"
URL_PUSH="$BASE/ws/push"

# ---- Step 1: GET /ws/status ----
echo -e "${YELLOW}→ GET $URL_STATUS${NC}"
RESP=$(curl -fsS -w "\nHTTP_CODE=%{http_code}" "$URL_STATUS" || true)
HTTP_CODE=$(echo "$RESP" | grep -o 'HTTP_CODE=[0-9]*' | cut -d= -f2)
BODY=$(echo "$RESP" | grep -v 'HTTP_CODE=')
echo "   HTTP $HTTP_CODE"
echo "   body: $BODY"

if [[ "$HTTP_CODE" != "200" ]]; then
  echo -e "${RED}❌ /ws/status returned HTTP $HTTP_CODE${NC}"
  exit 1
fi

if ! echo "$BODY" | grep -q '"totalConnections"'; then
  echo -e "${RED}❌ /ws/status missing totalConnections field${NC}"
  exit 1
fi

echo -e "${GREEN}   ✓ /ws/status OK${NC}"
echo

# ---- Step 2: POST /ws/push (with auth header) ----
echo -e "${YELLOW}→ POST $URL_PUSH${NC}"
PAYLOAD='{"topic":"onTaskStatus","target":"verify-smoke-test","payload":{"smoke":true}}'
RESP=$(curl -fsS -w "\nHTTP_CODE=%{http_code}" \
  -X POST \
  -H "Content-Type: application/json" \
  -H "X-ECAN-Push-Secret: $WEBSOCKET_PUSH_SECRET" \
  -d "$PAYLOAD" \
  "$URL_PUSH" || true)
HTTP_CODE=$(echo "$RESP" | grep -o 'HTTP_CODE=[0-9]*' | cut -d= -f2)
BODY=$(echo "$RESP" | grep -v 'HTTP_CODE=')
echo "   HTTP $HTTP_CODE"
echo "   body: $BODY"

if [[ "$HTTP_CODE" != "200" ]]; then
  echo -e "${RED}❌ /ws/push returned HTTP $HTTP_CODE${NC}"
  exit 1
fi

if ! echo "$BODY" | grep -q '"delivered"'; then
  echo -e "${RED}❌ /ws/push missing delivered field${NC}"
  exit 1
fi

DELIVERED=$(echo "$BODY" | grep -o '"delivered":[0-9]*' | cut -d: -f2)
echo -e "${GREEN}   ✓ /ws/push OK (delivered=$DELIVERED)${NC}"
echo

# ---- Step 3: WebSocket end-to-end (subscribe + push + receive) ----
# 验证 pushToWebSocketBridge 的 e2e 链路通：
#   1. 用 graphql-ws 客户端协议连上 /ws
#   2. 订阅 onTaskStatus(runID=verify-e2e)
#   3. 服务端内部 POST /ws/push 推一条消息
#   4. 客户端在 5 秒内收到 → 证明 "WS 连接 + HTTP 推送" 用的同一函数实例内存

echo -e "${YELLOW}→ WebSocket end-to-end (connect + subscribe + push + receive)${NC}"

cd "$ROOT"
WS_EXIT=0
python3 - <<'PYEOF' || WS_EXIT=$?
import asyncio
import json
import os
import sys
import urllib.request
import websockets

base = os.environ["CLOUDBASE_API_BASE"]
ws_url = base.replace("http://", "wss://").replace("https://", "wss://") + "/ws"
push_url = base + "/ws/push"
secret = os.environ["WEBSOCKET_PUSH_SECRET"]

print(f"   WS URL:   {ws_url}")
print(f"   push URL: {push_url}")

async def main():
    received = []
    push_result = {}
    try:
        async with websockets.connect(
            ws_url,
            subprotocols=["graphql-ws"],
            open_timeout=10,
            close_timeout=5,
        ) as ws:
            # 1. connection_init
            await ws.send(json.dumps({"type": "connection_init"}))

            ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            assert ack.get("type") == "connection_ack", f"expected connection_ack, got {ack}"

            # 2. start subscription
            sub_id = "verify-e2e-1"
            await ws.send(json.dumps({
                "id": sub_id,
                "type": "start",
                "payload": {
                    "query": "subscription { onTaskStatus(runID: \"verify-e2e\") { runID } }",
                    "variables": {"runID": "verify-e2e"},
                }
            }))
            await asyncio.sleep(0.5)

            # 3. POST /ws/push (服务端内部调用)
            req = urllib.request.Request(
                push_url,
                data=json.dumps({
                    "topic": "onTaskStatus",
                    "target": "verify-e2e",
                    "payload": {"runID": "verify-e2e", "status": "ok"}
                }).encode(),
                headers={
                    "Content-Type": "application/json",
                    "X-ECAN-Push-Secret": secret,
                },
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=10)
            push_result = json.loads(resp.read())
            print(f"   push_result: {json.dumps(push_result)}")

            # 4. 等客户端收到推送
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                received.append(json.loads(msg))
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
    if payload is None:
        return False
    return True

ok = asyncio.run(main())
sys.exit(0 if ok else 1)
PYEOF

if [[ $WS_EXIT -eq 0 ]]; then
  echo -e "${GREEN}   ✓ WS end-to-end OK (客户端成功收到推送)${NC}"
else
  echo -e "${RED}❌ WS end-to-end FAILED${NC}"
  echo "   客户端没收到推送 — 可能是:"
  echo "   1. ecan-websocket 的 WS 触发器未配置 (握手被网关拦截)"
  echo "   2. ALLOW_INSECURE_AUTH 未启用 (需要 JWT 验证)"
  echo "   3. WS 函数和 /ws/push HTTP 入口内存隔离 (两函数独立部署)"
  echo "   4. subprotocol 不匹配 (函数只接受 'graphql-ws' 或 'tcb')"
  exit 1
fi

echo
echo -e "${GREEN}✅ All WS HTTP endpoints + WebSocket end-to-end healthy${NC}"