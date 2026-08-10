#!/bin/bash
# ============================================================
# eCan.ai TCB 云函数部署脚本
# ============================================================
#
# 使用方式：
#   ./deploy.sh
#
# 前提条件：
#   1. 已安装 Node.js 16+
#   2. 已安装腾讯云 CLI (tcli)
#   3. 已购买云数据库 PostgreSQL
#   4. 已配置 .env.local（复制自 .env.local.example）

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目目录
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  eCan.ai TCB 云函数部署脚本${NC}"
echo -e "${BLUE}========================================${NC}\n"

# ============ 1. 检查环境 ============
echo -e "${YELLOW}📋 检查环境...${NC}"

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ 错误: Node.js 未安装${NC}"
    exit 1
fi
echo -e "  ✓ Node.js: $(node -v)"

# 检查 npm
if ! command -v npm &> /dev/null; then
    echo -e "${RED}❌ 错误: npm 未安装${NC}"
    exit 1
fi
echo -e "  ✓ npm: $(npm -v)"

# 检查环境变量文件
if [ ! -f ".env.local" ]; then
    echo -e "${YELLOW}⚠️  警告: .env.local 不存在，复制模板...${NC}"
    cp .env.local.example .env.local
    echo -e "${YELLOW}  请编辑 .env.local 填写正确的配置！${NC}"
    exit 1
fi
echo -e "  ✓ 环境变量文件存在"

echo ""

# ============ 2. 安装依赖 ============
echo -e "${YELLOW}📦 安装依赖...${NC}"
npm install
echo -e "  ✓ 依赖安装完成\n"

# ============ 3. 生成 Prisma Client ============
echo -e "${YELLOW}🔧 生成 Prisma Client...${NC}"
npx prisma generate
echo -e "  ✓ Prisma Client 生成完成\n"

# ============ 4. 打包代码 ============
echo -e "${YELLOW}📦 打包代码...${NC}"

# 创建临时目录
DEPLOY_DIR=".deploy_tmp"
rm -rf "$DEPLOY_DIR"
mkdir -p "$DEPLOY_DIR"

# 复制必要文件
echo "  复制文件..."
# 顶层 JS 模块：index.js 显式 require 这些，必须上传
cp -r node_modules "$DEPLOY_DIR/"
cp package.json "$DEPLOY_DIR/"
cp -r prisma "$DEPLOY_DIR/"
cp -r storage "$DEPLOY_DIR/"
cp -r scheduler "$DEPLOY_DIR/"
cp -r compat "$DEPLOY_DIR/"
cp -r services "$DEPLOY_DIR/"
cp -r resolvers "$DEPLOY_DIR/"   # index.js → require('./resolvers')
cp -r functions "$DEPLOY_DIR/"  # SCF entry points

# 顶层辅助模块
cp auth.js "$DEPLOY_DIR/"          # resolveIdentity / authenticatedOwner
cp tcb-init.js "$DEPLOY_DIR/"      # getPrisma / ensureConnected / disconnect
cp context-helpers.js "$DEPLOY_DIR/"  # assertOwnedAgent
cp event-bus.js "$DEPLOY_DIR/"     # subscriptions bus
cp health-check.js "$DEPLOY_DIR/"  # ecan-health SCF

# 复制入口文件
cp index.js "$DEPLOY_DIR/"

# 进入打包目录并安装依赖（用于生成最终包）
cd "$DEPLOY_DIR"
npm install --production

# === Bundle size reduction (cos upload 60s timeout) ===
# Drop dev-only trees that npm sometimes pulls in transitively.
echo "  瘦包..."
# Prisma engine binaries: SCF runtime is Node 20 on Linux. We only need the actively
# loaded engine. Prisma keeps many variations in node_modules/.prisma/client and
# node_modules/@prisma/engines. We delete the ones we don't need.
# Keep:
#   - libquery_engine-rhel-openssl-3.0.x.so.node  (SCF runtime, Node 20)
# Drop:
#   - linux-musl (Alpine, not used by SCF default runtime)
#   - darwin (any macOS dev)
#   - older openssl-1.0.x (Node 20 ships openssl 3.0.x)
#   - schema-engine-* (only used by `prisma migrate` CLI, not at runtime)
#   - PRISMA_FORCE_INTROSPECTION engine files (not relevant here)
find node_modules \( -path 'node_modules/.prisma/client/*darwin*' -o \
                    -path 'node_modules/.prisma/client/*linux-musl*' -o \
                    -path 'node_modules/.prisma/client/*openssl-1.0*' \) -delete 2>/dev/null
find node_modules/@prisma/engines \( -name '*darwin*' -o -name '*linux-musl*' \) -delete 2>/dev/null
# Same paths under @prisma/client — the runtime engine binary lives there too.
find node_modules/@prisma/client \( -name '*darwin*' -o -name '*linux-musl*' -o -name '*openssl-1.0*' \) -delete 2>/dev/null
# @cloudbase/cli is dev-only (CLI tooling, not used at runtime).
rm -rf node_modules/@cloudbase/cli 2>/dev/null
# The prisma CLI itself (58MB) — not loaded at runtime.
rm -rf node_modules/prisma 2>/dev/null
# @prisma sub-trees only used by the prisma CLI
rm -rf node_modules/@prisma/fetch-engine node_modules/@prisma/get-platform node_modules/@prisma/debug 2>/dev/null
# core-js-pure is a transitive polyfill; SCF Node 20 doesn't need it.
rm -rf node_modules/core-js-pure 2>/dev/null
# @prisma/client runtime + generator-build + scripts are only used by `prisma generate`
rm -rf node_modules/@prisma/client/runtime node_modules/@prisma/client/generator-build node_modules/@prisma/client/scripts 2>/dev/null
# Strip JS source maps (.map) and TypeScript declaration files (.d.ts).
find node_modules -name '*.map' -type f -delete 2>/dev/null
find node_modules -name '*.d.ts' -type f -delete 2>/dev/null
# npm bin directory is not needed at runtime.
rm -rf node_modules/.bin 2>/dev/null
# Strip test/example/docs subdirs.
find node_modules -type d \( -name test -o -name tests -o -name example -o -name examples -o -name docs \) -exec rm -rf {} + 2>/dev/null
# Strip docs/metadata files top-level.
find node_modules -type f \( -name '*.md' -o -name 'README*' -o -name 'LICENSE*' -o -name 'CHANGELOG*' -o -name '*.markdown' \) -delete 2>/dev/null
# tencentcloud-sdk-nodejs is a leftover from the WS push path; nothing requires it.
rm -rf node_modules/tencentcloud-sdk-nodejs 2>/dev/null

cd ..

# 打包
ZIP_FILE="ecan-graphql-deploy.zip"
rm -f "$ZIP_FILE"
cd "$DEPLOY_DIR"
zip -r "../$ZIP_FILE" . -x "node_modules/.cache/*" -x "*.map" -x ".git/*"
cd ..

# 清理临时目录
rm -rf "$DEPLOY_DIR"

echo -e "  ✓ 打包完成: $ZIP_FILE ($(du -h "$ZIP_FILE" | cut -f1))\n"

# ============ 4. 部署到 TCB（云函数） ============
echo -e "${YELLOW}☁️  部署云函数到腾讯云...${NC}"

# 读取配置
source .env.local

if [ -z "$TCB_ENV_ID" ]; then
    echo -e "${RED}❌ 错误: TCB_ENV_ID 未配置${NC}"
    echo -e "${YELLOW}  请在 .env.local 中配置 TCB_ENV_ID${NC}"
    exit 1
fi

# 检查 CLI
if ! command -v tcb &> /dev/null && ! command -v cloudbase &> /dev/null; then
    echo -e "${RED}❌ 错误: tcb/cloudbase CLI 未安装${NC}"
    echo -e "${YELLOW}  安装: npm install -g @cloudbase/cli${NC}"
    exit 1
fi

# 使用 cloudbase framework 部署（支持云端构建和触发器自动配置）
if command -v cloudbase &> /dev/null; then
    echo -e "  使用 cloudbase framework 部署..."
    
    # 部署 GraphQL API（包含 HTTP 触发器）
    echo -e "  → 部署 ecan-graphql-api..."
    cloudbase deploy . \
        --service-name ecan-graphql-api \
        --env-id "$TCB_ENV_ID" \
        --project-root . \
        --exclude "node_modules/*" \
        --exclude ".env.local" \
        --exclude ".env.*" \
        --exclude "*.test.js" \
        --exclude "test/**" \
        --exclude "scripts/**" \
        --exclude "deploy.sh" \
        --exclude "README.md" \
        --exclude "docs/**"
    echo -e "    ✓ ecan-graphql-api 部署完成"

    # 部署独立 SSE 函数 (sse-bridge)
    echo -e "  → 部署 ecan-graphql-sse..."
    ./scripts/bundle-sse.sh
    cloudbase functions:deploy ecan-graphql-sse \
        --env-id "$TCB_ENV_ID" \
        --code /tmp/sse-pkg \
        --handler index.main \
        --runtime Nodejs20.19 \
        --memory 256 \
        --timeout 300
    echo -e "    ✓ ecan-graphql-sse 部署完成"

elif command -v tcb &> /dev/null; then
    # 使用 tcb CLI
    echo -e "  使用 tcb CLI 部署..."

    # GraphQL API
    tcb fn deploy ecan-graphql-api \
        --env-id "$TCB_ENV_ID" \
        --code . \
        --handler index.main \
        --runtime Nodejs20.19 \
        --memory 512 \
        --timeout 60 \
        --region ap-shanghai

    # SSE 独立函数
    ./scripts/bundle-sse.sh
    tcb fn deploy ecan-graphql-sse \
        --env-id "$TCB_ENV_ID" \
        --code /tmp/sse-pkg \
        --handler index.main \
        --runtime Nodejs20.19 \
        --memory 256 \
        --timeout 300 \
        --region ap-shanghai

    # HTTP 触发器
    tcb fn trigger create ecan-graphql-api \
        --env-id "$TCB_ENV_ID" \
        --trigger-name http-trigger \
        --type http \
        --method GET,POST \
        --path /api/graphql

    # SSE 触发器
    tcb fn trigger create ecan-graphql-sse \
        --env-id "$TCB_ENV_ID" \
        --trigger-name http-trigger \
        --type http \
        --method GET,POST \
        --path /api/events
fi

echo ""

# ============ 5. 配置环境变量（自动） ============
echo -e "${YELLOW}⚙️  配置环境变量...${NC}"

# 必需变量检查
if [ -z "$DATABASE_URL" ] || [ -z "$COS_BUCKET" ] || [ -z "$COS_REGION" ] || [ -z "$SSE_PUSH_SECRET" ]; then
    echo -e "${RED}❌ 错误: 缺少必需的环境变量${NC}"
    echo -e "  请在 .env.local 中配置:"
    [ -z "$DATABASE_URL" ] && echo "    - DATABASE_URL"
    [ -z "$COS_BUCKET" ] && echo "    - COS_BUCKET"
    [ -z "$COS_REGION" ] && echo "    - COS_REGION"
    [ -z "$SSE_PUSH_SECRET" ] && echo "    - SSE_PUSH_SECRET"
    exit 1
fi

# 自动配置环境变量（TCB CLI 支持）
if command -v tcb &> /dev/null; then
    echo -e "  → 配置 ecan-graphql-api 环境变量..."
    tcb env:update ecan-graphql-api \
        --env-id "$TCB_ENV_ID" \
        --database-url "$DATABASE_URL" \
        --cos-bucket "$COS_BUCKET" \
        --cos-region "$COS_REGION" \
        --node-env "production" \
        --sse-push-secret "${SSE_PUSH_SECRET}" \
        --tcb-region "ap-shanghai" \
        --tcb-env-id "${TCB_ENV_ID}" 2>/dev/null || \
    echo -e "    ⚠️  请在控制台手动配置环境变量"

    echo -e "  → 配置 ecan-graphql-sse 环境变量..."
    tcb env:update ecan-graphql-sse \
        --env-id "$TCB_ENV_ID" \
        --sse-push-secret "${SSE_PUSH_SECRET}" \
        --node-env "production" \
        --tcb-region "ap-shanghai" \
        --tcb-env-id "${TCB_ENV_ID}" 2>/dev/null || \
    echo -e "    ⚠️  请在控制台手动配置环境变量"
elif command -v cloudbase &> /dev/null; then
    # cloudbase framework 使用 .env 文件管理环境变量
    # 用 600 权限、mktemp 模式，避免任何路径被 git 跟踪
    ENV_TCB="$(mktemp -t ecan-env.XXXXXX).tcb"
    chmod 600 "$ENV_TCB"
    cat > "$ENV_TCB" << EOF
# TCB 环境变量（自动生成，仅 deferred 部署使用；含密码，权限 600）
DATABASE_URL=${DATABASE_URL}
COS_BUCKET=${COS_BUCKET}
COS_REGION=${COS_REGION}
NODE_ENV=production
TCB_REGION=ap-shanghai
TCB_ENV_ID=${TCB_ENV_ID}
SSE_PUSH_SECRET=${SSE_PUSH_SECRET:-$(openssl rand -hex 32)}
EOF
    echo -e "  ✓ 已生成临时 env 文件（权限 600，仅当前会话可用）"
    echo -e "    ${ENV_TCB}"
    echo -e "  ✓ 使用 cloudbase framework 部署时会自动注入环境变量"
    # 部署后立即清理（即使部署失败也清理）
    trap "rm -f '$ENV_TCB'" EXIT
fi

echo -e "  ✓ 环境变量配置完成\n"

# ============ 7. 配置触发器 ============
echo -e "${YELLOW}🔔 配置触发器...${NC}"

if command -v tcb &> /dev/null || command -v cloudbase &> /dev/null; then
    echo -e "  创建 HTTP 触发器..."
    echo -e "  ⚠️  请在 TCB 控制台手动创建以下触发器："
    echo -e "  GraphQL:"
    echo -e "     - 云函数 → ecan-graphql-api → 触发方式 → HTTP 触发"
    echo -e "     - 路径: /api/graphql"
    echo -e "     - 方法: GET, POST"
    echo -e "  SSE:"
    echo -e "     - 云函数 → ecan-graphql-sse → 触发方式 → HTTP 触发"
    echo -e "     - 路径: /api/events"
    echo -e "     - 方法: GET"
    echo -e "  ecan-graphql-sse /publish 内部路径无需对外触发 (经 GraphQL → HTTP POST 调用)"
else
    echo -e "  ⚠️  请手动在 TCB 控制台创建触发器"
fi

echo ""

# ============ 8. 回写端点到 auth_config.yml ============
echo -e "${YELLOW}📝 回写端点到 auth_config.yml...${NC}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
UPDATE_SCRIPT="$SCRIPT_DIR/scripts/update_auth_config.py"

if [ -f "$UPDATE_SCRIPT" ]; then
    python3 "$UPDATE_SCRIPT"
    echo -e "  ✓ auth_config.yml updated\n"
else
    echo -e "${YELLOW}⚠️  update_auth_config.py not found, skipping config update${NC}"
    echo -e "  端点信息 (手动填入 apps/cn/config/auth_config.yml):"
    echo -e "    GRAPHQL_ENDPOINT: $TCB_API_URL"
    echo ""
fi

# ============ 9. 完成 ============
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ✅ 部署完成！${NC}"
echo -e "${GREEN}========================================${NC}\n"

echo -e "API 地址: ${BLUE}$TCB_API_URL${NC}\n"

echo -e "后续步骤："
echo -e "  1. ${YELLOW}配置环境变量${NC} - 在 TCB 控制台设置 DATABASE_URL（PostgreSQL）"
echo -e "  2. ${YELLOW}配置 VPC${NC} - 将云函数加入数据库同 VPC"
echo -e "  3. ${YELLOW}创建触发器${NC} - GraphQL HTTP + SSE HTTP (/api/events)"
echo -e "  4. ${YELLOW}迁移数据库${NC} - 运行 npm run db:deploy"
echo -e "  5. ${YELLOW}测试 API${NC} - 访问 Playground"
echo -e "  6. ${YELLOW}部署 Worker Launcher${NC} - TKE 集群 + 镜像（apps/cn/services/worker-launcher）"
echo -e "  7. ${YELLOW}运行覆盖测试${NC} - npm run schema:coverage && npm run test:unit\n"

# 清理打包文件
rm -f "$ZIP_FILE"

echo -e "📖 详细文档: ../docs/CN_VERSION_GUIDE.md\n"
