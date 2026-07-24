# 腾讯云 CloudBase 认证配置指南

## 概述

CN 版本（eCan.cn）使用腾讯云 CloudBase 作为认证服务，支持：
- 邮箱密码登录
- 手机号 + 验证码登录
- 微信登录

## GitHub Actions 自动构建

### 构建流程

GitHub Actions 中使用 `ECAN_APP_ID` 环境变量区分 CN/Intl 版本：

```yaml
# .github/workflows/release.yml

# Intl 版本构建
build-macos:
  env:
    ECAN_APP_ID: intl

# CN 版本构建
build-macos-cn:
  env:
    ECAN_APP_ID: cn
```

### 构建系统处理

`build_system/ecan_build.py` 的 `FrontendBuilder` 会：

1. 读取 `ECAN_APP_ID` 环境变量
2. 设置 `VITE_APP_ID` 传递给 Vite 构建
3. 构建系统统一处理环境变量注入（通过命令行环境变量）

```python
# FrontendBuilder._run_build() 中
app_id = os.environ.get('ECAN_APP_ID', 'intl')
env['VITE_APP_ID'] = app_id

# 环境变量通过 CI/CD 注入，不使用 .env 文件
```

### 前端构建配置

前端通过 `VITE_APP_ID` 环境变量选择登录页面：

```typescript
// gui_v2/src/routes/index.tsx
const isCNApp = (): boolean => getAppId() === 'cn';

const Login = lazyWithRetry(() =>
  isCNApp()
    ? import('../pages/Login/LoginCN')
    : import('../pages/Login/Login')
);
```

### 环境变量文件

开发时使用 `gui_v2/.env.example` 作为模板，创建 `.env.local` 进行本地覆盖：

生产环境通过 CI/CD 注入变量。

### 构建命令

```bash
# CN 版本
ECAN_APP_ID=cn python build.py prod --version v1.0.0

# Intl 版本
ECAN_APP_ID=intl python build.py prod --version v1.0.0
```

## 腾讯云控制台配置

### 1. 开通云开发 CloudBase

1. 登录 [腾讯云控制台](https://console.cloud.tencent.com/)
2. 搜索「云开发」并开通服务
3. 创建环境（建议选择广州区域 `ap-guangzhou`）
4. 获取 **环境 ID**

### 2. 配置登录方式

在云开发控制台 → 登录授权：
- ✅ 手机号登录（需要配置短信服务）
- ✅ 邮箱登录
- ✅ 微信登录（需要配置微信开放平台）

### 3. 配置短信服务（可选，用于手机号登录）

1. 登录 [腾讯云短信服务](https://console.cloud.tencent.com/smsv2/)
2. 创建应用，获取 **SDK AppID**
3. 配置短信签名和模板
4. 在云开发控制台绑定短信服务

### 4. 配置微信登录（可选）

1. 登录 [微信开放平台](https://open.weixin.qq.com/)
2. 创建移动应用，获取 **AppID** 和 **AppSecret**
3. 在云开发控制台绑定微信登录

## 环境变量配置

在部署环境中设置以下环境变量：

```bash
# ===== CloudBase 配置 =====
# CloudBase 环境 ID（必需）
export ECAN_TENCENT_CLOUDBASE_ENV_ID="your-env-id-xxxxxx"

# ===== 腾讯云 API 密钥 =====
# 用于调用 CloudBase API（必需）
export ECAN_TENCENT_SECRET_ID="your-secret-id"
export ECAN_TENCENT_SECRET_KEY="your-secret-key"

# ===== 微信登录配置（可选）=====
export ECAN_WECHAT_APP_ID="wx1234567890abcdef"
export ECAN_WECHAT_APP_SECRET="your-wechat-app-secret"

# ===== 短信服务配置（可选）=====
export ECAN_TENCENT_SMS_SDK_APP_ID="1400123456"

# ===== JWT 配置（可选）=====
# 用于生成应用内部 Token，建议设置
export ECAN_JWT_SECRET="your-jwt-secret-key-min-32-chars"
export ECAN_JWT_EXPIRES_IN="86400"  # 24小时

# ===== 应用标识 =====
export ECAN_APP_ID="cn"
```

## 前端环境变量

在 `gui_v2` 目录创建 `.env.local` 文件进行本地开发：

```bash
# gui_v2/.env.local (本地开发使用，gitignored)
# CloudBase 配置
VITE_CLOUDBASE_ENV_ID=your-env-id-xxxxxx
VITE_APP_ID=cn
```

## 文件结构

```
eCan.ai/
├── auth/
│   ├── tencent/
│   │   ├── __init__.py
│   │   └── cloudbase_auth.py    # CloudBase 后端 SDK
│   └── auth_config.py           # 认证配置（已更新支持 CLOUDBASE）
│
├── gui/
│   └── ipc/
│       └── w2p_handlers/
│           └── cloudbase_handler.py  # CloudBase IPC 处理器
│
├── gui_v2/
│   └── src/
│       └── services/
│           └── auth/
│               ├── cloudbaseAuth.ts     # CloudBase 前端 SDK
│               └── useCloudBaseAuth.ts # CloudBase Auth Hook
│       └── pages/
│           └── Login/
│               ├── Login.tsx       # Intl 版本登录页
│               └── LoginCN.tsx     # CN 版本登录页（CloudBase）
│
└── apps/
    └── cn/
        └── config/
            └── auth_config.yml    # CN 版本认证配置
```

## API 接口

### 后端 IPC 接口

| 接口名 | 方法 | 参数 | 说明 |
|--------|------|------|------|
| `cloudbase_login` | POST | email, password | 邮箱密码登录 |
| `cloudbase_phone_login` | POST | phone, code | 手机号验证码登录 |
| `cloudbase_send_code` | POST | phone, purpose | 发送验证码 |
| `cloudbase_wechat_login` | POST | code | 微信登录 |
| `cloudbase_signup` | POST | email, password | 邮箱注册 |
| `cloudbase_get_user_info` | POST | token | 获取用户信息 |
| `cloudbase_logout` | POST | token | 登出 |
| `cloudbase_refresh_token` | POST | refresh_token | 刷新 Token |
| `cloudbase_check_config` | GET | - | 检查配置状态 |

## 使用流程

### 1. 后端初始化

CloudBase 认证服务会自动检测 `ECAN_APP_ID=cn`，并加载 CloudBase 配置：

```python
from auth.tencent.cloudbase_auth import CloudBaseAuthService

# 自动初始化（读取配置文件和环境变量）
service = CloudBaseAuthService()
```

### 2. 前端集成

```typescript
import { cloudbaseAuth } from '@/services/auth/cloudbaseAuth';

// 初始化
cloudbaseAuth.initialize({ envId: 'your-env-id' });

// 邮箱登录
const result = await cloudbaseAuth.loginWithEmail('user@example.com', 'password');
if (result.success) {
  console.log('Token:', result.data.token);
  console.log('User:', result.data.userInfo);
}

// 手机号登录
await cloudbaseAuth.sendPhoneCode('13800138000', 'login');
const phoneResult = await cloudbaseAuth.loginWithPhone('13800138000', '123456');
```

### 3. 登录页面

CN 版本使用 `LoginCN.tsx`，支持：
- 邮箱登录 / 注册
- 手机号 + 验证码登录
- 微信登录（待实现）

## 故障排除

### 1. CloudBase 配置未生效

检查环境变量是否正确设置：
```bash
echo $ECAN_TENCENT_CLOUDBASE_ENV_ID
echo $ECAN_TENCENT_SECRET_ID
```

### 2. Token 验证失败

1. 检查 JWT_SECRET 是否设置
2. 确认 Token 未过期
3. 验证 Token 签名

### 3. 微信登录失败

1. 确认微信开放平台应用已审核通过
2. 检查 AppID 和 AppSecret 是否正确
3. 确认授权回调域已配置

### 4. 短信验证码发送失败

1. 检查短信服务是否开通
2. 确认 SDK AppID 正确
3. 检查短信签名和模板是否配置

## 安全建议

1. **JWT 密钥**：生产环境务必设置 `ECAN_JWT_SECRET`，使用随机字符串
2. **API 密钥**：使用最小权限原则，创建专用密钥
3. **Token 存储**：前端使用 HttpOnly Cookie 存储 Refresh Token
4. **敏感信息**：不要在前端存储密码，使用一次性 Token
