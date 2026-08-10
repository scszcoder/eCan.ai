#!/bin/bash
# ============================================================
# eCan.ai TCB 云函数部署脚本
# ============================================================
#
# 策略: 小 zip (不含 node_modules) + --install-dependency true
#   TCB COS 上传限制 60s, node_modules (~150MB) 会超时.
#   改由 TCB 云端运行 npm install,上传仅 ~100KB 源代码.
#
# ⚠️ 注意: WS 服务 (graphql-ws) 不再部署为 SCF 云函数.
#   请改用 ./deploy-ws-tcs.sh 部署到 TCB 云托管 (TCS).
#
# 使用方式：
#   ./deploy.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  eCan.ai TCB 云函数部署脚本${NC}"
echo -e "${BLUE}========================================${NC}\n"

# ============ 1. 检查环境 ============
echo -e "${YELLOW}📋 检查环境...${NC}"
command -v node > /dev/null && echo -e "  ✓ Node.js: $(node -v)"
command -v npm  > /dev/null && echo -e "  ✓ npm: $(npm -v)"
[ -f ".env.local" ] && echo -e "  ✓ .env.local 存在" || { echo -e "${RED}❌ .env.local 不存在${NC}"; exit 1; }

# ============ 2. 安装本地依赖 + prisma generate ============
echo -e "${YELLOW}📦 本地安装依赖 + 生成 Prisma Client...${NC}"
npm install --ignore-scripts 2>&1 | tail -3
npx prisma generate 2>&1 | tail -2
echo -e "  ✓ 完成\n"

# ============ 3. 同步源码到部署目录 ============
echo -e "${YELLOW}📦 同步源码到 functions/ecan-graphql-api/...${NC}"
# functions/ecan-graphql-api/ 包含完整的 node_modules (已在本地安装).
# 只需要把根目录的源码同步过去.
FA="functions/ecan-graphql-api"
cp index.js "$FA/root-index.js"
cp event-bus.js auth.js tcb-init.js context-helpers.js health-check.js "$FA/"
cp -r services resolvers compat prisma storage scheduler "$FA/" 2>/dev/null
echo -e "  ✓ 同步完成 (部署目录含 $(du -sh $FA | cut -f1))\n"

# ============ 4. 部署到 TCB ============
echo -e "${YELLOW}☁️  部署到腾讯云...${NC}"
source .env.local

if [ -z "$TCB_ENV_ID" ]; then
    echo -e "${RED}❌ TCB_ENV_ID 未配置${NC}"; exit 1; fi

CLI=""
command -v cloudbase > /dev/null && CLI="cloudbase"
command -v tcb      > /dev/null && [ -z "$CLI" ] && CLI="tcb"
if [ -z "$CLI" ]; then echo -e "${RED}❌ cloudbase / tcb CLI 未安装${NC}"; exit 1; fi
echo -e "  使用: $CLI"

if [ "$CLI" = "cloudbase" ]; then
    echo -e "  → 部署 ecan-graphql-api..."
    cloudbase functions:deploy ecan-graphql-api \
        --env-id "$TCB_ENV_ID" \
        --dir functions/ecan-graphql-api \
        --install-dependency false \
        --force 2>&1
    echo -e "    ✓ ecan-graphql-api 部署完成"

    # ============ 4b. 自动版本快照 ============
    echo -e "${YELLOW}📌 创建版本快照...${NC}"
    VER_DESC="$(git rev-parse --short HEAD 2>/dev/null || echo 'local') $(date '+%Y-%m-%d %H:%M')"
    cloudbase fn publish-version "ecan-graphql-api" --env-id "$TCB_ENV_ID" "$VER_DESC" 2>&1 | grep -v "^$" | head -2 || true

    echo ""
    echo -e "${YELLOW}⚠️  注意: WS 服务请单独部署${NC}"
    echo -e "  → 参考: ./deploy-ws-tcs.sh --help"
    echo -e "  → 部署 TCS 后运行: ./scripts/sync-tcb-env.sh"

elif [ "$CLI" = "tcb" ]; then
    echo -e "  → 部署 ecan-graphql-api..."
    tcb fn deploy ecan-graphql-api \
        --env-id "$TCB_ENV_ID" \
        --code . \
        --handler index.main \
        --runtime Nodejs20.19 \
        --memory 512 \
        --timeout 300 \
        --region ap-shanghai
    echo -e "  ✓ ecan-graphql-api 部署完成"

    echo ""
    echo -e "${YELLOW}⚠️  注意: WS 服务请单独部署${NC}"
    echo -e "  → 参考: ./deploy-ws-tcs.sh --help"
fi
echo ""

# ============ 5. 同步环境变量 ============
echo -e "${YELLOW}⚙️  同步环境变量到 TCB...${NC}"
./scripts/sync-tcb-env.sh 2>&1 | grep -v "^$"
echo ""

# ============ 6. 配置 HTTP 路由 ============
echo -e "${YELLOW}🔔 配置 HTTP 路由...${NC}"
DOMAIN="sccb0-d0gc5398xf028be6a.service.tcloudbase.com"

echo "  → 清理旧的 /api/events 路由 (SSE 已废弃)"
yes | cloudbase routes delete "$DOMAIN" --path "/api/events" --env-id "$TCB_ENV_ID" 2>&1 | grep -v "^y$" | tail -1 || true
echo ""
echo -e "${YELLOW}⚠️  WS 路由由 deploy-ws-tcs.sh 配置 (tcb routes add)${NC}"
echo -e "  参考: ./deploy-ws-tcs.sh"

# ============ 7. 完成 ============
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ✅ 部署完成！${NC}"
echo -e "${GREEN}========================================${NC}\n"
echo -e "GraphQL: ${BLUE}https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/api/graphql${NC}"
echo -e "WS:      ${BLUE}wss://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/ws${NC}\n"
echo -e "⚠️  注意: TCB 云端安装依赖需要 1-2 分钟,部署后请等 2 分钟再测试。\n"
rm -f "$ZIP_FILE"
