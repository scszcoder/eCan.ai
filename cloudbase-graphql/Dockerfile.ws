# eCan.ai CN 版本 - 自建 graphql-ws WebSocket 服务 (TCB 云托管 / TCS)
#
# 部署: ./deploy-ws-tcs.sh --source  (TCB 云端构建)
# 或本地:  docker build -f Dockerfile.ws ... && ./deploy-ws-tcs.sh --push --deploy
#
# 构建时通过 --build-arg 注入:
#   WS_PUSH_SECRET       推送密钥 (本地构建用, --source 模式用 sed 占位符)
#   ALLOW_INSECURE_AUTH  非生产跳过 JWT (默认 false)
#   BUILD_VERSION        构建版本信息 (本地构建自动注入)
#
# 运行时环境变量:
#   PORT, WS_PUSH_SECRET, ALLOW_INSECURE_AUTH, TCB_REGION, BUILD_VERSION, NODE_ENV

FROM node:20-alpine

# ── 构建时参数 ──────────────────────────────────────────────────────────────
ARG WS_PUSH_SECRET=""
ARG ALLOW_INSECURE_AUTH="false"
ARG BUILD_VERSION="local"

# ── 运行时环境变量 ─────────────────────────────────────────────────────────
ENV NODE_ENV=production \
    PORT=9102 \
    TCB_REGION=ap-shanghai \
    TCB_ENV_ID=sccb0-d0gc5398xf028be6a \
    ALLOW_INSECURE_AUTH=${ALLOW_INSECURE_AUTH} \
    WS_PUSH_SECRET=${WS_PUSH_SECRET} \
    BUILD_VERSION=${BUILD_VERSION}

WORKDIR /app

# 复制 package.json 先安装依赖 (利用 Docker 缓存)
COPY package.json ./

# 只安装运行时依赖 (ws 是必需的, @cloudbase/node-sdk 用于 JWT 验证)
RUN npm install --omit=dev --no-audit --no-fund \
    ws@8.18.0 \
    @cloudbase/node-sdk@3.18.3

# 复制入口和共享模块
# ws-protocol.js 和 event-bus.js 从 cloudbase-graphql 目录复制进来
COPY services/ ./services/
COPY event-bus.js ./
COPY functions/ecan-graphql-ws/index.js ./
COPY functions/ecan-graphql-ws/api-gateway-helper.js ./

# 不需要 bootstrap — 直接运行 index.js
# scf_bootstrap 仅用于 SCF 环境,这里用 node index.js

# 非 root 运行
USER node

# 容器监听 PORT 环境变量
EXPOSE ${PORT}

# 健康检查
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:${PORT}/healthz || exit 1

# 入口: 直接运行 WS server (require.main === module 路径会被 index.js 检测)
CMD ["node", "index.js"]
