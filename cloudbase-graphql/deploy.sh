#!/bin/bash
# =============================================================================
# cloudbase-graphql 部署脚本
# =============================================================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}==> eCan CN GraphQL API 部署${NC}"

# 检查依赖
if [ ! -d "node_modules" ]; then
  echo -e "${YELLOW}安装依赖...${NC}"
  npm install
fi

# 检查环境变量
if [ -z "$TCB_ENV_ID" ]; then
  echo -e "${RED}错误: TCB_ENV_ID 未设置${NC}"
  echo "请设置: export TCB_ENV_ID=your-env-id"
  exit 1
fi

if [ -z "$TDSQL_HOST" ]; then
  echo -e "${RED}错误: TDSQL_HOST 未设置${NC}"
  echo "请设置: export TDSQL_HOST=your-tdsql-host"
  exit 1
fi

# 部署云函数
echo -e "${GREEN}部署云函数...${NC}"

# 使用腾讯云 SCF CLI 部署
scf function deploy \
  --name ecan-graphql-api \
  --runtime Nodejs16.13 \
  --handler index.main_handler \
  --timeout 60 \
  --memory-size 256 \
  --environment-variables "NODE_ENV=production" \
  --ignore-file .scfignore

echo -e "${GREEN}==> 部署完成!${NC}"
echo ""
echo "云函数入口: https://${TCB_ENV_ID}.service.tcloudbase.com/graphql"
