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
它在 Node 20 Docker 容器中安装依赖并生成 Prisma Client，再把源码 stage 到
`.deploy_tmp/`，最后调 `cloudbase fn deploy ecan-graphql-api --dir .deploy_tmp
--force --install-dependency false`。

### Prisma / Tencent SCF 打包要求

2026-08-16 的依赖无关诊断函数验证了 SCF 运行环境：

- Linux x64
- Node.js 20.19.3
- CentOS 8 / RHEL 系
- glibc 2.28
- `process.versions.openssl = 3.0.15+quic`

Prisma 5.22 在该运行环境实际选择 `rhel-openssl-1.1.x`，尽管 Node 报告
OpenSSL 3。因此生成器必须同时包含 `rhel-openssl-1.1.x` 和
`rhel-openssl-3.0.x`，不能只根据 `process.versions.openssl` 选择一个。

CloudBase 的 COS 目录打包会忽略 `node_modules/.prisma`。部署脚本把生成的
client 复制到可见的根目录 `prisma-client/`，并重写
`node_modules/@prisma/client/{default,index}.js` 指向该目录。部署包必须包含：

- `prisma-client/index.js`
- `prisma-client/schema.prisma`
- `prisma-client/libquery_engine-rhel-openssl-1.1.x.so.node`
- `prisma-client/libquery_engine-rhel-openssl-3.0.x.so.node`
- `node_modules/@prisma/client/**`

不要从宿主机复制 Prisma Client，也不要让 CloudBase 在上传后重新生成它。
代码上传必须在目标函数配置为 `InstallDependency=FALSE` 时执行。`fn code update`
会读取当前目录最近的 `cloudbaserc.json`；操作测试函数时，应从 mode `0600` 的
临时配置目录运行，并用绝对 `--dir` 指向 `.deploy_tmp`，避免误用生产配置。

### 隔离的直接调用测试

`TCB_DIRECT_TEST_MODE=true` 只应配置在非公开测试函数（当前为
`ecan-graphql-api-test`）。直接事件格式：

```json
{
	"action": "direct_graphql_test",
	"owner": "wechat_b603a407904569a4ea88f9ac",
	"query": "mutation Add($input: [AgentInput!]!) { addAgents(input: $input) { id success error } }",
	"variables": {
		"input": [{ "id": "test-id", "name": "Test Agent", "status": "active" }]
	}
}
```

该路径只接受 SCF Event 直接调用。函数内部生成随机 proof，再经过同一套 Yoga
schema、resolver 和 Prisma 代码；外部 HTTP 请求无法仅靠伪造 header 启用它。
生产 `ecan-graphql-api` 必须保持 `TCB_DIRECT_TEST_MODE=false`。

首次成功测试：SCF request `1b4510da-ba00-474f-8974-e4cf29085d45` 创建
`agents.id=direct-test-agent-1786834065`，owner 为
`wechat_b603a407904569a4ea88f9ac`，随后通过 CloudBase PostgreSQL 查询验证。

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