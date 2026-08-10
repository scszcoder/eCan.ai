# ============================================================
# TCB Cloud Run WebSocket 服务 (TCS)
# 部署: tcb cloudrun deploy --source . --service-name ecan-graphql-ws
#
# 此文件被 TCB 用于构建容器镜像。
# TCB 会自动注入全部源码 (COPY . .)，然后:
#   1. 安装 package.json 中的依赖 (npm install)
#   2. 设置 PORT 环境变量
#   3. 运行 ENTRYPOINT/CMD
#
# PORT: 9102 (graphql-ws / AppSync-compatible WebSocket)
# ============================================================
FROM node:20-alpine

ENV NODE_ENV=production \
    PORT=9102 \
    TCB_REGION=ap-shanghai

# 安装 WebSocket 服务必需的运行时依赖
# ws: graphql-ws / AppSync WebSocket 协议
# @cloudbase/node-sdk: TCB JWT 验证
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund ws @cloudbase/node-sdk

# TCB 会自动 COPY . . 注入源码，此处 COPY 为本地测试兼容
COPY . .

EXPOSE 9102

# 入口: 直接运行 WS 服务 (WS 函数入口)
CMD ["node", "functions/ecan-graphql-ws/index.js"]
