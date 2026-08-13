# scripts/cn — CN (TCB) 部署工具

## 一键部署 + 验证

```bash
./scripts/cn/deploy_cn.sh
```

这条命令依次跑：

| # | 脚本 | 作用 |
|---|------|------|
| 1 | `precheck.js` | 单元/冒烟测试 |
| 2 | `sync-tcb-env.sh` | 把 `.env.local` 的敏感变量推送到 TCB 云函数 |
| 3 | `deploy-safe.sh` | 打 zip + 部署 + 版本管理 + 回滚支持 |
| 4 | `update_auth_config.py` | 回写 endpoints 到 `apps/cn/config/auth_config.yml` |
| 5 | `ws-trigger-setup.py --status` | 检查 WS 触发器是否到位（**不创建**） |
| 6 | `verify_websocket_endpoints.sh` | curl `GET /ws/status` + `POST /ws/push` 健康检查 |

## 只跑健康检查

```bash
./scripts/cn/deploy_cn.sh --verify
```

跳过测试和部署，只验证 WS HTTP 端点是否正常。

## 跳过测试

```bash
./scripts/cn/deploy_cn.sh --skip-test
```

## 不在 wrapper 里、需要你手动做的事

**WS 触发器** — `ecan-websocket` 必须有 WS 触发器才能接受 WebSocket 握手。
CLI 在新版 TCB 下创建 API Gateway 触发器**经常版本错位**，所以这一步**保留手动**：

```
TCB 控制台 → 云函数 → ecan-websocket → 触发管理 → 创建触发器
  触发方式：API 网关触发
  路径：/ws
  方法：ANY
  鉴权：免鉴权
```

配置完成后，`verify_websocket_endpoints.sh` 会通过（它验的是 HTTP 路径 `/ws/push` `/ws/status`）；
WS 长连接（`wss://...`）需要在客户端实测。

## 依赖

- `@cloudbase/cli`（`cloudbase` 或 `tcb`）已登录
- `cloudbase-graphql/.env.local` 存在，含 `TCB_ENV_ID` `DATABASE_URL` `WEBSOCKET_PUSH_SECRET`
- 根目录 `.env` 含 `CLOUDBASE_API_BASE` 和 `WEBSOCKET_PUSH_SECRET`（verify 用）

## 出错时看什么

- `sync-tcb-env.sh` 失败 → 检查 `cloudbaserc.json` 是否还是占位符（`__SET_IN_TCB_CONSOLE__`）
- `deploy-safe.sh` 失败 → 看 `.deploy_artifacts/versions.json` 找上一个可用版本
- `/ws/status` 返回 502 → 函数代码部署未生效，跑 `--verify` 前先跑完整流程
- `/ws/push` 返回 401 → `WEBSOCKET_PUSH_SECRET` 与 `.env.local` 不一致