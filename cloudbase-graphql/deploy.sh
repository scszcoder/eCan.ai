#!/bin/bash
# ============================================================
# eCan.ai TCB 云函数部署脚本
# ============================================================
# 使用方式：
#   ./deploy.sh
#
# 前提条件：
#   1. 已安装 Node.js 16+
#   2. 已安装腾讯云 CLI (tcli)
#   3. 已购买 TCB PostgreSQL
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

# 复制 index.js（主入口）
cp index.js "$DEPLOY_DIR/"

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

# ============ 5. 部署到 TCB ============
echo -e "${YELLOW}☁️  部署到腾讯云...${NC}"

# 读取配置
source .env.local

if [ -z "$TCB_ENV_ID" ]; then
    echo -e "${RED}❌ 错误: TCB_ENV_ID 未配置${NC}"
    echo -e "${YELLOW}  请在 .env.local 中配置 TCB_ENV_ID${NC}"
    exit 1
fi

# 使用腾讯云 CLI 部署
# 注意：需要先安装 tcli: npm install -g @cloudbase/cli
if command -v tcb &> /dev/null; then
    echo -e "  使用 tcb CLI 部署..."
    
    # 创建或更新云函数
    tcb fn deploy ecan-graphql-api \
        --env-id "$TCB_ENV_ID" \
        --code "$ZIP_FILE" \
        --handler index.main \
        --runtime Nodejs16.13 \
        --memory 512 \
        --timeout 30 \
        --region ap-guangzhou
        
elif command -v cloudbase &> /dev/null; then
    echo -e "  使用 cloudbase CLI 部署..."
    
    cloudbase functions:deploy ecan-graphql-api \
        --env-id "$TCB_ENV_ID" \
        --code "$ZIP_FILE" \
        --handler index.main \
        --runtime Nodejs16.13 \
        --memory 512 \
        --timeout 30
        
else
    echo -e "${YELLOW}⚠️  警告: tcb/cloudbase CLI 未安装${NC}"
    echo -e "  请手动上传 $ZIP_FILE 到 TCB 控制台"
    echo -e "  1. 打开腾讯云控制台 → 云函数"
    echo -e "  2. 创建或更新函数"
    echo -e "  3. 上传代码包"
fi

echo ""

# ============ 6. 配置环境变量 ============
echo -e "${YELLOW}⚙️  配置环境变量...${NC}"

if command -v tcb &> /dev/null || command -v cloudbase &> /dev/null; then
    echo -e "  配置 PostgreSQL 连接信息..."
    
    # 注意：实际部署时需要在控制台手动配置敏感信息
    echo -e "  ⚠️  请在 TCB 控制台手动配置以下环境变量："
    echo -e "     - PG_HOST"
    echo -e "     - PG_PORT"
    echo -e "     - PG_DATABASE"
    echo -e "     - PG_USER"
    echo -e "     - PG_PASSWORD"
else
    echo -e "  ⚠️  请手动在 TCB 控制台配置环境变量"
fi

echo ""

# ============ 7. 配置触发器 ============
echo -e "${YELLOW}🔔 配置 HTTP 触发器...${NC}"

if command -v tcb &> /dev/null || command -v cloudbase &> /dev/null; then
    echo -e "  创建 HTTP 触发器..."
    echo -e "  ⚠️  请在 TCB 控制台手动创建 HTTP 触发器："
    echo -e "     1. 云函数 → 触发方式 → 添加触发器"
    echo -e "     2. 选择 HTTP 触发"
    echo -e "     3. 路径: /api/graphql"
    echo -e "     4. 方法: GET, POST"
else
    echo -e "  ⚠️  请手动在 TCB 控制台创建 HTTP 触发器"
fi

echo ""

# ============ 8. 完成 ============
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ✅ 部署完成！${NC}"
echo -e "${GREEN}========================================${NC}\n"

echo -e "API 地址: ${BLUE}$TCB_API_URL${NC}\n"

echo -e "后续步骤："
echo -e "  1. ${YELLOW}配置环境变量${NC} - 在 TCB 控制台设置 PG_* 变量"
echo -e "  2. ${YELLOW}配置 VPC${NC} - 将云函数加入 PostgreSQL 同 VPC"
echo -e "  3. ${YELLOW}创建触发器${NC} - 添加 HTTP 触发"
echo -e "  4. ${YELLOW}初始化数据库${NC} - 运行 npm run db:seed"
echo -e "  5. ${YELLOW}测试 API${NC} - 访问 Playground\n"

# 清理打包文件
rm -f "$ZIP_FILE"

echo -e "📖 详细文档: ../docs/CN_VERSION_GUIDE.md\n"
