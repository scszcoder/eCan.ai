# GUI v2 开发指南

## 快速导航

- [快速开始](#快速开始)
- [环境配置](#环境配置)
- [运行时配置](#运行时配置)
- [生产构建](#生产构建)
- [故障排除](#故障排除)

---

## 快速开始

### 1. 克隆后首次配置

```bash
# 后端
cp .env.example .env
$EDITOR .env   # 设置 ECAN_APP_ID=cn|intl

# 前端
cp gui_v2/.env.example gui_v2/.env
# 开发期间保持默认值即可
```

### 2. 启动开发服务

```bash
# 终端 1: 后端
python main.py

# 终端 2: 前端
cd gui_v2 && npm run dev
```

### 3. 切换 CN / Intl

新架构：CN/Intl 由后端 `ECAN_APP_ID` 环境变量决定，**前端无需切换**。

```bash
# 切换后端产品
./scripts/dev.sh cn       # 或 intl
# 重启后端 (python main.py)
# 前端会自动通过 IPC handler `getAppConfig` 拿到正确的区域配置（desktop dev），
# web 部署则走 web_server.py 同源 GET /api/config
```

---

## 环境配置

### 文件结构

```
gui_v2/
├── .env                  # 桌面开发期共享默认（tracked）
├── .env.example          # 变量文档模板（tracked）
└── .env.local            # 个人覆盖（gitignored）
```

Vite 加载顺序：`.env` → `.env.local`（CN/Intl 不再使用构建期变量区分）

### 后端环境变量

后端 `.env`（项目根目录）控制 CN/Intl：

```bash
ECAN_APP_ID=cn    # 或 intl
```

后端启动时根据 `ECAN_APP_ID` 加载 `apps/{cn,intl}/config/` 下的所有配置。运行时配置通过两条路径暴露给前端（payload 一致）：
- **桌面端**：IPC handler `getAppConfig`（见 `gui/ipc/w2p_handlers/app_config_handler.py`）
- **Web 部署**：`web_server.py` 的同源 `GET /api/config`

---

## 运行时配置

**前端不在构建期硬编码任何 CN/Intl 相关的 endpoint**。运行时配置（`app_id/is_cn/auth_type` + `auth{cloudbase_env_id,wechat_app_id,cognito_domain,cognito_client_id}`）由后端根据 `ECAN_APP_ID` 自动返回。

### CN vs Intl 区别

| 特性 | CN | Intl |
|------|-----|------|
| 认证 | CloudBase (腾讯云) | Cognito (AWS) |
| 区域 | ap-shanghai | us-east-1 |
| 后端 | CloudBase SCF | AWS AppSync |
| 前端命令 | `npm run dev` | `npm run dev` |

---

## 生产构建

### 构建命令

| 命令 | 产物 |
|------|------|
| `npm run build` | 桌面版统一构建（IPC 模式） |
| `npm run build:web` | Web 版统一构建 |

新架构：所有前端构建产物在运行时区分 CN/Intl，构建期不区分。

### Web 版 base path

Web 版使用绝对路径，需要设置 `VITE_BASE`：

```bash
VITE_BASE=/app/gui-v2/ npm run build:web
```

### 生产环境变量

构建系统（`build_system/unified_build.py` + `ecan_build.py`）根据 `--app cn|intl` 在构建期设置 `ECAN_APP_ID` 传给打包脚本。前端构建本身不区分产品。

---

## 故障排除

### 问题: 登录失败

**检查项**:
1. 后端 `.env` 中 `ECAN_APP_ID` 是否正确？
   ```bash
   grep ECAN_APP_ID .env
   ```
2. 后端是否已重启？切换产品后必须重启。
3. 前端控制台 Network 面板检查 `getAppConfig` IPC 响应（桌面 dev）或 `/api/config` HTTP 响应（web 部署）

### 问题: Vite 端口被占用

```bash
# 查看占用端口的进程
lsof -i :3000

# 杀掉进程
kill -9 <PID>

# 或使用不同的端口
VITE_PORT=3001 npm run dev
```

### 问题: 依赖问题

```bash
cd gui_v2
rm -rf node_modules/.vite
npm install
npm run dev
```

### 问题: .env 变更不生效

Vite 在启动时加载 `.env` 文件。修改后需要**重启 Vite**。

---

## 更多资源

- [环境变量完整参考](../docs/ENVIRONMENT_VARIABLES.md)
- [CN 版本文档](../docs/CN_TENCENT_CLOUD_SERVICES.md)
- [部署指南](../docs/DEPLOYMENT_UBUNTU.md)