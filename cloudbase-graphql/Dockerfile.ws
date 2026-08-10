# eCan.ai CN 版本 - 自建 graphql-ws WebSocket 服务 (TCB 云托管 / TCS)
#
# 镜像: TCB TCR (腾讯云镜像仓库)
# 部署: tcb cloudrun deploy
#
# 构建 (本地):
#   docker build -f Dockerfile.ws -t ccr.ccs.tencentyun.com/<ns>/ecan-graphql-ws:latest .
#   docker push ccr.ccs.tencentyun.com/<ns>/ecan-graphql-ws:latest
#
# 部署 (TCS):
#   ./deploy-ws-tcs.sh
#
# 或一键构建+部署:
#   ./deploy-ws-tcs.sh --build --push --deploy
#
# 环境变量:
#   PORT           容器监听端口 (默认 9102)
#   WS_PUSH_SECRET API 函数推送到 WS 的认证密钥
#   TCB_REGION     腾讯云区域 (默认 ap-shanghai)
#   ALLOW_INSECURE_AUTH  非生产环境允许无认证 (默认 false)
#   NODE_ENV       production / development

FROM node:20-alpine

# 运行时环境
ENV NODE_ENV=production \
    PORT=9102 \
    TCB_REGION=ap-shanghai \
    ALLOW_INSECURE_AUTH=false

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
