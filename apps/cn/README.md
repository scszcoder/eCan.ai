# =============================================================================
# eCan.ai CN 版本 - 文件索引
# =============================================================================

## CN 版本架构

```
┌─────────────────────────────────────────────────────────────┐
│                      腾讯云 TCB                              │
│                                                              │
│   ┌─────────────────┐         ┌──────────────────┐          │
│   │    云函数 SCF     │ ←────→ │   PostgreSQL    │          │
│   │   (graphql-yoga) │  内网   │   (VPC 内网)    │          │
│   └────────┬─────────┘         └──────────────────┘          │
│            │                                                   │
│            │ HTTP 触发                                         │
└────────────│──────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│   本地客户端 (Python)                                         │
│                                                              │
│   认证: auth/tencent/ (TCB Auth)                            │
│   API: agent/cloud_api/cloud_api.py (GraphQL)                │
└─────────────────────────────────────────────────────────────┘
```

## 接口兼容性

**完全兼容 AWS AppSync GraphQL Schema** (`scripts/appsync_schema_current.graphql`)

| 操作 | AWS | CN (TCB) |
|------|-----|----------|
| Query | AppSync | 云函数 (GraphQL Yoga) |
| Mutation | AppSync | 云函数 (GraphQL Yoga) |
| 认证 | Cognito | TCB Auth |
| 数据库 | DynamoDB | PostgreSQL (Prisma) |

## 目录结构

### 认证模块
```
auth/tencent/
├── cloudbase_adapter.py      # Cognito 适配器
├── cloudbase_auth.py        # TCB Auth REST API
├── cloudbase_config.py      # 配置
├── sms_service.py           # 短信服务
└── code_store.py            # 验证码存储
```

### 后端 API（云函数）
```
cloudbase-graphql/
├── index.js              # 云函数入口 (graphql-yoga)
├── package.json          # npm 依赖
├── prisma/
│   └── schema.prisma    # PostgreSQL 数据库 Schema
├── deploy.sh             # 部署脚本
├── dev.sh               # 开发脚本
├── test-api.sh          # API 测试脚本
└── README.md            # 部署文档
```

### 配置
```
apps/cn/config/
├── auth_config.yml           # TCB Auth 配置
└── feature_flags.yml         # 功能开关
```

## 数据库表

Prisma Schema (`cloudbase-graphql/prisma/schema.prisma`) 定义以下表：

| 表名 | 说明 |
|------|------|
| `agents` | 智能体 |
| `agent_skills` | 技能 |
| `agent_tasks` | 任务 |
| `vehicles` | 车辆/设备 |
| `orgs` | 组织 |
| `prompts` | 提示词 |
| `avatars` | 头像 |
| `agent_knowledge` | 知识库 |
| `agent_tools` | 工具 |
| `settings` | 设置 |

## 环境变量

```bash
# TCB Auth
ECAN_TENCENT_CLOUDBASE_ENV_ID=sccb0-d0gc5398xf028be6a
ECAN_TENCENT_REGION=ap-shanghai

# TCB GraphQL API（部署后获取）
TCB_API_URL=https://your-env.service.tcloudbase.com/api/graphql
```

## 快速开始

### 1. 配置 TCB

1. 购买云数据库 PostgreSQL（与 CloudBase 同 VPC）
2. 部署云函数（`cloudbase-graphql/`）
3. 配置环境变量（PG_*）
4. 添加 HTTP 触发器

详细步骤见 `cloudbase-graphql/README.md`

### 2. 本地开发

```bash
cd cloudbase-graphql

# 安装依赖
npm install

# 配置环境变量
cp .env.local.example .env.local
# 编辑 .env.local

# 初始化数据库
./dev.sh init

# 启动本地服务器（测试用）
./dev.sh start
```

### 3. 部署云函数

```bash
cd cloudbase-graphql
./dev.sh deploy
```

## 相关文档

- **[CN 版本完整指南](../docs/CN_VERSION_GUIDE.md)** - 部署、配置、操作完整文档
- [微信登录配置](../docs/CN_WECHAT_LOGIN_SETUP.md) - 微信扫码登录接入
