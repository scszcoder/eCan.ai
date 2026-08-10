# CN TCB SSE 实时推送 — 部署与运维指南

## 1. 架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│  client (GUI / 脚本 / curl)                                              │
│   │                                                                      │
│   ├─ HTTP POST /api/graphql         → Query / Mutation / publish*       │
│   │                                                                      │
│   └─ GET /api/events?topic=xxx&...  → SSE 长连接                          │
│          │                                                               │
│   ┌──────▼───────────────────────────────────────────────────────┐       │
│   │  ecan-graphql-sse (HTTP trigger)  ←─── 独立云函数              │       │
│   │                                                              │       │
│   │  sse-bridge + event-bus (in-process)                          │       │
│   │   ↑                              ↑                            │       │
│   │   │ subscribe(topic, target)     │ publish(topic, target, …)  │       │
│   │   │                              │                            │       │
│   └─▲─┼──────────────────────────────┼────────────────────────────┘       │
│     │ │                              │                                    │
│     │ │                              │ HTTP POST /publish (X-ECAN-Push-Secret)│
│     │ │                              │                                    │
│   ┌─┼──────────────────────────────▼────────────────────────────┐       │
│   │  ecan-graphql-api (HTTP trigger)                    │       │
│   │                                                              │       │
│   │  yoga + prisma + event-bus + sse-bridge-push                │       │
│   │   ↑                                          │       │
│   │   │                                          │       │
│   │   │   bus.publish(...) ────►  attachSseBridge() ─◆ HTTP push  │       │
│   │   │   (resolver)                                   │       │
│   └────────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────────┘
```

**关键不变量**：
- SSE 客户端连接在 **ecan-graphql-sse** 这个独立函数实例里
- `ecan-graphql-api` 的 resolver 通过 `event-bus.publish(...)` 触发 publish
- `attachSseBridge()` 把每次 publish 同步 HTTP POST 到 `ecan-graphql-sse/publish`
- `ecan-graphql-sse` 收到 POST 后在**自己的 in-process** event-bus 上 publish，write 到所有 SSE 连接
- 跨实例投递镜像 AWS AppSync `appsync-api` ↔ `appsync-realtime-api` 拓扑

## 2. 部署步骤

### 2.1 准备

```bash
cd cloudbase-graphql
npm install   # 本地开发用，云端会用预编译的 zip
```

### 2.2 打包

```bash
# 1. GraphQL API (整体 28MB zipped — 瘦包后)
./deploy.sh
# 内部把 node_modules 修剪完 (移除 macOS-only prisma 引擎, tencentcloud-sdk, 等)
# 再 zip 出来

# 2. SSE 独立函数 (5.6MB zipped)
./scripts/bundle-sse.sh
```

### 2.3 同步环境变量

```bash
./scripts/sync-tcb-env.sh
# 推送以下 secret 到 TCB 控制台:
#   - DATABASE_URL  → ecan-graphql-api
#   - SSE_PUSH_SECRET  → ecan-graphql-api + ecan-graphql-sse (相同值)
#   - COS_BUCKET, COS_REGION, etc.
```

### 2.4 部署到 TCB

```bash
# cloudbase framework (cloudbaserc.json 驱动)
cloudbase deploy --env-id sccb0-d0gc5398xf028be6a

# 或 tcb CLI 单函数
tcb fn deploy ecan-graphql-api \
  --env-id sccb0-d0gc5398xf028be6a \
  --code . \
  --handler index.main \
  --runtime Nodejs20.19 \
  --memory 512 \
  --timeout 300 \
  --region ap-shanghai

tcb fn deploy ecan-graphql-sse \
  --env-id sccb0-d0gc5398xf028be6a \
  --code /tmp/sse-pkg \
  --handler index.main \
  --runtime Nodejs20.19 \
  --memory 256 \
  --timeout 300 \
  --region ap-shanghai
```

### 2.5 配置触发器

```bash
# GraphQL HTTP 触发器
tcb fn trigger create ecan-graphql-api \
  --env-id sccb0-d0gc5398xf028be6a \
  --trigger-name http-trigger \
  --type http \
  --method GET,POST \
  --path /api/graphql

# SSE HTTP 触发器 (客户端连接)
tcb fn trigger create ecan-graphql-sse \
  --env-id sccb0-d0gc5398xf028be6a \
  --trigger-name http-trigger \
  --type http \
  --method GET,POST \
  --path /api/events
```

## 3. 验证

### 3.1 健康检查

```bash
curl -sN "https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/api/graphql" \
  -H "Accept: text/html" | head -5
# 应该返回 graphql-yoga landing page

curl -s "https://ecan-graphql-sse-sccb0-d0gc5398xf028be6a.service.tcloudbase.com/healthz"
# {"success":true,"service":"ecan-graphql-sse"}
```

### 3.2 SSE 端到端

启动一个 SSE 客户端：
```bash
curl -sN "https://ecan-graphql-sse-sccb0-d0gc5398xf028be6a.service.tcloudbase.com/api/events?topic=onTaskStatus&runID=test-1"
# 应返回: : connected topic=onTaskStatus target=test-1  + 阻塞
```

在另一 shell 触发 publish：
```bash
curl -X POST "https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/api/graphql" \
  -H "Content-Type: application/json" \
  -d '{"query":"mutation { publishTaskStatus(input: {runID: \"test-1\", success: true, runner: \"verify\"}) { runID } }"}'
```

SSE 客户端应立即收到（来自 `ecan-graphql-sse` 函数实例的 push）：
```
event: onTaskStatus
data: {"topic":"onTaskStatus","payload":{"runID":"test-1",...}}
```

### 3.3 已知故障

| 现象 | 根因 | 解决 |
|------|------|------|
| `COS 上传超时（60秒）` | zip 仍然太大 | 重新跑 `deploy.sh` — 瘦包后会 < 30MB |
| SSE 客户端 404 | 路由 `/api/events` 未注册 | 跑 §2.5 第二段 |
| `Cannot find module '@prisma/client'` | node_modules 被 remove 过度 | 检查 deploy.sh 的 prune 列表 |
| `Cannot find libquery_engine-linux-x86_64` | 删错了 binary | 保留 `libquery_engine-rhel-openssl-1.1.x.so.node` |

## 4. 跨平台部署 — Prisma Engine Binary

`@prisma/client` 在 macOS dev 机上 `prisma generate` 会同时下载多个 engine binaries:
- `libquery_engine-darwin-arm64.dylib.node` (本地 dev)
- `libquery_engine-linux-musl-arm64-openssl-1.1.x.so.node` (Alpine)
- `libquery_engine-rhel-openssl-1.0.x.so.node` (旧 OpenSSL)
- `libquery_engine-rhel-openssl-1.1.x.so.node` (SCF Node 20 runtime)

deploy.sh 保留 **rhel-openssl-1.1.x** (Node 20 SCF runtime 用的), 删掉其他。
Prisma CLI 本身 (`node_modules/prisma/`, 58MB) 也被删掉 — 不需要 migrate, 用 `prisma db push` 部署即可。

## 5. 客户端适配

### 5.1 Intl (AWS AppSync)

**零改动**。`agent/chats/wan_chat.py` 继续走 `_aws_appsync_loop` (websocket-client)。

### 5.2 CN (TCB SSE)

业务层零改动。HTTP transport 从 WebSocket 换成 SSE 即可：

```python
# agent/cloud_api/endpoints.py
async def _tcb_sse_subscribe(topic, target, callback, ...):
    url = f"{base_url}/api/events?topic={topic}&{key}={target}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            event_name = None
            async for line in resp.content:
                if line.startswith(b'event: '):
                    event_name = line[7:].decode().strip()
                elif line.startswith(b'data: '):
                    payload = json.loads(line[6:].decode())
                    if event_name == topic:
                        await callback(payload)
```

### 5.3 浏览器

```javascript
const es = new EventSource('/api/events?topic=onTaskStatus&runID=xxx', {
  withCredentials: true
});
es.addEventListener('onTaskStatus', (e) => {
  const data = JSON.parse(e.data);
  console.log('update:', data.payload);
});
```

## 6. 主题清单

14 个 subscription topic, 与 `resolvers/subscriptions.js` 和 `services/sse-bridge.js` 的 `TOPIC_TARGET_KEY` 对齐。
