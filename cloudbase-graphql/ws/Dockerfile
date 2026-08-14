# ============================================================
# TCB Cloud Run WebSocket 服务 (TCS)
# 部署 (从 cloudbase-graphql/ 跑):
#   tcb cloudrun deploy --source ./ws --service-name ecan-graphql-ws
#
# 此文件被 TCB 用于构建容器镜像，源码必须与 Dockerfile 一起提交。
# TCB 会自动注入全部源码 (COPY . .，但 .dockerignore 会过滤),
# 然后:
#   1. 仅安装 ws 服务运行时需要的包 (避免装上 @prisma / cos / graphql-yoga 等 SCF 依赖)
#   2. 设置 PORT 环境变量
#   3. 运行 ENTRYPOINT/CMD
#
# 镜像大小 ~190MB（只装 ws + ws 工具链），与 SCF 依赖完全解耦。
#
# PORT: 9102 (graphql-ws / AppSync-compatible WebSocket)
# ============================================================
FROM node:20-alpine

ENV NODE_ENV=production \
    PORT=9102 \
    TCB_REGION=ap-shanghai

# 安装 WebSocket 服务必需的运行时依赖。
# 使用极简 package.json 而不是 COPY 仓库根 package.json, 因为后者会触发
# 安装 @prisma/cos/graphql-yoga 等 SCF 专属 deps, 单 @prisma/client 就 ~150MB。
WORKDIR /app
COPY package-runtime.json ./package.json
RUN npm install --omit=dev --no-audit --no-fund

# TCB 会自动 COPY . . 注入源码 (受 .dockerignore 过滤)
COPY . .

EXPOSE 9102

# 入口: 直接运行 WS 服务。ws/index.js 是入口, 用相对路径
# 让 ws/index.js 的 path.resolve(__dirname, 'event-bus') 和
# path.resolve(__dirname, 'services/ws-protocol') 能找到兄弟模块。
CMD ["node", "index.js"]
