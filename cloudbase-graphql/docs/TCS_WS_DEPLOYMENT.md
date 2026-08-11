# TCB 云托管 (TCS) WebSocket 服务部署指南

> **适用范围:** eCan.ai CN 版本 — 将旧的 SSE 推送 (`ecan-graphql-sse`) 替换为自建 WebSocket 服务 (`ecan-graphql-ws`)
>
> **目标:** 部署 `ecan-graphql-ws` 容器服务到 TCB 云托管，提供与 AWS AppSync Realtime 完全兼容的 WebSocket 接口。

---

## 一、系统架构

```
CN 用户客户端
      │
      │ WebSocket (graphql-ws subprotocol)
      ▼
TCB 云托管 (TCS)
┌─────────────────────────────────────┐
│  ecan-graphql-ws                    │
│  端口 9102                          │
│  ├── /healthz      (HTTP GET)       │
│  ├── /ws            (WebSocket)    │
│  └── /publish       (HTTP POST)    │
│                                      │
│  内网 (VPC) ───────────────────────│
│    └── Prisma → PostgreSQL          │
│    └── COS Storage                  │
└─────────────────────────────────────┘
      │ HTTPS + WS_PUSH_SECRET
      │ (跨实例推送)
      ▼
TCB SCF
┌─────────────────────────────────────┐
│  ecan-graphql-api                  │
│  Mutation publishSkillEditorStreamEvent
│  通过 /publish 推送到 WS            │
└─────────────────────────────────────┘
```

**与 AWS AppSync Realtime 完全兼容的协议:**

| 帧类型 | 方向 | 说明 |
|--------|------|------|
| `connection_init` | C→S | 初始化连接 |
| `connection_ack` | S→C | 连接确认 |
| `start` | C→S | 订阅 `{data, extensions}` |
| `start_ack` | S→C | 订阅确认 |
| `data` | S→C | 推送消息 `{id, payload}` |
| `ka` | S↔C | Keep-alive (每 25s) |
| `connection_terminate` | C→S | 主动断开 |

---

## 二、前置条件

### 2.1 账号与权限

- 腾讯云账号已登录 TCB (`tcb login`)
- 拥有云托管 (TCS) 读写权限
- TCR 镜像仓库写权限（TCB 自动创建）

### 2.2 环境检查

```bash
# 确认 tcb CLI 可用
tcb --version          # CloudBase CLI 3.7.x

# 确认已登录
tcb env list --json    # 能列出 sccb0 环境

# 确认 .env.local 存在
cat cloudbase-graphql/.env.local | grep TCB_ENV_ID
```

### 2.3 VPC 网络

WS 服务需要内网访问 PostgreSQL（VPC 模式）。确认以下网络资源存在：

| 资源 | 示例值 |
|------|--------|
| VPC ID | `vpc-2pt6t7qg` |
| 子网 ID | `subnet-h3cs01ip` |
| 子网 CIDR | `10.0.1.0/24` |

> ⚠️ **首次部署后需要手动配置 VPC**（见第六节「常见问题」）

---

## 三、一键部署

```bash
cd cloudbase-graphql

# 完整部署：构建 + 推送 + 部署
./deploy-tcs.sh --full

# 查看帮助
./deploy-tcs.sh --help
```

**部署流程：**

```
[1/3] Build Docker Image → [2/3] Push to TCR → [3/3] Deploy to TCS
```

**完成后会提示：**

```
⚠️  Add to .env.local:
  WS_TCS_URL=https://ecan-graphql-ws-xxxx.sh.run.tcloudbase.com
  WS_PUSH_SECRET=<生成的密钥>

⚠️  Then run: ./bin/sync-tcb-env
```

---

## 四、分步部署

### 4.1 构建 + 推送（可 CI/CD）

```bash
# 仅构建
./deploy-tcs.sh --build

# 构建 + 推送
./deploy-tcs.sh --build --push
```

### 4.2 部署

```bash
# 部署 latest
./deploy-tcs.sh --deploy

# 部署指定版本
./deploy-tcs.sh --deploy --version=v20260810-143022-abc123
```

### 4.3 从 TCB 控制台部署（备选）

如果 `tcb` CLI 不可用：

1. 打开 [TCB 控制台 → 云托管](https://console.cloud.tencent.com/tcb)
2. 选择环境 `sccb0`
3. 新建服务 → **容器镜像** → 选择 TCR 仓库
4. 配置端口 `9102`，开启公网访问

---

## 五、部署后配置

### 5.1 更新 .env.local

部署完成后，CBR 会返回一个访问地址（如 `https://ecan-graphql-ws-xxx.sh.run.tcloudbase.com`）。

```bash
# 编辑 .env.local，添加以下内容：
WS_TCS_URL=https://ecan-graphql-ws-xxx-xxxx-1251680599.sh.run.tcloudbase.com
WS_PUSH_SECRET=<部署时生成的密钥>
```

### 5.2 更新 WS_TCS_URL

WS 端点信息在 `bin/deploy-ws` 部署后自动写入 `.env.local`，并通过 `bin/sync-tcb-env` 同步到 SCF 环境变量。无需单独配置文件。

**关键：WS_ENDPOINT 必须使用 CBR 直接域名**
- ✅ `wss://ecan-graphql-ws-xxx.sh.run.tcloudbase.com`
- ❌ `wss://sccb0-xxx.service.tcloudbase.com/ws` (API Gateway 不支持 WebSocket 到 CBR 路由)

### 5.3 同步到 SCF

```bash
cd cloudbase-graphql
./bin/sync-tcb-env
```

这会将 `WS_TCS_URL` 和 `WS_PUSH_SECRET` 写入 SCF (`ecan-graphql-api`) 的环境变量。

### 5.3 验证端点

```bash
# 健康检查
curl https://ecan-graphql-ws-xxx.sh.run.tcloudbase.com/healthz

# 冒烟测试
./deploy-tcs.sh --smoke

# 本地协议测试
node services/test-ws-protocol.js
node services/test-ws-bridge.js
node scripts/test-graphql-parity.js
```

**预期输出：**
```
28 passed, 0 failed   (protocol)
15 passed, 0 failed   (bridge)
50 passed, 0 failed   (parity)
```

---

## 六、版本管理

### 6.1 版本记录文件

| 文件 | 内容 | 用途 |
|------|------|------|
| `.tcs-version` | 当前版本号 | 快速查看 |
| `.tcs-version-history` | 完整历史 | 版本追溯 |

### 6.2 版本号格式

```
v{YYYYMMDD-HHMMSS}-{git-hash}
例: v20260810-143022-a1b2c3d
```

### 6.3 回滚

```bash
# 回滚到上一版本
./deploy-tcs.sh --rollback

# 回滚到指定版本
./deploy-tcs.sh --rollback --version=v20260809-120000-abc123

# 查看可用版本
cat .tcs-version-history
```

### 6.4 部署指定版本

```bash
./deploy-tcs.sh --deploy --version=v20260809-120000-abc123
```

---

## 七、常见问题

### Q1: 部署后 healthz 返回非 200

**原因：** 构建仍在进行中（通常需要 5-10 分钟）

**解决：**
```bash
# 查看构建状态
tcb cloudrun record list --env-id sccb0-d0gc5398xf028be6a --service-name ecan-graphql-ws --json

# 查看构建日志
tcb cloudrun logs build --env-id sccb0-d0gc5398xf028be6a --service-name ecan-graphql-ws --json | tail -c 2000
```

### Q2: VPC 未配置（服务无法访问数据库）

**原因：** `tcb cloudrun deploy --source` 不支持 `--vpc-config`

**解决（手动配置）：**
1. 打开 [TCB 控制台 → 云托管](https://console.cloud.tencent.com/tcb)
2. 选择服务 `ecan-graphql-ws` → 「服务配置」
3. 开启「内网访问」→ 选择 VPC `vpc-2pt6t7qg` / 子网 `subnet-h3cs01ip`
4. 保存后等待重启

或通过 API 配置：
```bash
tcb api UpdateCloudBaseRunServerResource --env-id sccb0-d0gc5398xf028be6a \
  --ServerName ecan-graphql-ws \
  --VpcConf '{"VpcId":"vpc-2pt6t7qg","SubnetId":"subnet-h3cs01ip"}'
```

### Q3: TCR 推送失败（insufficient_scope）

**原因：** 本地 Docker 未登录 TCR

**解决：**
```bash
docker login ccr.ccs.tencentyun.com
# 输入腾讯云账号密码（或永久密钥）
```

### Q4: 想要使用本地 Dockerfile.ws 部署

```bash
# 构建本地镜像
docker build -f Dockerfile.ws \
  -t ccr.ccs.tencentyun.com/sccb0/ecan-graphql-ws:latest .

# 推送
docker push ccr.ccs.tencentyun.com/sccb0/ecan-graphql-ws:latest

# 从镜像部署
tcb cloudrun deploy \
  --env-id sccb0-d0gc5398xf028be6a \
  --service-name ecan-graphql-ws \
  --image-url ccr.ccs.tencentyun.com/sccb0/ecan-graphql-ws:latest \
  --port 9102 \
  --force
```

### Q5: 服务崩溃（OOM）

**原因：** 默认 1核/2G，可能不够

**解决：** 在控制台调整规格，或等待 TCB 自动扩缩容。

### Q6: docker: "Cannot connect to the Docker daemon"

**原因：** Docker Desktop 未启动

**解决：**
```bash
open -a Docker
# 等待 Docker 完全启动后再重试
```

---

## 八、CI/CD 集成

### 8.1 GitHub Actions

```yaml
name: Deploy TCS WS Service
on:
  push:
    branches: [main]
    paths: ['cloudbase-graphql/functions/ecan-graphql-ws/**']

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to TCS
        env:
          TCB_SECRET_ID: ${{ secrets.TCB_SECRET_ID }}
          TCB_SECRET_KEY: ${{ secrets.TCB_SECRET_KEY }}
        run: |
          cd cloudbase-graphql
          # 使用 tcb CLI 或腾讯云 SDK 部署
          tcb cloudrun deploy \
            --env-id sccb0-d0gc5398xf028be6a \
            --service-name ecan-graphql-ws \
            --source . \
            --port 9102 \
            --force
```

### 8.2 环境变量配置

在 GitHub Secrets 中配置：

| Secret | 说明 |
|--------|------|
| `TCB_SECRET_ID` | 腾讯云 SecretId |
| `TCB_SECRET_KEY` | 腾讯云 SecretKey |

> ⚠️ **安全提醒:** 切勿将 `WS_PUSH_SECRET` 等密钥提交到代码仓库。使用 TCB 控制台或 Secrets 管理。

---

## 九、回滚计划

如遇严重问题，回滚步骤：

```bash
# 1. 立即回滚到上一版本
./deploy-tcs.sh --rollback

# 2. 确认 healthz 正常
curl https://ecan-graphql-ws-xxx.sh.run.tcloudbase.com/healthz

# 3. 如仍有问题，联系 SCF 团队降级
```

---

## 十、监控与告警

### 10.1 关注指标

| 指标 | 正常范围 | 告警阈值 |
|------|----------|----------|
| 容器状态 | `normal` | `error` / `creating` > 10min |
| /healthz | 200 OK | 非 200 |
| 连接数 | 0-500 | > 800 |
| 内存使用 | < 70% | > 85% |

### 10.2 日志查看

```bash
# 构建日志
tcb cloudrun logs build --env-id sccb0-d0gc5398xf028be6a --service-name ecan-graphql-ws --json

# 运行时日志（需要 RunId）
tcb cloudrun record list --env-id sccb0-d0gc5398xf028be6a --service-name ecan-graphql-ws --json
# 找到 RunId 后
tcb cloudrun logs process --env-id sccb0-d0gc5398xf028be6a --run-id <RunId> --json
```
