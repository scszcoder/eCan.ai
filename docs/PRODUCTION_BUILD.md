# 生产环境变量注入指南

## 概述

生产环境配置通过 **CI/CD 管道注入 + 公开字段打包** 两种方式部署。

```
┌─────────────────────────────────────────────────────────────────┐
│                      配置分层（公开 vs 私密）                    │
├─────────────────────────────────────────────────────────────────┤
│ 公开字段：写在 apps/cn/config/auth_config.yml                    │
│   → PyInstaller 打包进 App                                     │
│   → 用户机器上看得到，安全（资源 ID / 公开参数）                │
│   → 例：CloudBase ENV_ID、微信 APP_ID、短信 SDK_APP_ID          │
├─────────────────────────────────────────────────────────────────┤
│ 私密字段：通过 GitHub Actions Secrets 注入到 env                │
│   → 构建时进 PyInstaller 产物（作为运行时环境变量）             │
│   → 永远不写入 yml / 仓库                                      │
│   → 例：腾讯云 SECRET_KEY、微信 APP_SECRET         │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  CI/CD Pipeline (GitHub Actions)                                │
├─────────────────────────────────────────────────────────────────┤
│ secrets:                                                        │
│   私密（运行时注入）:                                           │
│     ECAN_TENCENT_SECRET_ID                                      │
│     ECAN_TENCENT_SECRET_KEY                                     │
│   注意：ECAN_WECHAT_APP_SECRET 已移除（微信 AppSecret 仅需在 CloudBase 控制台配置）│
│                                                                 │
│   公开（前端 web 端用，可选）:                                  │
│     CN_API_BASE=https://api.fastprecisiontech.com              │
│     CN_WS_URL=wss://ws.fastprecisiontech.com/graphql           │
│     INT_API_BASE=https://api.ecan.ai                           │
│     INT_WS_URL=wss://ws.ecan.ai/graphql                        │
│     COGNITO_DOMAIN=ecan-auth.auth.us-east-1.amazoncognito.com  │
│     COGNITO_CLIENT_ID=xxxx                                     │
│                                                                 │
│ 桌面 App 的公开字段由 apps/cn/config/auth_config.yml 提供，     │
│ 不需要 CI 注入；运行时由后端 /api/config 返回给前端。            │
├─────────────────────────────────────────────────────────────────┤
│  桌面构建：                                                     │
│   ECAN_APP_ID=cn                                               │
│   ECAN_TENCENT_SECRET_ID=...    ← 私密，CI 注入                │
│   ECAN_TENCENT_SECRET_KEY=...   ← 私密，CI 注入                │
│   注意：微信 AppSecret 仅需在 CloudBase 控制台配置               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 配置分层（必须遵守）

| 字段 | 类型 | 来源 | 是否进 App 包 |
|---|---|---|---|
| `CLOUDBASE.ENV_ID` | 公开 | `auth_config.yml` | ✅ |
| `CLOUDBASE.REGION` | 公开 | `auth_config.yml` | ✅ |
| `WECHAT.APP_ID` | 公开 | `auth_config.yml` | ✅ |
| `WECHAT.LOGIN_TYPE` | 公开 | `auth_config.yml` | ✅ |
| `WECHAT.SCOPE` | 公开 | `auth_config.yml` | ✅ |
| `WECHAT.APP_SECRET` | **私密** | CloudBase 控制台 | ⚠️ 不在代码中 |
| `SMS.SDK_APP_ID` | 公开 | `auth_config.yml` | ✅ |
| `SMS.TEMPLATE_ID` | 公开 | `auth_config.yml` | ✅ |
| `SMS.SIGN_NAME` | 公开 | `auth_config.yml` | ✅ |
| `SMS.REGION` | 公开 | `auth_config.yml` | ✅ |
| `EMAIL.*` | 公开 | `auth_config.yml` | ✅ |
| `JWT.EXPIRES_IN` | 公开 | `auth_config.yml` | ✅ |

---

## GitHub Actions Secrets 配置

### 1. 添加 Secrets

进入 GitHub 仓库 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**。

### 2. CN App 需要的 Secrets（运行时注入到打包产物）

> **CloudBase Auth API 不需要任何私密环境变量**。微信 AppSecret 仅需在 CloudBase 控制台配置。

| Secret Name | 必填 | 说明 | 获取位置 |
|------------|------|------|----------|
| `ECAN_TENCENT_SECRET_ID` | ❌ | 腾讯云 API 长期密钥 ID（CloudBase Auth API 不需要） | [腾讯云访问管理 → API 密钥管理](https://console.cloud.tencent.com/cam/capi) |
| `ECAN_TENCENT_SECRET_KEY` | ❌ | 腾讯云 API 长期密钥（CloudBase Auth API 不需要） | 同上 |
| `ECAN_TENCENT_SMS_SDK_APP_ID` | ❌ | 短信 SDK AppID（CloudBase 内置 SMS 不需要） | [短信控制台](https://console.cloud.tencent.com/smsv2) |
| `ECAN_TENCENT_SMS_TEMPLATE_ID` | ❌ | 短信模板 ID（CloudBase 内置 SMS 不需要） | 同上 |
| `ECAN_TENCENT_SMS_SIGN_NAME` | ❌ | 短信签名（CloudBase 内置 SMS 不需要） | 同上 |

### 3. Web / 前端需要的 Secrets（Vite 构建期注入）

| Secret Name | 说明 | 示例值 |
|------------|------|--------|
| `CN_API_BASE` | CN API 端点 | `https://api.fastprecisiontech.com` |
| `CN_WS_URL` | CN WebSocket | `wss://ws.fastprecisiontech.com/graphql` |
| `INT_API_BASE` | Intl API 端点 | `https://api.ecan.ai` |
| `INT_WS_URL` | Intl WebSocket | `wss://ws.ecan.ai/graphql` |
| `COGNITO_DOMAIN` | Cognito 域名（Intl） | `ecan-auth.auth.us-east-1.amazoncognito.com` |
| `COGNITO_CLIENT_ID` | Cognito 客户端（Intl） | `xxxxxxxxxxxx` |

> **注意**：桌面 App 不需要 VITE_* secrets，因为前端通过后端 IPC handler `getAppConfig`（见 `gui/ipc/w2p_handlers/app_config_handler.py`）从 `auth_config.yml` 读取所有公开字段。VITE_* 仅用于 web 部署。

### 4. Workflow 已注入的位置

`.github/workflows/release.yml` 已在以下 job 的 env 中注入 CN 私密字段：

- `build-windows-cn`
- `build-macos-cn`
- `build-linux-cn`

字段：
```yaml
# 注意：ECAN_WECHAT_APP_SECRET 已移除，微信 AppSecret 仅需在 CloudBase 控制台配置
# CloudBase Auth API 不需要 SECRET_ID/SECRET_KEY
# ECAN_TENCENT_SECRET_ID: ${{ secrets.ECAN_TENCENT_SECRET_ID || 'NOT_SET' }}
# ECAN_TENCENT_SECRET_KEY: ${{ secrets.ECAN_TENCENT_SECRET_KEY || 'NOT_SET' }}
```

CloudBase Auth API 不需要 SECRET_ID/KEY。

---

## 本地生产构建

### CN 桌面版（本地手动）

```bash
cd gui_v2
# 公开字段从 apps/cn/config/auth_config.yml 读取，无需命令行注入
# 私密字段从环境变量读取，需要在 shell 里 export
export ECAN_APP_ID=cn
# 注意：ECAN_WECHAT_APP_SECRET 已移除，微信 AppSecret 仅需在 CloudBase 控制台配置
# CloudBase Auth API 不需要以下配置（Bearer token 认证）
# export ECAN_TENCENT_SECRET_ID=xxx
# export ECAN_TENCENT_SECRET_KEY=xxx
# export ECAN_TENCENT_SMS_SDK_APP_ID=xxx
# export ECAN_TENCENT_SMS_TEMPLATE_ID=xxx

# 构建后端（PyInstaller 打包）
python build_system/scripts/build_desktop_app.py --app cn --platform macos

# 构建前端（开发模式可直接 npm run dev；生产用 build）
npm run build:cn
```

### CN Web 版

```bash
cd gui_v2
VITE_BASE=/app/gui-v2/ \
VITE_API_BASE=https://api.fastprecisiontech.com \
VITE_WS_URL=wss://ws.fastprecisiontech.com/graphql \
npm run build:cn:web
```

> Web 版 VITE_* 必须从命令行/CI 注入，因为 web 部署前端走 web_server.py 的同源 `GET /api/config`，AppSync/CloudBase endpoint 等需要构建期确定。

### Intl 桌面版

```bash
cd gui_v2
# Intl 公开字段从 apps/intl/config/auth_config.yml 读取
# Cognito 私密字段（COGNITO_USER_POOL_ID 等）从环境变量读取
export ECAN_APP_ID=intl
export AWS_ACCESS_KEY_ID=xxx
export AWS_SECRET_ACCESS_KEY=xxx
export AWS_COGNITO_USER_POOL_ID=xxx
export AWS_COGNITO_CLIENT_ID=xxx
export AWS_COGNITO_CLIENT_SECRET=xxx

python build_system/scripts/build_desktop_app.py --app intl --platform macos
```

---

## 构建后的文件

| 产物 | 位置 | 说明 |
|------|------|------|
| `dist/` | `gui_v2/dist/` | 前端构建输出 |
| `*.app` | `gui_v2/build/` | macOS 应用 |
| `*.exe` | `gui_v2/build/` | Windows 安装包 |
| `*.deb` | `gui_v2/build/` | Linux 包 |

---

## 环境变量注入优先级（后端）

后端读取顺序（见 `auth/auth_config.py` 的 `_apply_env_overrides` 与 `auth/tencent/cloudbase_config.py`）：

1. **公开字段**：`apps/{app_id}/config/auth_config.yml`（最高优先级，仓库内）
2. **私密字段**：环境变量（构建时由 CI 注入）
3. 如果两者都为空：
   - 公开字段用 yml 中的默认值
   - 私密字段为 `""`，`is_configured()` 返回 `False`，启动期就报错

## 前端 Vite 环境变量优先级（web 版）

Vite 按以下优先级加载：

1. `.env.{product}` (如 `.env.cn`)
2. `.env.{product}.local`
3. **命令行环境变量** (CI/CD 注入)

```bash
# 命令行变量优先级最高
VITE_API_BASE=https://prod-api.example.com npm run build:cn
# 此时 VITE_API_BASE = https://prod-api.example.com
```

---

## 常见问题

### Q: 为什么生产不用 `.env` 文件？

**A**:
1. `.env` 文件包含敏感信息（密钥、端点 URL），不能进仓库
2. 桌面 App 打包后不需要 `.env`——所有配置由 `auth_config.yml`（公开字段）+ 编译进的环境变量（私密字段）提供
3. Web 版 `.env.cn` 文件是 `.gitignore` 例外（被 git 追踪），用于产品差异

### Q: 前端怎么拿到 CloudBase ENV_ID / 微信 APP_ID？

**A**: 桌面 App 通过后端 IPC handler `getAppConfig` 拉取（运行时，见 `gui/ipc/w2p_handlers/app_config_handler.py`），web 版走 web_server.py 同源 `GET /api/config`，两者 payload shape 一致（见 `gui_v2/src/contexts/AppConfigContext.tsx`）。

### Q: 如何验证构建后的配置？

**A**:
```bash
# 检查前端 dist 里的 API_BASE（仅 web 版）
grep -o 'https://[^"]*api\.[^"]*' gui_v2/dist/assets/*.js

# 检查 WS_URL
grep -o 'wss://[^"]*ws\.[^"]*graphql' gui_v2/dist/assets/*.js

# 桌面 App 启动后，通过 IPC handler getAppConfig 验证运行时配置：
python3 -c "from gui.ipc.w2p_handlers import _ensure_handlers_loaded; _ensure_handlers_loaded(); from gui.ipc.registry import IPCHandlerRegistry; from gui.ipc.types import IPCRequest; print(IPCHandlerRegistry.get_handler('getAppConfig')[0](IPCRequest(id='t', method='getAppConfig', params={}), {}).get('result'))"

# Web 部署（同源）：curl http(s)://<host>/api/config | jq .
```

**注意**：桌面 App 包内的 yml 公开字段可以用 `strings dist/main.app/Contents/MacOS/main | grep sccb0-d0gc5398xf028be6a` 查看，这是正常的（公开字段）。**绝不能用 `strings` 找 SECRET_KEY**，找到的话就是泄漏事件。

### Q: 不同环境可以用同一个构建产物吗？

**A**:
- Web 版：可以，不同部署位置配不同 `VITE_BASE`
- 桌面版：不行，每个产品（CN/Intl）需要单独构建

### Q: 构建失败 / 启动后 is_configured() 报错怎么办？

**A**: 检查：
1. GitHub Secrets 是否正确配置了 CN 四个私密字段
2. workflow 是否正确传入 env（看 `.github/workflows/release.yml` 中 `build-*-cn` 任务）
3. App 启动日志是否有 `WARNING: [CloudBaseAuth] Not configured - missing credentials`

---

## 维护

### 添加新的公开字段

1. 在 `apps/cn/config/auth_config.yml` 添加默认值
2. 更新 `auth/tencent/cloudbase_config.py` 的 dataclass 字段
3. 必要时更新后端 IPC handler `getAppConfig`（`gui/ipc/w2p_handlers/app_config_handler.py`）与 `web_server.py` 的 `GET /api/config`，两者 payload 必须保持一致
4. 更新 `docs/ENVIRONMENT_VARIABLES.md`

### 添加新的私密字段

1. 在 `auth/auth_config.py` 的 `_apply_env_overrides.env_map` 添加映射
2. 在 `auth/tencent/cloudbase_config.py` 的 `from_auth_config` 中添加 `os.getenv(...)`
3. 在 `.github/workflows/release.yml` 的三个 CN build job env 中添加 secret 注入
4. 更新 `docs/ENVIRONMENT_VARIABLES.md`，明确标注"私密字段"
5. **不要**写入 `auth_config.yml`

### 更新生产配置

**公开字段**：
1. 编辑 `apps/cn/config/auth_config.yml`，提交 PR
2. 重新触发 CI/CD 构建

**私密字段**：
1. 进入 GitHub Secrets 更新
2. 重新触发 CI/CD 构建（必须重新打包才能生效，因为环境变量编译进产物）

---

## 安全红线

⚠️ **永远不要**：
- 把 `ECAN_TENCENT_SECRET_KEY` 写入 `auth_config.yml`
- 把私密字段 commit 到 git 仓库
- 在 PR、Issue、Slack、邮件中讨论私密字段的具体值
- 在前端代码（gui_v2）中 `import.meta.env.VITE_*` 引用这些字段

> **注意**：`ECAN_WECHAT_APP_SECRET` 已移除，微信 AppSecret 仅需在 CloudBase 控制台配置。

✅ **必须**：
- 仅通过 GitHub Actions Secrets 管理
- 定期轮换（建议 90 天一次）
- 配置 [CAM 子账号](https://console.cloud.tencent.com/cam) + 最小权限策略，而非主账号密钥
