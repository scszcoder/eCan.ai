# scripts/cn — CN (TCB) 部署与验证工具

CN (腾讯云) 部署管道的独立验证脚本。部署/同步动作维护在私有 Tencent 后端仓库
的 `cn/tencent/cloudbase-graphql/`；这里仅保留顶层 orchestration 中需要的验证脚本。
顶层 orchestration 中需要的验证脚本。

## 包含的脚本

| 脚本 | 作用 |
|---|------|
| `verify_websocket_endpoints.sh` | curl `GET /healthz` + `POST /publish` + e2e WebSocket 订阅 |
| `e2e_full_stack_test.sh` | 完整端到端：HTTP query/mutation + WS push + WS 订阅 |

## 一行部署 + 验证（推荐）

```bash
# 1) SCF GraphQL API
cd "$ECAN_TENCENT_BACKEND_ROOT/scf" && ./scripts/deploy-api.sh

# 2) WS 容器 + 自动同步 WS_TCS_URL 到 SCF env
cd "$ECAN_TENCENT_BACKEND_ROOT" && ./bin/deploy-ws.sh

# 3) 端到端验证
bash scripts/cn/verify_websocket_endpoints.sh
# 或更彻底的端到端（含 HTTP query/mutation）:
bash scripts/cn/e2e_full_stack_test.sh
```

## 仅验证（部署后跳过）

```bash
bash scripts/cn/verify_websocket_endpoints.sh
```

## 失败排查

- `WS_TCS_URL missing` → 跑私有后端的 `bin/deploy-ws.sh`，它会回写 URL 到 `.env.local`
- `WS_PUSH_SECRET missing` → 检查私有后端的 `.env.local`
- `/healthz` 返回 502 → WS 容器没起来，去 TCB 控制台看 cloudrun 日志
- `/publish` 返回 401 → `WS_PUSH_SECRET` 与 SCF env 不一致，重新跑 `bin/sync-tcb-env.sh`
- WebSocket 订阅收不到消息 → 看 WS 容器的 stdout，确认 `event-bus` 已 sync

## 依赖

- `ECAN_TENCENT_BACKEND_ROOT` 指向私有 `cn/tencent/cloudbase-graphql/`
- 私有后端的 `.env.local` 存在，含 `WS_TCS_URL` + `WS_PUSH_SECRET`
- TCB CLI 已登录
