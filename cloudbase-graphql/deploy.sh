#!/bin/bash
# ============================================================
# eCan.ai TCB 云函数部署脚本
# ============================================================
#
# 策略: 小 zip (不含 node_modules) + --install-dependency true
#   TCB COS 上传限制 60s, node_modules (~150MB) 会超时.
#   改由 TCB 云端运行 npm install,上传仅 ~100KB 源代码.
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
    echo -e "  → 部署 ecan-graphql-api (functions/ecan-graphql-api/ 含完整 node_modules)..."
    cloudbase functions:deploy ecan-graphql-api \
        --env-id "$TCB_ENV_ID" \
        --dir functions/ecan-graphql-api \
        --install-dependency false \
        --force 2>&1
    echo -e "    ✓ ecan-graphql-api 部署完成"

    echo -e "  → 打包 ecan-graphql-sse..."
    ./scripts/bundle-sse.sh
    echo -e "  → 部署 ecan-graphql-sse..."
    cloudbase functions:deploy ecan-graphql-sse \
        --env-id "$TCB_ENV_ID" \
        --dir /tmp/sse-pkg \
        --install-dependency false \
        --force 2>&1
    echo -e "  ✓ ecan-graphql-sse 部署完成"

    # ============ 4b. 自动版本快照 ============
    # 每次 deploy 后自动快照,确保可回滚
    echo -e "${YELLOW}📌 创建版本快照...${NC}"
    for FN in ecan-graphql-api ecan-graphql-sse; do
      VER_DESC="$(git rev-parse --short HEAD 2>/dev/null || echo 'local') $(date '+%Y-%m-%d %H:%M')"
      cloudbase fn publish-version "$FN" --env-id "$TCB_ENV_ID" "$VER_DESC" 2>&1 | grep -v "^$" | head -2 || true
    done

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

    echo -e "  → 打包 ecan-graphql-sse..."
    ./scripts/bundle-sse.sh
    echo -e "  → 部署 ecan-graphql-sse..."
    tcb fn deploy ecan-graphql-sse \
        --env-id "$TCB_ENV_ID" \
        --code /tmp/sse-pkg \
        --handler index.main \
        --runtime Nodejs20.19 \
        --memory 256 \
        --timeout 300 \
        --region ap-shanghai
    echo -e "  ✓ ecan-graphql-sse 部署完成"
fi
echo ""

# ============ 5. 同步环境变量 ============
echo -e "${YELLOW}⚙️  同步环境变量到 TCB...${NC}"
./scripts/sync-tcb-env.sh 2>&1 | grep -v "^$"
echo ""

# ============ 6. 配置 HTTP 路由 ============
echo -e "${YELLOW}🔔 配置 HTTP 路由...${NC}"
DOMAIN="sccb0-d0gc5398xf028be6a.service.tcloudbase.com"

echo "  → /api/events → ecan-graphql-sse"
yes | cloudbase routes edit \
    --env-id "$TCB_ENV_ID" \
    --data "{\"domain\":\"$DOMAIN\",\"routes\":[{\"path\":\"/api/events\",\"upstreamResourceType\":\"SCF\",\"upstreamResourceName\":\"ecan-graphql-sse\",\"enable\":true,\"enableAuth\":false,\"enablePathTransmission\":true}]}" \
    2>&1 | grep -v "^y$" | tail -2

for R in "/ws/push" "/ws/status"; do
    echo "  → 删除旧路由 $R"
    yes | cloudbase routes delete "$DOMAIN" --path "$R" --env-id "$TCB_ENV_ID" 2>&1 | grep -v "^y$" | tail -1
done
echo ""

# ============ 7. 完成 ============
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ✅ 部署完成！${NC}"
echo -e "${GREEN}========================================${NC}\n"
echo -e "GraphQL: ${BLUE}https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/api/graphql${NC}"
echo -e "SSE:     ${BLUE}https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/api/events${NC}\n"
echo -e "⚠️  注意: TCB 云端安装依赖需要 1-2 分钟,部署后请等 2 分钟再测试。\n"
rm -f "$ZIP_FILE"
