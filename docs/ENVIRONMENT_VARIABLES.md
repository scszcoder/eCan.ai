# 环境变量配置指南

## 目录

1. [概览：公开 vs 私密](#概览公开-vs-私密)
2. [配置文件结构](#配置文件结构)
3. [公开字段（auth_config.yml）](#公开字段auth_configyml)
4. [私密字段（环境变量 / CI Secrets）](#私密字段环境变量--ci-secrets)
5. [变量参考](#变量参考)
6. [开发环境](#开发环境)
7. [生产环境](#生产环境)
8. [安全指南](#安全指南)
9. [常见问题](#常见问题)

---

## 概览：公开 vs 私密

eCan.ai 的配置遵循"**公开字段可打包、私密字段运行时注入**"原则：

| 分类 | 存储位置 | 是否进 App 安装包 | 是否可公开 |
|------|----------|-------------------|-----------|
| **公开字段** | `apps/{cn,intl}/config/auth_config.yml` | ✅ 打包进 PyInstaller | ✅ 可以公开（资源 ID / 公开参数） |
| **私密字段** | GitHub Actions Secrets → 环境变量 | ⚠️ 编译进产物（运行时存在） | ❌ 永远不能公开 |
| **前端开发用** | `gui_v2/.env.local` / `gui_v2/.env.{cn,intl}` | 仅 web 版（Vite 编译时） | 部分公开，部分私密 |

### 公开 vs 私密清单

| 字段 | 分类 | 说明 |
|------|------|------|
| `CLOUDBASE.ENV_ID` | 公开 | CloudBase 环境 ID，类似 Cognito User Pool ID |
| `CLOUDBASE.REGION` | 公开 | 区域 |
| `WECHAT.APP_ID` | 公开 | 微信开放平台 AppID（网站应用） |
| `WECHAT.LOGIN_TYPE` | 公开 | 登录类型：`open_platform`（扫码登录）或 `mp_official`（公众号授权） |
| `WECHAT.SCOPE` | 公开 | OAuth scope：`snsapi_login`（扫码）或 `snsapi_userinfo`（授权） |
| `SMS.SDK_APP_ID` | 公开 | 短信应用 ID（CloudBase 内置 SMS 不需要） |
| `SMS.TEMPLATE_ID` | 公开 | 短信模板 ID（CloudBase 内置 SMS 不需要） |
| `SMS.SIGN_NAME` | 公开 | 短信签名（CloudBase 内置 SMS 不需要） |
| `EMAIL.*` | 公开 | 邮件发件人、provider |
| `LOGIN.ENABLE_*` | 公开 | 登录方式开关 |
| `JWT.EXPIRES_IN` | 公开 | Token 有效期 |
| `CLOUDBASE.SECRET_ID` | 公开 | 腾讯云 API 长期密钥 ID（CloudBase Auth API 不需要） |
| `CLOUDBASE.SECRET_KEY` | 公开 | 腾讯云 API 长期密钥（CloudBase Auth API 不需要） |
| `JWT.SECRET` | 公开 | 应用内部 token 签名密钥 |

> **注意**：`WECHAT.APP_SECRET` 仅需在 CloudBase 控制台配置，不需要在环境变量中设置。

---

## 配置文件结构

```
eCan.ai/
├── apps/
│   ├── cn/
│   │   ├── config/
│   │   │   ├── auth_config.yml          # CN 公开字段（git tracked）
│   │   │   ├── cloud_endpoints.json     # CN 端点
│   │   │   ├── app_manifest.json        # App 元数据
│   │   │   └── push_config.json         # 推送配置
│   │   └── build/
│   │       └── build_config_cn.json     # 构建配置
│   └── intl/
│       └── config/                       # Intl 同样结构
├── gui_v2/
│   ├── .env.example                     # 前端开发模板（git tracked）
│   ├── .env.local                       # 本地覆盖（gitignored）
│   ├── .env.cn                          # CN 产品覆盖（git tracked）
│   └── .env.intl                        # Intl 产品覆盖（git tracked）
├── .env                                  # 后端主配置（gitignored）
├── .env.example                          # 后端模板（git tracked）
└── docs/
    └── ENVIRONMENT_VARIABLES.md          # 本文档
```

### 后端配置加载顺序

```python
# auth/auth_config.py 与 auth/tencent/cloudbase_config.py 中的逻辑
1. apps/{app_id}/config/auth_config.yml   ← 公开字段（主配置）
2. 环境变量 / GitHub Secrets              ← 私密字段（构建时注入）
3. 默认值                                 ← 代码内 fallback
```

### 前端 Vite 加载顺序（仅 web 版）

```
.env (基础)
 → .env.{product}     (产品覆盖)
 → .env.local         (本地覆盖)
 → 命令行环境变量       (CI/CD 注入)
```

---

## 公开字段（auth_config.yml）

### CN 版本：`apps/cn/config/auth_config.yml`

完整字段说明见文件顶部注释。这里只列重点：

```yaml
CLOUDBASE:
  ENV_ID: "sccb0-d0gc5398xf028be6a"  # 公开资源 ID
  REGION: "ap-shanghai"                # 公开
  ENABLE_EMAIL_LOGIN: true         # 公开功能开关
  ENABLE_PHONE_LOGIN: true
  ENABLE_WECHAT_LOGIN: true
  ENABLE_SIGNUP: true

JWT:
  EXPIRES_IN: 86400                # 公开（秒）

SMS:
  sdk_app_id: ""                  # 公开
  template_id: ""                 # 公开
  sign_name: "eCan"               # 公开
  region: "ap-shanghai"

WECHAT:
  APP_ID: ""                      # 公开（OAuth client_id）
  CALLBACK_URL: "https://..."     # 公开
  SCOPE: "snsapi_userinfo"        # 公开
```

> ✅ 这些字段可以放心 commit 到 git。打包后用户可以从 App 安装包里看到——这是**预期行为**。

---

## 私密字段（环境变量 / CI Secrets）

### CN App 必需的私密字段

> **CloudBase Auth API 不需要任何私密环境变量**。认证使用 Bearer token，AppSecret 仅需在 CloudBase 控制台配置。

| 变量名 | 用途 | 必填 | 获取位置 |
|--------|------|------|----------|
| `ECAN_TENCENT_SECRET_ID` | 腾讯云 API 长期密钥 ID | ❌（仅调用其他腾讯云服务时需要） | [腾讯云访问管理](https://console.cloud.tencent.com/cam/capi) |
| `ECAN_TENCENT_SECRET_KEY` | 腾讯云 API 长期密钥 | ❌（同上） | 同上（只能新建时查看一次） |
| `ECAN_TENCENT_SMS_SDK_APP_ID` | 短信 SDK AppID | ❌（CloudBase 内置 SMS 不需要） | [短信控制台](https://console.cloud.tencent.com/smsv2) |
| `ECAN_TENCENT_SMS_TEMPLATE_ID` | 短信模板 ID | ❌（CloudBase 内置 SMS 不需要） | 同上 |
| `ECAN_TENCENT_SMS_SIGN_NAME` | 短信签名 | ❌（CloudBase 内置 SMS 不需要） | 同上 |

### Intl App 必需的私密字段

| 变量名 | 用途 | 必填 |
|--------|------|------|
| `AWS_ACCESS_KEY_ID` | AWS IAM 凭证 | ✅ |
| `AWS_SECRET_ACCESS_KEY` | AWS IAM 凭证 | ✅ |
| `AWS_COGNITO_USER_POOL_ID` | Cognito 用户池 | ✅ |
| `AWS_COGNITO_CLIENT_ID` | Cognito 客户端 | ✅ |
| `AWS_COGNITO_CLIENT_SECRET` | Cognito 客户端密钥 | ✅ |

### 通用可选私密字段

| 变量名 | 用途 |
|--------|------|
| `OPENAI_API_KEY` | OpenAI API |
| `CLAUDE_API_KEY` | Anthropic Claude |
| `GEMINI_API_KEY` | Google Gemini |
| `DASHSCOPE_API_KEY` | 阿里云 DashScope |

### 后端行为契约

- **私密字段缺失时**：`is_configured()` 返回 `False`，登录注册相关 IPC 接口返回 `CLOUDBASE_NOT_CONFIGURED`，前端展示 `cloudbase_not_available` 错误
- **WECHAT_APP_SECRET 缺失时**：`is_wechat_configured()` 返回 `False`，微信登录不可用

---

## 变量参考

### 后端环境变量

| 变量名 | 必填 | 默认值 | 适用版本 | 分类 | 说明 |
|--------|------|--------|----------|------|------|
| `ECAN_APP_ID` | ✅ | `intl` | 通用 | 公开 | 产品标识: `cn` / `intl` |
| `LOG_LEVEL` | ❌ | `INFO` | 通用 | 公开 | DEBUG / INFO / WARNING / ERROR |
| `DEBUG_MODE` | ❌ | `false` | 通用 | 公开 | 启用后验证码接口返回 dev_code（仅 dev） |
| `ECAN_WS_URL` | ❌ | 自动 | 通用 | 公开 | AppSync WebSocket URL |
| `ECAN_TENCENT_SECRET_ID` | ❌ | - | CN | 公开 | 腾讯云 API 长期密钥 ID（CloudBase Auth API 不需要） |
| `ECAN_TENCENT_SECRET_KEY` | ❌ | - | CN | 公开 | 腾讯云 API 长期密钥（CloudBase Auth API 不需要） |
| `ECAN_TENCENT_SMS_SDK_APP_ID` | ❌ | - | CN | 公开 | 短信 SDK AppID（CloudBase 内置 SMS 不需要） |
| `ECAN_TENCENT_SMS_TEMPLATE_ID` | ❌ | - | CN | 公开 | 短信模板 ID（CloudBase 内置 SMS 不需要） |
| `ECAN_TENCENT_SMS_SIGN_NAME` | ❌ | - | CN | 公开 | 短信签名（CloudBase 内置 SMS 不需要） |
| `AWS_ACCESS_KEY_ID` | ✅ | - | Intl | **私密** | AWS IAM |
| `AWS_SECRET_ACCESS_KEY` | ✅ | - | Intl | **私密** | AWS IAM |
| `AWS_COGNITO_USER_POOL_ID` | ✅ | - | Intl | **私密** | Cognito User Pool |
| `AWS_COGNITO_CLIENT_ID` | ✅ | - | Intl | **私密** | Cognito Client |
| `AWS_COGNITO_CLIENT_SECRET` | ✅ | - | Intl | **私密** | Cognito Client Secret |

### 前端 Vite 变量（仅 web 版，桌面 App 走 `/api/config`）

| 变量名 | 适用 | 分类 | 说明 |
|--------|------|------|------|
| `VITE_APP_ID` | 通用 | 公开 | 产品标识 |
| `VITE_API_BASE` | 通用 | 公开 | API 基础 URL |
| `VITE_WS_URL` | 通用 | 公开 | WebSocket URL |
| `VITE_CLOUDBASE_ENV_ID` | CN | 公开 | CloudBase 环境 ID |
| `VITE_COGNITO_DOMAIN` | Intl | 公开 | Cognito 域名 |
| `VITE_COGNITO_CLIENT_ID` | Intl | 公开 | Cognito 客户端 ID |
| `VITE_COGNITO_REDIRECT_URI` | Intl | 公开 | OAuth 回调 |
| `VITE_COGNITO_LOGOUT_URI` | Intl | 公开 | 登出回调 |
| `VITE_COGNITO_SCOPES` | Intl | 公开 | OAuth scope |

---

## 开发环境

### 快速开始

```bash
# 1. 复制模板
cp .env.example .env

# 2. 选择产品
./scripts/dev.sh cn
# 或
./scripts/dev.sh intl  # 默认

# 3. （可选）填入开发用的私密字段
# CloudBase Auth API 不需要 ECAN_TENCENT_SECRET_ID/SECRET_KEY（Bearer token 认证）
# 只有调用其他腾讯云服务时才需要

# 4. 启动
python main.py                 # 终端 1: 后端
cd gui_v2 && npm run dev:cn    # 终端 2: 前端
```

### 查看配置状态

```bash
# 查看当前生效的 yml 配置
cat apps/cn/config/auth_config.yml

# 启动后端后，访问运行时配置端点
curl http://localhost:4668/api/config | jq .

# 验证私密字段是否生效
python -c "
import os
from auth.tencent.cloudbase_config import CloudBaseConfig
cfg = CloudBaseConfig.from_env()
print('is_configured:', cfg.is_configured())  # 应为 True
print('env_id:', cfg.env_id)
print('secret_id set:', bool(cfg.secret_id))
"
```

---

## 生产环境

### 桌面 App（PyInstaller 打包）

```bash
# 触发 CI/CD 即可（无需本地操作）
git tag v1.0.0
git push origin v1.0.0
# GitHub Actions 自动构建并注入 secrets
```

`.github/workflows/release.yml` 已在三个 CN build job 中自动注入：
- `ECAN_TENCENT_SECRET_ID`
- `ECAN_TENCENT_SECRET_KEY`

> **注意**：`ECAN_WECHAT_APP_SECRET` 已移除，微信 AppSecret 仅需在 CloudBase 控制台配置。

### Web 版（Vite 构建）

```bash
cd gui_v2
VITE_API_BASE=https://api.fastprecisiontech.com \
VITE_WS_URL=wss://ws.fastprecisiontech.com/graphql \
npm run build:cn:web
```

### 完整生产构建示例（GitHub Actions）

```yaml
- name: Build CN Desktop
  env:
    ECAN_APP_ID: cn
    # 公开字段从 yml 读取，无需注入
    # 私密字段由下方 CI 注入
    ECAN_TENCENT_SECRET_ID: ${{ secrets.ECAN_TENCENT_SECRET_ID }}
    ECAN_TENCENT_SECRET_KEY: ${{ secrets.ECAN_TENCENT_SECRET_KEY }}
    # 注意：ECAN_WECHAT_APP_SECRET 已移除，微信 AppSecret 仅需在 CloudBase 控制台配置
  run: |
    python build_system/scripts/build_desktop_app.py --app cn
```

---

## 安全指南

### ⚠️ 绝对禁止

1. 把任何 `SECRET_*` / `APP_SECRET` 写入 `auth_config.yml`
2. 把私密字段 commit 到 git（即使是一瞬间）
3. 在 PR、Issue、Slack、邮件、日志中讨论私密字段的具体值
4. 在前端代码（`gui_v2/src/**`）中读取私密字段
5. 把 `.env` 或包含真实凭据的文件提交到 git

### ✅ 正确做法

```bash
# 1. 验证 .env 已被 gitignore
git check-ignore .env
# 应该输出: .env

# 2. 本地开发用 .env（gitignored）
#    包含 dev 沙箱 key，不是生产 key

# 3. 生产 key 只能通过 GitHub Actions Secrets 管理
#    Settings → Secrets and variables → Actions

# 4. 定期轮换（建议 90 天）
#    - 腾讯云：CAM → API 密钥 → 禁用旧 key → 创建新 key
#    - 微信：mp.weixin.qq.com → 开发 → 基本配置 → 重置
```

### CAM 子账号 + 最小权限（强烈推荐）

生产环境**不要**用主账号 SecretKey。创建 CAM 子账号并授予：

```json
{
  "version": "2.0",
  "statement": [
    {
      "effect": "allow",
      "action": [
        "tcb:CreateUser",
        "tcb:LoginUser",
        "tcb:GetUserByPhone",
        "tcb:GetUserByOpenId",
        "tcb:ResetPasswordByPhone",
        "sms:SendSms"
      ],
      "resource": "*"
    }
  ]
}
```

完整策略见 `docs/CLOUDBASE_AUTH_GUIDE.md`。

---

## 常见问题

### Q: 切换产品需要重启吗？

**A**: 是的。后端启动时读取 `ECAN_APP_ID`，修改后必须重启：

```bash
^C                       # 停止
./scripts/dev.sh cn      # 切换
python main.py            # 重启
```

前端也需要重启 Vite dev server。

### Q: 生产环境需要哪些配置？

**A**: 分两类：

**公开字段**（已经打包进 App，无需额外配置）：
- `apps/cn/config/auth_config.yml` 中的所有字段

**私密字段**（CI 注入到 PyInstaller 产物，仅调用其他腾讯云服务时需要）：
- `ECAN_TENCENT_SECRET_ID` / `ECAN_TENCENT_SECRET_KEY`（CloudBase Auth API 本身不需要）

> **微信 AppSecret 仅需在 CloudBase 控制台配置，不需要环境变量。**

> **CloudBase 内置 SMS**：手机号登录/注册使用 CloudBase 平台内置的短信能力，不需要额外配置腾讯云短信。

### Q: 私密字段怎么轮换？

**A**:
1. 创建新的 CAM 子账号 SecretKey
2. 在 GitHub Actions Secrets 中更新
3. 重新构建并发布 App
4. 旧 key 保留 1 周后禁用（给用户升级时间）

### Q: 如何调试"CloudBase not configured"错误？

**A**:
```bash
# 1. 检查后端启动日志
grep -i "CloudBaseAuth.*Not configured" runlogs/*.log

# 2. 检查私密字段是否在环境中
python -c "
import os
for k in ['ECAN_TENCENT_SECRET_ID', 'ECAN_TENCENT_SECRET_KEY']:
    v = os.getenv(k, '')
    print(f'{k}: {\"SET\" if v else \"MISSING\"}')
"

# 3. 调用 /api/config 看公开字段
curl http://localhost:4668/api/config | jq .auth.cloudbase_env_id

# 4. 调用 cloudbase_check_config IPC
#    通过 IPC 客户端调用 "cloudbase_check_config"
```

### Q: 桌面 App 包里能看到 CloudBase ENV_ID 吗？

**A**: 能，但**这是正常的**。ENV_ID 是公开资源 ID（类似 Cognito User Pool ID），可以安全暴露。

但**绝对不能**：
- `strings *.app/Contents/MacOS/main | grep SECRET_KEY` 找到值
- 反编译看到 APP_SECRET / SECRET_KEY / SECRET_ID

如果找到任何一个，意味着密钥泄漏，必须立即轮换。

### Q: 为什么不用 .env 存私密字段？

**A**:
1. 桌面 App 打包后没有 .env 文件机制（PyInstaller 不支持）
2. .env 容易被误 commit
3. 多环境（dev / staging / production）需要差异化
4. CI/CD 注入更符合现代部署实践

---

## 维护

### 添加新的公开字段

1. 在 `apps/{cn,intl}/config/auth_config.yml` 添加默认值
2. 更新 `auth/auth_config.py` 中相关 dataclass / getter
3. 必要时更新 `gui/LocalServer.py` 的 `app_config_handler`（如前端需要）
4. 更新本文档

### 添加新的私密字段

1. 在 `auth/auth_config.py` 的 `_apply_env_overrides.env_map` 添加映射
2. 在 `auth/tencent/cloudbase_config.py` 的 `from_auth_config` 添加 `os.getenv(...)`
3. 在 `.github/workflows/release.yml` 的所有 CN build job `env` 中添加 secret 注入
4. 在本文档"私密字段"清单中标注
5. **不要**写入 `auth_config.yml`

### 更新生产配置

**公开字段**：
```bash
# 编辑 yml
vim apps/cn/config/auth_config.yml
git commit -am "feat(auth): 启用微信登录"
git push
# 触发 CI/CD
```

**私密字段**：
1. GitHub → Settings → Secrets → 更新对应 secret
2. 重新触发 CI/CD（必须重新打包）
3. 发布后通知用户升级
