#!/bin/bash
# ============================================================
# eCan.ai — TCB 云托管 (TCS) WebSocket 服务 自动化部署脚本
# 支持版本管理、灰度发布、快速回滚
# ============================================================
#
# 前置条件:
#   1. docker login ccr.ccs.tencentyun.com
#   2. tcb login
#
# 使用方式:
#   ./deploy-tcs.sh --help                           # 帮助
#   ./deploy-tcs.sh --build                          # 仅构建镜像
#   ./deploy-tcs.sh --build --push                   # 构建 + 推送
#   ./deploy-tcs.sh --deploy                         # 部署最新镜像
#   ./deploy-tcs.sh --deploy --version=v1.0.0       # 部署指定版本
#   ./deploy-tcs.sh --rollback                        # 回滚到上一版本
#   ./deploy-tcs.sh --rollback --version=v1.2.3      # 回滚到指定版本
#   ./deploy-tcs.sh --full                           # 构建 + 推送 + 部署 (默认)
#   ./deploy-tcs.sh --smoke                          # 冒烟测试

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'; BOLD='\033[1m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR" && pwd)"

# ============ 配置 ============
IMAGE_NAME="${IMAGE_NAME:-ecan-graphql-ws}"
REGISTRY="${REGISTRY:-ccr.ccs.tencentyun.com}"
TCS_SERVICE_NAME="${TCS_SERVICE_NAME:-ecan-graphql-ws}"
TCS_PORT="${TCS_PORT:-9102}"
VERSION_FILE="$PROJECT_DIR/.tcs-version"
VERSION_HISTORY="$PROJECT_DIR/.tcs-version-history"

# ============ 解析参数 ============
BUILD=false; PUSH=false; DEPLOY=false; ROLLBACK=false; SMOKE=false
HELP=false; TARGET_VERSION=""
for arg in "$@"; do
  case $arg in
    --build)    BUILD=true ;;
    --push)     PUSH=true ;;
    --deploy)   DEPLOY=true ;;
    --rollback) ROLLBACK=true ;;
    --smoke)    SMOKE=true ;;
    --full)     BUILD=true; PUSH=true; DEPLOY=true ;;
    --help|-h)  HELP=true ;;
    --version=*) TARGET_VERSION="${arg#*=}" ;;
    -*)         echo -e "${RED}Unknown option: $arg${NC}" >&2; exit 1 ;;
  esac
done

# 默认: --full
if [[ "$BUILD" == "false" && "$PUSH" == "false" && "$DEPLOY" == "false" && "$ROLLBACK" == "false" && "$SMOKE" == "false" ]]; then
  BUILD=true; PUSH=true; DEPLOY=true
fi

cd "$PROJECT_DIR"

# ============ 辅助函数 ============
log()  { echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $*"; }
info() { echo -e "${GREEN}  ✓ $*${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $*${NC}"; }
die()  { echo -e "${RED}❌ $*$NC" >&2; exit 1; }

current_version()  { [ -f "$VERSION_FILE" ] && cat "$VERSION_FILE" || echo "none"; }
previous_version()  { [ -f "$VERSION_HISTORY" ] && tail -n2 "$VERSION_HISTORY" | head -n1 | cut -d' ' -f1 || echo ""; }
save_version()      { echo "$1 $2 $(date -Iseconds)" >> "$VERSION_HISTORY"; echo "$1" > "$VERSION_FILE"; }
gen_version()       { local h="$(git rev-parse --short HEAD 2>/dev/null || echo 'nogit')"; echo "v$(date '+%Y%m%d-%H%M%S')-${h}"; }

# ============ 帮助 ============
if $HELP; then
  echo -e "${BOLD}eCan.ai — TCS WebSocket 部署脚本${NC}"
  echo ""
  echo -e "${BOLD}Usage:${NC}  $0 [OPTIONS]"
  echo ""
  echo "  --build              Build Docker image"
  echo "  --push               Push to TCR"
  echo "  --deploy             Deploy to TCS"
  echo "  --rollback           Rollback to previous version"
  echo "  --smoke              Run smoke tests"
  echo "  --full               Build + push + deploy (default)"
  echo "  --version=VER        Specify version (deploy/rollback)"
  echo "  --help, -h           Show this help"
  echo ""
  echo -e "${BOLD}Version:${NC}  current=$(current_version)"
  echo ""
  echo "  $0 --full                         # build + push + deploy"
  echo "  $0 --deploy --version=v1.0.0     # deploy specific version"
  echo "  $0 --rollback                     # rollback"
  echo "  $0 --smoke                       # smoke test"
  exit 0
fi

# ============ 加载 .env.local ============
if [ ! -f ".env.local" ]; then die ".env.local not found"; fi
set -a; . ./.env.local; set +a

TCB_ENV_ID="${TCB_ENV_ID:-sccb0-d0gc5398xf028be6a}"
TCB_REGION="${TCB_REGION:-ap-shanghai}"
TCR_NAMESPACE="${TCR_NAMESPACE:-$(echo $TCB_ENV_ID | cut -d'-' -f1)}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
VERSIONED_IMAGE="${REGISTRY}/${TCR_NAMESPACE}/${IMAGE_NAME}"
FULL_IMAGE="${VERSIONED_IMAGE}:${IMAGE_TAG}"

# ============ Header ============
echo -e "\n${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║  eCan.ai — TCS WebSocket Deploy (v2)       ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${CYAN}Image:${NC}   $FULL_IMAGE"
echo -e "  ${CYAN}TCS:${NC}    $TCS_SERVICE_NAME ($TCB_REGION)"
echo -e "  ${CYAN}Version:${NC} $(current_version)"
echo ""

# ============ BUILD ============
if $BUILD; then
  echo -e "${BOLD}===== [1/3] Build Docker Image =====${NC}"
  [ ! -f "Dockerfile.ws" ] && die "Dockerfile.ws not found"

  local VER
  VER="$(gen_version)"
  local VER_IMAGE="${VERSIONED_IMAGE}:${VER}"
  echo -e "  Version: ${GREEN}$VER${NC}"
  echo -e "  Image:   $VER_IMAGE"

  log "Building..."
  docker build --network=host \
    -f Dockerfile.ws \
    --build-arg NODE_ENV=production \
    --label "version=$VER" \
    --label "build-time=$(date -Iseconds)" \
    --label "git=$(git rev-parse HEAD 2>/dev/null || echo 'nogit')" \
    -t "$VER_IMAGE" \
    -t "$FULL_IMAGE" \
    . 2>&1 | tail -5

  info "Image built"
  docker images "$VER_IMAGE" --format "{{.Repository}}:{{.Tag}}  {{.Size}}" | grep "$IMAGE_NAME"
  save_version "$VER" "$VER_IMAGE"
  info "Version $VER saved"
fi

# ============ PUSH ============
if $PUSH; then
  echo -e "\n${BOLD}===== [2/3] Push to TCR =====${NC}"
  log "Pushing $FULL_IMAGE ..."
  if ! docker info 2>&1 | grep -q "$REGISTRY"; then
    warn "Not logged in to TCR. Run: docker login $REGISTRY"
    docker login "$REGISTRY" || warn "TCR login failed"
  fi
  docker push "$FULL_IMAGE" 2>&1 | tail -3
  info "Image pushed: $FULL_IMAGE"
  if $BUILD; then
    docker push "${VERSIONED_IMAGE}:$(current_version)" 2>&1 | tail -3
  fi
fi

# ============ DEPLOY ============
if $DEPLOY; then
  echo -e "\n${BOLD}===== [3/3] Deploy to TCS =====${NC}"

  local DEPLOY_IMAGE="$FULL_IMAGE"
  if [ -n "$TARGET_VERSION" ]; then
    DEPLOY_IMAGE="${VERSIONED_IMAGE}:${TARGET_VERSION}"
    echo -e "  Deploying: ${YELLOW}$TARGET_VERSION${NC} → $DEPLOY_IMAGE"
  fi

  # Generate WS_PUSH_SECRET if not set
  if [ -z "${WS_PUSH_SECRET:-}" ]; then
    WS_PUSH_SECRET="$(node -e "console.log(require('crypto').randomBytes(32).toString('hex'))")"
    warn "Auto-generated WS_PUSH_SECRET (${#WS_PUSH_SECRET} chars)"
  fi

  local VPC_ID="${TCB_VPC_ID:-vpc-2pt6t7qg}"
  local SUBNET_ID="${TCB_SUBNET_ID:-subnet-h3cs01ip}"
  local VPC_CONFIG="{\"vpcId\":\"$VPC_ID\",\"vpcCIDR\":\"10.0.0.0/16\",\"subnetId\":\"$SUBNET_ID\",\"subnetCIDR\":\"10.0.1.0/24\"}"

  echo -e "  ${CYAN}Service:${NC}  $TCS_SERVICE_NAME"
  echo -e "  ${CYAN}Image:${NC}   $DEPLOY_IMAGE"
  echo -e "  ${CYAN}Port:${NC}    $TCS_PORT"
  echo -e "  ${CYAN}VPC:${NC}     $VPC_ID / $SUBNET_ID"

  log "Deploying to TCS..."
  local TCS_OUT
  TCS_OUT=$(tcb cloudrun deploy \
    --env-id "$TCB_ENV_ID" \
    --service-name "$TCS_SERVICE_NAME" \
    --port "$TCS_PORT" \
    --image-url "$DEPLOY_IMAGE" \
    --vpc-config "$VPC_CONFIG" \
    --env-variable "WS_PUSH_SECRET=$WS_PUSH_SECRET" \
    --env-variable "ALLOW_INSECURE_AUTH=false" \
    --env-variable "TCB_REGION=$TCB_REGION" \
    --env-variable "NODE_ENV=production" \
    --force \
    --json 2>&1) || {
    echo -e "${RED}TCS deploy failed:${NC} $TCS_OUT" >&2
    die "Check TCS console"
  }

  info "TCS deploy complete"

  # 从 CBR detail API 提取当前访问地址
  local TCS_HOST
  TCS_HOST=$(tcb cloudrun detail --env-id "$TCB_ENV_ID" --service-name "$TCS_SERVICE_NAME" --json 2>/dev/null | \
    grep -o '"DefaultDomainName":"[^"]*"' | head -1 | sed 's/"DefaultDomainName":"//;s/"//g')
  local TCS_URL=""
  if [ -n "$TCS_HOST" ]; then
    TCS_URL="https://${TCS_HOST}"
    echo -e "\n${GREEN}========================================${NC}"
    echo -e "${GREEN}  ✅ Deploy Success${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "⚠️  ${BOLD}Add to .env.local:${NC}"
    echo ""
    echo -e "  # WS service address (TCS CBR direct domain)"
    echo -e "  WS_TCS_URL=${TCS_URL}"
    echo ""
    echo -e "  # Push secret (must match TCS container env)"
    echo -e "  WS_PUSH_SECRET=${WS_PUSH_SECRET}"
    echo ""
    echo -e "⚠️  Then run: ${CYAN}./bin/sync-tcb-env${NC}"
    echo -e "⚠️  Or update : ${CYAN}./${NC}"
  else
    warn "Could not extract CBR domain from TCS detail API"
    warn "Get it from: TCB Console → Cloud Hosting → ecan-graphql-ws → Access Address"
  fi
fi

# ============ ROLLBACK ============
if $ROLLBACK; then
  echo -e "${BOLD}===== Rollback TCS =====${NC}"
  local RB_TO
  if [ -n "$TARGET_VERSION" ]; then
    RB_TO="${VERSIONED_IMAGE}:${TARGET_VERSION}"
  else
    local PREV
    PREV="$(previous_version)"
    [ -z "$PREV" ] && die "No version to rollback to"
    RB_TO="${VERSIONED_IMAGE}:${PREV}"
    info "Rollback to: $PREV"
  fi
  echo -e "  ${CYAN}Image:${NC} $RB_TO"
  log "Rolling back..."
  tcb cloudrun deploy \
    --env-id "$TCB_ENV_ID" \
    --service-name "$TCS_SERVICE_NAME" \
    --port "$TCS_PORT" \
    --image-url "$RB_TO" \
    --force \
    --json 2>&1 | tail -5
  info "Rollback complete"
fi

# ============ SMOKE TEST ============
if $SMOKE; then
  echo -e "${BOLD}===== Smoke Test =====${NC}"
  log "Local tests..."
  node services/test-ws-protocol.js 2>&1 | tail -3
  node services/test-ws-bridge.js 2>&1 | tail -3
  local TCS_HOST
  TCS_HOST=$(tcb cloudrun detail --env-id "$TCB_ENV_ID" --service-name "$TCS_SERVICE_NAME" --json 2>/dev/null | \
    grep -o '"accessUrl":"[^"]*"' | head -1 | sed 's/"accessUrl":"//;s/"//g' || echo "")
  if [ -n "$TCS_HOST" ]; then
    log "TCS health check..."
    curl -sf "http://${TCS_HOST}/healthz" && info "TCS /healthz OK" || warn "TCS /healthz failed"
  fi
fi

echo -e "\n${GREEN}✅ Done${NC}\n"
