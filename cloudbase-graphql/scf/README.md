# eCan.ai — ecan-graphql-api (SCF 云函数)

腾讯云 SCF 云函数，运行 GraphQL API (graphql-yoga + Prisma + PostgreSQL)。

## 部署

```bash
# 从 cloudbase-graphql/scf/ 跑 deploy 脚本
./scripts/deploy-api.sh                  # 完整 10 步部署
./scripts/deploy-api.sh --dry-run        # preflight + tests + stage, 不上传
./scripts/deploy-api.sh --no-migrate     # 跳过 DB schema push
./scripts/deploy-api.sh --rollback       # 回滚到上一版
./scripts/deploy-api.sh --list-versions  # 查看所有版本
```

deploy 入口 → `cloudbase-graphql/scf/scripts/deploy-api.sh`，从 `cloudbase-graphql/scf/` 跑。
它把源码 stage 到 `.deploy_tmp/`，剥掉 darwin/arm64 prisma 引擎，
调 `cloudbase fn deploy ecan-graphql-api --dir .deploy_tmp --force --install-dependency false`。

## 本地测试

```bash
npm install --omit=dev
node scripts/test-units.js           # unit tests (snake_alias, etc.)
node scripts/test-graphql-parity.js  # SCF schema vs WS protocol topic map
node scripts/test-skill-store.js     # 49 unit + integration
node scripts/smoke-test-local.js     # 28 SCF ↔ WS subscription round-trips
```

## 目录

- `index.js` — SCF entry (`exports.main`, `exports.PreStop`)
- `auth.js` — Bearer token 验证 (SCF context user identity + HS256 session token)
- `event-bus.js` — in-process Pub/Sub；WS 容器复制了一份 (见 `bin/sync-event-bus.js`)
- `resolvers/` — GraphQL Mutation/Query/Subscription resolvers
- `prisma/` — schema.prisma + migrations
- `services/cn-*` — 中国版业务逻辑 (商品、车辆、订单、技能市场…)
- `services/ws-bridge-push.js` — SCF → WS 容器的跨实例推送桥
- `scheduler/tencent-scheduler.js` — 腾讯云定时触发器
- `compat/` — 老 entity/relation/legacy 兼容层
- `storage/cos-file-ops.js` — 腾讯云 COS (对象存储) 操作

## 与 WS 容器共享

`event-bus.js` 是 SCF 和 WS **都**要用的接口。两份源码必须保持 byte-identical：

```bash
# 验证 (deploy 时自动跑)
node ../bin/sync-event-bus.js

# 修复 (当一份改了另一份没改)
node ../bin/sync-event-bus.js --fix
```