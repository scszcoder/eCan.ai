# CN TCB SSE 实时推送 — 部署与运维指南

## 1. 架构

```
┌─────────────────────────────────────────────────────────────────┐
│  client (GUI / 脚本 / curl)                                     │
│   │                                                              │
│   ├─ HTTP POST /api/graphql  → Query / Mutation / publish*     │
│   │                                                              │
│   └─ GET /api/events?topic=xxx&<key>=yyy  (SSE 长连接)            │
│          │                                                       │
│   ┌──────▼──────────────────────────────────────────────────┐   │
│   │  ecan-graphql-api (HTTP trigger)                         │   │
│   │                                                         │   │
│   │  yoga + prisma + event-bus + sse-bridge                  │   │
│   │   ↑              ↑                ↑                       │   │
│   │   │              │                │                       │   │
│   │   │         publishTaskStatus    bus.publish ──────┐      │   │
│   │   │         (resolver)            │           │      │   │
│   │   │              │                │           │      │   │
│   │   │              └─ bus.publish ──┼───────────┘      │   │
│   │   │                               │                  │   │
│   │   │  /api/events  →  same proc  ←─┘                  │   │
│   │   │  sse-bridge.subscribe()                           │   │
│   │   └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**关键不变量**：
- SSE 客户端连接和 GraphQL resolver 在**同一个函数实例**进程里
- `event-bus.js` 是**进程内 pub/sub**——瞬时送达
- 跨实例推送（未来）+ Redis pub/sub

## 2. 部署步骤

### 2.1 准备

```bash
# 安装依赖
cd cloudbase-graphql
npm install

# 生成 Prisma Client (macOS 开发机)
npx prisma generate
```

### 2.2 复制代码到 functions/ecan-graphql-api

`functions/ecan-graphql-api/` 是 SCF 入口目录。它的 `index.js` 是 thin wrapper，
所有真实代码（`index.js`, `services/`, `resolvers/`, `event-bus.js`, 等）**必须被复制进来**
——因为 SCF 容器的工作目录就是 `functions/ecan-graphql-api/`，父目录代码找不到。

```bash
cd functions/ecan-graphql-api
# 复制所有源代码（**不要**复制 node_modules）
cp -r ../../services .
cp -r ../../resolvers .
cp -r ../../compat .
cp -r ../../scheduler .
cp ../../auth.js .
cp ../../tcb-init.js .
cp ../../context-helpers.js .
cp ../../event-bus.js .
cp ../../health-check.js .
cp ../../websocket.js .
cp ../../index.js ./main.js     # 改名避开 self-require
cp ../../prisma/schema.prisma ./prisma/schema.prisma  # 必要
cp ../../package.json ./package.json
cp ../../prisma/.env ./prisma/.env  # 必要
```

### 2.3 安装依赖

```bash
cd functions/ecan-graphql-api
npm install --production
# 关键：这一步会跑 prisma generate 把 .prisma/client/ 写到 node_modules/.prisma/client/
```

### 2.4 部署到 TCB

```bash
# 部署单个函数
tcb fn deploy ecan-graphql-api \
  --env-id sccb0-d0gc5398xf028be6a \
  --dir functions/ecan-graphql-api \
  --install-dependency false \
  --force
```

**注意**：不要用 `--install-dependency true` —— 因为 package.json 里的 `postinstall: prisma generate`
在云端会跑 5+ 分钟且经常因为 Linux x86_64 prisma engine binary 缺失失败。

**部署超时**：COS 上传默认 60 秒，~200M 体积需约 3 分钟。SCF CLI 不暴露超时参数；
如果失败，重复运行（CLI 内部会重试）。

### 2.5 注册 /api/events 路由

```bash
yes | tcb routes add -e sccb0-d0gc5398xf028be6a --region ap-shanghai \
  --data '{"domain":"sccb0-d0gc5398xf028be6a.service.tcloudbase.com",
           "routes":[{"path":"/api/events",
                      "upstreamResourceType":"SCF",
                      "upstreamResourceName":"ecan-graphql-api",
                      "enablePathTransmission":true}]}'
```

**同时给旧域名 (app.tcloudbase.com) 也加一份** —— 两个域名路由表独立。

## 3. 测试

### 3.1 SSE 连接

```bash
curl -sN "https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/api/events?topic=onTaskStatus&runID=test-1"
# 应返回 : connected topic=onTaskStatus target=test-1 注释然后阻塞
```

### 3.2 触发 publish

```bash
curl -X POST "https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/api/graphql" \
  -H "Content-Type: application/json" \
  -d '{"query":"mutation { publishTaskStatus(input: {runID: \"test-1\", success: true, error: \"\", runner: \"verify\"}) { runID } }"}'
```

**SSE 客户端应立即收到**：
```
event: onTaskStatus
data: {"topic":"onTaskStatus","payload":{"runID":"test-1","success":true,"error":"","runner":"verify"}}
```

### 3.3 已知故障模式

| 现象 | 根因 | 解决 |
|------|------|------|
| HTTP 404 `/api/events` | 路由未注册 | 跑 `tcb routes add` |
| HTTP 500 `Function code exception` | 容器 init 失败 | 看 `tcb logs search` 的 `tcb_log` 字段 |
| `Cannot find module '@prisma/client'` | node_modules 没装全 | 重新 `npm install --production` |
| `Cannot find libquery_engine-linux-x86_64` | macOS 装的 prisma 没 Linux binary | 见 §4 |

## 4. 跨平台部署 — Prisma Engine Binary 问题

**问题**：在 macOS 上 `npx prisma generate` 生成的 `libquery_engine-*` 只覆盖 darwin 平台。
SCF 容器是 Linux x86_64，运行时会找不到 query engine。

**解决 A — 用 Linux 容器打包**：
```bash
docker run --rm -v $(pwd):/app -w /app node:20 bash -c \
  "npm install --production && npx prisma generate"
```

**解决 B — Docker multi-stage build**：
```dockerfile
FROM node:20-bookworm AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm install --production
COPY . .
RUN npx prisma generate

FROM node:20-bookworm-slim AS runtime
COPY --from=build /app /app
COPY --from=build /app/node_modules/.prisma /app/node_modules/.prisma
CMD ["node", "functions/ecan-graphql-api/index.js"]
```

**解决 C — 用 Prisma Data Proxy**（不推荐：增加外部依赖）：
```bash
# 环境变量
DATABASE_URL=prisma://...?api_key=xxx
```

## 5. 客户端适配

### 5.1 Intl (AWS AppSync)

**零改动**。`agent/chats/wan_chat.py` 继续走 `_aws_appsync_loop` (websocket-client)。

### 5.2 CN (TCB)

业务层（`wan_chat.py`、`w2p_handlers/chat_handler.py`）**零改动**。
只需把 HTTP transport 层从 WebSocket 换成 SSE：

```python
# agent/cloud_api/endpoints.py
async def _tcb_sse_subscribe(topic, target, callback, ...):
    """SSE 客户端 — 替换 _tcb_subscribe WebSocket 实现"""
    url = f"{base_url}/api/events?topic={topic}&{key}={target}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
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

## 6. 跨实例推送（未来）

当前 `bus.publish` 只送达同进程订阅者。SCF 水平扩展后，instance A 上的 mutation
**不会**触发 instance B 上的 SSE 客户端。

**当前选择 — 接受限制**：
- AWS AppSync 路径同样有此限制（subscriptions 在 AppSync 服务维护，不在 lambda）
- CN 业务量小，SCF 实例数通常 1-2 个
- 客户端断线重连时，`/api/graphql` Query 仍能拉到最新状态（DB 持久）

**未来方案 — Redis pub/sub**：
```javascript
// 每个 instance 启动时
bus.attachBridge((event) => {
  redisClient.publish('ecan-events', JSON.stringify(event));
});

// Redis subscriber
redisClient.subscribe('ecan-events');
redisClient.on('message', (channel, msg) => {
  const event = JSON.parse(msg);
  bus.publish(event.topic, event.target, event.payload);
});
```

## 7. 主题清单 (与 resolver subscriptions.js 对齐)

| Schema field | URL 参数 | 触发 source |
|---|---|---|
| `onMessageReceived(chatID)` | `?chatID=xxx` | `sendWanMessage` mutation |
| `onA2AMessageReceived(channelId)` | `?channelId=xxx` | `sendA2AMessage` |
| `onAccountNotification(owner)` | `?owner=xxx` | `publishAccountNotification` |
| `onSkillEditorStreamEvent(sessionId)` | `?sessionId=xxx` | `publishSkillEditorStreamEvent` |
| `onPassiveCommand(runId, clientId)` | `?runId=xxx&clientId=yyy` | `publishPassiveCommand` |
| `onPassiveHello(runId, clientId)` | `?runId=xxx` | `publishPassiveHello` |
| `onPassiveStepResult(runId, clientId)` | `?runId=xxx` | `publishPassiveStepResult` |
| `onPuzzleReceived` | 无 (broadcast) | `publishPuzzle` |
| `onPuzzleResultReceived(pzid)` | `?pzid=xxx` | `publishPuzzleResult` |
| `onLongLLMTaskComplete(id)` | `?id=xxx` | `publishLongLLMTaskComplete` |
| `onSceneComplete(request_id)` | `?request_id=xxx` | `publishSceneComplete` |
| `onAgentSceneEvent(acctSiteID)` | `?acctSiteID=xxx` | `publishAgentSceneEvent` |
| `onStoryUpdate(acctSiteID)` | `?acctSiteID=xxx` | `publishStoryUpdate` |
| `onTaskStatus(runID)` | `?runID=xxx` | `publishTaskStatus` |
