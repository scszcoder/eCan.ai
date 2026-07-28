# eCan.ai CN 版本后端

使用腾讯云 TCB 原生能力：
- **认证**: TCB Auth (Bearer Token) - 云函数自动验证
- **数据库**: TCB Database (原生集合权限控制)

## 目录结构

```
cloudbase-graphql/
├── index.js      # 云函数入口
├── package.json  # npm 依赖
├── deploy.sh     # 部署脚本
└── README.md     # 本文档
```

## TCB Database 集合

| 集合名 | 说明 | 权限 |
|--------|------|------|
| `agents` | Agent 数据 | owner == uid |
| `agent_skills` | Agent 技能 | owner == uid |
| `agent_tasks` | 任务 | owner == uid |
| `agent_vehicles` | 车辆 | owner == uid |
| `settings` | 设置 | - |

## API 用法

### 部署

```bash
cd cloudbase-graphql
npm install
./deploy.sh
```

### RESTful API

```bash
# 登录后获取 token，然后请求带上 Authorization: Bearer <token>

# 列表
curl -X GET https://your-env.service.tcloudbase.com/agents \
  -H "Authorization: Bearer $TOKEN"

# 添加
curl -X POST https://your-env.service.tcloudbase.com/ \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"collection": "agents", "name": "我的Agent"}'

# 更新
curl -X PUT https://your-env.service.tcloudbase.com/agents/{id} \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name": "新名称"}'

# 删除
curl -X DELETE https://your-env.service.tcloudbase.com/agents/{id} \
  -H "Authorization: Bearer $TOKEN"
```

## TCB 控制台配置

1. 创建集合，设置权限规则：

```json
// agents 集合权限
{
  "read": "doc.owner == auth.uid",
  "write": "doc.owner == auth.uid"
}
```

2. 环境变量（云函数配置）：
   - `TCB_ENV_ID`: 环境 ID
