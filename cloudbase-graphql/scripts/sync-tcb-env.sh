#!/bin/bash
# ============================================================
# 推 .env.local 的敏感变量到 TCB 云函数环境变量
# ============================================================
#
# 用法：
#   ./scripts/sync-tcb-env.sh
#
# 关键：所有 secret 只从 .env.local 读，**绝不写入 cloudbaserc.json**，**绝不进 git**。
# cloudbaserc.json 里的 secret 字段是占位符 __SET_VIA_TCB_CONSOLE_OR_LOCAL_ENV__。
#
# 依赖：
#   npm install -g @cloudbase/cli
#   cloudbase login
#

set -e

PINK='\033[1;35m'
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  同步 .env.local → TCB 云函数环境变量${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Check CLI
if ! command -v cloudbase &> /dev/null && ! command -v tcb &> /dev/null; then
  echo -e "${RED}❌ cloudbase / tcb CLI 未安装${NC}"
  echo -e "${YELLOW}  安装: npm install -g @cloudbase/cli${NC}"
  exit 1
fi

# Load .env.local
if [ ! -f ".env.local" ]; then
  echo -e "${RED}❌ .env.local 不存在${NC}"
  exit 1
fi
set -a
. .env.local
set +a

if [ -z "$TCB_ENV_ID" ]; then
  echo -e "${RED}❌ TCB_ENV_ID 未配置${NC}"
  exit 1
fi

# Sanity: must not be the placeholder
if [[ "$DATABASE_URL" == *"__SET_VIA_TCB_CONSOLE_OR_LOCAL_ENV__"* ]]; then
  echo -e "${RED}❌ DATABASE_URL 还是占位符，请先在 .env.local 填写真实密码${NC}"
  exit 1
fi

if [[ "$WEBSOCKET_PUSH_SECRET" == *"__SET_VIA_TCB_CONSOLE_OR_LOCAL_ENV__"* ]]; then
  echo -e "${RED}❌ WEBSOCKET_PUSH_SECRET 还是占位符${NC}"
  # auto-generate one
  WEBSOCKET_PUSH_SECRET=$(node -e "console.log(require('crypto').randomBytes(32).toString('hex'))")
  echo -e "${YELLOW}  → 自动生成新密钥: $WEBSOCKET_PUSH_SECRET${NC}"
fi

# --- Detect CLI ---
USE_CLOUDBASE=0
USE_TCB=0
command -v cloudbase &> /dev/null && USE_CLOUDBASE=1
command -v tcb &> /dev/null && USE_TCB=1

upsert_env() {
  local func=$1
  local key=$2
  local value=$3
  echo -e "${PINK}  → $func.$key${NC}"
  if [ $USE_CLOUDBASE -eq 1 ]; then
    cloudbase functions:update-config "${func}" \
      --env-id "${TCB_ENV_ID}" \
      --env "${key}=${value}" 2>/dev/null || \
    cloudbase functions:update-config "${func}" \
      --env-id "${TCB_ENV_ID}" \
      --env "${key}=${value}"
  elif [ $USE_TCB -eq 1 ]; then
    tcb fn config update "${func}" \
      --env-id "${TCB_ENV_ID}" \
      --key "${key}" \
      --value "${value}"
  fi
}

# 1. GraphQL API
#    WEBSOCKET_PUSH_SECRET 仅在 websocket.js 内部使用，不在 ecan-graphql-api 中
#    WEBSOCKET_FUNCTION_NAME 已在 cloudbaserc.json 中作为静态值，重复推送仅是冗余
echo -e "${YELLOW}⚙️  配置 ecan-graphql-api${NC}"
upsert_env ecan-graphql-api DATABASE_URL "$DATABASE_URL"
upsert_env ecan-graphql-api COS_BUCKET "$COS_BUCKET"
upsert_env ecan-graphql-api COS_REGION "$COS_REGION"
upsert_env ecan-graphql-api TCB_REGION "ap-shanghai"
upsert_env ecan-graphql-api NODE_ENV "production"
[ -n "$TENCENT_SCHEDULER_FUNCTION" ] && upsert_env ecan-graphql-api TENCENT_SCHEDULER_FUNCTION "$TENCENT_SCHEDULER_FUNCTION"
[ -n "$TENCENT_SCF_NAMESPACE" ]      && upsert_env ecan-graphql-api TENCENT_SCF_NAMESPACE "$TENCENT_SCF_NAMESPACE"
[ -n "$TENCENT_REGION" ]             && upsert_env ecan-graphql-api TENCENT_REGION "$TENCENT_REGION"

# 2. WebSocket
echo -e "${YELLOW}⚙️  配置 ecan-websocket${NC}"
upsert_env ecan-websocket WEBSOCKET_PUSH_SECRET "$WEBSOCKET_PUSH_SECRET"
upsert_env ecan-websocket TCB_REGION "ap-shanghai"
upsert_env ecan-websocket NODE_ENV "production"
upsert_env ecan-websocket COS_BUCKET "$COS_BUCKET"
upsert_env ecan-websocket COS_REGION "$COS_REGION"

# 3. Health
echo -e "${YELLOW}⚙️  配置 ecan-health${NC}"
upsert_env ecan-health TCB_REGION "ap-shanghai"
upsert_env ecan-health NODE_ENV "production"

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  ✅ 环境变量已同步到 TCB 控制台${NC}"
echo -e "${GREEN}========================================${NC}\n"
echo -e "⚠️  提醒：密码只来自 .env.local（已 gitignore）。"
echo -e "   cloudbaserc.json 仍是占位符，绝无明文密码。\n"
