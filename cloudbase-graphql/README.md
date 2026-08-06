# eCan.ai CN 版本后端 - TCB GraphQL API

基于 **graphql-yoga + Prisma + 腾讯云** 的现代化 GraphQL 后端。

## 架构

```
┌──────────────────────────────────────────────────────────────┐
│                      腾讯云 TCB（生产环境）                  │
│                                                              │
│   ┌─────────────────┐         ┌──────────────────┐          │
│   │    云函数 SCF     │ ←────→ │   PostgreSQL    │          │
│   │   (graphql-yoga) │  内网   │   (VPC 内网)    │          │
│   └────────┬─────────┘         └──────────────────┘          │
│            │                                                   │
│            │ HTTP 触发                                         │
└────────────│──────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│                      本地开发                                │
│   App / 前端            ← 只调用云函数 API                   │
│   curl / Postman        ← 测试 API                          │
└─────────────────────────────────────────────────────────────┘
```

| 层级 | 技术 | 说明 |
|------|------|------|
| 运行时 | Node.js 16+ | 腾讯云 SCF |
| GraphQL | graphql-yoga | 现代化 GraphQL 服务器 |
| ORM | Prisma | 数据库访问层 |
| 数据库 | PostgreSQL | 云数据库 PostgreSQL |

## 快速开始

### 方式一：直接调用云函数 API（推荐）

```bash
# 直接测试已部署的 API
curl -X POST https://your-env.service.tcloudbase.com/api/graphql \
  -H "Content-Type: application/json" \
  -d '{"query": "query { getOrgs { id name } }"}'
```

### 方式二：本地开发（测试用）

```bash
# 1. 进入目录
cd cloudbase-graphql

# 2. 安装依赖
npm install

# 3. 复制并配置环境变量
cp .env.local.example .env.local
# 编辑 .env.local，填入 PostgreSQL 连接信息

# 4. 启动本地服务器
./dev.sh start
# 或 node index.js

# 5. 访问 Playground
# http://localhost:3000/api/graphql
```

### 方式三：部署到 TCB

```bash
# 1. 配置环境变量
cp .env.local.example .env.local
# 编辑填入 TCB_ENV_ID 等信息

# 2. 部署
./dev.sh deploy
# 或 ./deploy.sh

# 3. 在 TCB 控制台配置：
#    - 环境变量（PG_*）
#    - VPC 配置
#    - HTTP 触发器

# 4. 预发布/生产环境执行已提交迁移
npm run db:deploy
```

## 常用命令

| 命令 | 说明 |
|------|------|
| `./dev.sh start` | 启动本地开发服务器 |
| `./dev.sh init` | 初始化数据库（创建表 + 种子数据） |
| `./dev.sh studio` | 启动 Prisma Studio（数据库可视化） |
| `./dev.sh test` | 测试 API |
| `./dev.sh deploy` | 部署到 TCB |
| `./dev.sh help` | 查看帮助 |
| `npm run schema:build` | 仅验证 GraphQL schema 构造（不打 db） |
| `npm run schema:coverage` | 与 AppSync schema 对比，输出覆盖率与缺失项 |
| `npm run test:unit` | 不依赖数据库的纯函数单元测试 |

## GraphQL API

### Query

| 操作 | 说明 |
|------|------|
| `getAgents` | 获取 Agent 列表 |
| `getAgentSkills` | 获取技能列表 |
| `getAgentTasks` | 获取任务列表 |
| `getVehicles` | 获取车辆列表 |
| `getOrgs` | 获取组织列表 |
| `getOrgTree` | 获取组织树 |
| `getOrgAgentTree` | 获取组织-Agent 树 |
| `getPrompts` | 获取提示词 |
| `getAvatars` | 获取头像 |
| `getAgentKnowledges` | 获取知识库 |
| `getAgentTools` | 获取工具 |
| `getSettings` | 获取设置 |
| `getAllMine` | 批量获取当前用户数据 |
| `reqFileOp` | COS 上传/下载预签名 URL、列表及删除 |
| `getSkillEditorEvents` | Skill Editor 事件 |
| `queryAgentEndpoints` | 查询同一组织下活跃的 Agent 终端 |
| `getLongLLMTask` | 长时间 LLM 任务状态 |
| `getSkillEditorChatSessions` / `getSkillEditorChatHistory` | 技能编辑器对话 |
| `queryAgentEndpoints` / `upsertAgentEndpoint` | Agent 上线/下线/心跳 |

### Mutation

| 操作 | 说明 |
|------|------|
| `addAgents` / `updateAgents` / `removeAgents` | Agent CRUD |
| `addAgentSkills` / `updateAgentSkills` / `removeAgentSkills` | 技能 CRUD |
| `addAgentTasks` / `updateAgentTasks` / `removeAgentTasks` | 任务 CRUD |
| `addVehicles` / `updateVehicles` / `removeVehicles` | 车辆 CRUD |
| `addOrgs` / `updateOrgs` / `removeOrgs` | 组织 CRUD |
| `addPrompts` / `updatePrompts` / `removePrompts` | 提示词 CRUD |
| `addAvatars` / `updateAvatars` / `removeAvatars` | 头像 CRUD |
| `addAgentKnowledges` / `updateAgentKnowledges` / `removeAgentKnowledges` | 知识库 CRUD |
| `addAgentTools` / `updateAgentTools` / `removeAgentTools` | 工具 CRUD |
| `addAgentSkillRels` / `addAgentTaskRels` / `addAgentOrgRels` | 关系管理 |
| `addAgentSkillRelations` / `addAgentSkillToolRels` / `addAgentSkillKnowledgeRels` / `addAgentTaskSkillRels` | Intl 兼容关系管理 |
| `runCloudTasks` | 立即触发 cloud-type 任务（通过 TKE Worker Launcher） |
| `reqRAGStore` | 注册 RAG 文档元数据（档案落在 COS `users/<owner>/rag/<pid>/<file>`） |
| `upsertAgentEndpoint` / `sendA2AMessage` | Agent 注册 + A2A 消息 |
| `publishSkillEditorStreamEvent` | 向 WebSocket 频道发布事件 |
| `sendWanMessage` / `getWanMessage` | WAN 消息收发 |
| `reqApiKey` | API Key 创建/撤销 |

## 示例

### 查询

```graphql
query {
  getAgents {
    id
    name
    status
    createdAt
  }
}
```

### 添加

```graphql
mutation {
  addAgents(input: [{
    name: "My Agent"
    description: "A test agent"
    status: "active"
  }]) {
    id
    success
  }
}
```

### 更新

```graphql
mutation {
  updateAgents(input: [{
    id: "agent_xxx"
    name: "Updated Name"
  }]) {
    id
    success
  }
}
```

## 数据库

### Prisma Schema

数据库模型位于 `prisma/schema.prisma`，包含以下实体：

- **Agent** - 智能体
- **AgentSkill** - 技能
- **AgentTask** - 任务
- **Vehicle** - 车辆/设备
- **Org** - 组织
- **Prompt** - 提示词
- **Avatar** - 头像
- **AgentKnowledge** - 知识库
- **AgentTool** - 工具
- **Setting** - 设置
- **Relations** - 关系表（AgentSkillRel, AgentTaskRel, AgentOrgRel 等）

### 数据库操作

```bash
# 生成 Prisma Client
npx prisma generate

# 推送 Schema 到数据库（开发用）
npx prisma db push

# 创建开发迁移
npx prisma migrate dev

# 部署已提交迁移（预发布/生产）
npm run db:deploy

# 打开 Prisma Studio（数据库可视化）
npx prisma studio

# 初始化数据库（创建表 + 种子数据）
./dev.sh init
```

## 文件结构

```
cloudbase-graphql/
├── index.js                 # 云函数入口
├── package.json             # 依赖配置
├── prisma/
│   ├── schema.prisma       # 数据库 Schema
│   └── init.js             # 数据库初始化脚本
├── .env.local.example       # 环境变量模板
├── deploy.sh                # 部署脚本
├── dev.sh                   # 开发脚本
├── test-api.sh             # API 测试脚本
└── README.md                # 本文档
```

## 文档

- [CN 版本完整指南](../docs/CN_VERSION_GUIDE.md) - 完整部署、操作文档
- [微信登录配置](../docs/CN_WECHAT_LOGIN_SETUP.md) - 微信扫码登录接入
- [TCB 后端差异报告](../docs/CN_TCB_BACKEND_GAP_REPORT.md) - 接口覆盖及迁移顺序

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
