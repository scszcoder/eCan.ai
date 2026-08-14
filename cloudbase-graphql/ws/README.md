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
| `BUILD_VERSION`   | 否             | 由 deploy 脚本自动注入 git commit + timestamp |

所有密钥通过 TCB ServerConfig.EnvParams 配置 (`tcb api tcbr UpdateCloudRunServerConfig`)，不进入源码 / 镜像 / git。