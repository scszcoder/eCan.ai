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
| 运行时 | Node.js 20 | 腾讯云 SCF |
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
# 编辑填入 TCB_ENV_ID / DATABASE_URL / COS_BUCKET / WEBSOCKET_PUSH_SECRET 等

# 2. 部署云函数 + 同步 secret 到 TCB 控制台
./deploy.sh
./scripts/sync-tcb-env.sh

# 3. 在 TCB 控制台配置：
#    - VPC 配置（让 SCF 访问 PostgreSQL）
#    - HTTP 触发器（路径 /api/graphql）
#    - API 网关 WebSocket 触发器（路径 /ws，集成 ecan-websocket）

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
| `npm run test:smoke` | 启动内存 HTTP server，跑全套 HTTP/WS 集成测试 |
| `npm run precheck` | 部署前健康检查（环境变量 + secret hygiene + unit + smoke） |
| `npm run deploy:safe` | 走 `scripts/deploy-safe.sh` 的 10 步安全部署流水线 |

## 部署到 TCB

我们提供两条部署路径。`./deploy.sh` 是历史脚本，新代码部署请走 `npm run deploy:safe`（即 `scripts/deploy-safe.sh`）。

### 为什么需要新脚本

老的 `deploy.sh` 重复踩过三个坑：

1. **本地编译的 Prisma engine 被错传到云**。Mac 上 `npm install --production` 装的是 darwin-arm64 binary，TCB 是 linux x86_64 — load 时报 `Authentication failed`、查询返 `Unknown argument 'rating'`。
2. **没跑 `prisma generate`**。新加的字段在已 deployed 的 client 里不存在。
3. **没推 schema**。代码用了 `agentSkill.rating`，但 DB 没这列，云端启动后查不到。

新脚本按 10 个 stage 编排，每次 deploy 都强制重新 generate Prisma client、剥掉 darwin/arm64 binary、自动 `prisma db push`，并拒绝 destructive schema diff。

### 常用调用

```bash
# 完整部署（推荐）
npm run deploy:safe

# 不真上传 — 只跑 preflight + tests + stage
npm run deploy:safe -- --dry-run

# 只打包不部署 — 验 .deploy_tmp/ 里东西对不对
npm run deploy:safe -- --package-only

# 跳过 DB schema 推送（你刚手动跑过）
npm run deploy:safe -- --no-migrate

# 只跑 schema push
npm run deploy:safe -- --migrate-only

# 跳过 precheck（CI 里跑过）
npm run deploy:safe -- --skip-tests
```

### Pipeline stages

| # | stage | 说明 |
|---|-------|------|
| 1 | preflight | node / cloudbase CLI / `.env.local` 校验，CLI 已登录 |
| 2 | tests | `npm run precheck`：env + secret hygiene + unit + smoke + skill-store |
| 3 | prisma | `npx prisma generate`，重生成 client 代码 |
| 4 | tree | 复制源码到 `.deploy_tmp/`，剥掉 darwin/arm64 binary |
| 5 | upload | `cloudbase fn deploy`（COS 大包上传） |
| 6 | publish_version | （roadmap：snapshot 命名版本而非覆盖 $LATEST） |
| 7 | migrate | `prisma migrate diff` 预检 → `prisma db push` additive only |
| 8 | flip_traffic | （roadmap：切流到新版本） |
| 9 | env | 调用 `scripts/sync-tcb-env.sh` 推送 `.env.local` 真值到云端 env |
| 10 | smoke | curl `/api/graphql` 公共 query 验证 runtime 可达 |

### Schema 安全性

`stage_migrate` 会先 `prisma migrate diff` 跑一次脚本生成器。**任何包含以下关键字的 diff 都拒绝自动应用**：

- `DROP TABLE` / `DROP COLUMN`
- `ALTER COLUMN ... TYPE`
- `ALTER COLUMN ... DROP NOT NULL`

出现时会把 diff 写到 `.deploy_tmp/diff.sql` 并报错退出。Operator 需要手工 backup DB、调整 schema 后再 `npm run deploy:safe -- --no-migrate`。

### 回滚

`scripts/deploy-safe.sh --rollback-tag <hash>` 是 roadmap。当前回滚方式：

```bash
# 1. 找到上一次 deploy 留下的 .deploy_tmp.zip / .deploy_checksums.txt
ls -lt .deploy_tmp.zip*

# 2. 把那个 zip 解压回 .deploy_tmp/，重新跑
unzip -o .deploy_tmp.zip.<timestamp> -d .deploy_tmp/
npm run deploy:safe -- --no-migrate
```

未来 stage 6 / 8 切到 `cloudbase fn publish-version` + `config-route` 后，回滚就变成一句话。

### 部署流程对数据安全的影响

| 行为 | 影响 |
|------|------|
| `npm run deploy:safe` | additive schema 改自动应用；destructive 拒绝；现有数据保留 |
| `prisma db push --accept-data-loss` | 只对"加 NOT NULL DEFAULT 列"是 no-op；对其他操作仍是 fail-fast |
| 覆盖 `$LATEST` | SCF 容器会在 ~1 分钟内全量替换为新版本，正在运行的实例继续到结束才回收 |
| 已发数据 | 不删 / 不改 / 不重命名（除非 schema 改了） |

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
| `publishPuzzle` / `publishPuzzleResult` / `publishLongLLMTaskComplete` | 订阅触发（订阅前置触发器） |
| `publishStoryUpdate` / `publishSceneComplete` / `publishAgentSceneEvent` | 订阅触发（订阅前置触发器） |

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
- **SkillRunState / SkillBreakpoint / EditorCache** - 技能编辑器运行时状态
- **AccountNotification / A2AMessage / LongLLMTaskResult** - 通知、Agent-to-Agent 消息、长时间 LLM 任务
- **LegacyRecord** - Intl 兼容 fallback 实体（JSONB 模式）

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
├── index.js                       # 云函数主入口（SDL + createYoga）
├── websocket.js                   # WebSocket SCF 入口（onConnect/Disconnect/Message）
├── health-check.js                # ecan-health SCF 入口
├── auth.js                        # 鉴权（resolveIdentity / authenticatedOwner）
├── tcb-init.js                    # TCB App / Prisma 懒加载初始化
├── context-helpers.js             # resolver 辅助函数（assertOwnedAgent 等）
├── event-bus.js                   # 进程内 Pub/Sub（Subscriptions 驱动）
├── functions/                     # TCB SCF 入口集合（ecan-graphql-api / ecan-websocket / ecan-health）
├── resolvers/                     # 拆分的 GraphQL resolvers（14 个模块）
│   ├── capabilities.js / commerce.js / core.js / cos.js / entities.js
│   ├── jobs.js / legacy.js / misc.js / relations.js / scene.js
│   ├── skill-editor.js / subscriptions.js / types.js / publishers.js
│   └── index.js                  # 合并 + deep-merge 入口
├── services/                      # CN 业务实现（cn-capabilities, cn-scene, cn-skill-editor, …）
├── compat/                        # INTL 兼容层（cn-relations, cn-entities, cn-legacy）
├── scheduler/                     # 腾讯云 SCF 定时触发器封装
├── storage/                       # COS 工具 + bucket policy / CORS 配置
├── scripts/                       # deploy-safe / sync-tcb-env / precheck / test-units / smoke-test-local / schema-coverage / test-skill-store
├── prisma/                        # schema.prisma + init.js + migrations/
├── docs/                          # 本工程专属文档（DEPLOYMENT_CHECKLIST / CN_TCB_BACKEND_GAP_REPORT / COS_SETUP）
├── cloudbaserc.json               # TCB 部署声明（仅占位符，无明文 secret）
├── deploy.sh                      # 历史脚本（已被 deploy-safe.sh 取代）
├── dev.sh                         # 本地开发脚本
├── test-api.sh                    # API smoke 调用示例
├── .env.local.example             # 环境变量模板
└── README.md                      # 本文档
```

## 文档

- [docs/DEPLOYMENT_CHECKLIST.md](./docs/DEPLOYMENT_CHECKLIST.md) - 完整部署步骤、TCB 控制台手动配置清单
- [docs/COS_SETUP.md](./docs/COS_SETUP.md) - COS 存储桶 + 跨域配置
- [docs/CN_TCB_BACKEND_GAP_REPORT.md](./docs/CN_TCB_BACKEND_GAP_REPORT.md) - 接口覆盖及迁移顺序

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
