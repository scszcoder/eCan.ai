# 腾讯云架构设计方案 (v2)

> **设计原则**：认证使用 TCB CloudBase (现成方案)，业务 GraphQL API 自建 (与 AWS AppSync 接口完全一致)

---

## 一、架构概览

### 1.1 AWS 当前架构
```
┌─────────────────────────────────────────────────────────────────┐
│                         客户端 (跨平台)                            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      AWS AppSync                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ GraphQL API │  │ Auth (Cognito)│ │ Subscription (WSS)    │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
┌─────────────────┐ ┌─────────────┐ ┌─────────────────────────────┐
│   Lambda        │ │ Aurora/MySQL│ │ S3 / SQS / ECS            │
│   (业务逻辑)     │ │ (数据存储)   │ │ (存储/队列/任务执行)        │
└─────────────────┘ └─────────────┘ └─────────────────────────────┘
```

### 腾讯云目标架构
```
┌─────────────────────────────────────────────────────────────────┐
│                         客户端 (跨平台)                            │
└──────────┬─────────────────────────────────┬───────────────────┘
           │                                 │
           ▼                                 ▼
┌─────────────────────┐           ┌─────────────────────────────────┐
│   TCB Auth          │           │   自建 GraphQL API              │
│   (登录/认证)        │           │   (SCF + TDSQL/COS)             │
│                     │           │   接口与 AppSync 完全一致!        │
│  - 邮箱登录         │           │                                 │
│  - 手机号登录        │           │  ┌─────────────┐ ┌───────────┐ │
│  - 微信登录         │           │  │ GraphQL    │ │ WebSocket │ │
│  - 短信验证         │           │  └─────────────┘ └───────────┘ │
└─────────────────────┘           └────────────────┬────────────────┘
                                                  │
                              ┌───────────────────┼───────────────────┐
                              ▼                   ▼                   ▼
                    ┌─────────────────┐ ┌─────────────┐ ┌─────────────────┐
                    │   TDSQL-C MySQL │ │     COS     │ │    CMQ / TKE    │
                    │   (数据存储)     │ │  (文件存储) │ │ (队列/任务执行)  │
                    └─────────────────┘ └─────────────┘ └─────────────────┘
```

---

## 二、核心设计决策

### 2.1 服务选型对比

| 能力 | AWS (当前) | 腾讯云 (目标) | 决策 |
|------|-----------|--------------|------|
| **认证** | Cognito | **TCB Auth** | ✅ 使用 TCB (现成方案) |
| **GraphQL API** | AppSync | **API Gateway + SCF** | 自建，接口一致 |
| **数据库** | Aurora MySQL | **TDSQL-C MySQL** | ✅ 100% MySQL 兼容 |
| **文件存储** | S3 | **COS** | ✅ 接口相似 |
| **消息队列** | SQS | **CMQ** | 自建适配层 |
| **定时任务** | EventBridge | **SCF 定时触发器** | 自建适配层 |
| **任务执行** | ECS/Fargate | **TKE / SCF 异步** | 自建适配层 |
| **实时订阅** | AppSync Subscription | **API GW WebSocket** | 自建适配层 |

### 2.2 为什么选择这个方案？

#### ✅ TCB 认证的优势
1. **开箱即用**：邮箱、手机号、微信登录无需开发
2. **合规**：符合中国法规要求
3. **维护少**：腾讯云托管
4. **成本低**：免费额度充足

#### ✅ 自建 GraphQL API 的优势
1. **接口一致**：前端代码复用率 > 95%
2. **灵活性**：支持复杂业务逻辑
3. **可测试**：可以本地运行测试
4. **可控性**：不依赖腾讯云特定版本

---

## 三、接口一致性设计

### 3.1 认证接口差异

| 项目 | AWS Cognito | 腾讯云 TCB | 前端适配 |
|------|------------|------------|---------|
| Token 格式 | JWT | TCB Custom Token | 需要适配 |
| Token 验证 | 前端验证 | 前端验证 | 需要适配 |
| 用户信息 | `cognito:*` claims | TCB User Info API | 需要适配 |
| 刷新Token | 自动处理 | TCB SDK 处理 | 需要适配 |

**解决方案**：封装统一的认证适配层

```typescript
// 前端统一认证模块
import { TCBAuth } from '@/auth/tcb-adapter';
import { CognitoAuth } from '@/auth/cognito-adapter';

interface AuthProvider {
  signIn(credentials): Promise<User>;
  signOut(): Promise<void>;
  getToken(): Promise<string>;
  getUserInfo(): Promise<UserInfo>;
}

// 根据环境切换
export const auth: AuthProvider = isCNRegion 
  ? new TCBAuth()
  : new CognitoAuth();
```

### 3.2 GraphQL 接口完全一致

**核心原则**：GraphQL Schema、Query、Mutation、Subscription 100% 一致

```graphql
# AWS AppSync Schema
type Query {
  getAgents(owner: String!): [Agent]
  queryAgents(input: AWSJSON): [Agent]
}

type Mutation {
  addAgents(input: [AgentInput!]!): [AgentResult]
  updateAgents(input: [AgentInput!]!): [AgentResult]
}

type Subscription {
  onAgentUpdated(owner: String): Agent
}
```

```graphql
# 腾讯云 GraphQL Schema (完全相同!)
type Query {
  getAgents(owner: String!): [Agent]
  queryAgents(input: AWSJSON): [Agent]
}

type Mutation {
  addAgents(input: [AgentInput!]!): [AgentResult]
  updateAgents(input: [AgentInput!]!): [AgentResult]
}

type Subscription {
  onAgentUpdated(owner: String): Agent
}
```

### 3.3 认证 Token 传递方式

前端获取 TCB Token 后，通过 HTTP Header 传递给 GraphQL API：

```typescript
// 前端请求
const response = await fetch(GRAPHQL_ENDPOINT, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${tcbToken}`,  // TCB Token
  },
  body: JSON.stringify({ query, variables }),
});

// 后端解析 (SCF)
function extractIdentity(token) {
  // 验证 TCB Token
  const userInfo = await tcbService.getUserInfo(token);
  return {
    sub: userInfo.uid,           // 与 AWS Cognito sub 对应
    email: userInfo.email,
    username: userInfo.nickname,
  };
}
```

---

## 四、服务详细设计

### 4.1 TCB 认证服务

**功能**：
- 邮箱/密码登录
- 手机号 + 短信验证码登录
- 微信登录
- Token 管理

**配置**：
```json
{
  "envId": "sccb0-d0gc5398xf028be6a",
  "authType": ["email", "phone", "wechat"]
}
```

**前端集成**：
```typescript
// gui_v2/src/services/auth/tcbAuth.ts
import cloudbase from '@cloudbase/js-sdk';

class TCBAdapter implements AuthProvider {
  private app: any;
  
  async init() {
    this.app = cloudbase.init({
      env: import.meta.env.VITE_CLOUDBASE_ENV_ID,
    });
  }
  
  async signInWithEmail(email: string, password: string) {
    const auth = this.app.auth();
    return await auth.signInByEmailAndPassword(email, password);
  }
  
  async signInWithPhone(phone: string, code: string) {
    const auth = this.app.auth();
    return await auth.signInWithPhoneAndPassword(phone, code);
  }
  
  async getToken() {
    const auth = this.app.auth();
    const user = auth.currentUser;
    return user ? await user.getToken() : null;
  }
  
  async getUserInfo() {
    const auth = this.app.auth();
    return await auth.getUserInfo();
  }
}
```

### 4.2 GraphQL API 服务

**技术栈**：
- 运行时：腾讯云 SCF (Node.js 16.13)
- 框架：Apollo Server
- 数据库：TDSQL-C MySQL
- 存储：COS

**入口函数**：
```javascript
// SCF 入口
exports.main_handler = async (event, context) => {
  // 1. 提取 TCB Token
  const token = event.headers?.Authorization?.replace('Bearer ', '');
  
  // 2. 验证 Token，获取用户身份
  const identity = await verifyTCBToken(token);
  
  // 3. 构建 GraphQL Context
  const context = {
    user: identity,
    requestId: context.request_id,
  };
  
  // 4. 交给 Apollo Server 处理
  return apolloHandler(event, context);
};
```

**GraphQL Schema**：
```graphql
# 直接复用现有 schema
# 文件: agent/cloud_api/appsync_schema.graphql
```

**Resolvers 目录结构**：
```
src/resolvers/
├── Query/
│   ├── agents.js       # getAgents, queryAgents
│   ├── skills.js      # getAgentSkills, queryAgentSkills
│   ├── tasks.js       # getAgentTasks, queryAgentTasks
│   ├── vehicles.js    # getVehicles
│   └── ...
├── Mutation/
│   ├── agents.js      # addAgents, updateAgents, removeAgents
│   ├── skills.js      # addAgentSkills, updateAgentSkills
│   ├── tasks.js       # addAgentTasks, updateAgentTasks
│   └── ...
└── Subscription/
    ├── agents.js      # onAgentUpdated
    └── tasks.js       # onTaskStatusChanged
```

### 4.3 数据访问层

```javascript
// src/datasources/mysql.js
class MySQLDataSource {
  async executeStatement({ sql, parameters }) {
    // 模拟 RDS Data API 格式
    const [rows] = await this.pool.execute(sql, parameters);
    return { records: rows };
  }
}

// src/datasources/cos.js  
class COSDataSource {
  async putObject(key, body) { /* ... */ }
  async getSignedUrl(key) { /* ... */ }
}
```

### 4.4 定时任务服务

**替换 EventBridge Scheduler**：

| AWS EventBridge | 腾讯云 SCF |
|----------------|------------|
| cron() 表达式 | SCF 定时触发器 |
| CreateSchedule | 创建触发器 |
| DeleteSchedule | 删除触发器 |

```javascript
// src/services/scheduler.js
class ScheduleManager {
  async createSchedule({ name, expression, target }) {
    // SCF 定时触发器配置
    await scf.createTrigger({
      TriggerName: name,
      Type: 'timer',
      TriggerDesc: expression, // cron 表达式
      CustomArgument: JSON.stringify(target),
    });
  }
}
```

### 4.5 任务执行服务

**替换 ECS/Fargate**：

| AWS ECS | 腾讯云 TKE |
|---------|-----------|
| RunTaskCommand | TKE Job |
| Fargate | TKE 通用调度 |
| 任务元数据 | K8s Labels |

```javascript
// src/services/taskRunner.js
class TaskRunner {
  async runTask({ taskId, owner, params }) {
    // 使用 TKE Job 或 SCF 异步调用
    const job = await tke.createJob({
      Name: `ecan-task-${taskId}`,
      Container: [{
        Image: process.env.TASK_IMAGE,
        Env: [
          { Name: 'ECAN_TASK_ID', Value: taskId },
          { Name: 'ECAN_OWNER', Value: owner },
        ],
      }],
    });
    return { runId: job.uid };
  }
}
```

---

## 五、数据流设计

### 5.1 登录流程

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────────┐
│  前端   │────▶│  TCB    │────▶│ 获取    │────▶│ 存储Token   │
│  UI     │     │  Auth   │     │ TCB Token│    │  跳转首页   │
└─────────┘     └─────────┘     └─────────┘     └─────────────┘
```

### 5.2 API 请求流程

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────────┐
│  前端   │────▶│  附加   │────▶│  SCF    │────▶│  验证Token  │
│  请求   │     │  TCB    │     │  GraphQL│     │  查询DB    │
│         │     │  Token  │     │  Apollo │     │  返回数据   │
└─────────┘     └─────────┘     └─────────┘     └─────────────┘
```

### 5.3 实时订阅流程

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────────┐
│  前端   │────▶│  WS     │────▶│  Redis  │────▶│  发布消息   │
│  订阅   │     │  连接   │     │  PubSub │     │  推送更新   │
└─────────┘     └─────────┘     └─────────┘     └─────────────┘
```

---

## 六、项目结构

```
qcloud_implementation/
├── README.md                    # 本文档
│
├── frontend/                    # 前端适配
│   ├── auth/
│   │   ├── index.ts           # 统一认证接口
│   │   ├── tcb-adapter.ts     # TCB 实现
│   │   └── cognito-adapter.ts # Cognito 实现 (AWS)
│   ├── graphql/
│   │   ├── client.ts          # GraphQL 客户端
│   │   ├── queries.ts          # 查询定义
│   │   └── mutations.ts        # 变更定义
│   └── config/
│       └── endpoints.ts        # 端点配置
│
├── backend/                     # 后端服务
│   ├── functions/
│   │   └── graphql-api/        # GraphQL API 云函数
│   │       ├── index.js        # SCF 入口
│   │       ├── apollo.config.js# Apollo Server 配置
│   │       ├── schema.graphql  # GraphQL Schema
│   │       ├── resolvers/      # Resolver 实现
│   │       ├── datasources/    # 数据源
│   │       │   ├── mysql.js
│   │       │   ├── cos.js
│   │       │   └── cmq.js
│   │       ├── auth/
│   │       │   └── tcb-verify.js # TCB Token 验证
│   │       └── utils/
│   │
│   └── ws-server/             # WebSocket 服务器
│       ├── index.js
│       ├── connections.ts
│       └── pubsub.ts
│
├── database/
│   ├── schema.sql             # 数据库初始化
│   └── migrations/            # 迁移脚本
│
├── terraform/                  # 基础设施代码
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
│
├── deployment/                  # 部署脚本
│   ├── deploy.sh
│   └── ci-cd.yml
│
└── docs/
    ├── api-reference.md       # API 参考
    └── migration-guide.md     # 迁移指南
```

---

## 七、前端适配层

### 7.1 统一认证接口

```typescript
// frontend/src/auth/AuthProvider.ts
export interface UserInfo {
  uid: string;
  email?: string;
  phone?: string;
  nickname?: string;
}

export interface AuthProvider {
  // 初始化
  initialize(): Promise<void>;
  
  // 登录方式
  signInWithEmail(email: string, password: string): Promise<UserInfo>;
  signInWithPhone(phone: string, code: string): Promise<UserInfo>;
  signInWithWechat(): Promise<UserInfo>;
  
  // 登出
  signOut(): Promise<void>;
  
  // 获取用户信息
  getUser(): Promise<UserInfo | null>;
  getToken(): Promise<string | null>;
  
  // 状态监听
  onAuthStateChanged(callback: (user: UserInfo | null) => void): () => void;
}
```

### 7.2 TCB 适配器

```typescript
// frontend/src/auth/TcbAuthAdapter.ts
import cloudbase from '@cloudbase/js-sdk';
import type { AuthProvider, UserInfo } from './AuthProvider';

export class TcbAuthAdapter implements AuthProvider {
  private app: any;
  private auth: any;
  
  async initialize(): Promise<void> {
    this.app = cloudbase.init({
      env: import.meta.env.VITE_CLOUDBASE_ENV_ID,
    });
    this.auth = this.app.auth();
  }
  
  async signInWithEmail(email: string, password: string): Promise<UserInfo> {
    const result = await this.auth.signInByEmailAndPassword(email, password);
    return this.mapUserInfo(result.userInfo);
  }
  
  async signInWithPhone(phone: string, code: string): Promise<UserInfo> {
    // 腾讯云短信验证码登录
    const result = await this.auth.signInWithPhoneAndPassword(phone, code);
    return this.mapUserInfo(result.userInfo);
  }
  
  async signInWithWechat(): Promise<UserInfo> {
    const result = await this.auth.signInWithWXMiniprogram();
    return this.mapUserInfo(result.userInfo);
  }
  
  async signOut(): Promise<void> {
    await this.auth.signOut();
  }
  
  async getUser(): Promise<UserInfo | null> {
    const user = this.auth.currentUser;
    if (!user) return null;
    
    try {
      const info = await user.getUserInfo();
      return this.mapUserInfo(info);
    } catch {
      return null;
    }
  }
  
  async getToken(): Promise<string | null> {
    const user = this.auth.currentUser;
    if (!user) return null;
    
    try {
      const result = await user.getToken();
      return result.token;
    } catch {
      return null;
    }
  }
  
  onAuthStateChanged(callback: (user: UserInfo | null) => void): () => void {
    this.auth.onLoginStateChanged((loginState: any) => {
      if (loginState) {
        callback(this.mapUserInfo(loginState.userInfo));
      } else {
        callback(null);
      }
    });
    
    // 返回取消订阅函数
    return () => {};
  }
  
  private mapUserInfo(info: any): UserInfo {
    return {
      uid: info.uid || info.openId,
      email: info.email,
      phone: info.phone,
      nickname: info.nickname || info.name,
    };
  }
}
```

### 7.3 认证工厂

```typescript
// frontend/src/auth/index.ts
import type { AuthProvider } from './AuthProvider';

export function createAuthProvider(): AuthProvider {
  const isCNRegion = import.meta.env.VITE_APP_REGION === 'cn';
  
  if (isCNRegion) {
    // 动态导入 TCB SDK
    return new (await import('./TcbAuthAdapter')).TcbAuthAdapter();
  } else {
    // AWS Cognito
    return new (await import('./CognitoAuthAdapter')).CognitoAuthAdapter();
  }
}

// 统一导出
export const auth = createAuthProvider();
```

### 7.4 GraphQL 客户端配置

```typescript
// frontend/src/graphql/client.ts
import { ApolloClient, InMemoryCache, createHttpLink } from '@apollo/client/core';

function createClient() {
  const isCNRegion = import.meta.env.VITE_APP_REGION === 'cn';
  
  const httpLink = createHttpLink({
    uri: isCNRegion 
      ? import.meta.env.VITE_GRAPHQL_ENDPOINT_CN
      : import.meta.env.VITE_GRAPHQL_ENDPOINT_INT,
  });
  
  // 添加认证 Header
  const authLink = setContext(async (_, { headers }) => {
    const token = await auth.getToken();
    return {
      headers: {
        ...headers,
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    };
  });
  
  return new ApolloClient({
    link: authLink.concat(httpLink),
    cache: new InMemoryCache(),
    defaultOptions: {
      watchQuery: { fetchPolicy: 'cache-and-network' },
    },
  });
}

export const graphqlClient = createClient();
```

---

## 八、环境变量配置

### 8.1 前端环境变量

```env
# .env.production.cn
VITE_APP_REGION=cn
VITE_CLOUDBASE_ENV_ID=sccb0-d0gc5398xf028be6a
VITE_GRAPHQL_ENDPOINT_CN=https://api.cn.ecan.cn/graphql
VITE_WEBSOCKET_ENDPOINT_CN=wss://api.cn.ecan.cn/graphql
VITE_STORAGE_CN=https://cos.cn.ecan.cn
```

### 8.2 后端环境变量（TCB 云开发）

> **注意**：此节描述 SCF 旧架构占位符，实际当前 CN App 使用 TCB（云开发）架构，
> 云函数已迁移至 TCB 云托管（TCS），不再需要 SCF/TDSQL/CMQ 等配置。
> 真实环境变量见私有 `eCan_lambda/cn/tencent/cloudbase-graphql/.env.local`。

```env
# TCB 云开发环境
TCB_ENV_ID=sccb0-d0gc5398xf028be6a
TCB_REGION=ap-shanghai

# COS 文件存储（TCB COS, runtime 桶 — 与 AWS S3 的 ecan-skills 短名对齐）
COS_BUCKET=ecan-skills-1251680599
COS_REGION=ap-shanghai

# API Gateway
TCB_API_URL=https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/api/graphql
```

---

## 九、部署架构

### 9.1 腾讯云资源

| 资源类型 | 名称 | 说明 |
|---------|------|------|
| SCF | `ecan-graphql-api` | GraphQL API 云函数 |
| SCF | `ecan-graphql-ws` | WebSocket 订阅服务器 |
| API Gateway | `ecan-api` | HTTP/WSS 入口 |
| TDSQL-C | `ecan-db` | MySQL 数据库 |
| COS | `ecan-files` | 文件存储桶 |
| CMQ | `ecan-queue` | 消息队列 |
| Redis | `ecan-redis` | PubSub 缓存 |
| TCB | `sccb0-d0gc5398xf028be6a` | 认证服务 |

### 9.2 部署流程

```bash
# 1. Terraform 创建基础设施
cd terraform
terraform init
terraform apply

# 2. 初始化数据库
mysql -h <tdsql-host> -u ecan_admin -p < database/schema.sql

# 3. 部署云函数
cd backend/functions/graphql-api
npm run build
scf function deploy --name ecan-graphql-api --zip-file dist.zip

# 4. 配置 API Gateway (手动或 Terraform)
# 4.1 创建 API 服务
# 4.2 添加 /graphql 路由
# 4.3 绑定 SCF 函数
# 4.4 配置自定义域名

# 5. 配置 TCB 认证
# 5.1 创建 TCB 环境
# 5.2 开启认证服务
# 5.3 配置登录方式
```

---

## 十、维护策略

### 10.1 代码复用原则

| 模块 | AWS | 腾讯云 | 复用方式 |
|------|-----|--------|---------|
| GraphQL Schema | ✅ | ✅ | 100% 复用 |
| Resolver 逻辑 | Lambda.js | SCF.js | 90% 复用 (SDK 调用不同) |
| 数据模型 | Aurora/MySQL | TDSQL-C | 100% 复用 |
| 前端 GraphQL 调用 | ✅ | ✅ | 100% 复用 |
| 认证逻辑 | Cognito | TCB | 封装适配层 |

### 10.2 适配层隔离

```
┌─────────────────────────────────────────────────────────┐
│                    业务代码 (复用)                        │
│  resolvers/, datasources/, services/                    │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                   SDK 适配层 (差异)                      │
│  aws-sdk/  ───────────────────────▶  tencentcloud-sdk/  │
│  RDSDataClient.executeStatement()    mysql2.execute()   │
│  S3Client.putObject()              COS.putObject()     │
└─────────────────────────────────────────────────────────┘
```

### 10.3 测试策略

```bash
# 本地测试 (两个环境)
docker-compose -f docker-compose.aws.yml up   # AWS 模拟
docker-compose -f docker-compose.tcb.yml up  # TCB 模拟

# CI 测试
- 单元测试: jest
- 集成测试: 模拟 AppSync 和 SCF 环境
- E2E 测试: Playwright
```

---

## 十一、总结

### 11.1 优势

1. **认证使用 TCB**：开箱即用，符合中国法规，维护成本低
2. **GraphQL 接口一致**：前端代码 95% 复用
3. **数据库兼容**：TDSQL-C 100% MySQL 兼容，schema 零改动
4. **架构清晰**：认证与业务分离，职责明确

### 11.2 关键决策

| 决策点 | 选择 | 原因 |
|--------|------|------|
| 认证 | TCB | 现成方案，合规 |
| GraphQL | 自建 | 接口一致性 |
| 数据库 | TDSQL-C | MySQL 兼容 |
| 存储 | COS | AWS S3 类似 |
| 队列 | CMQ | SQS 替代 |
| 订阅 | WebSocket + Redis | AppSync Subscription 替代 |

### 11.3 后续步骤

1. [ ] 创建 `frontend/src/auth/` 适配层
2. [ ] 创建 `backend/functions/graphql-api/` 云函数
3. [ ] 配置 TCB 认证服务
4. [ ] 部署并测试
5. [ ] 性能优化
