# eCan.ai CN 版本部署清单

## 一、当前状态

### 云函数状态
| 函数名 | 状态 | 运行时 | 内存 | 超时 | 触发器 |
|--------|------|--------|------|------|--------|
| `ecan-graphql-api` | Active | Nodejs20.19 | 512MB | 60秒 | HTTP `/api/graphql` |
| `ecan-websocket` | Active | Nodejs20.19 | 512MB | 300秒 | WebSocket connect/disconnect/message |

### 当前环境变量（来自 cloudbaserc.json）

| 函数 | 变量 | 状态 |
|------|------|------|
| `ecan-graphql-api` | `NODE_ENV` | `production` ✅ |
| `ecan-graphql-api` | `TCB_REGION` | `ap-shanghai` ✅ |
| `ecan-graphql-api` | `COS_REGION` | `ap-shanghai` ✅ |
| `ecan-graphql-api` | `COS_BUCKET` | `7363-sccb0-d0gc5398xf028be6a-1251680599` ✅ |
| `ecan-graphql-api` | `WEBSOCKET_FUNCTION_NAME` | `ecan-websocket` ✅ |
| `ecan-graphql-api` | `DATABASE_URL` | 🔴 推送真实密码（占位符替换） |
| `ecan-websocket` | `NODE_ENV` | `production` ✅ |
| `ecan-websocket` | `TCB_REGION` | `ap-shanghai` ✅ |
| `ecan-websocket` | `COS_REGION` | `ap-shanghai` ✅ |
| `ecan-websocket` | `COS_BUCKET` | `7363-sccb0-d0gc5398xf028be6a-1251680599` ✅ |
| `ecan-websocket` | `WEBSOCKET_PUSH_SECRET` | 🔴 推送真实 HMAC 密钥（占位符替换） |
| `ecan-health` | `NODE_ENV` | `production` ✅ |
| `ecan-health` | `TCB_REGION` | `ap-shanghai` ✅ |

> **不在 cloudbaserc.json 中但可由 `sync-tcb-env.sh` 推送（可选）**：
> `TENCENT_SCHEDULER_FUNCTION` / `TENCENT_SCF_NAMESPACE` / `TENCENT_REGION` — 用于 TKE Worker Launcher 调度，可后续按需配置。

### HTTP 触发器
- **状态**: ❌ 未配置
- **路径**: /api/graphql
- **方法**: GET, POST

### WebSocket 触发器
- **状态**: ❌ 未配置（控制台 → 云函数 → ecan-websocket → 触发管理）
- **API 网关**: 启用集成 `SCF`，路径 `/ws`

### VPC 配置
- **状态**: ❌ 未配置
- **需求**: 需要配置以便 SCF 访问 PostgreSQL 数据库

### TKE Worker Launcher
- **镜像**: `apps/cn/services/worker-launcher`（Node 20）
- **位置**: TKE 集群 `ecan-workers` 命名空间
- **服务**: `ecan-worker-launcher` Service（Internal-CLB）
- **必须共享**: `WORKER_LAUNCH_SECRET` 与 `TENCENT_WORKER_LAUNCH_SECRET` 一致

---

## 二、必须手动配置项 (TCB 控制台)

### 1. PostgreSQL 数据库连接信息 🔴 最关键

**获取位置**: 
- 腾讯云控制台 → 云开发 → 数据库 → PostgreSQL
- 或访问: https://console.cloud.tencent.com/tcb/database/postgres?envId=sccb0-d0gc5398xf028be6a

**实例信息** (从环境详情获取):
- 实例ID: `tnt-850w63jr0`
- 地域: ap-shanghai
- 状态: RUNNING

**需要填写**:
```
DATABASE_URL=postgresql://用户名:密码@主机地址:5432/ecan
```

**示例格式**:
```
DATABASE_URL=postgresql://ecan_user:your_password@10.16.x.x:5432/ecan
```

### 2. HTTP 触发器配置 🔴 API 访问

**配置步骤**:
1. 进入 TCB 控制台 → 云函数 → ecan-graphql-api
2. 点击「触发管理」→ 「创建触发器」
3. 选择触发方式: HTTP 触发
4. 配置:
   - 触发路径: `/api/graphql`
   - 请求方法: GET, POST
   - 认证方式: 免鉴权 (或按需配置)

### 3. WebSocket 触发器配置 🔴 实时推送

**配置步骤**:
1. 进入 TCB 控制台 → 云函数 → ecan-websocket
2. 点击「触发管理」→ 「创建触发器」
3. 选择 API 网关 WebSocket，启用集成 `SCF`
4. 路径: `/ws`
5. 进 API 网关启用 WebSocket 协议

**关键环境变量**:
- `WEBSOCKET_PUSH_SECRET`：与来自其他 SCF 的 push HTTP 调用之间的 HMAC 共享密钥

### 4. VPC 网络配置 🔴 数据库访问

**配置步骤**:
1. 进入 TCB 控制台 → 云函数 → ecan-graphql-api → 函数配置
2. 编辑 VPC 配置:
   - 选择与 PostgreSQL 同 VPC 的网络
   - 选择对应子网

**注意**: PostgreSQL 实例 `tnt-850w63jr0` 需要开启公网访问，或 SCF 与数据库在同一 VPC 内网互通。

### 5. COS 存储配置 🟡 文件操作

**获取位置**:
- TCB 控制台 → 存储 → 查看存储桶

**当前存储桶**:
```
Bucket: 7363-sccb0-d0gc5398xf028be6a-1251680599
Region: ap-shanghai
```

**环境变量**:
```
COS_BUCKET=7363-sccb0-d0gc5398xf028be6a-1251680599
COS_REGION=ap-shanghai
```

### 6. TKE Worker Launcher 🟡 任务下发

**部署清单**:
- `apps/cn/services/worker-launcher/Dockerfile`
- `apps/cn/services/worker-launcher/deployment.yaml`
- `apps/cn/services/worker-launcher/rbac.yaml`
- `apps/cn/services/worker-launcher/schema.sql`（postgreSQL 表：`worker_launch_requests`、`cloud_task_runs`、`cloud_task_run_history`）

**前置条件**:
- 已创建 TKE 集群与 `ecan-workers` 命名空间
- ServiceAccount `ecan-cloud-worker`（业务容器）和 `ecan-worker-launcher`（Launcher）
- 内网 CLB（端口 80 → 8080）允许 SCF 所在 VPC 访问
- 推送镜像到 TCR，Secret `ecan-worker-launcher` 含 `database-url` 和 `launch-secret`

**SCF 共享密钥**:
- `TENCENT_WORKER_LAUNCH_SECRET` (SCF) === `WORKER_LAUNCH_SECRET` (Launcher)

---

## 三、代码修改清单

### 已修改文件

| 文件 | 修改内容 | 必要性 |
|------|----------|--------|
| `index.js` | BigInt `lastSeen` → `String`（AppSync 客户端不原生支持 BigInt） | ✅ 必需 |
| `cloudbaserc.json` | 启用 `ecan-graphql-api` HTTP 触发器 + 新增 `ecan-websocket` SCF 与 WebSocket 触发器 | ✅ 必需 |
| `websocket.js` | TCB SCF WebSocket 入口（`onConnect` / `onDisconnect` / `onMessage`） | ✅ 必需 |
| `package.json` | 新增 `schema:coverage` 与 `test:unit` 脚本 | 🟡 推荐 |

### 自动创建/补全

| 文件 | 说明 |
|------|------|
| `scripts/schema-coverage.js` | 与 AppSync schema 对比，输出 CN GraphQL 操作覆盖率 |
| `scripts/test-units.js` | 纯函数单元测试（不依赖 DB） |
| `prisma/migrations/migration_lock.toml` | Prisma 迁移锁（之前缺失） |

### 清理完成
- ✅ `scf_bootstrap` 文件已删除
- ✅ `.deploy_tmp` 目录已清理
- ✅ `ecan-graphql-api` 符号链接已清理

---

## 四、一键部署命令 (完成手动配置后)

```bash
cd /Users/liuqiang/WorkSpace/ecan/eCan.ai/cloudbase-graphql

# 推荐：使用 ./deploy.sh 一键打包 + 部署
./deploy.sh

# 同步 .env.local 中的 secret 到 TCB 控制台（DATABASE_URL、WEBSOCKET_PUSH_SECRET 等）
./scripts/sync-tcb-env.sh
```

**关键提示**：
- `deploy.sh` 已会自动复制 `auth.js` / `tcb-init.js` / `event-bus.js` / `context-helpers.js` /
  `health-check.js` / `resolvers/` / `services/` / `functions/` 等全部模块。
- `cloudbaserc.json` 里的 `DATABASE_URL` password 是占位符 `__SET_VIA_TCB_CONSOLE_OR_LOCAL_ENV__`，
  真实密码通过 `sync-tcb-env.sh` 从 `.env.local` 推送到 TCB 控制台（不写入 git）。

---

## 五、API 测试 (配置完成后)

```bash
# 获取 API 地址
echo "https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/api/graphql"

# 测试查询
curl -X POST https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/api/graphql \
  -H "Content-Type: application/json" \
  -d '{"query": "query { getOrgs { id name } }"}'
```

---

## 六、数据库初始化 (API 可用后)

```bash
cd /Users/liuqiang/WorkSpace/ecan/eCan.ai/cloudbase-graphql

# 配置 DATABASE_URL 后执行
npm run db:push  # 推送 schema 到数据库
node prisma/init.js  # 初始化种子数据
```

---

## 七、疑难解答

### 问题: "Missing DATABASE_URL"
**原因**: PostgreSQL 连接字符串未配置
**解决**: 在 TCB 控制台配置环境变量

### 问题: "0 code exit unexpected"
**原因**: 函数代码执行失败
**解决**: 
1. 检查环境变量是否完整
2. 查看函数日志: `tcb fn log ecan-graphql-api`

### 问题: API 返回 443 错误
**原因**: HTTP 触发器未配置
**解决**: 在 TCB 控制台创建 HTTP 触发器

---

## 八、架构说明

```
┌─────────────────────────────────────────────────────────────┐
│                      腾讯云 TCB                             │
│                                                             │
│   ┌─────────────────┐         ┌──────────────────┐          │
│   │    云函数 SCF     │ ←────→ │   PostgreSQL     │          │
│   │   (graphql-yoga) │  内网   │   (tnt-850w63)  │          │
│   └────────┬─────────┘         └──────────────────┘          │
│            │                                                   │
│            │ HTTP 触发                                         │
└────────────│──────────────────────────────────────────────────┘
             │
             ▼
    ┌─────────────────────┐
    │   API 端点          │
    │  /api/graphql       │
    └─────────────────────┘
```

---

## 九、联系信息

- **环境ID**: sccb0-d0gc5398xf028be6a
- **地域**: ap-shanghai
- **函数名**: ecan-graphql-api
- **函数ID**: lam-rpnvrxfz
