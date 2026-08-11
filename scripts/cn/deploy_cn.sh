#!/usr/bin/env bash
# ============================================================
# eCan.ai · CN (TCB) one-shot deploy + verify
# ============================================================
#
# 用法:
#   ./scripts/cn/deploy_cn.sh            # 完整流程
#   ./scripts/cn/deploy_cn.sh --skip-test # 跳过预检查
#   ./scripts/cn/deploy_cn.sh --verify    # 只跑 verify, 不部署
#   ./scripts/cn/deploy_cn.sh --skip-ws   # 跳过 WS cloudrun 部署 (only deploy SCF)
#
# 流程 (新拓扑: graphql-ws 自建 TCS 服务 + ws-bridge-push.js):
#   1. precheck                  (cloudbase-graphql/scripts/precheck.js)
#   2. sync-tcb-env.sh           (.env.local → TCB SCF env)
#   3. deploy-safe.sh            (打 zip + deploy SCF ecan-graphql-api)
#   4. update_auth_config.py     (回写 endpoints 到 auth_config.yml)
#   5. bin/deploy-ws             (build → push → deploy TCS ecan-graphql-ws + 回写 WS_TCS_URL)
#   6. sync-tcb-env.sh           (再次, 把 WS_TCS_URL 推到 SCF env)
#   7. verify_websocket_endpoints.sh (curl /healthz + /publish + e2e WS)
#
# 不做的事:
#   - DB schema 迁移 (deploy-safe.sh 默认会跑, --no-migrate 可跳过)
#   - 老 SCF WS 触发器配置 — 新拓扑不需要 (WS 是独立 cloudrun 服务)
#
# 退码:
#   - 任一步骤失败立即退出
#
# 依赖:
#   - cloudbase CLI 已登录 (cloudbase login)
#   - .env.local 在 cloudbase-graphql/ 下, 含 TCB_ENV_ID / DATABASE_URL / WS_PUSH_SECRET
#   - docker 已登录 TCR (ccr.ccs.tencentyun.com) — 仅在部署 WS cloudrun 时需要

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
SKIP_WS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-test)  SKIP_TEST=1; shift ;;
    --verify)     VERIFY_ONLY=1; shift ;;
    --skip-ws)    SKIP_WS=1; shift ;;
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
  step "Verify-only: WS service"
  bash "$ROOT/scripts/cn/verify_websocket_endpoints.sh"
  exit 0
fi

# ---------- 完整流程 ----------
step "1/7 precheck (unit/smoke/skill-store)"
if [[ $SKIP_TEST -eq 0 ]]; then
  npm run precheck || die "precheck failed (use --skip-test to bypass)"
  ok "precheck passed"
else
  echo "  (skipped)"
fi

step "2/7 sync-tcb-env.sh (push .env.local → TCB SCF env)"
./scripts/sync-tcb-env.sh || die "sync-tcb-env failed"
ok "env synced to TCB"

step "3/7 deploy-safe.sh (zip + deploy SCF ecan-graphql-api)"
./scripts/deploy-safe.sh || die "deploy-safe failed"
ok "ecan-graphql-api deployed"

step "4/7 update_auth_config.py (回写 endpoints 到 auth_config.yml)"
python3 scripts/update_auth_config.py || die "update_auth_config failed"
ok "auth_config.yml updated"

if [[ $SKIP_WS -eq 0 ]]; then
  step "5/7 bin/deploy-ws (build → push → deploy TCS ecan-graphql-ws)"
  bash "$CB_DIR/bin/deploy-ws" || die "deploy-ws failed (用 --skip-ws 跳过)"
  ok "ecan-graphql-ws (TCS) deployed; WS_TCS_URL 已回写到 .env.local"

  step "6/7 sync-tcb-env.sh (再次,把新的 WS_TCS_URL 推到 SCF env)"
  ./scripts/sync-tcb-env.sh || die "sync-tcb-env (round 2) failed"
  ok "WS_TCS_URL synced to SCF env"
else
  echo
  echo -e "${YELLOW}  ⚠️  跳过 WS cloudrun 部署 (--skip-ws)${NC}"
fi

step "7/7 verify_websocket_endpoints.sh (curl /healthz + /publish + e2e WS)"
bash "$ROOT/scripts/cn/verify_websocket_endpoints.sh" || \
  die "WS service not healthy — check WS_TCS_URL / WS_PUSH_SECRET / cloudrun logs"
ok "WS service + push + e2e all healthy"

echo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ✅ CN deploy + verify complete${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo -e "${YELLOW}下一步 (你必须做一次):${NC}"
echo "  - 客户端连接地址 (auth_config.yml APPSYNC.WS_ENDPOINT) 已自动回写"
echo "  - 给 cn worker / cn agent 加 WS_TCS_URL + WS_PUSH_SECRET 环境变量 (部署日志里有)"
echo "  - 测试客户端订阅: wscat -c <WS_TCS_URL 转换的 wss://> --protocol graphql-ws"