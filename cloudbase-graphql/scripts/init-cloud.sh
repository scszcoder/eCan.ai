#!/bin/bash
# ============================================================
# eCan.ai CN 版本 - 一键初始化脚本
# 
# 功能：
#   1. 检测/创建云数据库 PostgreSQL
#   2. 检测/创建 COS 存储桶
#   3. 自动更新 .env.local
#   4. 配置 VPC（可选）
#
# 使用方式：
#   ./scripts/init-cloud.sh
#
# 前提条件：
#   1. 安装腾讯云 CLI: npm install -g @cloudbase/cli
#   2. 配置腾讯云密钥: tcb login 或 cloudbase login
# ============================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 项目目录
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo -e "${BLUE}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}  eCan.ai CN - 云资源一键初始化${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# ============ 0. 检查依赖 ============
echo -e "${YELLOW}📋 检查依赖...${NC}"

check_command() {
    if ! command -v $1 &> /dev/null; then
        echo -e "  ${RED}✗ $1${NC} 未安装"
        return 1
    fi
    echo -e "  ${GREEN}✓ $1${NC}"
    return 0
}

# 检查腾讯云 CLI
if command -v cloudbase &> /dev/null; then
    TCB_CLI="cloudbase"
    echo -e "  ${GREEN}✓ cloudbase CLI${NC}"
elif command -v tcb &> /dev/null; then
    TCB_CLI="tcb"
    echo -e "  ${GREEN}✓ tcb CLI${NC}"
else
    echo -e "  ${RED}✗ 未安装腾讯云 CLI${NC}"
    echo -e "  ${CYAN}安装: npm install -g @cloudbase/cli${NC}"
    exit 1
fi

# 检查 jq（用于 JSON 解析）
if ! command -v jq &> /dev/null; then
    echo -e "  ${YELLOW}⚠ jq 未安装，部分功能可能受限${NC}"
    echo -e "  ${CYAN}安装: brew install jq (macOS) 或 apt install jq (Linux)${NC}"
fi

# 检查 tencentcloud SDK
if ! command -v tccli &> /dev/null; then
    echo -e "  ${YELLOW}⚠ 腾讯云 CLI (tccli) 未安装${NC}"
    echo -e "  ${CYAN}安装: pip install tencentcloud-sdk-python${NC}"
    echo -e "  ${CYAN}或参考: https://cloud.tencent.com/document/product/440/34007${NC}"
fi

echo ""

# ============ 1. 读取现有配置 ============
echo -e "${YELLOW}📂 读取现有配置...${NC}"

if [ -f ".env.local" ]; then
    source .env.local
    echo -e "  ✓ 读取 .env.local"
else
    echo -e "  ${YELLOW}⚠  .env.local 不存在，将创建新文件${NC}"
fi

# 默认值
TCB_ENV_ID="${TCB_ENV_ID:-}"
COS_BUCKET="${COS_BUCKET:-}"
COS_REGION="${COS_REGION:-ap-shanghai}"
DATABASE_URL="${DATABASE_URL:-}"

echo ""

# ============ 2. 交互式配置 ============
echo -e "${YELLOW}🔧 交互式配置...${NC}"
echo -e "${CYAN}（直接回车使用默认值或已有值）${NC}"
echo ""

# TCB 环境 ID
echo -e "  ${BLUE}1/4${NC} TCB 环境 ID"
echo -e "      ${CYAN}在 TCB 控制台 → 环境 → 环境 ID 获取${NC}"
read -p "      输入值 [$TCB_ENV_ID]: " input
TCB_ENV_ID="${input:-$TCB_ENV_ID}"
if [ -z "$TCB_ENV_ID" ]; then
    echo -e "      ${RED}✗ 环境 ID 不能为空${NC}"
    exit 1
fi
echo -e "      ${GREEN}✓ $TCB_ENV_ID${NC}"
echo ""

# 数据库连接
echo -e "  ${BLUE}2/4${NC} PostgreSQL 数据库连接"
echo -e "      ${CYAN}在 TCB 控制台 → 数据库 → PostgreSQL 获取连接信息${NC}"
echo -e "      ${CYAN}格式: postgresql://user:pass@host:5432/dbname${NC}"
read -p "      DATABASE_URL [$DATABASE_URL]: " input
DATABASE_URL="${input:-$DATABASE_URL}"
echo ""

# 选择数据库方案
if [ -z "$DATABASE_URL" ]; then
    echo -e "      ${YELLOW}⚠ 未配置数据库连接${NC}"
    echo -e "      请选择方案："
    echo -e "      1) 我已有数据库连接字符串"
    echo -e "      2) 创建新的 TCB PostgreSQL（推荐但需要手动）"
    echo -e "      3) 跳过数据库配置，稍后手动填写"
    read -p "      选择 [3]: " db_choice
    db_choice="${db_choice:-3}"
    
    case $db_choice in
        1)
            echo -e "      ${CYAN}请提供完整连接字符串:${NC}"
            read -p "      " DATABASE_URL
            ;;
        2)
            echo -e "      ${CYAN}请在 TCB 控制台手动创建 PostgreSQL:${NC}"
            echo -e "      ${CYAN}  TCB 控制台 → 数据库 → 创建数据库 → PostgreSQL${NC}"
            echo -e "      ${CYAN}创建后将连接字符串填入 .env.local${NC}"
            ;;
        *)
            echo -e "      ${YELLOW}⚠ 跳过数据库配置${NC}"
            ;;
    esac
fi
echo ""

# COS 存储桶
echo -e "  ${BLUE}3/4${NC} COS 存储桶"
echo -e "      ${CYAN}在腾讯云 COS 控制台创建存储桶${NC}"
echo -e "      ${CYAN}格式: bucket-name-APPID (如: ecan-files-1250000000)${NC}"
read -p "      COS_BUCKET [$COS_BUCKET]: " input
COS_BUCKET="${input:-$COS_BUCKET}"

read -p "      COS_REGION [$COS_REGION]: " input
COS_REGION="${input:-$COS_REGION}"
echo ""

# SSE 推送密钥 (CN 实时推送, 跨函数 HTTP POST 鉴权)
echo -e "  ${BLUE}4/4${NC} 安全配置"
SSE_PUSH_SECRET="${SSE_PUSH_SECRET:-$(openssl rand -hex 32)}"
echo -e "      SSE_PUSH_SECRET: ${GREEN}${#SSE_PUSH_SECRET} 字符${NC} (已自动生成)"
echo ""

# ============ 3. 保存配置 ============
echo -e "${YELLOW}💾 保存配置...${NC}"

cat > .env.local << EOF
# ============================================================
# eCan.ai CN 版本 - TCB 云函数配置（自动生成）
# 生成时间: $(date '+%Y-%m-%d %H:%M:%S')
# ============================================================

# ============ PostgreSQL 连接信息 =============
DATABASE_URL=${DATABASE_URL:-}

# ============ TCB 环境信息 ============
TCB_ENV_ID=${TCB_ENV_ID}
TCB_API_URL=https://${TCB_ENV_ID}.service.tcloudbase.com/api/graphql

# ============ COS 用户文件存储 ============
COS_BUCKET=${COS_BUCKET}
COS_REGION=${COS_REGION}

# ============ SSE 推送密钥 ============
SSE_PUSH_SECRET=${SSE_PUSH_SECRET}

# ============ CN 云任务调度 ============
TENCENT_SCHEDULER_FUNCTION=ecan-graphql-api
TENCENT_SCF_NAMESPACE=default
TENCENT_REGION=${COS_REGION}

# ============ 本地开发配置 ============
NODE_ENV=production
ALLOW_INSECURE_AUTH=false
EOF

echo -e "  ✓ 配置已保存到 .env.local"
echo ""

# ============ 4. 尝试自动创建资源（可选） ============
echo -e "${YELLOW}☁️  云资源检查...${NC}"

# 检查 COS 存储桶是否存在
if [ -n "$COS_BUCKET" ] && command -v tccli &> /dev/null; then
    echo -e "  检查 COS 存储桶: $COS_BUCKET..."
    # 提取 APPID
    APPID=$(echo "$COS_BUCKET" | grep -oE '[0-9]+$')
    BUCKET_NAME=$(echo "$COS_BUCKET" | sed "s/-$APPID$//")
    
    if [ -n "$APPID" ]; then
        # 检查存储桶
        tccli cos HeadBucket --Bucket "${BUCKET_NAME}" --Region "${COS_REGION}" 2>/dev/null && \
            echo -e "    ${GREEN}✓ 存储桶存在${NC}" || \
            echo -e "    ${YELLOW}⚠ 存储桶不存在，需要手动创建${NC}" && \
            echo -e "    ${CYAN}创建地址: https://console.cloud.tencent.com/cos5/bucket${NC}"
    fi
fi

# 检查 PostgreSQL
if [ -n "$DATABASE_URL" ]; then
    echo -e "  检查 PostgreSQL 连接..."
    # 提取主机
    DB_HOST=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:]*\):.*|\1|p')
    if [ -n "$DB_HOST" ]; then
        if timeout 3 bash -c "cat < /dev/null > /dev/tcp/${DB_HOST}/5432" 2>/dev/null; then
            echo -e "    ${GREEN}✓ 数据库可连接${NC}"
        else
            echo -e "    ${YELLOW}⚠ 数据库不可达，请检查网络配置${NC}"
        fi
    fi
fi

echo ""

# ============ 5. 下一步指引 ============
echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}  ✅ 初始化完成！${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "配置文件: ${CYAN}.env.local${NC}"
echo ""

echo -e "后续步骤："
echo -e "  1. ${BLUE}创建云数据库${NC}"
echo -e "     TCB 控制台 → 数据库 → 创建 PostgreSQL"
echo -e ""
echo -e "  2. ${BLUE}创建 COS 存储桶${NC}"
echo -e "     腾讯云 COS 控制台 → 创建存储桶（开启静态网站）"
echo -e ""
echo -e "  3. ${BLUE}部署云函数${NC}"
echo -e "     ./deploy.sh"
echo -e ""
echo -e "  4. ${BLUE}配置环境变量（部署时自动）${NC}"
echo -e "     或手动: TCB 控制台 → 云函数 → 环境配置"
echo -e ""
echo -e "  5. ${BLUE}初始化数据库${NC}"
echo -e "     npm run db:push && npm run db:seed"
echo ""

echo -e "查看详细文档: ${CYAN}../docs/CN_VERSION_GUIDE.md${NC}"
echo ""
