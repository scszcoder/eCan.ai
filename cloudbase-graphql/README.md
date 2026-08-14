# eCan.ai CN 版本后端 — TCB GraphQL + WebSocket

基于 **graphql-yoga + Prisma + 腾讯云** 的现代化 GraphQL 后端，配套一个独立的 WebSocket 容器。

## 目录结构

```
cloudbase-graphql/
├── scf/                  # ecan-graphql-api — TCB 云函数 (graphql-yoga + Prisma + PostgreSQL)
│   ├── index.js          # SCF main entry (exports.main / PreStop)
│   ├── auth.js           # resolveIdentity + session-token mint/verify
│   ├── event-bus.js      # in-process Pub/Sub
│   ├── resolvers/        # 14 个 GraphQL resolver 模块
│   ├── services/         # cn-capabilities, cn-scene, ws-bridge-push 等
│   ├── prisma/           # schema.prisma + migrations + init.js
│   ├── scheduler/ compat/ storage/
│   ├── scripts/          # deploy-api.sh + 8 tests
│   └── package.json + package-lock.json + node_modules/
│
├── ws/                   # ecan-graphql-ws — TCB 云托管容器 (graphql-ws / AppSync-compatible)
│   ├── index.js          # HTTP + WebSocket server entry
│   ├── event-bus.js      # 与 scf/ 保持 byte-identical (bin/sync-event-bus.js 验证)
│   ├── services/ws-protocol.js
│   ├── scripts/deploy.sh # TCB cloud build + deploy
│   ├── package-runtime.json  # 给 Dockerfile 用 (仅 ws deps)
│   └── README.md
│
├── bin/                  # 跨 SCF/WS 的 utility
│   ├── deploy-ws         # 一行命令部署 WS + 自动同步 WS_TCS_URL 到 SCF
│   ├── precheck          # .env.local + cloudbaserc.json 占位符 + 健康检查
│   ├── sync-event-bus.js # 验证/修复 scf/event-bus.js 与 ws/event-bus.js 一致
│   ├── sync-tcb-env      # 推送 .env.local → SCF EnvParams
│   └── test-tcb-endpoints
│
├── Dockerfile            # TCB source build 用 (留给 TCB, 不删)
├── .dockerignore         # 排除 scf/ 等不需要的内容
├── cloudbaserc.json      # TCB 部署声明 (functionRoot=scf, 仅占位符)
├── deploy.sh             # 兼容入口, 转发到 scf/scripts/deploy-api.sh
├── docs/COS_SETUP.md
├── README.md             # 本文档
└── .env.local.example    # 环境变量模板
```

## 架构

```
┌──────────────────────────────────────────────────────────────┐
│                      腾讯云 TCB（生产环境）                  │
│                                                              │
│   ┌─────────────────┐         ┌──────────────────┐          │
│   │   scf/ 云函数    │ ←────→ │   PostgreSQL    │          │
│   │   (graphql-yoga) │  内网   │   (VPC 内网)    │          │
│   └────────┬────────┘         └──────────────────┘          │
│            │ HTTP /publish                                     │
│            ▼                                                   │
│   ┌─────────────────┐                                          │
│   │  ws/  云托管容器  │  ←── WSS 客户端（桌面 App / GUI）     │
│   │  (graphql-ws)   │                                          │
│   └─────────────────┘                                          │
└──────────────────────────────────────────────────────────────┘
```

| 层级 | 技术 |
|------|------|
| 运行时 | Node.js 20 |
| GraphQL | graphql-yoga (scf/) + graphql-ws (ws/) |
| ORM | Prisma |
| 数据库 | PostgreSQL (云数据库) |

## 快速开始

### 1. 安装并配置环境变量

```bash
# 仓库根目录
cp cloudbase-graphql/.env.local.example cloudbase-graphql/.env.local
# 编辑 .env.local, 填入 TCB_ENV_ID / DATABASE_URL / COS_BUCKET / WS_PUSH_SECRET / ECAN_JWT_SECRET
```

### 2. 部署 SCF 云函数 (GraphQL API)

```bash
cd cloudbase-graphql/scf
npm install --omit=dev

# 完整 10 步部署 (preflight + tests + prisma generate + stage + upload + migrate + sync env + smoke)
./scripts/deploy-api.sh

# 其他模式
./scripts/deploy-api.sh --dry-run        # preflight + tests + stage, 不上传
./scripts/deploy-api.sh --no-migrate     # 跳过 DB schema push
./scripts/deploy-api.sh --rollback       # 回滚到上一版
./scripts/deploy-api.sh --list-versions  # 查看历史版本
```

### 3. 部署 WS 容器 (WebSocket)

```bash
# 一行命令: TCB cloud build + deploy + 自动同步 WS_TCS_URL 到 SCF
cd cloudbase-graphql && ./bin/deploy-ws.sh

# 或单跑 WS deploy (不含同步 SCF 那一步)
cd cloudbase-graphql/ws && ./scripts/deploy.sh --source
```

### 4. 本地开发

```bash
cd cloudbase-graphql/scf
npm install --omit=dev

# 启动 GraphQL API (Playground 在 http://localhost:3000/api/graphql)
node index.js

# DB 操作
npm run db:generate    # prisma generate
npm run db:push        # 推 schema 到本地 DB (开发)
npm run db:studio      # 打开 Prisma Studio
npm run db:seed        # 运行 prisma/init.js
```

## 常用命令

```bash
cd cloudbase-graphql/scf

npm run precheck        # 部署前检查 (.env.local + cloudbaserc + unit + smoke + skill-store)
npm run test:unit       # 单元测试
npm run test:smoke      # SCF ↔ WS subscription round-trips
npm run test:ws-stack   # WS 服务端到端测试
npm run test:ws-protocol # graphql-ws 协议层测试 (在 ws/services/)
npm run test:graphql-parity # SCF schema vs WS protocol topic map 一致性
npm run test:skill-store
npm run test:all        # 全套
npm run deploy:safe     # 等价于 ./scripts/deploy-api.sh
npm run deploy:env      # 等价于 ./../bin/sync-tcb-env.sh (推送 secret → TCB 控制台)
npm run schema:build    # 仅验证 GraphQL schema 构造 (不打 db)
npm run schema:coverage # 与 AppSync schema 对比, 输出覆盖率与缺失项
```

## 部署细节

详见 [scf/README.md](./scf/README.md) 和 [ws/README.md](./ws/README.md)。

## 文档

- [scf/README.md](./scf/README.md) — SCF 云函数部署与本地开发
- [ws/README.md](./ws/README.md) — WS 容器部署与配置
- [docs/COS_SETUP.md](./docs/COS_SETUP.md) — COS 存储桶 + 跨域配置

## 鉴权要求

所有 GraphQL 请求必须携带 `Authorization: Bearer <TCB token>`。认证失败
不会降级为匿名用户。本地调试可在非生产环境显式设置
`ALLOW_INSECURE_AUTH=true`，并用 `X-ECAN-Test-User` 指定模拟用户；生产
环境即使误配该开关也不会启用。

## CN 云任务调度

`addAgentTasks`、`updateAgentTasks` 和 `removeAgentTasks` 会同步腾讯云 SCF
定时触发器，兼容 Intl 入参 `runCloudTasks(input: [{ task_id/task_name,
options }])`，并通过 HMAC 签名请求调用 TKE 内网的 Worker Launcher。部署前必须配置 `TENCENT_SCHEDULER_FUNCTION`、
`TENCENT_WORKER_LAUNCH_URL` 和 `TENCENT_WORKER_LAUNCH_SECRET`；Launcher
部署清单及说明位于 `../apps/cn/services/worker-launcher/`。
