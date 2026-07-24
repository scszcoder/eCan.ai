#!/bin/bash
# 部署腾讯云 SCF 云函数
# 用法: ./scripts/deploy.sh [ENV]

set -e

ENV=${1:-development}
REGION=${REGION:-ap-guangzhou}
FUNCTION_NAME="ecan-graphql-api"

echo "=== 部署配置 ==="
echo "环境: $ENV"
echo "区域: $REGION"

required_vars=("TENCENT_SECRET_ID" "TENCENT_SECRET_KEY" "TDSQL_HOST" "TDSQL_PASSWORD" "COS_BUCKET")
missing=()
for var in "${required_vars[@]}"; do
  if [ -z "${!var}" ]; then missing+=("$var"); fi
done

if [ ${#missing[@]} -gt 0 ]; then
  echo "错误: 缺少环境变量: ${missing[*]}"
  exit 1
fi

cd "$(dirname "$0")/../functions/graphql-api"
npm install --production

rm -f ../../function.zip
zip -r ../../function.zip . -x "*.test.js" -x "test/*" -x ".git/*" -x "*.md"

if command -v scf &> /dev/null; then
  scf function deploy \
    --name "$FUNCTION_NAME" \
    --region "$REGION" \
    --runtime Nodejs16.13 \
    --handler index.main_handler \
    --zip-file ../../function.zip \
    --memory 512 \
    --timeout 60 \
    --env "TDSQL_HOST=$TDSQL_HOST" \
    --env "TDSQL_PORT=${TDSQL_PORT:-3306}" \
    --env "TDSQL_USER=${TDSQL_USER:-ecan_admin}" \
    --env "TDSQL_PASSWORD=$TDSQL_PASSWORD" \
    --env "TDSQL_DATABASE=${TDSQL_DATABASE:-ecan_db}" \
    --env "COS_BUCKET=$COS_BUCKET" \
    --env "COS_REGION=${COS_REGION:-ap-guangzhou}" \
    --env "TENCENT_SECRET_ID=$TENCENT_SECRET_ID" \
    --env "TENCENT_SECRET_KEY=$TENCENT_SECRET_KEY" \
    --env "TCB_ENV_ID=${TCB_ENV_ID}"
  echo "部署成功!"
else
  echo "scf CLI 未安装，请安装: npm install -g scf"
fi
