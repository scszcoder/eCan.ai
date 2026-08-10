#!/bin/bash
# ============================================================
# eCan.ai TCB 云托管 (TCS) 部署脚本 - 自建 graphql-ws WS 服务
# ============================================================
#
# 部署自建 WebSocket 服务到 TCB 云托管:
#   - 构建 Docker 镜像
#   - 推送到 TCR (腾讯云镜像仓库)
#   - 部署到 TCS 云托管
#
# 架构:
#   WS 服务 (TCS)  ← HTTP POST /publish ← GraphQL API (SCF)
#   WS 服务 (TCS)  ← WSS 客户端连接 ← 桌面 App
#
# 前置条件:
#   1. docker login --server ccr.ccs.tencentyun.com
#   2. tcb login
#   3. TCR 命名空间已创建 (在 TCB 控制台)
#   4. .env.local 中已配置 TCB_ENV_ID
#
# 使用方式:
#   ./deploy-ws-tcs.sh                  # 仅部署已有镜像
#   ./deploy-ws-tcs.sh --build         # 构建镜像
#   ./deploy-ws-tcs.sh --build --push   # 构建 + 推送
#   ./deploy-ws-tcs.sh --build --push --deploy  # 全量 (默认)
#   ./deploy-ws-tcs.sh --local         # 本地 Docker 运行 (开发测试)

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR" && pwd)"

# ============ 解析参数 ============
BUILD=false
PUSH=false
DEPLOY=false
LOCAL=false

for arg in "$@"; do
  case $arg in
    --build)    BUILD=true ;;
    --push)    PUSH=true ;;
    --deploy)  DEPLOY=true ;;
    --local)   LOCAL=true ;;
    --help)
      echo "用法: $0 [OPTIONS]"
      echo "  --build   构建 Docker 镜像"
      echo "  --push   推送到 TCR"
      echo "  --deploy  部署到 TCS (云托管)"
      echo "  --local   本地 Docker 运行 (开发测试)"
      echo ""
      echo "示例:"
      echo "  $0 --build --push --deploy  # 全量构建+部署"
      echo "  $0 --deploy                   # 仅部署已有镜像"
      echo "  $0 --local                   # 本地开发测试"
      exit 0
      ;;
  fi
done

cd "$PROJECT_DIR"

# 默认: 全量 (构建+推送+部署)
if [[ "$BUILD" == "false" && "$PUSH" == "false" && "$DEPLOY" == "false" && "$LOCAL" == "false" ]]; then
  BUILD=true; PUSH=true; DEPLOY=true
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  eCan.ai WS 服务 → TCB 云托管 (TCS)${NC}"
echo -e "${BLUE}========================================${NC}"
echo "  BUILD=$BUILD  PUSH=$PUSH  DEPLOY=$DEPLOY  LOCAL=$LOCAL"

# ============ 加载 .env.local ============
if [ ! -f ".env.local" ]; then
  echo -e "${RED}❌ .env.local 不存在${NC}"; exit 1; fi
set -a
. .env.local
set +a

TCB_ENV_ID="${TCB_ENV_ID:-sccb0-d0gc5398xf028be6a}"
TCB_REGION="${TCB_REGION:-ap-shanghai}"

# ============ TCR 配置 ============
# TCR 命名空间: 从 TCB 控制台获取 (环境 -> 基础设置 -> 镜像仓库)
# 默认使用 TCB_ENV_ID 的前缀作为命名空间
TCR_NAMESPACE="${TCR_NAMESPACE:-$(echo $TCB_ENV_ID | cut -d'-' -f1)}"
TCR_IMAGE_TAG="ccr.ccs.tencentyun.com/${TCR_NAMESPACE}/ecan-graphql-ws:latest"

echo ""
echo -e "${YELLOW}📋 配置信息${NC}"
echo "  环境:     $TCB_ENV_ID"
echo "  区域:     $TCB_REGION"
echo "  TCR NS:   $TCR_NAMESPACE"
echo "  镜像:     $TCR_IMAGE_TAG"

# ============ 镜像构建 ============
if $BUILD; then
  echo ""
  echo -e "${YELLOW}🐳 构建 Docker 镜像...${NC}"
  if [ ! -f "Dockerfile.ws" ]; then
    echo -e "${RED}❌ Dockerfile.ws 不存在${NC}"; exit 1; fi

  # 构建时传入环境变量 (不包含 secret)
  docker build \
    --network=host \
    -f Dockerfile.ws \
    --build-arg NODE_ENV=production \
    -t "$TCR_IMAGE_TAG" \
    .
  echo -e "  ✓ 镜像构建完成: $TCR_IMAGE_TAG"
  docker images "$TCR_IMAGE_TAG" --format "{{.Repository}}:{{.Tag}}  {{.Size}}"
fi

# ============ 镜像推送 ============
if $PUSH; then
  echo ""
  echo -e "${YELLOW}☁️  推送镜像到 TCR...${NC}"

  # 检查是否已登录
  if ! docker info 2>&1 | grep -q "ccr.ccs.tencentyun.com"; then
    echo -e "${YELLOW}  → 未登录 TCR, 尝试自动登录...${NC}"
    # TCR 登录需要 TCCAPI_TOKEN，通常通过 tcb login 自动获取
    echo -e "${YELLOW}  ⚠️  请先手动运行: docker login ccr.ccs.tencentyun.com${NC}"
    echo -e "${YELLOW}  ⚠️  或在 TCB 控制台 -> 环境 -> 基础设置 -> 镜像仓库 -> 访问凭证${NC}"
    echo -e "${YELLOW}  ⚠️  如已有凭证, 运行: docker login ccr.ccs.tencentyun.com${NC}"
    # 继续尝试 (可能已通过 tcb login 注入凭证)
  fi

  docker push "$TCR_IMAGE_TAG"
  echo -e "  ✓ 镜像推送完成"
fi

# ============ 部署到 TCS ============
if $DEPLOY; then
  echo ""
  echo -e "${YELLOW}🚀 部署到 TCB 云托管 (TCS)...${NC}"

  # 生成 WS_PUSH_SECRET (如果未设置)
  if [ -z "$WS_PUSH_SECRET" ]; then
    WS_PUSH_SECRET="$(node -e "console.log(require('crypto').randomBytes(32).toString('hex'))")"
    echo -e "${YELLOW}  → 自动生成 WS_PUSH_SECRET (长度: ${#WS_PUSH_SECRET})"
    echo -e "${YELLOW}  → 请在 .env.local 中保存: WS_PUSH_SECRET=$WS_PUSH_SECRET${NC}"
  fi

  # VPC 配置 (与 SCF 相同: 让 WS 服务能访问 TDSQL-C)
  VPC_ID="${TCB_VPC_ID:-vpc-2pt6t7qg}"
  SUBNET_ID="${TCB_SUBNET_ID:-subnet-h3cs01ip}"
  VPC_CONFIG="{\"vpcId\":\"$VPC_ID\",\"vpcCIDR\":\"10.0.0.0/16\",\"subnetId\":\"$SUBNET_ID\",\"subnetCIDR\":\"10.0.1.0/24\"}"

  echo -e "  服务名称: ecan-graphql-ws"
  echo -e "  镜像:     $TCR_IMAGE_TAG"
  echo -e "  端口:     9102"
  echo -e "  VPC:      $VPC_ID / $SUBNET_ID"

  # 部署到 TCS
  # --install-dependency=false 因为依赖已打包进镜像
  tcb cloudrun deploy \
    --service-name "ecan-graphql-ws" \
    --port 9102 \
    --image-url "$TCR_IMAGE_TAG" \
    --vpc-config "$VPC_CONFIG" \
    --force \
    --json 2>&1 | tee /tmp/tcs-deploy-output.json

  echo ""
  echo -e "  ✓ TCS 部署完成"

  # 提取内网访问地址 (用于 SCF 推送)
  # TCS 会分配一个内网 IP 或 CLB 地址
  TCS_SERVICE_INFO=$(tcb cloudrun detail --service-name "ecan-graphql-ws" --json 2>/dev/null || echo "{}")
  echo ""
  echo -e "${GREEN}========================================${NC}"
  echo -e "${GREEN}  ✅ 云托管部署完成${NC}"
  echo -e "${GREEN}========================================${NC}"
  echo ""
  echo -e "⚠️  下一步 — 必须在 .env.local 中配置:"
  echo ""
  echo -e "  # WS 服务云托管内网地址 (SCF 用, 格式: http://<ip>:9102 或 http://<clb>:9102)"
  echo -e "  WS_TCS_URL=http://<TCS内网IP>:9102"
  echo ""
  echo -e "  # 推送密钥 (必须与 TCS 容器环境变量一致)"
  echo -e "  WS_PUSH_SECRET=${WS_PUSH_SECRET}"
  echo ""
  echo -e "⚠️  然后运行: ./scripts/sync-tcb-env.sh"
  echo ""
fi

# ============ 本地开发测试 ============
if $LOCAL; then
  echo ""
  echo -e "${YELLOW}🐳 本地 Docker 运行 (端口 9102)...${NC}"

  # 本地开发: 随机生成 secret
  LOCAL_SECRET="$(node -e "console.log(require('crypto').randomBytes(16).toString('hex'))")"
  echo -e "  WS_PUSH_SECRET=$LOCAL_SECRET"

  docker run --rm \
    --name ecan-graphql-ws-local \
    -p 9102:9102 \
    -e WS_PUSH_SECRET="$LOCAL_SECRET" \
    -e ALLOW_INSECURE_AUTH=true \
    -e NODE_ENV=development \
    -e TCB_REGION=ap-shanghai \
    -v "$PROJECT_DIR/services:/app/services:ro" \
    -v "$PROJECT_DIR/event-bus.js:/app/event-bus.js:ro" \
    -v "$PROJECT_DIR/functions/ecan-graphql-ws/index.js:/app/index.js:ro" \
    -v "$PROJECT_DIR/functions/ecan-graphql-ws/api-gateway-helper.js:/app/api-gateway-helper.js:ro" \
    --network=host \
    node:20-alpine \
    node /app/index.js &

  LOCAL_PID=$!
  echo -e "  → 容器 PID: $LOCAL_PID"
  echo -e "  → WS 服务:   http://localhost:9102"
  echo -e "  → 健康检查:  http://localhost:9102/healthz"
  echo ""
  echo -e "  按 Ctrl+C 停止"
  wait $LOCAL_PID
fi
