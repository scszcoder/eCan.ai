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
## 架构先天缺陷与对策

> 必读 — 这是 eCan.ai CN 版本当前架构固有的安全权衡,不是"修复就能消除"的问题。

### 1. 问题陈述

**架构事实**:
- 客户端(.exe / .app)是**单进程**,内含 PySide6 GUI + 本地 Starlette 后端 + CloudBase SDK
- **没有任何独立的"服务端"**,前端 + 后端都在用户机器上
- 用户邮箱/手机号登录需调 `CreateUser` / `LoginUser` / `ResetPasswordByPhone` 等腾讯云 API
- **必须**用 Tencent SK 签名

**结论**:
- SK 必须驻留在 .exe 进程(否则调不通腾讯云 API)
- .exe 跟着用户机器走 → 反编译(pyinstxtractor / 反射) / 环境变量 / 进程内存 dump → **SK 必然可被攻击者拿到**
- **没有"零暴露"方案**

### 2. 对策优先级

| 优先级 | 措施 | 收益 |
|---|---|---|
| **P0 必修** | **子账号策略(CAM Sub-User)** | SK 泄露后损失降为 0 |
| P1 强烈建议 | `.env` chmod 600 + **不随 .exe 打包** | SK 不落 exe 旁 |
| P2 持续 | SK **每月 rotate** | 缩短泄露窗口 |
| P3 已做 | yml 拦截 + 日志拦截 | 兜底 |
| P4 可选 | SK 加密存储(`cryptography.fernet` + 机器 ID 派生) | 防 .env 被直接读 |

### 3. P0 — 子账号策略(必需)

**不要用主账号 SK**。在 https://console.cloud.tencent.com/cam 创建专用子账号 `ecan-runtime`,只授予最少权限:

```json
{
  "version": "2.0",
  "statement": [
    {
      "effect": "allow",
      "action": [
        "tcb:CreateUser",
        "tcb:LoginUser",
        "tcb:ResetPasswordByPhone",
        "tcb:GetUserByPhone",
        "tcb:GetUserByEmail",
        "tcb:GetUserByOpenId"
      ],
      "resource": ["qcs::tcb:::envId/sccb0-d0gc5398xf028be6a"]
    }
  ]
}
```

**关键**:
- ❌ 不授 `tcb:DeleteEnv` / `tcb:UpdateEnv` / `*`
- ✅ 只授"读取用户 + 创建登录用户"相关的有限 action
- 资源范围限定到单一 env_id

**泄露后的真实损失**:攻击者只能调登录接口,**没法删数据库 / 开新资源 / 改云函数**。

### 4. P1 — `.env` 不随 .exe 打包

**PyInstaller 默认会把 `.env` 打进去**(如果路径在 `datas` 里)。**不要**:

```python
# ❌ build_system/hook-*.py — 不要这样
datas = [('.env', '.'), ...]
```

应该:
- ✅ `.env` 留在用户机器的 `~/Library/Application Support/eCan.cn/.env`(Mac) 或 `%APPDATA%/eCan.cn/.env`(Windows)
- ✅ 安装器首次运行时**生成**一个空 `.env`,**让用户填**(或由 activation flow 写入)
- ✅ `.env` 创建时 `chmod 600`(Mac/Linux) / `icacls %APPDATA%\eCan.cn\.env /inheritance:r /grant:r "%USERNAME%:F"`(Windows)
- ✅ 启动时检测权限,fallback 警告

### 5. P2 — SK rotate

- **每 30 天**强制 rotate(在 build_system / CI 里加 cron)
- 旧 SK 设 `Disable` 而不是立即删除 — 留 7 天观察窗口
- rotate 时同步更新 CI secret + 本地 .env.example 占位说明
- **记录 SK 创建时间**,启动时检查 >30 天则警告用户

### 6. P4 — SK 加密存储(可选)

```python
import base64
import hashlib
from cryptography.fernet import Fernet

def _derive_key(machine_id: str) -> bytes:
    """从机器 ID 派生 Fernet key。攻击者拿到 .env 也读不出明文。"""
    digest = hashlib.sha256(f"ecan-{machine_id}".encode()).digest()
    return base64.urlsafe_b64encode(digest)

def encrypt_sk(sk: str, machine_id: str) -> str:
    return Fernet(_derive_key(machine_id)).encrypt(sk.encode()).decode()

def decrypt_sk(encrypted: str, machine_id: str) -> str:
    return Fernet(_derive_key(machine_id)).decrypt(encrypted).decode()
```

**注意**:这是 **P4 不是 P0** —— 加密只防 .env 文件泄露,挡不住进程内存 dump / 反编译。

### 7. 失败模式权衡

| 假设 | 是否能防御 |
|---|---|
| 用户 .env 被备份到云盘 | ✅ P1(chmod 600) + P4(加密) |
| 用户机器中恶意软件读进程内存 | ❌ 任何方案都挡不住 |
| .exe 被反编译 | ❌ 任何方案都挡不住 |
| SK 被泄露到 GitHub | ✅ P2(rotate 缩短窗口) |
| 攻击者拿到 SK 想删库 | ✅ **P0 子账号** — 没权限 |

### 8. 必须接受的真实风险

- ❌ **零暴露方案不存在** — 架构就这样
- ✅ **真实目标**:泄露后的损失 = 0(子账号策略实现)
- ✅ 任何"加密 SK 防泄露"的话术都是 P4 锦上添花,**不能替代 P0**

---

## 安全建议

1. **JWT 密钥**:生产环境务必设置 `ECAN_JWT_SECRET`,使用随机字符串
2. **API 密钥**:使用最小权限原则,创建专用密钥
3. **Token 存储**:前端使用 HttpOnly Cookie 存储 Refresh Token
4. **敏感信息**:不要在前端存储密码,使用一次性 Token