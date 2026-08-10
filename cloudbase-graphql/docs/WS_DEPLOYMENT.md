# 自建 graphql-ws WS 服务 — 部署说明

## 1. 架构

```
┌──────────────────────────────────────────────────────────────┐
│  Client (浏览器/Python, 标准 graphql-ws 客户端)                │
│  new WebSocket(wss://.../ws, 'graphql-ws')                    │
└──────────────────────────────────────────────────────────────┘
              │                       ▲
              │ 1. connection_init    │ 2. connection_ack
              │ 3. start              │ 4. start_ack
              │                       │ 5. data { id, payload.data.<field> }
              ▼                       │
┌──────────────────────────────────────────────────────────────┐
│  TCB Cloud Function: ecan-graphql-ws                          │
│  - 服务: services/ws-protocol.js (graphql-ws 协议层)            │
│  - 传输: ws 库 + HTTP server + upgrade handler                │
│  - 路由: /ws (通过 API Gateway)                                │
│  - 订阅: event-bus.subscribe(topic, target, ctx)              │
└──────────────────────────────────────────────────────────────┘
              ▲                       │
              │                       │ bus.publish(topic, target, payload)
              │                       ▼
┌──────────────────────────────────────────────────────────────┐
│  TCB Cloud Function: ecan-graphql-api                         │
│  - 业务: GraphQL Yoga                                         │
│  - 跨实例桥: services/ws-bridge-push.js                        │
│              bus.publish → HTTP POST /publish                 │
└──────────────────────────────────────────────────────────────┘
```

## 2. 客户端代码（与 AWS AppSync 兼容，零改动）

### 浏览器
```javascript
const ws = new WebSocket(
  `wss://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/ws?token=${jwt}`,
  'graphql-ws'
);

ws.onopen = () => {
  ws.send(JSON.stringify({ type: 'connection_init' }));
};

ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  if (msg.type === 'connection_ack') {
    ws.send(JSON.stringify({
      id: 'sub-1',
      type: 'start',
      payload: {
        data: JSON.stringify({
          query: 'subscription S { onMessageReceived(chatID: "abc") { id } }',
        }),
      },
    }));
  } else if (msg.type === 'data' && msg.id === 'sub-1') {
    console.log('Got:', msg.payload.data.onMessageReceived);
  }
};
```

### Python (wan_chat.py 已自动支持)
```python
ws = new WebSocket("wss://sccb0-.../ws?token=...", "graphql-ws")
# 协议由 wan_chat.py 内部处理
```

## 3. 部署

```bash
cd cloudbase-graphql
./deploy.sh
```

部署脚本会：
1. 同步 `ecan-graphql-api` 源码（含 `services/ws-bridge-push.js`）
2. 打包 `ecan-graphql-ws` 到 `/tmp/ws-pkg/`（含 ws + @cloudbase/node-sdk）
3. 部署到 TCB
4. 同步 `WS_PUSH_SECRET` 到两个函数
5. 清理旧的 `/api/events` SSE 路由

## 4. 验证

```bash
# 单元测试
npm run test:ws-protocol    # 协议层
npm run test:ws-bridge      # WS 端到端
npm run test:graphql-parity # topic 一致性
npm run test:ws-stack       # 完整 stack
npm run test:local-stack    # 与 SSE 兼容的拓扑

# 全部测试
npm run test:all
```

## 5. 端到端验证（部署后）

```bash
# 1. 检查 WS 函数健康
curl https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/healthz

# 2. 用 websocket-client 验证
wscat -c 'wss://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/ws?token=test' \
  -s graphql-ws \
  -x '{"type":"connection_init"}'
```

## 6. 故障排查

| 现象 | 排查 |
|------|------|
| connection_ack 收不到 | 检查 subprotocol 必须是 `graphql-ws` |
| start_ack 收不到 | 检查 query 必须是 subscription + 字段名在 14 个 topic 内 |
| data 收不到 | 检查 `WS_PUSH_SECRET` 在两个函数一致；检查 bus.publish 调用 |
| 401 from push | 检查 `WS_PUSH_SECRET` 和 `X-WS-Push-Secret` header |
| 连接立即断开 | 检查 TCB 路由是否配置：`/ws` → `ecan-graphql-ws` |

## 7. 与旧 SSE 的兼容性

- 已删除所有 SSE 相关代码（`services/sse-bridge.js`, `services/sse-bridge-push.js`, `functions/ecan-graphql-sse/`, `scripts/bundle-sse.sh`, `services/test-sse-bridge.js`）
- 客户端代码 `agent/chats/wan_chat.py` 改为走新 WS 路径
- 配置文件 `apps/cn/config/auth_config.yml` 移除 `SSE_ENDPOINT`，增加 `WS_ENDPOINT`
- 部署脚本 `deploy.sh` 不再部署 SSE 函数
- 旧 `/api/events` HTTP 路由在 deploy 时自动清理

## 8. 协议映射

| Client → | Server → | 说明 |
|----------|----------|------|
| `{type: connection_init}` | `{type: connection_ack}` | 握手 |
| `{type: start, id, payload:{data, extensions}}` | `{type: start_ack, id}` | 订阅 |
| (内部: bus.publish) | `{type: data, id, payload:{data:{<field>:<value>}}}` | 推送 |
| `{type: stop, id}` | (无响应) | 取消订阅 |
| `{type: ka}` | `{type: ka}` | 心跳 |
| `{type: connection_terminate}` | (关闭) | 主动断开 |
| (其他) | `{type: error, id, payload:[{message}]}` | 错误 |

完全镜像 AWS AppSync Realtime API 协议。
