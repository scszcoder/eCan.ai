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
cp -r node_modules "$DEPLOY_DIR/"
cp package.json "$DEPLOY_DIR/"
cp -r prisma "$DEPLOY_DIR/"
cp -r storage "$DEPLOY_DIR/"
cp -r scheduler "$DEPLOY_DIR/"
cp -r compat "$DEPLOY_DIR/"
cp -r services "$DEPLOY_DIR/"

# 复制 index.js（主入口）
cp index.js "$DEPLOY_DIR/"
cp websocket.js "$DEPLOY_DIR/"

# 进入打包目录并安装依赖（用于生成最终包）
cd "$DEPLOY_DIR"
npm install --production
cd ..

# 打包
ZIP_FILE="ecan-graphql-deploy.zip"
rm -f "$ZIP_FILE"
cd "$DEPLOY_DIR"
zip -r "../$ZIP_FILE" . -x "node_modules/.cache/*" -x "*.map" -x ".git/*"
cd ..

# 清理临时目录
rm -rf "$DEPLOY_DIR"

echo -e "  ✓ 打包完成: $ZIP_FILE\n"

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
    
    # 部署 WebSocket 函数
    echo -e "  → 部署 ecan-websocket..."
    cloudbase functions:deploy ecan-websocket \
        --env-id "$TCB_ENV_ID" \
        --code . \
        --handler websocket.main \
        --runtime Nodejs20.19 \
        --memory 512 \
        --timeout 300
    echo -e "    ✓ ecan-websocket 部署完成"
    
    # 配置 WebSocket 触发器
    echo -e "  → 配置 WebSocket 触发器..."
    cloudbase gateway:create \
        --env-id "$TCB_ENV_ID" \
        --api-id "ecan-websocket-ws" \
        --service-name ecan-websocket \
        --service-path /ws \
        --service-port 9000 \
        --protocol ws 2>/dev/null || \
    echo -e "    ⚠️  WebSocket 网关请在控制台手动配置"
    
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
    
    # WebSocket
    tcb fn deploy ecan-websocket \
        --env-id "$TCB_ENV_ID" \
        --code . \
        --handler websocket.main \
        --runtime Nodejs20.19 \
        --memory 512 \
        --timeout 300 \
        --region ap-shanghai
    
    # HTTP 触发器
    tcb fn trigger create ecan-graphql-api \
        --env-id "$TCB_ENV_ID" \
        --trigger-name http-trigger \
        --type http \
        --method GET,POST \
        --path /api/graphql
fi

echo ""

# ============ 5. 配置环境变量（自动） ============
echo -e "${YELLOW}⚙️  配置环境变量...${NC}"

# 必需变量检查
if [ -z "$DATABASE_URL" ] || [ -z "$COS_BUCKET" ] || [ -z "$COS_REGION" ]; then
    echo -e "${RED}❌ 错误: 缺少必需的环境变量${NC}"
    echo -e "  请在 .env.local 中配置:"
    [ -z "$DATABASE_URL" ] && echo "    - DATABASE_URL"
    [ -z "$COS_BUCKET" ] && echo "    - COS_BUCKET"
    [ -z "$COS_REGION" ] && echo "    - COS_REGION"
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
        --tcb-region "ap-shanghai" 2>/dev/null || \
    echo -e "    ⚠️  请在控制台手动配置环境变量"
    
    echo -e "  → 配置 ecan-websocket 环境变量..."
    tcb env:update ecan-websocket \
        --env-id "$TCB_ENV_ID" \
        --websocket-push-secret "${WEBSOCKET_PUSH_SECRET:-$(openssl rand -hex 32)}" \
        --node-env "production" \
        --tcb-region "ap-shanghai" 2>/dev/null || \
    echo -e "    ⚠️  请在控制台手动配置环境变量"
elif command -v cloudbase &> /dev/null; then
    # cloudbase framework 使用 .env 文件管理环境变量
    # 生成 .env 文件供 cloudbase 使用
    cat > .env.tcb << EOF
# TCB 环境变量（自动生成）
DATABASE_URL=${DATABASE_URL}
COS_BUCKET=${COS_BUCKET}
COS_REGION=${COS_REGION}
NODE_ENV=production
TCB_REGION=ap-shanghai
WEBSOCKET_PUSH_SECRET=${WEBSOCKET_PUSH_SECRET:-$(openssl rand -hex 32)}
EOF
    echo -e "  ✓ 已生成 .env.tcb 文件"
    echo -e "  ✓ 使用 cloudbase framework 部署时会自动注入环境变量"
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
    echo -e "  WebSocket:"
    echo -e "     - 云函数 → ecan-websocket → 触发方式 → API 网关 WebSocket"
    echo -e "     - 启用 SCF 集成"
    echo -e "     - 路径: /ws"
else
    echo -e "  ⚠️  请手动在 TCB 控制台创建触发器"
fi

echo ""

# ============ 8. 完成 ============
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ✅ 部署完成！${NC}"
echo -e "${GREEN}========================================${NC}\n"

echo -e "API 地址: ${BLUE}$TCB_API_URL${NC}\n"

echo -e "后续步骤："
echo -e "  1. ${YELLOW}配置环境变量${NC} - 在 TCB 控制台设置 DATABASE_URL（PostgreSQL）"
echo -e "  2. ${YELLOW}配置 VPC${NC} - 将云函数加入数据库同 VPC"
echo -e "  3. ${YELLOW}创建触发器${NC} - GraphQL HTTP + ecan-websocket WebSocket"
echo -e "  4. ${YELLOW}迁移数据库${NC} - 运行 npm run db:deploy"
echo -e "  5. ${YELLOW}测试 API${NC} - 访问 Playground"
echo -e "  6. ${YELLOW}部署 Worker Launcher${NC} - TKE 集群 + 镜像（apps/cn/services/worker-launcher）"
echo -e "  7. ${YELLOW}运行覆盖测试${NC} - npm run schema:coverage && npm run test:unit\n"

# 清理打包文件
rm -f "$ZIP_FILE"

echo -e "📖 详细文档: ../docs/CN_VERSION_GUIDE.md\n"
