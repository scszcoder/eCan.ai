# eCan WebSocket 部署说明

## 概述
`ecan-websocket` 云函数运行在腾讯云开发（TCB）环境，通过 HTTP 路由暴露 WebSocket 风格的 API。

## 部署的函数
- **环境**：`sccb0-d0gc5398xf028be6a`（ap-shanghai）
- **函数名**：`ecan-websocket`
- **类型**：Event（事件函数）
- **Handler**：`index.main`
- **EIP**：`124.221.64.30`（动态分配）

## 路由

| 路径 | 方法 | 用途 |
|------|------|------|
| `/ws` | GET | 健康检查 |
| `/ws/push` | POST | 推送事件到 WebSocket 频道 |
| `/ws/status` | GET | 查询连接状态 |

## API 端点

### 健康检查
```bash
curl https://sccb0-d0gc5398xf028be6a-1251680599.ap-shanghai.app.tcloudbase.com/ws
```

### 推送事件
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "x-ecan-push-secret: $WEBSOCKET_PUSH_SECRET" \
  -d '{"channel":"task-status","target":"userId","data":{...}}' \
  https://sccb0-d0gc5398xf028be6a-1251680599.ap-shanghai.app.tcloudbase.com/ws/push
```

### 查询状态
```bash
curl -H "x-ecan-push-secret: $WEBSOCKET_PUSH_SECRET" \
  https://sccb0-d0gc5398xf028be6a-1251680599.ap-shanghai.app.tcloudbase.com/ws/status
```

## 部署步骤

### 1. 打包
```bash
cd cloudbase-graphql
mkdir -p /tmp/websocket-pkg
cp functions/ecan-websocket/index.js /tmp/websocket-pkg/
cp websocket.js /tmp/websocket-pkg/websocket.js
cp functions/ecan-websocket/scf_bootstrap /tmp/websocket-pkg/
cd /tmp/websocket-pkg
zip -r /tmp/ecan-websocket.zip index.js websocket.js scf_bootstrap
```

### 2. 通过 SCF API 创建/更新
```bash
# 创建（首次）
tencentcloud scf CreateFunction --cli-unfold-argument \
  --FunctionName ecan-websocket \
  --Runtime Nodejs20.19 \
  --Handler index.main \
  --MemorySize 512 --Timeout 300 \
  --Namespace sccb0-d0gc5398xf028be6a \
  --Role TCB_QcsRole --Stamp MINI_QCBASE \
  --Code @/tmp/ecan-websocket.zip \
  --Environment.Variables.0.Key NODE_ENV \
  --Environment.Variables.0.Value production \
  --Environment.Variables.1.Key TCB_REGION \
  --Environment.Variables.1.Value ap-shanghai \
  --PublicNetConfig.PublicNetStatus ENABLE \
  --PublicNetConfig.EipConfig.EipStatus ENABLE

# 更新代码（后续）
tencentcloud scf UpdateFunctionCode --cli-unfold-argument \
  --FunctionName ecan-websocket \
  --Namespace sccb0-d0gc5398xf028be6a \
  --ZipFile @/tmp/ecan-websocket.zip
```

### 3. 添加 HTTP 路由
```bash
cd cloudbase-graphql
tcb routes add -d '{
  "domain": "sccb0-d0gc5398xf028be6a-1251680599.ap-shanghai.app.tcloudbase.com",
  "routes": [
    {"path":"/ws","upstreamResourceType":"SCF","upstreamResourceName":"ecan-websocket","enable":true,"enablePathTransmission":true},
    {"path":"/ws/push","upstreamResourceType":"SCF","upstreamResourceName":"ecan-websocket","enable":true,"enablePathTransmission":true},
    {"path":"/ws/status","upstreamResourceType":"SCF","upstreamResourceName":"ecan-websocket","enable":true,"enablePathTransmission":true}
  ]
}'
```

## 代码结构

```
cloudbase-graphql/
├── websocket.js                                  # 共享实现（本地 dev + 生产）
└── functions/ecan-websocket/
    ├── index.js                                  # 部署入口（HTTP 路由分发）
    └── scf_bootstrap                             # 启动脚本
```

## 已知限制
- 浏览器端 WebSocket 实时连接不可用（无 `ProtocolType: WS`）
- 当前只支持 HTTP 推送模式（push/status）
- 上游 API（`ecan-graphql-api`）可通过 `callWebSocket()` 调用此函数推送事件

## 快速链接
- TCB 控制台：https://console.cloud.tencent.com/tcb
- SCF 函数列表：https://console.cloud.tencent.com/scf/list
- API 路由：https://console.cloud.tencent.com/tcb/env/access