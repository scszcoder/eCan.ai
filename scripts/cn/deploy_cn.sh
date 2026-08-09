#!/usr/bin/env bash
# ============================================================
# eCan.ai · CN (TCB) one-shot deploy + verify
# ============================================================
#
# 用法:
#   ./scripts/cn/deploy_cn.sh            # 完整流程
#   ./scripts/cn/deploy_cn.sh --skip-test # 跳过预检查
#   ./scripts/cn/deploy_cn.sh --verify    # 只跑 verify, 不部署
#
# 流程:
#   1. precheck                (cloudbase-graphql/scripts/precheck.js)
#   2. sync-tcb-env.sh         (.env.local → TCB 云函数 env)
#   3. deploy-safe.sh          (打 zip + deploy + 版本管理)
#   4. update_auth_config.py   (回写 endpoints 到 auth_config.yml)
#   5. ws-trigger-setup.py --status  (检查 WS 触发器是否到位)
#   6. verify_websocket_endpoints.sh (curl /ws/status + /ws/push)
#
# 不做的事:
#   - DB schema 迁移 (deploy-safe.sh 默认会跑, --no-migrate 可跳过)
#   - WS 触发器创建 (ws-trigger-setup.py --apply; 你说要去控制台手点, 默认不动)
#
# 退码:
#   - 任一步骤失败立即退出
#
# 依赖:
#   - cloudbase CLI 已登录 (cloudbase login)
#   - .env.local 在 cloudbase-graphql/ 下, 含 TCB_ENV_ID / DATABASE_URL / WEBSOCKET_PUSH_SECRET

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CB_DIR="$ROOT/cloudbase-graphql"

SKIP_TEST=0
VERIFY_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-test)  SKIP_TEST=1; shift ;;
    --verify)     VERIFY_ONLY=1; shift ;;
    -h|--help)
      grep -E '^#' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

step() { echo -e "\n${BLUE}=== $1 ===${NC}"; }
ok()   { echo -e "${GREEN}✓ $1${NC}"; }
die()  { echo -e "${RED}✗ $1${NC}"; exit 1; }

cd "$CB_DIR"

# ---------- Verify-only 路径 ----------
if [[ $VERIFY_ONLY -eq 1 ]]; then
  step "Verify-only: WS HTTP endpoints"
  bash "$ROOT/scripts/cn/verify_websocket_endpoints.sh"
  exit 0
fi

# ---------- 完整流程 ----------
step "1/6 precheck (unit/smoke/skill-store)"
if [[ $SKIP_TEST -eq 0 ]]; then
  npm run precheck || die "precheck failed (use --skip-test to bypass)"
  ok "precheck passed"
else
  echo "  (skipped)"
fi

step "2/6 sync-tcb-env.sh (push .env.local → TCB)"
./scripts/sync-tcb-env.sh || die "sync-tcb-env failed"
ok "env synced to TCB"

step "3/6 deploy-safe.sh (zip + deploy)"
./scripts/deploy-safe.sh || die "deploy-safe failed"
ok "functions deployed"

step "4/6 update_auth_config.py (回写 endpoints)"
python3 scripts/update_auth_config.py || die "update_auth_config failed"
ok "auth_config.yml updated"

step "5/6 ws-trigger-setup.py --status (检查 WS 触发器)"
python3 scripts/ws-trigger-setup.py --status || \
  echo -e "${YELLOW}  ⚠️  ws-trigger-setup --status failed, check manually${NC}"

step "6/6 verify_websocket_endpoints.sh (curl /ws/status + /ws/push)"
bash "$ROOT/scripts/cn/verify_websocket_endpoints.sh" || \
  die "WS endpoints not healthy — check TCB console for trigger config"
ok "WS HTTP endpoints healthy"

echo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ✅ CN deploy + verify complete${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo -e "${YELLOW}下一步 (你必须做一次):${NC}"
echo "  - 去 TCB 控制台, 给 ecan-websocket 配 WS 触发器"
echo "    路径: /ws, 协议: API 网关触发, 方法: ANY"
echo "  - 然后跑:"
echo "    wscat -c wss://${TCB_ENV_ID:-sccb0-d0gc5398xf028be6a}.service.tcloudbase.com/ws"
echo "    或在你的 GUI 里启用 WS 客户端"