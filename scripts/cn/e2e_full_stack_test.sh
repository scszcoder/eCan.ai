#!/usr/bin/env bash
# ============================================================
# eCan.ai CN (TCB) — full-stack end-to-end test
# ============================================================
#
# 测试矩阵 (新拓扑: graphql-ws TCS 服务 + ws-bridge-push.js):
#   ┌─ HTTP Query / Mutation (ecan-graphql-api → prisma → postgres)
#   │    1. getAgents        (read, 验证 graphql + prisma + db)
#   │    2. addAgents        (write, 验证 mutation 落 db)
#   │    3. getAgents        (read again, 验证刚写的能读回)
#   │    4. removeAgents     (cleanup)
#   │
#   ├─ HTTP /publish        (ecan-graphql-ws TCS 服务, 验证 push 入口 + 鉴权)
#   │    5. POST /publish wrong secret → 401
#   │    6. POST /publish correct secret → 200 ok:true (no-op,无订阅者)
#   │
#   ├─ WebSocket             (ecan-graphql-ws, 验证 graphql-ws 协议 + 客户端)
#   │    7. WS connect + connection_ack
#   │    8. WS start subscription
#   │    9. WS receive pushed message
#   │
#   └─ 通过验证：
#        ✓ HTTP Query/Mutation 全通 = 业务 API 健康
#        ✓ HTTP /publish 鉴权 + 推送入口健康
#        ✓ WS 收到推送 = 端到端通了
#
# 前提（私有 Tencent 后端的 `.env.local`）:
#   - WS_TCS_URL        # TCS cloudrun 服务地址
#   - WS_PUSH_SECRET    # push 鉴权密钥
#   - CLOUDBASE_API_BASE # GraphQL API host
#   - DATABASE_URL, TCB_ENV_ID (业务测试需要)
#   - ALLOW_INSECURE_AUTH=true 在 ecan-graphql-api 函数环境变量里（让 verify 脚本能调 query）
#   - 如果不想修改生产函数,也支持 ACCESS_TOKEN env var 走 JWT 路径

set -uo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
PASS=0; FAIL=0
PUSH_PASS=0  # /publish 鉴权+no-op 两步专用计数器

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_ROOT="${ECAN_TENCENT_BACKEND_ROOT:-}"
[[ -n "$BACKEND_ROOT" ]] || { echo -e "${RED}❌ ECAN_TENCENT_BACKEND_ROOT missing${NC}"; exit 1; }
CB_ENV_FILE="$BACKEND_ROOT/.env.local"

[[ -f "$CB_ENV_FILE" ]] || { echo -e "${RED}❌ $CB_ENV_FILE missing${NC}"; exit 1; }
# shellcheck disable=SC1090
set -a; source "$CB_ENV_FILE"; set +a

[[ -n "${CLOUDBASE_API_BASE:-}" ]] || { echo -e "${RED}❌ CLOUDBASE_API_BASE missing${NC}"; exit 1; }
[[ -n "${WS_PUSH_SECRET:-}"    ]] || { echo -e "${RED}❌ WS_PUSH_SECRET missing${NC}"; exit 1; }
WS_TCS_URL="${WS_TCS_URL:-${CLOUDBASE_API_BASE}}"
# 本地机器不能解析 TCB 内网域名 (WS_TCS_URL), verify 用 WS_PUBLIC_URL (公网)。
# SCF 公网 endpoint (CLOUDBASE_API_BASE) 仍走 SCF, 无此问题。
WS_PUBLIC_URL="${WS_PUBLIC_URL:-https://ecan-graphql-ws-288118-5-1251680599.sh.run.tcloudbase.com}"

BASE="$CLOUDBASE_API_BASE"
GRAPHQL_URL="$BASE/api/graphql"
URL_PUBLISH="$WS_PUBLIC_URL/publish"

# 生成一个随机所有者用于本次测试,避免与真实数据冲突
# 注意: SCF 强制 owner == identity.sub (生产安全规则, authenticatedOwner 检查)。
# 我们的 JWT sub 是 'verify-e2e-user', 所以 TEST_OWNER 必须 = 'verify-e2e-user'。
TEST_OWNER="verify-e2e-user"
TEST_AGENT_ID="agent-$(date +%s)-$RANDOM"

ok()   { echo -e "${GREEN}✓ $1${NC}"; PASS=$((PASS+1)); }
fail() { echo -e "${RED}✗ $1${NC}"; FAIL=$((FAIL+1)); }
hdr()  { echo -e "\n${BLUE}=== $1 ===${NC}"; }

# 调 GraphQL;接受带 Authorization Bearer token。
# SCF 生产 env (NODE_ENV=production) 强制 bearer token, ALLOW_INSECURE_AUTH=true 不会生效。
# Token 从 ECAN_JWT_SECRET (eCan 自签 HS256, 与 resolvers/auth.js mintSessionToken 共用)
# 自动 mint。如果 .env.local 里显式给了 ACCESS_TOKEN, 用 ACCESS_TOKEN 而非 mint。
if [[ -z "${ACCESS_TOKEN:-}" && -n "${ECAN_JWT_SECRET:-}" ]]; then
  ACCESS_TOKEN=$(node -e "
const c=require('crypto');
const s=process.env.ECAN_JWT_SECRET;
const h=Buffer.from(JSON.stringify({alg:'HS256',typ:'JWT'})).toString('base64url');
const n=Math.floor(Date.now()/1000);
const p=Buffer.from(JSON.stringify({sub:'verify-e2e-user',iat:n,exp:n+3600})).toString('base64url');
const g=c.createHmac('sha256',s).update(\`\${h}.\${p}\`).digest('base64url');
console.log(\`\${h}.\${p}.\${g}\`);
")
  export ACCESS_TOKEN
fi
gql() {
  local query="$1"
  curl -fsS -X POST "$GRAPHQL_URL" \
    -H "Content-Type: application/json" \
    ${ACCESS_TOKEN:+-H "Authorization: Bearer $ACCESS_TOKEN"} \
    -d "{\"query\":$(echo -n "$query" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')}" \
    2>&1
}

# ---- Step 1: getAgents (empty) ----
hdr "1/9 HTTP Query getAgents (验证 graphql + prisma + db)"
RESP=$(gql "query { getAgents(input: {owner: \"$TEST_OWNER\"}) { id name } }")
echo "   $RESP"
if echo "$RESP" | grep -q '"data"'; then
  ok "getAgents returned valid GraphQL response"
else
  fail "getAgents failed: $RESP"
fi

# ---- Step 2: addAgents (write to db) ----
hdr "2/9 HTTP Mutation addAgents (写入 db)"
RESP=$(gql "mutation { addAgents(input: [{id: \"$TEST_AGENT_ID\", owner: \"$TEST_OWNER\", name: \"verify-agent\"}]) { id success error } }")
echo "   $RESP"
if echo "$RESP" | grep -q '"success":true'; then
  ok "addAgents wrote to db"
else
  fail "addAgents failed: $RESP"
fi

# ---- Step 3: getAgents (read back) ----
hdr "3/9 HTTP Query getAgents (读回)"
RESP=$(gql "query { getAgents(input: {owner: \"$TEST_OWNER\"}) { id name owner } }")
echo "   $RESP"
if echo "$RESP" | grep -q "\"$TEST_AGENT_ID\""; then
  ok "getAgents read back the just-written agent"
else
  fail "getAgents didn't return the written agent: $RESP"
fi

# ---- Step 4: removeAgents (cleanup) ----
hdr "4/9 HTTP Mutation removeAgents (清理)"
RESP=$(gql "mutation { removeAgents(ids: [\"$TEST_AGENT_ID\"]) { id success } }")
echo "   $RESP"
if echo "$RESP" | grep -q '"success":true'; then
  ok "removeAgents cleaned up"
else
  fail "removeAgents failed: $RESP"
fi

# ---- Step 5: /publish wrong secret → 401 ----
hdr "5/9 HTTP POST /publish with WRONG secret (应 401)"
# curl --fail-with-body: 返回 4xx/5xx 时, body 仍保留在 stderr/stdout,exit code 非 0.
RESP=$(curl -sS --fail-with-body -X POST "$URL_PUBLISH" \
  -H "Content-Type: application/json" \
  -H "X-WS-Push-Secret: wrong-on-purpose" \
  -d '{"topic":"onTaskStatus","target":"verify-no-sub","payload":{"smoke":true}}' \
  2>&1)
EXIT=$?
HTTP=$(echo "$RESP" | grep -o 'HTTP_CODE=[0-9]*' | cut -d= -f2)
# --fail-with-body 把 HTTP 状态写到 stderr 行尾 "HTTP CODE: 401", 简单 grep 拿
if [[ -z "$HTTP" ]]; then
  HTTP=$(echo "$RESP" | grep -oE '\b(401|400|403|500)\b' | head -1)
fi
echo "   exit=$EXIT HTTP=$HTTP body=$RESP"
if [[ "$EXIT" -ne 0 && ( "$HTTP" == "401" || "$RESP" == *"401"* ) ]]; then
  ok "/publish wrong secret → 401 (鉴权工作)"
  PUSH_PASS=$((PUSH_PASS + 1))
else
  fail "/publish wrong-secret 应 401, 实际 exit=$EXIT HTTP=$HTTP"
fi

# ---- Step 6: /publish correct secret → 200 (no-subscriber no-op) ----
hdr "6/9 HTTP POST /publish with correct secret (no subscriber → 200 no-op)"
RESP=$(curl -fsS -X POST "$URL_PUBLISH" \
  -H "Content-Type: application/json" \
  -H "X-WS-Push-Secret: $WS_PUSH_SECRET" \
  -d '{"topic":"onTaskStatus","target":"verify-no-sub","payload":{"smoke":true}}' \
  2>&1)
echo "   $RESP"
if echo "$RESP" | grep -q '"ok":true'; then
  ok "/publish returned ok:true"
  PUSH_PASS=$((PUSH_PASS + 1))
else
  fail "/publish malformed response: $RESP"
fi

# ---- Step 7-9: WS end-to-end ----
hdr "7-9/9 WebSocket end-to-end (connect + subscribe + push + receive)"
cd "$ROOT"
WS_EXIT=0
# WS e2e 用公网 URL (本地机器能解析), push 也走公网 — 同 cloudrun 服务, 同 process。
# 生产模式 (ALLOW_INSECURE_AUTH=false) 下 WS 服务拒绝任意非 JWT token, 所以 WS 也走
# ACCESS_TOKEN (HS256 session JWT, 同 HTTP). WS 通过 connection_init params 收 token:
#   wss://...?token=<jwt>
# 验证路径: ws/index.js resolveIdentity → JWT_SECRET 验签 → claims.sub=userId。
WS_PUBLIC_URL="$WS_PUBLIC_URL" WS_PUSH_SECRET="$WS_PUSH_SECRET" ACCESS_TOKEN="$ACCESS_TOKEN" python3 - <<PYEOF || WS_EXIT=$?
import asyncio, json, os, sys, urllib.request, urllib.error, websockets

ws_base = os.environ["WS_PUBLIC_URL"]
push_secret = os.environ["WS_PUSH_SECRET"]
access_token = os.environ.get("ACCESS_TOKEN", "")
ws_url = ws_base.replace("http://", "ws://").replace("https://", "wss://").rstrip("/")
push_url = ws_base.rstrip("/") + "/publish"

# Use a short token prefix indicator so the log shows which path was taken
# (production uses JWT, dev/insecure uses literal "verify")
if access_token and access_token.count(".") == 2:
    print(f"   WS URL:   {ws_url}/?token=<jwt-{access_token[-8:]}>  (HS256 session token, production path)")
else:
    print(f"   WS URL:   {ws_url}/?token=verify  (ALLOW_INSECURE path)")

async def main():
    received = []
    token_for_ws = access_token if access_token and access_token.count(".") == 2 else "verify"
    try:
        async with websockets.connect(
            ws_url + "/?token=" + token_for_ws,
            subprotocols=["graphql-ws"],
            open_timeout=10,
            close_timeout=5,
        ) as ws:
            await ws.send(json.dumps({"type": "connection_init"}))
            ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            assert ack.get("type") == "connection_ack", f"got {ack}"
            print(f"   ✓ connection_ack")

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
                print(f"   /publish → {json.dumps(push_result)}")
            except urllib.error.HTTPError as e:
                print(f"   /publish → HTTP {e.code}: {e.read().decode()}")
                return False

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
            except asyncio.TimeoutError:
                received.append({"error": "timeout"})

    except Exception as e:
        print(f"   WS error: {type(e).__name__}: {e}")
        return False

    print(f"   client received: {json.dumps(received)}")
    if received and received[0].get("type") == "data":
        return True
    return False

sys.exit(0 if asyncio.run(main()) else 2)
PYEOF

case $WS_EXIT in
  0) ok "WS end-to-end: 客户端收到推送(in-process bus ✅)" ;;
  2)
    fail "WS end-to-end: 客户端没收到推送"
    echo -e "${YELLOW}   说明:${NC}"
    echo "     - WS 服务和 /publish 入口是同一个 cloudrun 进程 (in-process bus 投递)"
    echo "     - 失败常见原因: WS_TCS_URL 不对 / ALLOW_INSECURE_AUTH 没启用"
    echo "     - WS_PUSH_SECRET 不匹配 / subprotocol 不是 graphql-ws"
    ;;
  *) fail "WS end-to-end: 客户端连接失败 (WS 服务没起来?网络不通?)" ;;
esac

# ---- Summary ----
# PASS covers: 4 HTTP query/mutation + push (step 5/6) + WS (step 7-9 if WS_EXIT=0).
# 但 push 单独用 PUSH_PASS 计数 (避免 PASS 跨域反推).
# 公式: HTTP_QUERY_OK = min(4, PASS); PUSH_OK = PUSH_PASS (0/1/2); WS_OK from WS_EXIT.
HTTP_QUERY_OK=$(( PASS > 4 ? 4 : PASS ))
PUSH_OK=$PUSH_PASS
WS_OK=$( [[ $WS_EXIT -eq 0 ]] && echo "passed" || echo "failed" )

echo
echo -e "${BLUE}========================================${NC}"
echo -e "  HTTP Query/Mutation:     $HTTP_QUERY_OK/4 passed"
echo -e "  HTTP /publish auth+no-op: $PUSH_OK/2 passed"
echo -e "  WS end-to-end:           $WS_OK"
echo -e "${BLUE}========================================${NC}"

exit $(( FAIL > 0 ? 1 : 0 ))