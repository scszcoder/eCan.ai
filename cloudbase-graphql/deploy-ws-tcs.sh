#!/bin/bash
# ============================================================
# eCan.ai TCB 云托管 (TCS) 部署脚本 - 自建 graphql-ws WS 服务
# ============================================================
#
# 架构:
#   WS 服务 (TCS)  ← HTTP POST /publish ← GraphQL API (SCF)
#   WS 服务 (TCS)  ← WSS 客户端连接 ← 桌面 App
#
# 使用方式:
#   ./deploy-ws-tcs.sh --source      # TCB 云端构建 + 部署 (推荐, 不需要 docker login TCR)
#   ./deploy-ws-tcs.sh --local       # 本地 Docker 运行 (开发测试)
#
# 前置条件:
#   1. tcb login                              (本脚本自动检测, 缺失时引导扫码)
#   2. TCR 命名空间已创建 (在 TCB 控制台)
#   3. .env.local 中已配置 TCB_ENV_ID
#
# 注意:
#   - 本脚本**仅支持 --source 模式** (TCB 云端构建)。本地 docker build/push 模式已废弃:
#     它会把 WS_PUSH_SECRET/ECAN_JWT_SECRET 通过 Docker ARG → ENV 永久写入 image layer,
#     任何人 pull 镜像都能看到明文密钥。
#   - 密钥通过 TCB ServerConfig.EnvParams 注入 (tcb api tcbr UpdateCloudRunServerConfig),
#     一次性配在 TCS 服务上, 后续 deploy 自动继承, deploy 脚本不再动源码/不传密钥。
#
# 部署:
#   ./deploy-ws-tcs.sh --source           # 一行命令: build + deploy + close old versions

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR" && pwd)"

# ============ 解析参数 ============
# 模式互斥: --source (推荐) 或 --local (dev), 默认 --source
LOCAL=false
SOURCE=false

for arg in "$@"; do
  case $arg in
    --local)   LOCAL=true ;;
    --source)  SOURCE=true ;;   # TCB 云端构建 + 部署 (默认, 推荐)
    --help|-h)
      echo "用法: $0 [OPTIONS]"
      echo "  --source  TCB 云端构建 + 部署 (默认, 不需要 docker login TCR)"
      echo "  --local   本地 Docker 运行 (开发测试)"
      echo ""
      echo "示例:"
      echo "  $0 --source    # TCB 云端构建 + 部署"
      echo "  $0             # 同上 (默认)"
      echo "  $0 --local     # 本地 Docker 启动 (端口 9102)"
      exit 0
      ;;
    -*)         echo -e "${RED}Unknown option: $arg${NC}" >&2; exit 1 ;;
  esac
done

cd "$PROJECT_DIR"

# 默认: --source (云端构建部署)
if [[ "$LOCAL" == "false" && "$SOURCE" == "false" ]]; then
  SOURCE=true
fi

# --local 与 --source 互斥
if $LOCAL && $SOURCE; then
  echo -e "${RED}❌ --local 与 --source 互斥${NC}"; exit 1
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  eCan.ai WS 服务 → TCB 云托管 (TCS)${NC}"
echo -e "${BLUE}========================================${NC}"
if $LOCAL; then
  echo "  模式: LOCAL (本地 Docker 启动, 端口 9102)"
else
  echo "  模式: --source (TCB 云端构建 + 部署)"
fi

# ============ 加载 .env.local ============
if [ ! -f ".env.local" ]; then
  echo -e "${RED}❌ .env.local 不存在${NC}"; exit 1; fi
set -a
. .env.local
set +a

TCB_ENV_ID="${TCB_ENV_ID:-sccb0-d0gc5398xf028be6a}"
TCB_REGION="${TCB_REGION:-ap-shanghai}"

# --source 模式: TCB 云端构建, 不需要本地 docker, 也不需要 TCR 镜像 tag
# 但保留 BUILD_VERSION 用于日志追溯和镜像 tag (TCB 也会用 BUILD_VERSION 作为版本信息)
if [ -z "$BUILD_VERSION" ]; then
  if git rev-parse --verify HEAD >/dev/null 2>&1; then
    BUILD_VERSION="$(git rev-parse --short HEAD 2>/dev/null)-$(date +%Y%m%d-%H%M%S)"
  else
    BUILD_VERSION="local-$(date +%Y%m%d-%H%M%S)"
  fi
fi

echo ""
echo -e "${YELLOW}📋 配置信息${NC}"
echo "  环境:     $TCB_ENV_ID"
echo "  区域:     $TCB_REGION"
echo "  版本:     $BUILD_VERSION"

# ============ 镜像构建 (本地 docker build) ============
# 注意: 本脚本**仅支持 --source 模式**。本地 docker build/push 已废弃:
#   secrets 通过 Dockerfile ARG → ENV 永久写入 image layer, pull 镜像就能看到明文密钥。
#   --source 模式用 TCB 云端构建 + ServerConfig.EnvParams 注入密钥, 源码不出现密钥, image 不出现密钥。

# ============ 部署到 TCS ============
if $SOURCE; then
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

  # ── 同步 EnvParams 到 TCS 服务配置 ─────────────────────────────────
  # 密钥不走源码占位符 (那条路会污染源码 + trap 风险 + 跨过 git)。
  # 改为 TCB server-level EnvParams (通过 tcb api tcbr UpdateCloudRunServerConfig):
  #   - 一次性配置, 后续 deploy 自动继承
  #   - 密钥永远只在 .env.local (gitignored) → shell env → TCB API → ServerConfig
  #   - 源码不出现密钥, image 不出现密钥, git working tree 不出现密钥
  #
  # 必须的 env vars (缺少任何一个部署直接失败, 不允许 silent fallback):
  #   WS_PUSH_SECRET    SCF → WS 推送鉴权
  #   ECAN_JWT_SECRET   WS 验证 30-day session token (与 resolvers/auth.js 共用)
  # 可选:
  #   ALLOW_INSECURE_AUTH  dev/test only
  #   BUILD_VERSION       runtime log 追溯 (git short SHA + timestamp)
  _missing=()
  [ -z "$WS_PUSH_SECRET" ] && _missing+=("WS_PUSH_SECRET")
  [ -z "$ECAN_JWT_SECRET" ] && _missing+=("ECAN_JWT_SECRET")
  if [ ${#_missing[@]} -gt 0 ]; then
    echo ""
    echo -e "${RED}❌ .env.local 缺少必要密钥: ${_missing[*]}${NC}"
    echo -e "${YELLOW}  请先在 .env.local 配置 (密钥本身由 .env.local 管理, 不应出现在脚本里)${NC}"
    exit 1
  fi

  # 读当前 ServerConfig, 保留所有字段 (Cpu/Mem/VPC 等), 只覆盖 EnvParams
  _srv_config_json=$(tcb cloudrun detail --env-id "$TCB_ENV_ID" --service-name "ecan-graphql-ws" --json 2>/dev/null \
    | node -e "
let d=''; process.stdin.on('data',c=>d+=c).on('end',()=>{
  try{
    const j=JSON.parse(d);
    const cfg=j.data.ServerConfig;
    process.stdout.write(JSON.stringify({
      EnvId: cfg.EnvId,
      ServerName: cfg.ServerName,
      OpenAccessTypes: cfg.OpenAccessTypes,
      Cpu: cfg.Cpu,
      Mem: cfg.Mem,
      MinNum: cfg.MinNum,
      MaxNum: cfg.MaxNum,
      PolicyDetails: cfg.PolicyDetails,
      CustomLogs: cfg.CustomLogs,
      InitialDelaySeconds: cfg.InitialDelaySeconds,
      CreateTime: cfg.CreateTime,
      Port: cfg.Port,
      HasDockerfile: cfg.HasDockerfile,
      Dockerfile: cfg.Dockerfile,
      BuildDir: cfg.BuildDir
    }));
  }catch(e){process.exit(1)}
})
")
  if [ -z "$_srv_config_json" ]; then
    echo ""
    echo -e "${RED}❌ 无法读取 TCS ServerConfig (tcb cloudrun detail 失败)${NC}"
    exit 1
  fi

  # 构造新 EnvParams (JSON 字符串). 用 node 拼装避免 shell 转义陷阱.
  _body=$(WS_PUSH_SECRET="$WS_PUSH_SECRET" ECAN_JWT_SECRET="$ECAN_JWT_SECRET" ALLOW_INSECURE_AUTH="${ALLOW_INSECURE_AUTH:-false}" BUILD_VERSION="$BUILD_VERSION" node -e "
const cfg = $_srv_config_json;
cfg.EnvParams = JSON.stringify({
  WS_PUSH_SECRET:     process.env.WS_PUSH_SECRET,
  ECAN_JWT_SECRET:    process.env.ECAN_JWT_SECRET,
  ALLOW_INSECURE_AUTH: process.env.ALLOW_INSECURE_AUTH,
  BUILD_VERSION:      process.env.BUILD_VERSION
});
process.stdout.write(JSON.stringify({
  EnvId: process.env.TCB_ENV_ID,
  ServerBaseConfig: cfg
}));
")

  echo ""
  echo -e "  ${BLUE}→ 同步 EnvParams (TCS 服务配置)...${NC}"
  tcb api tcbr UpdateCloudRunServerConfig \
    --api-version 2022-02-17 \
    --body "$_body" 2>&1 | tail -5 \
    && echo -e "  ${GREEN}✓${NC} EnvParams 已同步 (WS_PUSH_SECRET + ECAN_JWT_SECRET + ALLOW_INSECURE_AUTH + BUILD_VERSION)" \
    || { echo -e "${RED}❌ EnvParams 同步失败${NC}"; exit 1; }

  echo -e "  ${GREEN}✓${NC} 构建版本: $BUILD_VERSION"

  # ── 调 TCB CLI 部署 ───────────────────────────────────────────────
  # TCB CLI 在 no-TTY 环境下会卡在 "Enable gray deployment?" prompt 上并立即返回假成功。
  # 必须用 expect + script 提供伪 TTY，处理所有 prompt，并加 --wait 等 build 真正完成。
  # 注: 容器 ENV 由 ServerConfig.EnvParams 提供 (deploy 之前一步同步), deploy 不再传任何密钥。
  _expect_script="${PROJECT_DIR}/scripts/_tcs_deploy.exp"
  cat > "$_expect_script" <<EXPECT_EOF
#!/usr/bin/expect -f
# 自动化 TCB CLI 部署: 在伪 TTY 中处理所有 prompt, 等 build 完成
set timeout 1800
log_user 1

# 用 script 创建伪 TTY, 让 CLI 的 inquirer/inquirer-prompt 能正常工作
spawn script -q /tmp/tcs_deploy_console.log tcb cloudrun deploy --service-name ecan-graphql-ws --port 9102 --source . --force --wait

expect {
  -re "Enable gray deployment.*"      { send "\r"; exp_continue }
  -re "tasks? running.*\\?"           { send "Y\r"; exp_continue }
  -re "Overwrite.*\\?"                { send "Y\r"; exp_continue }
  -re "Confirm.*\\?"                  { send "Y\r"; exp_continue }
  -re "Y/n|y/N"                       { send "Y\r"; exp_continue }
  -re "Submitting.*"                  {
    puts "\n========== CLI submitting, waiting for build ==========\n"
    exp_continue
  }
  -re "DEPLOY.*FAILED|ERROR.*deploy"  { puts "\nDEPLOY FAILED MARKER\n"; exit 1 }
  eof                                  { puts "\nCLI EOF\n"; exit 0 }
  timeout                              { puts "\nTIMEOUT\n"; exit 2 }
}
EXPECT_EOF
  chmod +x "$_expect_script"

  "$_expect_script"
  _deploy_rc=$?

  rm -f "$_expect_script"

  if [ $_deploy_rc -ne 0 ]; then
    echo ""
    echo -e "${RED}❌ TCB 部署失败 (expect 退出码: $_deploy_rc)${NC}"
    echo -e "${YELLOW}  详细日志: /tmp/tcs_deploy_console.log${NC}"
    echo -e "${YELLOW}            /tmp/tcs-deploy-output.json${NC}"
    exit $_deploy_rc
  fi

  # ── 验证 build 真正成功 (而非假性成功) ──────────────────────────────
  # 检查 deploy record 列表: 最新版本 status 必须不是 create_failed
  _latest_status=$(tcb cloudrun record list --service-name "ecan-graphql-ws" 2>/dev/null \
    | grep -E '│ [0-9]+ +│' | head -1 | awk -F'│' '{gsub(/^ +| +$/,"",$4); print $4}')
  if [ "$_latest_status" = "create_failed" ] || [ "$_latest_status" = "failed" ]; then
    echo ""
    echo -e "${RED}❌ TCB build 失败 (status=$_latest_status)${NC}"
    echo -e "${YELLOW}  查看 build log: tcb cloudrun logs build --service-name ecan-graphql-ws${NC}"
    exit 1
  fi

  echo ""
  echo -e "  ${GREEN}✓${NC} TCS 部署完成 (build 已成功)"

  echo ""

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
