# =============================================================================
# eCan.ai CN 版本 - 文件索引
# =============================================================================

## CN 版本架构

```
客户端 (Python)
  │
  ├─ 认证: auth/tencent/ (TCB Auth)
  │
  └─ 后端: cloudbase-graphql/ (TCB Database)
```

**使用 TCB 原生能力:**
- 认证: TCB Auth (Bearer Token)
- 数据库: TCB Database (原生集合权限控制)

## 目录结构

### 认证模块
```
auth/tencent/
├── cloudbase_adapter.py      # Cognito 适配器
├── cloudbase_auth.py         # TCB Auth REST API
├── cloudbase_config.py       # 配置
├── sms_service.py            # 短信服务
└── code_store.py             # 验证码存储
```

### 后端 API
```
cloudbase-graphql/
├── index.js      # 云函数入口 (TCB Database REST API)
├── package.json  # npm 依赖
└── README.md     # 部署文档
```

### 配置
```
apps/cn/config/
├── auth_config.yml           # TCB Auth 配置
└── feature_flags.yml         # 功能开关
```

## 环境变量

```bash
# TCB Auth
CLOUDBASE_ENV_ID=sccb0-d0gc5398xf028be6a
CLOUDBASE_REGION=ap-shanghai

# TCB 后端 (部署后获取)
CLOUDBASE_API_URL=https://your-env.service.tcloudbase.com
```

## TCB Database 集合

| 集合名 | 说明 | 权限 |
|--------|------|------|
| `agents` | Agent 数据 | owner == uid |
| `agent_skills` | Agent 技能 | owner == uid |
| `agent_tasks` | 任务 | owner == uid |
| `agent_vehicles` | 车辆 | owner == uid |
| `settings` | 设置 | - |

## 快速开始

1. 部署后端
```bash
cd cloudbase-graphql
npm install
./deploy.sh
```

2. 在 TCB 控制台创建集合并设置权限

3. 配置环境变量
