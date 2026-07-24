# 腾讯云 (Tencent Cloud) 后端实现

> eCan.ai 中国版的云端后端代码 (与 `lambda_functions/` 同级)

## 设计原则

1. `qcloud/` **只放云端后端代码** (类似 `lambda_functions/`)
2. 前端代码在 `gui_v2/src/`，与 AWS 版本共用 (95%+ 复用)
3. 配置由构建脚本管理，前端**只通过环境变量**使用
4. 前端对后端云厂商**完全无感知** (Cognito/TCB 都是后端的实现细节)

## 目录结构

```
qcloud/
├── functions/                    # SCF 云函数 (后端)
│   └── graphql-api/
│       ├── index.js              # SCF 入口
│       ├── schema.js             # GraphQL Schema
│       ├── resolvers.js          # Resolver 实现
│       └── package.json
├── schema/                       # 数据库 Schema
│   └── init.sql                  # TDSQL-C 表结构
└── scripts/                      # 部署脚本
    └── deploy.sh
```

## 前端代码在哪？

**前端在 `gui_v2/src/`，不在 `qcloud/`！**

```
gui_v2/src/
├── services/auth/                # 认证适配器
│   ├── AuthProvider.ts          # 统一接口 (按 VITE_IS_CN 切换)
│   ├── cognitoAuth.ts           # AWS Cognito (Intl 专用)
│   └── cloudbaseAuth.ts         # 腾讯云 TCB (CN 专用)
└── config/
    ├── api.ts                    # API 端点 (从 VITE_API_BASE/VITE_WS_URL 读)
    └── platform.ts
```

**前端构建时根据 `VITE_IS_CN` 环境变量选择不同的适配器**，但代码 100% 共享：

```typescript
// 业务代码不需要关心是哪个区域
import { getAuthAdapter } from '@/services/auth/AuthProvider';
const auth = getAuthAdapter();
await auth.signInWithEmail(email, password);  // CN 自动走 TCB，Intl 自动走 Cognito
```

## 前端配置 (构建时)

前端只关心两个环境变量：

```bash
# .env.cn.* 或 .env.intl.*
VITE_API_BASE=https://api.fastprecisiontech.com   # 或 https://api.ecan.ai
VITE_WS_URL=wss://ws.fastprecisiontech.com/graphql # 或 wss://ws.ecan.ai/graphql

# CN 专用
VITE_IS_CN=true
VITE_CLOUDBASE_ENV_ID=ecan-cn-prod-xxxxx

# Intl 专用
VITE_IS_CN=false
VITE_COGNITO_DOMAIN=ecan.auth.us-east-1.amazoncognito.com
VITE_COGNITO_CLIENT_ID=xxx
```

**前端不直接读取** `apps/cn/config/cloud_endpoints.json` 等配置文件。
这些 JSON 文件用于 CI/CD 构建脚本生成 `.env.*` 文件。

## 后端服务映射

| 能力 | AWS (Intl) | 腾讯云 (CN) |
|------|-----------|----------|
| GraphQL API | AppSync | **SCF + Apollo** (`qcloud/functions/graphql-api`) |
| 认证 | Cognito | **TCB** (后端处理) |
| 数据库 | Aurora | **TDSQL-C** (`qcloud/schema/init.sql`) |
| 对象存储 | S3 | **COS** |
| 实时通知 | AppSync Subscription | **API GW WS + Redis** |

## 部署

```bash
cd qcloud
./scripts/deploy.sh production
```

## 部署脚本从哪里读取配置？

`scripts/deploy.sh` 读取环境变量 (CI/CD 注入)：

```bash
TENCENT_SECRET_ID=xxx
TENCENT_SECRET_KEY=xxx
TDSQL_HOST=tdsql.cn-xxx.tencentcdb.com
TDSQL_PASSWORD=xxx
COS_BUCKET=ecan-cn-files
TCB_ENV_ID=ecan-cn-prod
```

这些来自 CI/CD 的 Secrets 存储，不是前端代码。

## 接口一致性

所有 GraphQL Query/Mutation/Subscription 接口与 AWS AppSync **完全一致**。
前端代码 0 修改，只换构建产物。

## 与 AWS 镜像设计

| AWS | 腾讯云 |
|-----|--------|
| `lambda_functions/` | `qcloud/` |
| `apps/intl/config/` | `apps/cn/config/` (构建脚本使用) |
| `gui_v2/.env.intl.*` | `gui_v2/.env.cn.*` |
| `cognitoAuth.ts` | `cloudbaseAuth.ts` |
| `AuthProvider.ts` (统一) | 同文件共用 |
