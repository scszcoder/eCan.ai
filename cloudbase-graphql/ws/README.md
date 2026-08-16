# eCan.ai — ecan-graphql-ws (TCS 云托管容器)

腾讯云云托管 (TCS / TCC) 容器，跑 graphql-ws / AppSync-compatible WebSocket 服务。

## 部署

```bash
# 从 cloudbase-graphql/ws/ 跑 deploy 脚本
./scripts/deploy.sh                  # TCB 云端构建 + 部署 (默认)
./scripts/deploy.sh --source         # 同上 (显式)
./scripts/deploy.sh --local          # 本地 Docker 跑 (端口 9102)

# 或用顶层 wrapper
../bin/deploy-ws.sh                 # 同 ./scripts/deploy.sh + 自动同步 WS_TCS_URL 到 SCF
../bin/deploy-ws.sh --dry-run
```

deploy 入口 → `cloudbase-graphql/ws/scripts/deploy.sh`，从 `cloudbase-graphql/` 跑。
它用 `tcb cloudrun deploy --source .` 让 TCB 云端从源码构建镜像，避开了本地 docker build → TCR push 的繁琐链路。

## 本地测试

```bash
node services/test-ws-protocol.js    # 28 protocol-level tests (no network)
```

## 入口

- `index.js` — HTTP + WS server
  - `GET  /healthz` — 健康检查
  - `POST /publish`  — SCF → WS 跨实例推送 (需 `WS_PUSH_SECRET` header)
  - `WS   /ws`      — graphql-ws subprotocol, 客户端用 JWT token 连

## 与 SCF 共享

`event-bus.js` 是 SCF 和 WS **都**要用的接口（订阅 ↔ 发布）。WS 这份必须与 `cloudbase-graphql/scf/event-bus.js` byte-identical：

```bash
# 验证
node ../bin/sync-event-bus.js

# 修复
node ../bin/sync-event-bus.js --fix
```

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `PORT`            | 否 (默认 9102) | 监听端口 |
| `WS_PUSH_SECRET`  | 是 (生产)      | SCF → WS 推送鉴权 (header X-Push-Secret) |
| `ECAN_JWT_SECRET` | 是 (生产)      | HS256 验证 30-day session token |
| `ALLOW_INSECURE_AUTH` | 否 (默认 false) | 测试用：任意 token 都接受 (仅 ALLOW_INSECURE=local dev) |
| `WS_TEST_AUTH_MODE` | 否 (默认 false) | 仅隔离云端测试服务启用，接受受签名、短期 WS 测试 token |
| `WS_TEST_AUTH_SECRET` | 仅测试模式 | 测试 token 的 HMAC 密钥；不得配置到生产服务 |
| `BUILD_VERSION`   | 否             | 由 deploy 脚本自动注入 git commit + timestamp |

## Isolated Cloud E2E Test

The `ecan-graphql-ws-test` Cloud Run service is reserved for an end-to-end
subscription check with `ecan-graphql-api-test`. It must have
`WS_TEST_AUTH_MODE=true`, a unique `WS_TEST_AUTH_SECRET`, and its own protected
`WS_PUSH_SECRET`. Production `ecan-graphql-ws` must leave test auth disabled.

Run the focused check with the test service's public WSS URL and test-auth
secret supplied only through the process environment:

```bash
TCB_TEST_WS_URL=wss://<test-service>/ws \
WS_TEST_AUTH_SECRET=<test-only-secret> \
node scripts/test-cloud-ws-e2e.js
```

The runner connects a real `graphql-ws` client, subscribes to `onTaskStatus`,
direct-invokes `ecan-graphql-api-test` to publish an event, and asserts that the
matching `data` frame is received. It never writes the secret to disk or logs it.

所有密钥通过 TCB ServerConfig.EnvParams 配置 (`tcb api tcbr UpdateCloudRunServerConfig`)，不进入源码 / 镜像 / git。