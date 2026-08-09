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

if [[ ! -f "$ENV_FILE" ]]; then
  echo -e "${RED}❌ $ENV_FILE not found${NC}"
  exit 1
fi

# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

if [[ -z "${CLOUDBASE_API_BASE:-}" ]]; then
  echo -e "${RED}❌ CLOUDBASE_API_BASE missing in $ENV_FILE${NC}"
  echo "  格式: https://{env_id}.service.tcloudbase.com"
  exit 1
fi

if [[ -z "${WEBSOCKET_PUSH_SECRET:-}" ]]; then
  echo -e "${RED}❌ WEBSOCKET_PUSH_SECRET missing in $ENV_FILE${NC}"
  echo "  从 cloudbase-graphql/ecan-websocket.bak.json 的 Environment.WEBSOCKET_PUSH_SECRET 取"
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
echo -e "${GREEN}✅ All WS HTTP endpoints healthy${NC}"