# GUI v2 开发指南

## 快速导航

- [快速开始](#快速开始)
- [环境配置](#环境配置)
- [产品切换](#产品切换)
- [生产构建](#生产构建)
- [故障排除](#故障排除)

---

## 快速开始

### 1. 克隆后首次配置

```bash
# 复制环境配置模板
cp .env.example .env

# 切换到产品版本
./scripts/dev.sh intl   # 或 ./scripts/dev.sh cn
```

### 2. 启动开发服务

```bash
# 终端 1: 后端
python main.py

# 终端 2: 前端 (取决于产品)
cd gui_v2 && npm run dev:cn     # CN 版本
cd gui_v2 && npm run dev:intl    # Intl 版本 (默认)
```

### 3. 验证

打开浏览器访问 http://localhost:3000

---

## 环境配置

### 文件结构

```
gui_v2/
├── .env                 # 基础配置 (所有产品共用)
├── .env.cn             # CN 产品覆盖
├── .env.intl           # Intl 产品覆盖
├── .env.local          # 本地覆盖 (gitignored)
└── .env.example        # 配置模板
```

Vite 自动加载: `.env` → `.env.{product}` → `.env.local`

---

## 产品切换

### 使用 dev.sh 切换

```bash
./scripts/dev.sh status   # 查看当前状态
./scripts/dev.sh cn       # 切换到 CN
./scripts/dev.sh intl     # 切换到 Intl
```

### 切换后操作

1. **停止当前后端** (Ctrl+C)
2. **停止当前前端** (Ctrl+C)
3. **启动新后端**: `python main.py`
4. **启动新前端**: `npm run dev:cn` 或 `npm run dev:intl`

### CN vs Intl 区别

| 特性 | CN | Intl |
|------|-----|------|
| 认证 | CloudBase (腾讯云) | Cognito (AWS) |
| 区域 | ap-guangzhou | us-east-1 |
| API | api.fastprecisiontech.com | api.ecan.ai |
| 前端命令 | `npm run dev:cn` | `npm run dev:intl` |

---

## 生产构建

### 构建命令

| 命令 | 产物 |
|------|------|
| `npm run build:cn:desktop` | CN 桌面版 (.app/.exe) |
| `npm run build:cn:web` | CN Web 版 |
| `npm run build:intl:desktop` | Intl 桌面版 |
| `npm run build:intl:web` | Intl Web 版 |

### Web 版 base path

Web 版使用绝对路径，需要设置 `VITE_BASE`：

```bash
VITE_BASE=/app/gui-v2/ npm run build:cn:web
```

### 生产环境变量

生产构建时通过环境变量注入真实配置：

```bash
# 示例: 构建 CN 生产版
VITE_API_BASE=https://api.fastprecisiontech.com \
VITE_WS_URL=wss://ws.fastprecisiontech.com/graphql \
npm run build:cn:desktop
```

---

## 故障排除

### 问题: 登录失败

**检查项**:
1. `ECAN_APP_ID` 是否正确？
   ```bash
   grep ECAN_APP_ID .env
   ```
2. 前端和后端产品是否一致？
   - CN 后端 + CN 前端
   - Intl 后端 + Intl 前端
3. 重启后端和前端

### 问题: Vite 端口被占用

```bash
# 查看占用端口的进程
lsof -i :3000

# 杀掉进程
kill -9 <PID>

# 或使用不同的端口
VITE_PORT=3001 npm run dev:intl
```

### 问题: 依赖问题

```bash
# 清理并重新安装
cd gui_v2
rm -rf node_modules/.vite
npm install

# 重新启动
npm run dev:cn
```

### 问题: .env 变更不生效

Vite 在启动时加载 `.env` 文件。修改后需要**重启 Vite**。

---

## 更多资源

- [环境变量完整参考](../docs/ENVIRONMENT_VARIABLES.md)
- [CN 版本文档](../docs/CN_TENCENT_CLOUD_SERVICES.md)
- [部署指南](../docs/DEPLOYMENT_UBUNTU.md)
