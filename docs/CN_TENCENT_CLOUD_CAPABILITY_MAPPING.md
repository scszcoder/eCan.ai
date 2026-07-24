# AWS ↔ 腾讯云 后端能力等价映射

> **目标**：将 eCan.ai 国际版的 AWS 后端能力一对一映射到腾讯云（中国版）

---

## 一、AWS 后端能力清单

根据 `lambda_functions/resolvers.md`，AWS 后端包含以下主要能力：

| 类别 | AWS DataSource | 用途 |
|------|----------------|------|
| **agentScheduler** | Lambda | Agent/技能/任务/CRUD |
| **botScheduler** | Lambda | Bot/技能调度 |
| **skillEditorAgent** | Lambda | 技能编辑器 (AI生成) |
| **chatter** | Lambda | A2A 消息 |
| **ecbAccountManager** | Lambda | 账号/订单 |
| **scenesDynamoDB** | DynamoDB | 场景数据 |
| **taskStatus** | Lambda | 任务状态推送 |
| **llm_notifier** | Lambda | LLM 异步任务 |
| **acctNotification** | SNS | 账号通知 |
| **passiveCommand** | SNS | 被动命令 |
| **passiveStepResult** | SNS | 步骤结果 |
| **scene_notifier** | SNS | 场景通知 |
| **SkillEditorStreamEvent** | SNS | 流式事件 |
| **a2a** | SNS | Agent 间消息 |
| **getKey** | Lambda | API Key |
| **puzzle_problem** | SNS | 拼图问题 |
| **nada** | SNS | 万能消息 |

---

## 二、完整能力映射表

### 2.1 计算服务

| 能力 | AWS | 腾讯云 | 等价性 |
|------|-----|--------|--------|
| 函数计算 | Lambda | **SCF (云函数)** | ✅ 100% 等价 |
| 容器编排 | ECS/Fargate | **TKE (Kubernetes)** | ✅ 等价 |
| 异步任务 | Lambda Async | **SCF 异步调用** | ✅ 等价 |
| 定时任务 | EventBridge | **SCF 定时触发器** | ✅ 等价 |
| 批量计算 | AWS Batch | **BatchCompute** | ✅ 等价 |

### 2.2 数据存储

| 能力 | AWS | 腾讯云 | 等价性 |
|------|-----|--------|--------|
| 关系数据库 | Aurora MySQL | **TDSQL-C MySQL** | ✅ 100% 兼容 MySQL 8.0 |
| NoSQL 文档 | DynamoDB | **MongoDB (腾讯云版)** / **TcaplusDB** | ✅ 等价 |
| 缓存 | ElastiCache (Redis) | **TencentDB for Redis** | ✅ 等价 |
| 键值存储 | DynamoDB | **CKV (Redis)** | ✅ 等价 |
| 对象存储 | S3 | **COS (对象存储)** | ✅ API 几乎等价 |
| 文件存储 | EFS | **CFS (文件存储)** | ✅ 等价 |

### 2.3 消息与流

| 能力 | AWS | 腾讯云 | 等价性 |
|------|-----|--------|--------|
| 消息队列 | SQS | **CMQ** | ✅ 等价 |
| 主题订阅 | SNS | **CMQ Topic** | ✅ 等价 |
| 流处理 | Kinesis | **CKafka / TDSQL-H** | ✅ 等价 |
| 事件总线 | EventBridge | **EventBridge (腾讯云版)** | ✅ 等价 |

### 2.4 API 与集成

| 能力 | AWS | 腾讯云 | 等价性 |
|------|-----|--------|--------|
| GraphQL API | **AppSync** | **API Gateway + SCF + Apollo** | ✅ 自建，接口完全一致 |
| REST API | API Gateway | **API Gateway** | ✅ 等价 |
| WebSocket | API Gateway WS | **API Gateway WS** | ✅ 等价 |
| DNS | Route 53 | **DNSPod** | ✅ 等价 |

### 2.5 安全与认证

| 能力 | AWS | 腾讯云 | 等价性 |
|------|-----|--------|--------|
| 用户认证 | **Cognito** | **TCB (CloudBase) Auth** | ✅ 等价，更适合中国 |
| API 授权 | IAM | **CAM (访问管理)** | ✅ 等价 |
| 密钥管理 | Secrets Manager | **Secrets Manager** | ✅ 等价 |
| Web 应用防火墙 | WAF | **WAF** | ✅ 等价 |

### 2.6 DevOps 与监控

| 能力 | AWS | 腾讯云 | 等价性 |
|------|-----|--------|--------|
| CI/CD | CodePipeline | **CODING / TKE** | ✅ 等价 |
| 监控 | CloudWatch | **Cloud Monitor** | ✅ 等价 |
| 日志 | CloudWatch Logs | **CLS (日志服务)** | ✅ 等价 |
| 链路追踪 | X-Ray | **CAT (应用监控)** | ✅ 等价 |
| 容器镜像 | ECR | **TCR (容器镜像服务)** | ✅ 等价 |

### 2.7 AI 与机器学习

| 能力 | AWS | 腾讯云 | 等价性 |
|------|-----|--------|--------|
| LLM 服务 | Bedrock | **混元大模型 / 文生文** | ✅ 等价 |
| 语音识别 | Transcribe | **ASR** | ✅ 等价 |
| 语音合成 | Polly | **TTS** | ✅ 等价 |
| 机器翻译 | Translate | **机器翻译** | ✅ 等价 |
| 图像识别 | Rekognition | **AI 视觉** | ✅ 等价 |
| OCR | Textract | **通用 OCR** | ✅ 等价 |

---

## 三、具体 Lambda 函数映射

### 3.1 agentScheduler

| AWS | 腾讯云 | 说明 |
|-----|--------|------|
| Lambda (Node.js) | **SCF (Node.js 16.13)** | 同样的运行时 |
| Aurora MySQL (RDS Data API) | **TDSQL-C MySQL** | 完全兼容 SQL |
| EventBridge Scheduler | **SCF 定时触发器** | 等价 |
| SQS | **CMQ** | 等价 |

**已实现**: `qcloud/backend/functions/graphql-api/`

### 3.2 botScheduler

| AWS | 腾讯云 |
|-----|--------|
| Lambda | **SCF** |
| S3 | **COS** |
| SQS | **CMQ** |

**实现位置**: `qcloud/backend/functions/bot-scheduler/` (待建)

### 3.3 skillEditorAgent ⭐

**最复杂的 Lambda**，包含 AI 技能生成、代码编辑、流式响应等。

| AWS 能力 | 腾讯云等价 |
|---------|----------|
| Lambda (Python) | **SCF (Python 3.7)** |
| OpenAI API | **腾讯混元大模型** (私有部署可绕过) |
| EFS (存储技能文件) | **CFS** 或 **COS** |
| DynamoDB (场景数据) | **TDSQL-C** 或 **MongoDB** |
| **SNS StreamEvent** | **API Gateway WebSocket** + **Redis** |
| EventBridge (异步生成) | **SCF 异步调用** |
| Step Functions | **SCF 编排** |

**关键点**：流式事件需要从 SNS 改为 WebSocket + Redis Pub/Sub。

**实现位置**: `qcloud/backend/functions/skill-editor-agent/` (待建)

### 3.4 chatter (A2A 消息)

| AWS | 腾讯云 |
|-----|--------|
| Lambda | **SCF** |
| SNS (`a2a`) | **CMQ Topic** / **API Gateway WebSocket** |
| DynamoDB (消息存储) | **TDSQL-C** |

**实现位置**: `qcloud/backend/functions/chatter/` (待建)

### 3.5 ecbAccountManager

| AWS | 腾讯云 |
|-----|--------|
| Lambda | **SCF** |
| RDS (账号数据) | **TDSQL-C** |

**实现位置**: `qcloud/backend/functions/account-manager/` (待建)

---

## 四、消息通知类映射

### 4.1 实时通知 (AppSync Subscription 替代)

AWS 多个 Lambda 通过 SNS 推送：

| AWS SNS Topic | 用途 | 腾讯云等价 |
|--------------|------|----------|
| `SkillEditorStreamEvent` | 技能编辑器流式事件 | **API GW WebSocket + Redis** |
| `a2a` | Agent 间消息 | **API GW WebSocket + Redis** |
| `taskStatus` | 任务状态推送 | **API GW WebSocket + Redis** |
| `passiveCommand` | 被动命令 | **API GW WebSocket + Redis** |
| `passiveStepResult` | 步骤结果 | **API GW WebSocket + Redis** |
| `scene_notifier` | 场景通知 | **API GW WebSocket + Redis** |
| `acctNotification` | 账号通知 | **API GW WebSocket + Redis** / **CMQ** |
| `llm_notifier` | LLM 异步完成 | **API GW WebSocket + Redis** |

**统一方案**：
```
┌─────────────────────────────────────────────────────────┐
│  WebSocket API Gateway (后端推送)                        │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Redis (Pub/Sub) - 模拟 SNS Topic                       │
│  - channel: skill-editor-stream                          │
│  - channel: task-status                                  │
│  - channel: a2a-message                                  │
│  - channel: ...                                          │
└─────────────────────────────────────────────────────────┘
```

前端通过 GraphQL Subscription (WebSocket) 接收，自动适配。

### 4.2 异步任务处理

| AWS | 腾讯云 |
|-----|--------|
| Lambda Async Invoke | **SCF 异步调用** (`--async` 参数) |
| DLQ (Dead Letter Queue) | **CMQ + SCF 重试策略** |
| Step Functions | **SCF 编排 / 状态机 (SM)** |

---

## 五、存储适配

### 5.1 对象存储适配

**AWS S3 → COS 主要差异**：

```javascript
// 适配层示例
class StorageAdapter {
  // AWS S3
  async s3GetObject(key) {
    return s3.getObject({ Bucket, Key: key }).promise();
  }
  
  // 腾讯云 COS
  async cosGetObject(key) {
    return cos.getObject({
      Bucket: process.env.COS_BUCKET,
      Region: process.env.COS_REGION,
      Key: key,
    });
  }
  
  // 统一接口
  async getObject(key) {
    return isCNRegion 
      ? await this.cosGetObject(key)
      : await this.s3GetObject(key);
  }
}
```

### 5.2 数据库适配

**AWS RDS Data API → TDSQL-C**:

```javascript
// 适配层
class DatabaseAdapter {
  // AWS RDS Data API
  async rdsExecute(sql, params) {
    const result = await rdsData.executeStatement({
      resourceArn: process.env.AURORA_CLUSTER_ARN,
      secretArn: process.env.AURORA_SECRET_ARN,
      database: process.env.DB_NAME,
      sql,
      parameters: params,
    });
    return result.records;
  }
  
  // 腾讯云 TDSQL-C
  async tdsqlExecute(sql, params) {
    const [rows] = await mysqlPool.execute(sql, params);
    return rows;
  }
  
  async execute(sql, params) {
    return isCNRegion
      ? await this.tdsqlExecute(sql, params)
      : await this.rdsExecute(sql, params);
  }
}
```

---

## 六、关键能力差异

### 6.1 差异列表

| 项目 | AWS | 腾讯云 | 兼容方式 |
|------|-----|--------|---------|
| **认证 Token 格式** | JWT (Cognito) | TCB Custom Token | 适配层 |
| **GraphQL 实时** | AppSync Subscription (内置) | 自建 WebSocket + Redis | 自建，但接口一致 |
| **异步调用** | Lambda Async | SCF 异步调用 | 等价 |
| **数据库连接** | RDS Data API (REST) | mysql2 (TCP) | 适配层 |
| **对象存储 API** | aws-sdk S3 | cos-nodejs-sdk-v5 | 适配层 |
| **消息队列** | SQS / SNS | CMQ | 适配层 |
| **任务调度** | EventBridge | SCF 定时触发器 | 等价 |
| **密钥管理** | Secrets Manager | Secrets Manager | 等价 |

### 6.2 必须自建的能力

1. **GraphQL API** - AppSync 无完全等价服务，需要 API Gateway + SCF + Apollo
2. **WebSocket 订阅** - 需要自建 (API Gateway WS + Redis Pub/Sub)
3. **流式事件** - 通过 WebSocket 实现
4. **数据库适配层** - RDS Data API → mysql2/promise

---

## 七、实施建议

### 7.1 推荐实施顺序

```
1. ✅ 认证 (TCB Auth)
2. ✅ GraphQL API (SCF + Apollo)
3. ✅ 数据库 (TDSQL-C)
4. ✅ 基础 Resolver (CRUD)
5. ⏳ 技能编辑器 (skillEditorAgent) - 待建
6. ⏳ Bot 调度 (botScheduler) - 待建
7. ⏳ A2A 消息 (chatter) - 待建
8. ⏳ 账号管理 (ecbAccountManager) - 待建
9. ⏳ WebSocket 订阅服务 - 待建
10. ⏳ 定时任务 - 待建
```

### 7.2 复用策略

| 层级 | 复用率 | 说明 |
|------|--------|------|
| **GraphQL Schema** | 100% | 完全相同的 API 定义 |
| **Resolver 业务逻辑** | 90% | 业务逻辑相同，只换数据访问层 |
| **数据访问层** | 30% | RDS → TDSQL-C 需要适配 |
| **前端 GraphQL 调用** | 100% | API 完全一样 |
| **前端认证** | 10% | Cognito → TCB 需要适配 |

---

## 八、总结

### 8.1 等价能力覆盖率

| 类别 | 覆盖率 | 备注 |
|------|--------|------|
| 计算 (Lambda/SCF) | 100% | 完全等价 |
| 数据库 (Aurora/TDSQL-C) | 100% | MySQL 8.0 兼容 |
| 对象存储 (S3/COS) | 95% | API 相似 |
| 消息队列 (SQS/CMQ) | 90% | 等价 |
| 主题订阅 (SNS/CMQ Topic) | 85% | 需要适配 |
| **GraphQL API** | 100% | 自建，接口一致 |
| **认证 (Cognito/TCB)** | 100% | 等价 |
| 实时订阅 (Subscription) | 100% | 自建实现 |

### 8.2 关键决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 认证 | **TCB** | 现成方案，符合中国合规 |
| GraphQL API | **自建 (SCF + Apollo)** | 接口一致性 |
| 数据库 | **TDSQL-C** | MySQL 100% 兼容 |
| 实时订阅 | **自建 (WS + Redis)** | 模拟 AppSync Subscription |
| 对象存储 | **COS** | API 相似 |

### 8.3 最终架构对比

```
AWS                              Tencent Cloud
─────────────────────            ─────────────────────
Lambda              →            SCF 云函数
Aurora MySQL        →            TDSQL-C MySQL
S3                  →            COS
SQS / SNS           →            CMQ (Queue + Topic)
EventBridge         →            SCF 定时触发器
AppSync (GraphQL)   →            API Gateway + SCF + Apollo
Cognito             →            TCB CloudBase
DynamoDB            →            TDSQL-C (或 MongoDB)
ElastiCache         →            Redis (TencentDB)
EFS                 →            CFS
CloudWatch          →            Cloud Monitor
CloudWatch Logs     →            CLS 日志服务
Step Functions      →            SCF 编排 (状态机)
Bedrock (LLM)       →            混元大模型
WAF                 →            WAF
```

腾讯云提供了**几乎完整的能力等价**，主要差异是需要自建 GraphQL API 层和 WebSocket 订阅服务。
