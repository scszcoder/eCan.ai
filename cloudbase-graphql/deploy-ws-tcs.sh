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
#   1. docker login ccr.ccs.tencentyun.com   (TCR 个人版长期凭证, 一次配置持久可用)
#      获取方式: 主账号在 https://console.cloud.tencent.com/tcr/personal
#               → 顶部 "访问凭证" → "生成长期凭证" → 用户名 tencentcloud + 自定义密码
#   2. tcb login                              (本脚本自动检测, 缺失时引导扫码)
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
SOURCE=false   # 新增: 使用 TCB 云端构建, 不需要本地 TCR 登录

for arg in "$@"; do
  case $arg in
    --build)    BUILD=true ;;
    --push)    PUSH=true ;;
    --deploy)  DEPLOY=true ;;
    --local)   LOCAL=true ;;
    --source)  SOURCE=true ;;   # TCB 云端构建 (不需要 docker login TCR)
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
  esac
done

cd "$PROJECT_DIR"

# 默认: 全量 (构建+推送+部署)
# --source 模式下: 仅 DEPLOY=true, BUILD/PUSH 由 TCB 云端处理
if [[ "$BUILD" == "false" && "$PUSH" == "false" && "$DEPLOY" == "false" && "$LOCAL" == "false" && "$SOURCE" == "false" ]]; then
  BUILD=true; PUSH=true; DEPLOY=true
fi

# --source 模式: BUILD/PUSH 由 TCB 云端完成, 只走 --deploy
if $SOURCE; then BUILD=false; PUSH=false; DEPLOY=true; fi

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

  # arm64 Mac 本地构建 → 必须交叉构建 linux/amd64 (TCB 云托管运行 x86_64)
  # WS_PUSH_SECRET: 若 .env.local 已配置则通过 build-arg 注入镜像 ENV
  #                若未配置, 则留给 --deploy 阶段生成 (镜像默认 ENV="" 即可, 容器启动时控制台覆盖)
  BUILD_ARGS=(--build-arg NODE_ENV=production)
  if [ -n "$WS_PUSH_SECRET" ]; then
    BUILD_ARGS+=(--build-arg "WS_PUSH_SECRET=$WS_PUSH_SECRET")
    echo "  → WS_PUSH_SECRET 将随镜像 ENV 注入 (长度: ${#WS_PUSH_SECRET})"
  fi
  docker buildx build \
    --platform linux/amd64 \
    --network=host \
    -f Dockerfile.ws \
    "${BUILD_ARGS[@]}" \
    -t "$TCR_IMAGE_TAG" \
    --load \
    .
  echo -e "  ✓ 镜像构建完成: $TCR_IMAGE_TAG"
  docker images "$TCR_IMAGE_TAG" --format "{{.Repository}}:{{.Tag}}  {{.Size}}"
fi

# ============ 镜像推送 ============
if $PUSH; then
  echo ""
  echo -e "${YELLOW}☁️  推送镜像到 TCR...${NC}"

  # ===== TCR 凭证检查 =====
  # TCB CLI 不会自动从 STS 拿 docker login 凭证, 必须预先 docker login
  if [ ! -f "$HOME/.docker/config.json" ] \
     || ! grep -q '"ccr.ccs.tencentyun.com"' "$HOME/.docker/config.json" 2>/dev/null; then
    echo ""
    echo -e "${RED}❌ TCR (ccr.ccs.tencentyun.com) 未登录${NC}"
    echo ""
    echo -e "${YELLOW}请执行以下操作之一:${NC}"
    echo ""
    echo -e "${BLUE}  方案 A (推荐): 主账号开通 TCR 个人版, 生成长期凭证${NC}"
    echo -e "    1. 主账号登录: https://console.cloud.tencent.com/tcr/personal"
    echo -e "    2. 顶部 '访问凭证' → '生成长期凭证' → 自定义密码"
    echo -e "    3. 本机执行:"
    echo -e "         \$ docker login ccr.ccs.tencentyun.com"
    echo -e "         Username: tencentcloud"
    echo -e "         Password: <主账号给的密码>"
    echo ""
    echo -e "${BLUE}  方案 B: 让主账号在 CAM 给当前子账号绑 QcloudTCRFullAccess${NC}"
    echo -e "         然后你可以自己去 TCR 控制台生成凭证"
    echo ""
    exit 1
  fi
  echo -e "  ✓ TCR 凭证检查通过 (ccr.ccs.tencentyun.com 已登录)"

  docker push "$TCR_IMAGE_TAG"
  echo -e "  ✓ 镜像推送完成"
fi

# ============ 部署到 TCS ============
if $DEPLOY; then
  echo ""
  echo -e "${YELLOW}🚀 部署到 TCB 云托管 (TCS)...${NC}"

  # 记录部署前的所有版本 (用于部署后关闭老版本)
  PRE_VERSIONS=$(tcb cloudrun detail --service-name "ecan-graphql-ws" --json 2>/dev/null \
    | node -e "let d=''; process.stdin.on('data',c=>d+=c).on('end',()=>{try{const j=JSON.parse(d);console.log((j.OnlineVersionInfos||[]).map(v=>v.VersionName+'|'+v.FlowRatio).join('\n'))}catch(e){console.log('')}})" 2>/dev/null || echo "")
  echo -e "  ${BLUE}→ 当前在线版本:${NC}"
  if [ -n "$PRE_VERSIONS" ]; then
    echo "$PRE_VERSIONS" | sed 's/^/    /'
  else
    echo "    (无)"
  fi

  # 生成 WS_PUSH_SECRET (如果未设置)
  if [ -z "$WS_PUSH_SECRET" ]; then
    WS_PUSH_SECRET="$(node -e "console.log(require('crypto').randomBytes(32).toString('hex'))")"
    echo -e "${YELLOW}  → 自动生成 WS_PUSH_SECRET (长度: ${#WS_PUSH_SECRET})"
    # 写回 .env.local，避免下次重新生成导致 SCF/TCS 不一致
    if grep -q "^WS_PUSH_SECRET=" .env.local; then
      # macOS/BSD sed 与 GNU sed 兼容: -i.bak 备份 + 同步删除
      sed -i.bak "s|^WS_PUSH_SECRET=.*|WS_PUSH_SECRET=$WS_PUSH_SECRET|" .env.local && rm -f .env.local.bak
    else
      echo "WS_PUSH_SECRET=$WS_PUSH_SECRET" >> .env.local
    fi
    echo -e "${YELLOW}  → 已写入 .env.local${NC}"
  fi

  # VPC 配置 (与 SCF 相同: 让 WS 服务能访问 TDSQL-C)
  VPC_ID="${TCB_VPC_ID:-vpc-2pt6t7qg}"
  SUBNET_ID="${TCB_SUBNET_ID:-subnet-h3cs01ip}"
  VPC_CONFIG="{\"vpcId\":\"$VPC_ID\",\"vpcCIDR\":\"10.0.0.0/16\",\"subnetId\":\"$SUBNET_ID\",\"subnetCIDR\":\"10.0.1.0/24\"}"

  echo -e "  服务名称: ecan-graphql-ws"
  echo -e "  端口:     9102"
  echo -e "  VPC:      $VPC_ID / $SUBNET_ID"

  # 部署到 TCS
  if $SOURCE; then
    # --source 模式: TCB 云端构建 (不需要本地 docker login TCR)
    # 根 Dockerfile 会检测 Dockerfile.ws 并使用它构建
    echo -e "  模式:     TCB 云端构建 (--source)"
    tcb cloudrun deploy \
      --service-name "ecan-graphql-ws" \
      --port 9102 \
      --source . \
      --vpc-config "$VPC_CONFIG" \
      --force \
      --json 2>&1 | tee /tmp/tcs-deploy-output.json
  else
    # --image-url 模式: 使用预构建镜像 (需要本地 docker buildx + TCR 登录)
    echo -e "  镜像:     $TCR_IMAGE_TAG"
    echo -e "  模式:     预构建镜像 (--image-url)"
    tcb cloudrun deploy \
      --service-name "ecan-graphql-ws" \
      --port 9102 \
      --image-url "$TCR_IMAGE_TAG" \
      --vpc-config "$VPC_CONFIG" \
      --force \
      --json 2>&1 | tee /tmp/tcs-deploy-output.json
  fi

  echo ""
  echo -e "  ✓ TCS 部署完成"

  # 提取新版本名 (用于标记"当前最新")，与老版本区分
  NEW_VERSION=$(tcb cloudrun detail --service-name "ecan-graphql-ws" --json 2>/dev/null \
    | node -e "let d=''; process.stdin.on('data',c=>d+=c).on('end',()=>{try{const j=JSON.parse(d);const latest=j.OnlineVersionInfos?.[j.OnlineVersionInfos.length-1];console.log(latest?.VersionName||'')}catch(e){console.log('')}})" 2>/dev/null || echo "")

  # ── 关闭老版本 ──────────────────────────────────────────────────
  # 部署后: detail 中一般只剩一个新版本 (TCB 默认模式是 "replace" 而非 "canary")
  # 但若 PRE_VERSIONS 里有 > 1 个, 说明老版本还在, 主动关停
  OLD_VERSIONS=$(echo "$PRE_VERSIONS" | awk -F'|' -v new="$NEW_VERSION" '$1 != new && $1 != "" {print $1}')
  if [ -n "$OLD_VERSIONS" ]; then
    echo ""
    echo -e "${YELLOW}🛑 检测到遗留老版本，主动关闭:${NC}"
    echo "$OLD_VERSIONS" | sed 's/^/    /'
    # tcb cloudrun version delete --version-names a,b,c  --is-delete-server false --is-delete-image false
    # 关闭版本但保留镜像 (供回滚)
    OLD_LIST=$(echo "$OLD_VERSIONS" | paste -sd ',' -)
    echo ""
    echo -e "  → 调用: tcb cloudrun version delete --version-names $OLD_LIST --is-delete-image false --force"
    tcb cloudrun version delete \
      --service-name "ecan-graphql-ws" \
      --version-names "$OLD_LIST" \
      --is-delete-image false \
      --force 2>&1 | tail -10 \
      && echo -e "  ${GREEN}✓ 老版本已停止 (镜像已保留供回滚)${NC}" \
      || echo -e "  ${YELLOW}⚠️  老版本停止失败, 可手动在控制台操作${NC}"
  else
    echo ""
    echo -e "  ${GREEN}✓ 无遗留老版本需要关闭${NC}"
  fi

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
  echo -e "⚠️  然后运行: ./bin/sync-tcb-env"
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
