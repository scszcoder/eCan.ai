# eCan.ai CN 版本完整指南

> CN 版本（腾讯云）开发、部署、操作完整文档

## 目录

1. [架构概览](#1-架构概览)
2. [快速开始](#2-快速开始)
3. [数据库](#3-数据库)
4. [云函数部署](#4-云函数部署)
5. [认证配置](#5-认证配置)
6. [前端集成](#6-前端集成)
7. [附录](#7-附录)

---

## 1. 架构概览

### 1.1 AWS ↔ 腾讯云能力映射

| AWS | 腾讯云 | 说明 |
|-----|--------|------|
| Lambda | SCF (云函数) | 100% 等价 |
| DynamoDB | PostgreSQL + Prisma | 关系型更优 |
| AppSync | GraphQL Yoga | 接口一致 |
| Cognito | TCB Auth | 等价 |
| S3 | COS | API 相似 |
| SNS/SQS | CMQ | 等价 |
| **AppSync WS** | **TCB API GW WS** | **新增：实时推送** |
| ElastiCache | Redis | 等价 |

### 1.2 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                           CN 版本 (腾讯云)                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐     ┌────────────┐     ┌────────────────┐       │
│  │  App     │────▶│  云函数 SCF  │────▶│  GraphQL Yoga  │       │
│  │  (桌面)  │     │  (HTTP)    │     │  (Prisma)      │       │
│  └──────────┘     └────────────┘     └────────┬───────┘       │
│       │                                      │                 │
│       │ WebSocket                            │                 │
│       │ (实时订阅)                            ▼                 │
│       │                              ┌────────────────┐        │
│       │                              │  PostgreSQL    │        │
│       │                              │  (TDSQL-C)     │        │
│       │                              └────────────────┘        │
│       │                                                       │
│       │           ┌────────────┐     ┌────────────────┐        │
│       │           │  TCB Auth  │     │  COS           │        │
│       └──────────▶│  (REST)   │     │  (对象存储)    │        │
│                   └────────────┘     └────────────────┘        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 快速开始

### 2.1 部署脚本执行

```bash
# 1. 进入云函数目录
cd cloudbase-graphql

# 2. 安装依赖
npm install

# 3. 复制并配置环境变量
cp .env.local.example .env.local
# 编辑 .env.local，填入以下配置：
#   - TCB_ENV_ID
#   - TCB_SECRET_ID / TCB_SECRET_KEY
#   - PG_HOST / PG_PORT / PG_USER / PG_PASSWORD / PG_DATABASE

# 4. 部署到腾讯云
./deploy.sh

# 5. 在 TCB 控制台配置：
#   - 环境变量（PG_*）
#   - VPC（云函数与 PostgreSQL 同 VPC）
#   - HTTP 触发器（路径：/api/graphql）

# 6. 初始化数据库
./dev.sh init
```

### 2.2 本地开发

```bash
# 启动本地服务器
./dev.sh start
# 访问 http://localhost:3000/api/graphql

# 打开数据库可视化
./dev.sh studio

# 测试 API
./dev.sh test
```

### 2.3 常用命令

| 命令 | 说明 |
|------|------|
| `./dev.sh start` | 启动本地开发服务器 |
| `./dev.sh init` | 初始化数据库（创建表 + 种子数据） |
| `./dev.sh studio` | 启动 Prisma Studio |
| `./dev.sh deploy` | 部署到 TCB |
| `./dev.sh test` | 测试 API |

---

## 3. 数据库

### 3.1 概述

**PostgreSQL**（通过 Prisma ORM）

| 对比 | AWS Intl | CN (腾讯云) |
|------|----------|-------------|
| 数据库 | DynamoDB (NoSQL) | **PostgreSQL** (关系型) |
| ORM | 无 | **Prisma** |
| 表结构 | 25+ 张宽表 | 17+ 张规范化表 |

### 3.2 数据模型

| 表名 | 说明 | 对应 AWS |
|------|------|---------|
| `Agent` | 智能体 | DynamoDB agents |
| `AgentSkill` | 技能 | DynamoDB skills |
| `AgentTask` | 任务 | DynamoDB tasks |
| `Vehicle` | 车辆/设备 | DynamoDB vehicles |
| `Org` | 组织 | DynamoDB orgs |
| `Prompt` | 提示词 | DynamoDB prompts |
| `Avatar` | 头像 | DynamoDB avatars |
| `AgentKnowledge` | 知识库 | DynamoDB knowledges |
| `AgentTool` | 工具 | DynamoDB tools |
| `Setting` | 设置 | DynamoDB settings |
| `AgentSkillRel` | Agent-Skill 关系 | - |
| `AgentTaskRel` | Agent-Task 关系 | - |
| `AgentOrgRel` | Agent-Org 关系 | - |
| `SkillEditorEvent` | 技能编辑器事件 | DynamoDB events |

### 3.3 数据库操作

```bash
# 生成 Prisma Client
npx prisma generate

# 推送 Schema 到数据库（开发用）
npx prisma db push

# 执行迁移（生产用）
npx prisma migrate dev

# 打开 Prisma Studio（可视化）
npx prisma studio
```

---

## 4. 云函数部署

### 4.1 TCB 控制台配置

1. **创建环境**
   - 登录腾讯云 → 云开发 CloudBase
   - 创建环境，选择区域（推荐 ap-shanghai 或 ap-guangzhou）

2. **开通数据库**
   - 环境 → 数据库 → 开通 PostgreSQL
   - 记录连接信息：主机、端口、数据库名、用户名、密码

3. **创建云函数**
   - 云函数 → 创建函数
   - 名称：`ecan-graphql-api`
   - 运行时：Node.js 16.13
   - 内存：512 MB
   - 超时：30 秒

4. **配置环境变量**
   ```
   PG_HOST=xxxxx.postgresql.tencentcdb.com
   PG_PORT=5432
   PG_DATABASE=postgres
   PG_USER=postgres
   PG_PASSWORD=your_password
   ```

5. **配置 VPC**
   - 云函数 → 函数配置 → VPC
   - 选择与 PostgreSQL 相同的 VPC 和子网

6. **配置触发器**
   - 触发方式 → 添加触发器
   - 触发类型：HTTP 触发
   - 路径：/api/graphql
   - 方法：GET, POST

### 4.2 部署后获取 API 地址

部署成功后，在触发器配置页面获取 API 地址：
```
https://service-xxxx-xxxx.env-id.region.tcb-api.tencentcloudapi.com/api/graphql
```

---

## 5. 认证配置

### 5.1 支持的登录方式

| 登录方式 | 说明 | 配置文件 |
|----------|------|---------|
| 邮箱密码 | 自定义登录 | `auth_config.yml` |
| 短信验证码 | OTP 登录 | `auth_config.yml` |
| 微信扫码 | 微信授权登录 | `auth_config.yml` |

### 5.2 配置项

```yaml
# apps/cn/config/auth_config.yml

CLOUDBASE:
  ENV_ID: "your-env-id"
  REGION: "ap-shanghai"
  GRAPHQL_ENDPOINT: "https://service-xxx.env.region.tcb-api.tencentcloudapi.com"
  WEBSOCKET_ENDPOINT: "wss://service-xxx.env.region.tcb-api.tencentcloudapi.com/ws"
  PUBLISH_KEY: ""
  APPSYNC_API_KEY: ""
  WECHAT_APP_ID: ""
  
FEATURES:
  ENABLE_CLOUDBASE: true
  ENABLE_WECHAT_LOGIN: false
  ENABLE_SMS_LOGIN: false
```

### 5.3 登录流程

```
用户 → App → TCB Auth API → 换取 Token → App 存储 Token
                              ↓
                    调用 GraphQL API（携带 Token）
```

---

## 6. 前端集成

### 6.1 GraphQL API 调用

```python
from agent.cloud_api.cloud_api import CloudApi

# 初始化 API
api = CloudApi(app_id="cn")

# 调用 API
result = api.query_agents(owner="user@example.com")
```

### 6.2 实时订阅

```python
from gui.ipc.appsync_subscription_client import start_appsync_subscriptions_for_desktop

# 启动订阅（自动检测 CN 版本，使用 TCB WebSocket）
start_appsync_subscriptions_for_desktop()
```

### 6.3 存储上传

```python
from utils.storage.tencent_cos import TencentCOSStorage

storage = TencentCOSStorage()
url = storage.upload_file(file_path, "avatars/user123.png")
```

---

## 7. 附录

### 7.1 文件结构

```
cloudbase-graphql/
├── index.js                 # GraphQL API 云函数入口
├── websocket.js             # WebSocket 云函数（实时订阅）
├── package.json             # 依赖配置
├── prisma/
│   ├── schema.prisma       # 数据库 Schema
│   └── init.js             # 数据库初始化脚本
├── .env.local.example       # 环境变量模板
├── deploy.sh                # 部署脚本
├── dev.sh                   # 开发脚本
└── test-api.sh             # API 测试脚本

auth/tencent/
├── cloudbase_auth.py        # TCB Auth REST API
├── cloudbase_adapter.py     # Cognito 适配器
├── cloudbase_config.py      # 配置
├── sms_service.py           # 短信服务
└── code_store.py           # 验证码存储

agent/cloud_api/
├── cloud_api.py             # GraphQL 客户端
├── cloud_api_service.py     # 服务层
├── graphql_builder.py       # 查询构建器
├── schema_builder.py        # Schema 构建器
├── schema_registry.py       # Schema 注册表
└── constants.py            # 常量定义

utils/storage/
└── tencent_cos.py           # COS 存储
```

### 7.2 GraphQL API 端点

| 环境 | 端点 |
|------|------|
| 生产 | `https://service-xxx.env.region.tcb-api.tencentcloudapi.com/api/graphql` |
| WebSocket | `wss://service-xxx.env.region.tcb-api.tencentcloudapi.com/ws` |
| 本地 | `http://localhost:3000/api/graphql` |

### 7.3 相关文档

| 文档 | 说明 |
|------|------|
| `docs/CN_IMPLEMENTATION_REPORT.md` | 实现完整性报告 |
| `cloudbase-graphql/README.md` | 云函数详细文档 |
| `apps/cn/README.md` | CN 版本目录索引 |

---

> 文档版本：2026-07-30
