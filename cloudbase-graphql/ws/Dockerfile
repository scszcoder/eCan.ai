# ============================================================
# TCB Cloud Run WebSocket 服务 (TCS)
# 部署: tcb cloudrun deploy --source . --service-name ecan-graphql-ws
#
# 此文件被 TCB 用于构建容器镜像。
# TCB 会自动注入全部源码 (COPY . .，但 .dockerignore 会过滤),
# 然后:
#   1. 仅安装 ws 服务运行时需要的包 (避免装上 @prisma / cos / graphql-yoga 等 SCF 依赖)
#   2. 设置 PORT 环境变量
#   3. 运行 ENTRYPOINT/CMD
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
# 只装 WS 真正需要的两个包 (~40MB)。
WORKDIR /app
COPY package-runtime.json ./package.json
RUN npm install --omit=dev --no-audit --no-fund

# TCB 会自动 COPY . . 注入源码 (受 .dockerignore 过滤)
COPY . .

EXPOSE 9102

# 入口: 直接运行 WS 服务 (WS 函数入口)
CMD ["node", "functions/ecan-graphql-ws/index.js"]
