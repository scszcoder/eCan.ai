#!/usr/bin/env bash
# ============================================================
# eCan.ai CN (TCB) — full-stack end-to-end test
# ============================================================
#
# 测试矩阵：
#   ┌─ HTTP Query / Mutation (ecan-graphql-api → prisma → postgres)
#   │    1. getAgents        (read, 验证 graphql + prisma + db)
#   │    2. addAgents        (write, 验证 mutation 落 db)
#   │    3. getAgents        (read again, 验证刚写的能读回)
#   │    4. removeAgents     (cleanup)
#   │
#   ├─ HTTP /ws/push         (ecan-websocket-api, 验证 HTTP 推送入口)
#   │    5. POST /ws/push   → 应返回 delivered=N (N=订阅者数)
#   │
#   ├─ WebSocket             (ecan-websocket, 验证 WS 协议 + 客户端)
#   │    6. WS connect + connection_ack
#   │    7. WS start subscription
#   │    8. WS receive pushed message
#   │
#   └─ 通过验证：
#        ✓ HTTP Query/Mutation 全通 = 业务 API 健康
#        ✓ HTTP /ws/push 返回 200 = 推送入口健康
#        ✓ WS 收到推送 = 端到端通了
#          ✗ WS 收不到推送 = 内存隔离（HTTP 和 WS 进程不共享 subscriptions）
#                     → 后续需要 TCB Redis 或类似方案
#
# 前提:
#   - .env 有 CLOUDBASE_API_BASE
#   - cloudbase-graphql/.env.local 有 WEBSOCKET_PUSH_SECRET / DATABASE_URL / TCB_ENV_ID
#   - ALLOW_INSECURE_AUTH=true 在 ecan-graphql-api 函数环境变量里（让 verify 脚本能调 query）
#   - 如果不想修改生产函数，也支持 ACCESS_TOKEN env var 走 JWT 路径

set -uo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
PASS=0; FAIL=0

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$ROOT/.env"
CB_ENV_FILE="$ROOT/cloudbase-graphql/.env.local"

[[ -f "$ENV_FILE" ]]    || { echo -e "${RED}❌ $ENV_FILE missing${NC}"; exit 1; }
[[ -f "$CB_ENV_FILE" ]] || { echo -e "${RED}❌ $CB_ENV_FILE missing${NC}"; exit 1; }
set -a; source "$ENV_FILE";    set +a
set -a; source "$CB_ENV_FILE"; set +a

[[ -n "${CLOUDBASE_API_BASE:-}"    ]] || { echo -e "${RED}❌ CLOUDBASE_API_BASE missing${NC}"; exit 1; }
[[ -n "${WEBSOCKET_PUSH_SECRET:-}" ]] || { echo -e "${RED}❌ WEBSOCKET_PUSH_SECRET missing${NC}"; exit 1; }

BASE="$CLOUDBASE_API_BASE"
GRAPHQL_URL="$BASE/api/graphql"
WS_PUSH_URL="$BASE/ws/push"
WS_STATUS_URL="$BASE/ws/status"
WS_URL="${BASE/http/wss}/ws"

# 生成一个随机所有者用于本次测试，避免与真实数据冲突
TEST_OWNER="verify-$(date +%s)-$RANDOM"
TEST_AGENT_ID="agent-$(date +%s)-$RANDOM"

ok()   { echo -e "${GREEN}✓ $1${NC}"; PASS=$((PASS+1)); }
fail() { echo -e "${RED}✗ $1${NC}"; FAIL=$((FAIL+1)); }
hdr()  { echo -e "\n${BLUE}=== $1 ===${NC}"; }

# 调 GraphQL；接受无认证（依赖 ALLOW_INSECURE_AUTH=true），
# 也接受带 Authorization Bearer token。
gql() {
  local query="$1"
  curl -fsS -X POST "$GRAPHQL_URL" \
    -H "Content-Type: application/json" \
    ${ACCESS_TOKEN:+-H "Authorization: Bearer $ACCESS_TOKEN"} \
    -d "{\"query\":$(echo -n "$query" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')}" \
    2>&1
}

# ---- Step 1: getAgents (empty) ----
hdr "1/8 HTTP Query getAgents (验证 graphql + prisma + db)"
RESP=$(gql "query { getAgents(input: {owner: \"$TEST_OWNER\"}) { id name } }")
echo "   $RESP"
if echo "$RESP" | grep -q '"data"'; then
  ok "getAgents returned valid GraphQL response"
else
  fail "getAgents failed: $RESP"
fi

# ---- Step 2: addAgents (write to db) ----
hdr "2/8 HTTP Mutation addAgents (写入 db)"
RESP=$(gql "mutation { addAgents(input: [{id: \"$TEST_AGENT_ID\", owner: \"$TEST_OWNER\", name: \"verify-agent\"}]) { id success error } }")
echo "   $RESP"
if echo "$RESP" | grep -q '"success":true'; then
  ok "addAgents wrote to db"
else
  fail "addAgents failed: $RESP"
fi

# ---- Step 3: getAgents (read back) ----
hdr "3/8 HTTP Query getAgents (读回)"
RESP=$(gql "query { getAgents(input: {owner: \"$TEST_OWNER\"}) { id name owner } }")
echo "   $RESP"
if echo "$RESP" | grep -q "\"$TEST_AGENT_ID\""; then
  ok "getAgents read back the just-written agent"
else
  fail "getAgents didn't return the written agent: $RESP"
fi

# ---- Step 4: removeAgents (cleanup) ----
hdr "4/8 HTTP Mutation removeAgents (清理)"
RESP=$(gql "mutation { removeAgents(ids: [\"$TEST_AGENT_ID\"]) { id success } }")
echo "   $RESP"
if echo "$RESP" | grep -q '"success":true'; then
  ok "removeAgents cleaned up"
else
  fail "removeAgents failed: $RESP"
fi

# ---- Step 5: HTTP /ws/push ----
hdr "5/8 HTTP POST /ws/push (推送入口健康检查)"
RESP=$(curl -fsS -X POST "$WS_PUSH_URL" \
  -H "Content-Type: application/json" \
  -H "X-ECAN-Push-Secret: $WEBSOCKET_PUSH_SECRET" \
  -d '{"topic":"onTaskStatus","target":"verify-no-subscriber","payload":{"smoke":true}}' \
  2>&1)
echo "   $RESP"
if echo "$RESP" | grep -q '"delivered"'; then
  ok "/ws/push returned delivered field"
else
  fail "/ws/push malformed response: $RESP"
fi

# ---- Step 6-8: WS end-to-end ----
hdr "6-8/8 WebSocket end-to-end (connect + subscribe + push + receive)"
cd "$ROOT"
WS_EXIT=0
python3 - <<PYEOF || WS_EXIT=$?
import asyncio, json, os, sys, urllib.request, websockets

base = os.environ["CLOUDBASE_API_BASE"]
ws_url = base.replace("http://", "wss://").replace("https://", "wss://") + "/ws"
push_url = base + "/ws/push"
secret = os.environ["WEBSOCKET_PUSH_SECRET"]

print(f"   WS URL:   {ws_url}")
print(f"   push URL: {push_url}")

async def main():
    received = []
    try:
        async with websockets.connect(
            ws_url,
            subprotocols=["graphql-ws"],
            open_timeout=10,
            close_timeout=5,
        ) as ws:
            await ws.send(json.dumps({"type": "connection_init"}))
            ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            assert ack.get("type") == "connection_ack", f"got {ack}"
            print(f"   ✓ connection_ack")

            sub_id = "verify-e2e-1"
            await ws.send(json.dumps({
                "id": sub_id,
                "type": "start",
                "payload": {
                    "query": "subscription { onTaskStatus(runID: \"verify-e2e\") { runID status } }",
                    "variables": {"runID": "verify-e2e"},
                }
            }))
            await asyncio.sleep(0.5)

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
            print(f"   /ws/push → {json.dumps(push_result)}")

            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                received.append(json.loads(msg))
            except asyncio.TimeoutError:
                received.append({"error": "timeout"})

    except Exception as e:
        print(f"   WS error: {type(e).__name__}: {e}")
        sys.exit(1)

    print(f"   client received: {json.dumps(received)}")
    if received and received[0].get("type") == "data":
        sys.exit(0)
    sys.exit(2)

sys.exit(asyncio.run(main()))
PYEOF

case $WS_EXIT in
  0) ok "WS end-to-end: 客户端收到推送（内存共享 ✅）" ;;
  2)
    fail "WS end-to-end: 客户端没收到推送 — 内存隔离"
    echo -e "${YELLOW}   说明:${NC}"
    echo "     - ecan-websocket-api (HTTP, /ws/push) 和 ecan-websocket (WS, 客户端连接) 是两个进程"
    echo "     - subscriptions Map 在 ecan-websocket 进程的内存里"
    echo "     - /ws/push 请求落到 ecan-websocket-api 时，内存里没有订阅者"
    echo "     - 修复需要: subscriptions 存到 TCB DB / Redis 共享"
    ;;
  *) fail "WS end-to-end: 客户端连接失败 (WS 触发器未配?)" ;;
esac

# ---- Summary ----
echo
echo -e "${BLUE}========================================${NC}"
echo -e "  HTTP Query/Mutation: $(( PASS > 4 ? 4 : PASS ))/4 passed"
echo -e "  HTTP /ws/push:       $( [[ $FAIL -eq 0 ]] && echo "1/1 passed" || echo "failed" )"
echo -e "  WS end-to-end:       $( [[ $WS_EXIT -eq 0 ]] && echo "passed" || echo "failed" )"
echo -e "${BLUE}========================================${NC}"

exit $(( FAIL > 0 ? 1 : 0 ))