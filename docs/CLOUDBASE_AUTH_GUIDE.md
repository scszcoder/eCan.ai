# 登录认证系统完整指南

> 适用版本:eCan.cn v0.7.0+ · 文档版本:2026-07-27
> 本文档合并了之前的 `CLOUDBASE_AUTH_GUIDE.md` / `CN_AUTH_DESIGN.md` / `CN_AUTH_REST_API.md` / `CN_AUTH_SECURITY.md` 四篇,便于一次性查阅。

## 目录

| § | 内容 | 适用读者 |
|---|---|---|
| **第一部分:控制台与部署** | | |
| [§1](#1-腾讯云控制台配置) | 开通云开发 / 配置用户管理 / 配置域名 / 拿到 env_id | 部署运维 |
| [§2](#2-环境变量与配置) | yml + env 公开/私密字段 / 优先级规则 | 部署运维 |
| [§3](#3-构建命令) | ECAN_APP_ID / VITE_APP_ID / CI/CD | DevOps |
| **第二部分:架构** | | |
| [§4](#4-架构总览) | 分层 / 模块清单 / Singleton / 数据流 | 架构师 |
| [§5](#5-关键设计决策) | device_id 演进 / 错误码 / 短信路径 / 校验规则 | 架构师 |
| **第三部分:API** | | |
| [§6](#6-通用约定) | Headers / 响应格式 / 19 错误码 | 全员 |
| [§7](#7-端点参考) | 13 个 REST 端点(全部 curl + JSON 示例) | 前端 / API 集成方 |
| **第四部分:安全** | | |
| [§8](#8-限流) | 6 规则 + token bucket 算法 | 安全 / 运维 |
| [§9](#9-审计日志) | 12 事件 + 字段表 + 文件位置 | 安全 / 运维 |
| [§10](#10-device_id-链路) | header 透传 + 文件兜底 + 优先级 | 安全 / 前端 |
| [§11](#11-横向安全清单) | HTTPS / CSRF / CORS / CAPTCHA 状态 | 安全 |
| **第五部分:测试与运维** | | |
| [§12](#12-测试策略) | 4 层金字塔 / 121 个用例 | 全员 |
| [§13](#13-常见问题排查) | FAQ / debug / 日志位置 | 运维 |
| [§14](#14-已知限制与改进方向) | 单进程限流 / 没切分日志 / 没接 SIEM | 架构师 |
| **附录** | | |
| [附录 A](#附录-a-控制台详细配置步骤) | 控制台截图级步骤 | 部署运维 |
| [附录 B](#附录-b-api-完整字段速查) | 13 端点字段表 | 前端 |

---

# 第一部分:控制台与部署

## 1. 腾讯云控制台配置

CN 版本(eCan.cn)使用腾讯云 CloudBase 作为认证服务,支持:
- 邮箱密码登录
- 手机号 + 验证码登录
- 微信登录

### 1.1 开通云开发 CloudBase

1. 登录 [腾讯云控制台](https://console.cloud.tencent.com/tcb)
2. 创建新环境(选择包年包月 / 按量付费)
3. 进入环境 → 用户管理 → 登录方式 → 开启:
   - ✅ 用户名密码登录
   - ✅ 手机号验证码登录
   - ❌ 匿名登录(默认关闭,需要时手动开)
   - ❌ 微信登录(需要先注册公众号)

### 1.2 获取环境标识 env_id

环境 ID 形如 `eCan-xxxxx`,在控制台首页可见。

### 1.3 配置短信签名/模板(可选,使用腾讯云短信)

如果用我们自己的 SMS service(走 Tencent Cloud SMS API),需要:
1. 在 [腾讯云短信控制台](https://console.cloud.tencent.com/smsv2) 创建签名 + 模板
2. 拿到 SecretId / SecretKey
3. 填入 `cloudbase.sms_secret_id` / `cloudbase.sms_secret_key` 或 env 变量

### 1.4 安全相关策略

P0 必须:子账号策略
- ❌ 不要用主账号 AK/SK
- ✅ 创建子账号 `eCan-auth-runtime`,只授权:
  - `tcb:CreateUser`
  - `tcb:LoginUser`
  - `tcb:ResetPasswordByPhone`
  - `tcb:GetUserInfo`
- ✅ 子账号 AK 填入 env,主账号永不下发到客户端

详见 [§11 横向安全清单](#11-横向安全清单) 与附录 A。

---

## 2. 环境变量与配置

### 2.1 配置优先级

```
1. 环境变量(ECAN_TENCENT_CLOUDBASE_*)     ← 最高
2. yml 配置文件(config/default.yml)         ← 中等
3. 代码默认值                                ← 最低
```

**只读 env,公开字段(env_id 等)永远走 yml** — 详见 [`ENVIRONMENT_VARIABLES.md`](./ENVIRONMENT_VARIABLES.md) 的 §"auth.cloudbase" 章节。

### 2.2 私密字段(走 env 变量)

| 字段 | Env 变量 | 说明 |
|---|---|---|
| SK | `ECAN_TENCENT_CLOUDBASE_SECRET_ID` | 子账号 AK |
| SK | `ECAN_TENCENT_CLOUDBASE_SECRET_KEY` | 子账号 SK |
| SMS SecretId | `ECAN_TENCENT_CLOUDBASE_SMS_SECRET_ID` | 腾讯云短信 AK |
| SMS SecretKey | `ECAN_TENCENT_CLOUDBASE_SMS_SECRET_KEY` | 腾讯云短信 SK |
| JWT Secret | `ECAN_JWT_SECRET` | 本地 token 签名 |

### 2.3 公开字段(走 yml)

| 字段 | yml 路径 |
|---|---|
| env_id | `auth.cloudbase.env_id` |
| enable_email_login | `auth.cloudbase.enable_email_login` |
| enable_phone_login | `auth.cloudbase.enable_phone_login` |
| enable_anonymous_login | `auth.cloudbase.enable_anonymous_login` |
| enable_signup | `auth.cloudbase.enable_signup` |

---

## 3. 构建命令

### 3.1 GitHub Actions 自动构建

`ECAN_APP_ID` 区分 CN/Intl 版本:

```yaml
# .github/workflows/release.yml

# Intl 版本
build-macos:
  env:
    ECAN_APP_ID: intl

# CN 版本
build-macos-cn:
  env:
    ECAN_APP_ID: cn
```

### 3.2 构建系统处理

`build_system/ecan_build.py::FrontendBuilder`:

```python
app_id = os.environ.get('ECAN_APP_ID', 'intl')
env['VITE_APP_ID'] = app_id
```

### 3.3 本地构建

```bash
# CN 版本
ECAN_APP_ID=cn python build.py prod --version v1.0.0

# Intl 版本
ECAN_APP_ID=intl python build.py prod --version v1.0.0
```

### 3.4 前端选择登录页

```typescript
// gui_v2/src/routes/index.tsx
const isCNApp = (): boolean => getAppId() === 'cn';

const Login = lazyWithRetry(() =>
  isCNApp()
    ? import('../pages/Login/LoginCN')
    : import('../pages/Login/Login')
);
```

### 3.5 .env.local(开发)

开发时使用 `gui_v2/.env.example` 作为模板,创建 `.env.local` 做本地覆盖。生产通过 CI/CD 注入。

---

# 第二部分:架构

## 4. 架构总览

### 4.1 为什么需要这套设计

eCan 桌面端(PySide6)同一份代码要支持两种部署形态:

| 部署形态 | 适用版本 | 认证后端 |
|---|---|---|
| CN(`ECAN_APP_ID=cn`) | 中国大陆 | **CloudBase**(本文主角) |
| Intl(`ECAN_APP_ID=intl`) | 其他地区 | 各自的 auth provider |

本文档只覆盖 **CN 路径**。

### 4.2 两套并行接口

| 接口 | 谁在用 |
|---|---|
| **历史 IPC**(WebSocket) | PySide6 直接调,继续保留可用 |
| **现有 REST**(`/api/auth/v1`) | 新加,React web 前端用 |
| **目标用户** | 旧 IPC 不动(没强制迁移窗口),新前端走 REST(清爽) |

**为什么不直接替换 IPC** — 现有 IPC 是稳定代码,迁移风险高,而 web 前端还没上线。两套并存保证:
- ✅ 老用户不受影响
- ✅ 新前端能用 REST
- ✅ 同一份业务逻辑(`auth_service.py`)被两层调用,不重复

### 4.3 分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend                                                        │
│  ┌──────────────────────────┐    ┌──────────────────────────┐   │
│  │ PySide6 WebEngine (旧)    │    │ React/Vite (新) gui_v2/  │   │
│  └──────────────┬───────────┘    └───────────────┬──────────┘   │
│         IPC (WS)                           HTTP REST             │
│         ↓                                  ↓                    │
├─────────────────────────────────────────────────────────────────┤
│  gui/LocalServer.py (Starlette)                                  │
│   ├─ IPC handlers (cloudbase_handler.py · 旧)                    │
│   └─ /api/auth/v1/*  REST routes (auth_routes.py · 新)           │
│          │                                  │                   │
│          └──────────────┬───────────────────┘                   │
│                         ↓                                       │
│  auth/tencent/auth_service.py  ← 业务编排 + 输入校验             │
│                         ↓                                       │
│  auth/tencent/cloudbase_auth.py ← CloudBase SDK 适配层            │
│                         ↓                                       │
│  https://{env_id}.api.tcloudbasegateway.com                      │
└─────────────────────────────────────────────────────────────────┘
```

### 4.4 模块清单

| 模块 | 行数 | 职责 |
|---|---|---|
| `auth_routes.py` | 527 | REST 路由层(Starlette),限流 + 审计 + HTTP 序列化 |
| `auth_service.py` | 344 | 业务编排,输入校验,参数规整,钩子保持向后兼容 |
| `cloudbase_auth.py` | 560 | CloudBase SDK 适配,web_v3 REST 调用,token 解析 |
| `rate_limiter.py` | 189 | 内存 token bucket,6 条规则,防爆破 / 短信炸弹 |
| `audit_log.py` | 134 | JSONL 审计日志,12 类事件,线程安全 |
| `code_store.py` | 127 | 验证码本地存储 + cooldown(SMS 用) |
| `sms_service.py` | 193 | 腾讯云 SMS 真实发送 |
| `cloudbase_config.py` | ~120 | yml + env 合并,公开/私密字段分类 |

**总计 ~2190 行**(不含测试)。测试代码 ~1500 行,121 个测试。

### 4.5 数据流示例:用户名密码登录

```
1. 前端 fetch("POST /api/auth/v1/signin", {
     body: {username, password},
     headers: {x-device-id: "uuid-xxx"}
   })
   ↓
2. auth_routes.signin_password:
   ├─ _read_json(body)
   ├─ _rate_limit_or_fail("signin")  ← bucket: ip|resource
   ├─ _device_id(request)            ← x-device-id header
   ├─ audit.record(SIGNIN_*)         ← 异步记录
   ├─ svc.signin_password(..., device_id)
   ↓
3. AuthService.signin_password:
   ├─ normalize_username            ← trim + lowercase @ 段
   ├─ validate_username / validate_password  ← 正则
   ├─ check config.is_configured
   ├─ cloudbase.sign_in_with_password(device_id=...)
   ↓
4. CloudBaseAuthService.sign_in_with_password:
   ├─ self._post("/auth/v1/signin", payload, device_id=did)
   ├─ _headers(device_id=did)        ← x-device-id header 注入
   ├─ requests.post(..., timeout=30)
   ↓
5. https://{env_id}.api.tcloudbasegateway.com/auth/v1/signin
   ↓ 返回: {access_token, refresh_token, expires_in}
   ↓
6. _wrap_token_response: 构造 CloudBaseUserInfo,封装 AuthResult.ok
   ↓
7. _auth_result_response:
   ├─ success → JSON {"success": true, "data": {...}}
   └─ failure → JSON {"success": false, "error": {code, message}}, HTTP 4xx/5xx
```

### 4.6 Singleton 模式

| 单例 | 作用 | 测试可重置 |
|---|---|---|
| `get_cloudbase_service()` | CloudBase SDK,持有 env_id / SK / device_id | `reset_cloudbase_service` |
| `get_auth_service()` | 业务层,包装 SDK + 校验 | `reset_auth_service` |
| `get_rate_limiter()` | 限流器,内存 bucket | `reset_rate_limiter` |
| `get_audit_log()` | 审计 logger | `reset_audit_log` |
| `get_code_store()` | 验证码 + cooldown | — |
| `get_sms_service()` | SMS SDK | — |

**单进程可行**:PySide6 GUI 单进程,内存单例没问题。
**多进程扩展**: rate_limiter 换 Redis 实现(同接口),无需改业务层。

---

## 5. 关键设计决策

### 5.1 device_id 演进

| 阶段 | 来源 | 状态 |
|---|---|---|
| (历史) | 后端写 `~/.eCan.cn/device_id` | ✅ 仍可工作(向后兼容) |
| (当前) | 客户端 header 透传 | ✅ 新 REST 全程支持 |
| (目标) | 客户端读写 localStorage | ⏸️ 前端还没接入 |

详见 [§10 device_id 链路](#10-device_id-链路)。

### 5.2 错误码 → HTTP 状态码

`_ERROR_TO_HTTP` 在 `auth_routes.py`:

| 错误码 | HTTP | 含义 |
|---|---|---|
| `INVALID_INPUT` | 400 | 入参格式错 |
| `INVALID_CREDENTIALS` / `UNAUTHORIZED` / `EXPIRED_TOKEN` | 401 | 凭证错 / token 无效 |
| `DISABLED` | 403 | 此登录方式被禁用 |
| `USER_EXISTS` | 409 | 注册冲突 |
| `WEAK_PASSWORD` | 400 | 密码太短 |
| `COOLDOWN` / `RATE_LIMITED` | 429 | 限流 |
| `SMS_SEND_FAILED` / `NETWORK_ERROR` | 502 | 上游错 |
| `NOT_CONFIGURED` | 503 | 后端没配好 |

**为什么这么分** — 前端不用解读"魔法字符串",HTTP 状态码就足够分类。先看 status,再看 `error.code` 决定 UI 文案。

### 5.3 短信验证码两条路径

| 目的 | endpoint | 实际发送 |
|---|---|---|
| 登录 + 注册 | `/auth/v1/verification/phone` | 我们自己的 SMS service (腾讯云短信 API) + 本地 `code_store` |
| 重置密码 | `/auth/v1/password/forgot` → `/auth/v1/verification/phone` | 同上 |

**为什么不直接调 CloudBase 短信 endpoint** — 腾讯云 SMS 是云开发附带的(走 SDK),我们走自己签的 SMS API 更可控,可加 cooldown、可看历史。

### 5.4 输入校验规则

| 字段 | 正则 | 备注 |
|---|---|---|
| username | `^[0-9a-zA-Z\-_.:+@ ]{2,48}$` | 允许 email 当 username |
| password | 长度 8-128 | 不限字符(CloudBase 强制复杂度) |
| phone | `^\+?[0-9 \-()]{7,20}$` | 国际号 |
| email | `^[^@\s]+@[^@\s]+\.[^@\s]+$` | 标准 email |
| verification token | 长度 ≥ 4 | 防空入参 |

只用 `re`,零依赖、好测试。

---

# 第三部分:API

## 6. 通用约定

### 6.1 Headers

| Header | 必填 | 说明 |
|---|---|---|
| `Content-Type` | 是(POST) | `application/json` |
| `Authorization` | 否(部分) | 形如 `Bearer <access_token>` |
| `x-device-id` | 推荐 | 客户端生成的 UUID,详见 [§10](#10-device_id-链路) |
| `User-Agent` | 自动 | 记录到审计日志 |

### 6.2 响应格式

**成功**:
```json
{
  "success": true,
  "data": { ... }
}
```

**失败**:
```json
{
  "success": false,
  "error": {
    "code": "INVALID_INPUT",
    "message": "Password must be at least 8 characters",
    "retry_after": 60
  }
}
```

### 6.3 全局错误码(19 类)

| `error.code` | HTTP | 含义 |
|---|---|---|
| `INVALID_INPUT` | 400 | 入参格式错 |
| `INVALID_CREDENTIALS` | 401 | 凭证错 |
| `UNAUTHORIZED` | 401 | 缺 token / token 无效 |
| `EXPIRED_TOKEN` | 401 | access_token 过期 |
| `DISABLED` | 403 | 此登录方式被禁用 |
| `USER_EXISTS` | 409 | 注册冲突 |
| `WEAK_PASSWORD` | 400 | 密码太短 |
| `RESET_FAILED` | 400 | 重置失败 |
| `SIGNUP_FAILED` | 400 | 注册失败 |
| `REFRESH_FAILED` | 401 | refresh 失败 |
| `LOGIN_FAILED` | 401 | 登录失败(generic) |
| `NOT_CONFIGURED` | 503 | 后端没配好(env_id 空) |
| `COOLDOWN` | 429 | 验证码 cooldown |
| `RATE_LIMITED` | 429 | 限流(带 `retry_after`) |
| `SMS_SEND_FAILED` | 502 | SMS 发送失败 |
| `NETWORK_ERROR` | 502 | 上游超时 / 网络错 |
| `LOGOUT_FAILED` | 502 | 登出失败 |
| `REQUEST_FAILED` | 502 | 通用请求失败 |
| `NO_TOKEN` | 502 | (历史保留) |

---

## 7. 端点参考

> 完整字段说明在 [附录 B](#附录-b-api-完整字段速查),本节给出每端点的 curl + 关键 JSON。

### 7.1 健康检查

```bash
GET /api/auth/v1/health
```

```json
{"success": true, "data": {"status": "ok", "service": "cloudbase-auth"}}
```

---

### 7.2 配置状态

```bash
GET /api/auth/v1/config
```

```json
{
  "success": true,
  "data": {
    "configured": true,
    "enable_email_login": true,
    "enable_phone_login": true,
    "enable_anonymous_login": false,
    "enable_signup": true,
    "sms_configured": true
  }
}
```

> 前端根据这个决定显示哪些登录方式。

---

### 7.3 用户名密码登录

```bash
POST /api/auth/v1/signin
Content-Type: application/json
x-device-id: <uuid>

{"username": "alice@example.com", "password": "MySecret123!"}
```

```json
{
  "success": true,
  "data": {
    "user_info": {"sub": "user_abc123", "email": "alice@example.com", "login_type": "password"},
    "access_token": "eyJhbGci...",
    "refresh_token": "rt_abc...",
    "expires_in": 7200
  }
}
```

**限流**:15min 最多 5 次(按 IP)。第 6 次返回 429 `RATE_LIMITED` + `retry_after`。

---

### 7.4 匿名登录

```bash
POST /api/auth/v1/signin/anonymously
Content-Type: application/json
x-device-id: <uuid>

{}
```

> 需要在腾讯云控制台开启"允许匿名登录"。

---

### 7.5 刷新 token

```bash
POST /api/auth/v1/signin/refresh
Content-Type: application/json
x-device-id: <uuid>

{"refresh_token": "rt_abc..."}
```

> 也支持 OAuth 风格 — Bearer access_token + 空 body,但 refresh_token 仍从 body 取。

---

### 7.6 验证码注册

```bash
POST /api/auth/v1/signup
Content-Type: application/json
x-device-id: <uuid>

{
  "phone_number": "+86 13800138000",
  "verification_token": "123456",
  "username": "alice",
  "password": "MySecret123!"
}
```

或邮箱版(`email` 替代 `phone_number`)。**冲突(409)**:邮箱或手机已注册 → `USER_EXISTS`。
**限流**:1h 最多 3 次(按 IP+资源)。

---

### 7.7 发送手机验证码

```bash
POST /api/auth/v1/verification/phone
Content-Type: application/json
x-device-id: <uuid>

{"phone_number": "+86 13800138000", "purpose": "signup"}
```

> purpose 可选:`login`(默认)/ `signup` / `reset_password`。

**限流**:60s cooldown + 1h 10 次(按 IP+手机)。

---

### 7.8 发送邮箱验证码

```bash
POST /api/auth/v1/verification/email
Content-Type: application/json
x-device-id: <uuid>

{"email": "alice@example.com", "purpose": "signup"}
```

**限流**:60s cooldown + 1h 20 次(按 IP+邮箱)。

---

### 7.9 触发重置密码验证码

```bash
POST /api/auth/v1/password/forgot
Content-Type: application/json
x-device-id: <uuid>

{"phone_number": "+86 13800138000"}
```

**限流**:60s cooldown + 1h 5 次。

---

### 7.10 提交新密码

```bash
POST /api/auth/v1/password/reset
Content-Type: application/json
x-device-id: <uuid>

{
  "phone_number": "+86 13800138000",
  "code": "123456",
  "new_password": "NewSecret456!"
}
```

**限流**:1h 最多 3 次。

---

### 7.11 当前登录用户

```bash
GET /api/auth/v1/user
Authorization: Bearer <access_token>
```

---

### 7.12 验证 token 有效性

```bash
POST /api/auth/v1/verify
Authorization: Bearer <access_token>

{}
```

返回 `{valid: true, user: {...}}` 或 401。

> 与 `/user` 差别:`/user` 只返 user_info;`/verify` 同时判断 valid + user,适合前端启动时探活。

---

### 7.13 登出

```bash
POST /api/auth/v1/logout
Authorization: Bearer <access_token>
```

> 无 token 也返回 200(用于前端清理)。

---

### 7.14 写登录前端 checklist

1. `GET /config` 决定显示哪些登录方式
2. 生成 `x-device-id` UUID,持久化到 localStorage
3. `POST /verification/phone or /verification/email` 拿 `verification_token`
4. 用户填验证码 → `POST /signup` 或 `POST /signin`
5. 拿 `access_token` + `refresh_token` 存内存(不存 localStorage)
6. 后续请求带 `Authorization: Bearer <access_token>`
7. `401 EXPIRED_TOKEN` → `POST /signin/refresh`
8. `401` 仍未救活 → 跳登录页
9. 用户主动登出 → `POST /logout`,清理内存 token

---

# 第四部分:安全

## 8. 限流

### 8.1 算法 — Token Bucket 简化版(滑动窗口)

- 每个 (key, action) 是一个 bucket
- bucket 内存一个 timestamp deque + last_request_at
- 每次来:
  1. `cooldown_seconds` 检查(防止秒级连发)
  2. 窗口限流:清理过期 + 计数
  3. 通过则追加 timestamp,失败则拒绝

**复杂度**:O(timestamp_count) 每个 bucket,O(1) 检查。

**为什么不用 Redis** — PySide6 单进程 GUI,in-memory 已够。代码用 `threading.Lock` 保证线程安全。**未来多进程部署时换 Redis 实现,同一接口**。

### 8.2 6 条规则

| Endpoint | 规则名 | 窗口 | Max | Cooldown |
|---|---|---|---|---|
| `POST /signin` | `signin` | 15min | 5 | 0 |
| `POST /verification/phone` | `verification_phone` | 1h | 10 | 60s |
| `POST /verification/email` | `verification_email` | 1h | 20 | 60s |
| `POST /signup` | `signup` | 1h | 3 | 0 |
| `POST /password/forgot` | `password_forgot` | 1h | 5 | 60s |
| `POST /password/reset` | `password_reset` | 1h | 3 | 0 |

**为什么这么定**:
- **signin 5/15min** — 用户正常一次登录至少 1min,5 次足够,15min 窗口保护正常用户
- **phone 10/1h + 60s cooldown** — 短信收费,严控;但允许用户短期换号重试
- **email 20/1h** — 邮件免费,可以稍宽
- **signup 3/1h** — 防自动化注册
- **forgot 5/1h + 60s** — 防"我狂发不同手机收验证码"
- **reset 3/1h** — 重置密码每次都通知用户,3 次足够

### 8.3 限流键

格式:`{ip}|{resource}`

| Endpoints | 资源 |
|---|---|
| `/signin` | `-` (按 IP 限) |
| `/verification/phone` | `phone_number` |
| `/verification/email` | `email` |
| `/signup` | `email` 或 `phone_number` |
| `/password/forgot` | `email` 或 `phone_number` |
| `/password/reset` | `email` 或 `phone_number` |

**为什么 ip + resource 组合**:
- 单 IP → 用 IP(防止单点爆破)
- 攻击者换 IP 但换不了用户手机号 → 用 resource(防止换 IP 攻击同一用户)

### 8.4 返回值

被限流时返 **HTTP 429**:

```json
{
  "success": false,
  "error": {
    "code": "RATE_LIMITED",
    "message": "Too many requests. Try again in 47 seconds.",
    "retry_after": 47
  }
}
```

`retry_after` 是秒数,前端可以用作 setTimeout 自动重试。

### 8.5 客户端 IP 提取

```python
def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
```

**当前**:127.0.0.1(本地)直接拿 `request.client.host`,不走代理。
**未来**:如果上 CDN / 反向代理,要让代理传 `X-Forwarded-For`。

---

## 9. 审计日志

### 9.1 设计目标

| 目标 | 满足 |
|---|---|
| 事后追溯"谁、什么时候、做了什么" | ✅ |
| 出错时调试"哪个调用挂了" | ✅ |
| 合规(GDPR / 等保) | ✅ |
| 写入失败不能阻塞主流程 | ✅ |
| 多线程安全 | ✅ |

**不记录**(出于设计):
- 密码明文
- 验证码明文
- access_token / refresh_token

### 9.2 事件类型(12 类)

`auth/tencent/audit_log.py::AuthEvent`:

| Enum 值 | 实际值 | 触发 |
|---|---|---|
| `SIGNIN_SUCCESS` | `signin_success` | signin_password 成功 |
| `SIGNIN_FAILED` | `signin_failed` | signin_password 失败(含限流) |
| `SIGNUP` | `signup` | signup 成功 |
| `SIGNUP_FAILED` | `signup_failed` | signup 失败 |
| `SIGNOUT` | `signout` | logout 调用(无论成功失败) |
| `VERIFICATION_SENT` | `verification_sent` | 验证码发送成功 |
| `VERIFICATION_FAILED` | `verification_failed` | 验证码发送失败 |
| `PASSWORD_FORGOT` | `password_forgot` | forgot 调用(成功/失败共用) |
| `PASSWORD_RESET` | `password_reset` | reset 成功 |
| `PASSWORD_RESET_FAILED` | `password_reset_failed` | reset 失败 |
| `TOKEN_REFRESH` | `token_refresh` | refresh 成功 |
| `TOKEN_REFRESH_FAILED` | `token_refresh_failed` | refresh 失败 |

### 9.3 字段

```json
{
  "timestamp": "2026-07-27T09:30:00.123456+00:00",
  "event": "signin_success",
  "result": "success",
  "hostname": "laptop-of-user",
  "request_id": null,
  "user_id": "user_abc123",
  "username": "alice@example.com",
  "ip": "127.0.0.1",
  "user_agent": "Mozilla/5.0 ...",
  "method": "POST",
  "path": "/api/auth/v1/signin",
  "error_code": null,
  "extra": {"purpose": "login", "device_id": "uuid-..."}
}
```

| 字段 | 来源 | 必填 |
|---|---|---|
| `timestamp` | UTC ISO 8601 | ✅ |
| `event` | AuthEvent enum | ✅ |
| `result` | "success" / "failure" | ✅ |
| `hostname` | socket.gethostname | ✅ |
| `request_id` | (预留,未实现) | ❌ |
| `user_id` | CloudBase 返回 `sub` | 成功登录/注册时 |
| `username` | 用户提交的 email/phone | ✅ |
| `ip` | request.client.host / X-Forwarded-For | ✅ |
| `user_agent` | request headers | 截断 256 字符 |
| `method` | HTTP method | ✅ |
| `path` | request url path | ✅ |
| `error_code` | AuthResult.error_code | 失败时 |
| `extra` | 端点自定义 e.g. purpose=signup | ❌ |

### 9.4 文件位置与格式

`runlogs/auth_audit.log`,格式:**JSON Lines**(每行一个 JSON 对象)。

```bash
$ tail -f runlogs/auth_audit.log | jq .
{
  "timestamp": "2026-07-27T09:30:00.123456+00:00",
  "event": "signin_failed",
  "result": "failure",
  "username": "alice",
  "ip": "127.0.0.1",
  "user_agent": "Mozilla/5.0...",
  "method": "POST",
  "path": "/api/auth/v1/signin",
  "error_code": "INVALID_CREDENTIALS",
  "extra": {}
}
{
  "timestamp": "2026-07-27T09:30:15.000000+00:00",
  "event": "signin_failed",
  "result": "failure",
  "username": "alice",
  "error_code": "RATE_LIMITED",
  "ip": "127.0.0.1",
  "extra": {}
}
```

### 9.5 失败兜底

写入失败(磁盘满 / 权限错)**不会抛异常**,只写 stderr。**为什么** — 审计日志是 secondary 关注点,主流程不能因为日志写不进去就崩。

---

## 10. device_id 链路

### 10.1 演进路径

| 阶段 | device_id 来源 | 状态 |
|---|---|---|
| (历史) | 后端写 `~/.eCan.cn/device_id` | ✅ 仍可工作(向后兼容) |
| (当前) | 客户端 header 透传 | ✅ 新 REST 全程支持 |
| (目标) | 客户端读写 localStorage | ⏸️ 前端还没接入 |

### 10.2 数据流

```
[前端] 生成 UUID → localStorage(持久化)
        ↓
        fetch("/", headers: {x-device-id: "uuid-xxx"})
        ↓
[Route] _device_id(request)  读 x-device-id
        ↓
[Service] svc.signin_xxx(..., device_id="uuid-xxx")
        ↓
[CloudBase SDK] self._post(..., device_id="uuid-xxx")
        ↓
[CloudBase] _headers(device_id=...) → header "x-device-id: uuid-xxx"
        ↓
https://{env_id}.api.tcloudbasegateway.com
```

### 10.3 优先级

**`device_id` 解析优先级**:

| 来源 | 优先级 |
|---|---|
| HTTP header `x-device-id` (per-request) | 🥇 最高 |
| 单例 `self._device_id` (cloudbase_auth 启动时) | 🥈 |
| 文件 `~/.eCan.cn/device_id` (兜底) | 🥉 |

```python
# cloudbase_auth.py:_headers()
h["x-device-id"] = device_id or self._device_id
```

`device_id` 是函数参数,`self._device_id` 是单实例属性。无 header → 走单例 / 兜底文件。

### 10.4 大小写

HTTP/1.1 标准:header 名**不区分大小写**。Starlette 把所有 header 转成小写存储。
- `x-device-id` ✅
- `X-Device-Id` ✅

### 10.5 缺省行为

不传 header → 一切正常工作(向后兼容):
- ✅ 老前端没升级,继续用现有 IPC 路径
- ✅ 测试用例没传 header 都能跑过
- ✅ SDK 自动用 `~/.eCan.cn/device_id`

### 10.6 为什么用 UUID

- **不可预测性**:防止攻击者伪造 device_id 绕过限流
- **冲突几乎为零**:2^122 空间下,碰撞概率 ~10^-18
- **生态友好**:Python / JS / Java 都内置

(当前实现中,device_id 不参与限流键 — 限流键只用 IP+resource。device_id 主要用于后续 CloudBase 端的异常检测。)

---

## 11. 横向安全清单

| 项 | 状态 | 说明 |
|---|---|---|
| **密码明文** | ✅ | 走 HTTPS,不落本地 |
| **token 明文** | ✅ | 在内存,不在 localStorage(推荐前端也这样做) |
| **SQL injection** | ✅ | 不用 SQL,用 HTTP API |
| **XSS** | ✅ | 用户输入(username)不进 HTML |
| **CSRF** | ✅ | local-only 127.0.0.1 |
| **CORS** | ✅ | 同源 |
| **HTTPS** | ✅ | CloudBase 强制 |
| **rate limiting** | ✅ | 6 规则 |
| **audit logging** | ✅ | 12 事件 |
| **device_id** | ✅ | header 透传 |
| **错误码规范** | ✅ | 不泄露内部细节,401 vs 400 区分明确 |
| **认证锁定** | ✅ | 5 次失败 15min 内拒绝(就是 signin rate limit) |
| **子账号 AK** | ✅ | P0,必须 |
| **CAPTCHA** | ⚠️ | UI 层补 |
| **webhook 通知** | ⚠️ | 邮件通知 |
| **设备指纹** | ⚠️ | UA + device_id 持续完善 |
| **SIEM 接入** | ⚠️ | 没接 |

### 11.1 必须接受的真实风险

- ❌ **零暴露方案不存在** — 架构就这样
- ✅ **真实目标**:泄露后的损失 = 0(子账号策略实现)
- ✅ 任何"加密 SK 防泄露"的话术都是 P4 锦上添花,**不能替代 P0**

### 11.2 SK 泄露损失表

| 泄露情形 | 损失 | 缓解 |
|---|---|---|
| SK 误提交到 yml | ❌ 写入 GitHub | ✅ pre-commit hook + gitignore |
| 用户机器中恶意软件读进程内存 | ❌ 任何方案都挡不住 | — |
| .exe 被反编译 | ❌ 任何方案都挡不住 | — |
| SK 被泄露到 GitHub | ✅ P2 | rotate 缩短窗口 |
| 攻击者拿到 SK 想删库 | ✅ **P0 子账号** | 没权限 |

---

# 第五部分:测试与运维

## 12. 测试策略

### 12.1 4 层金字塔

| 层级 | 文件 | 数量 | 时长 |
|---|---|---|---|
| 单元 | `tests/unit/test_auth_service.py` | 9 | <0.1s |
| 单元 | `tests/unit/test_rate_limit_audit.py` | 35 | <0.1s |
| 集成 | `tests/integration/test_auth_api.py` | 31 | <0.1s |
| E2E | `tests/e2e/test_auth_flow.py` | 9 | ~3s |
| **合计** | | **84 + 35 + 31 + 9 = 121,5 skip** | |

### 12.2 覆盖维度

- ✅ 入参校验(空、错、边界)
- ✅ 业务编排(disabled / not configured)
- ✅ HTTP 序列化(JSON 格式 / status code)
- ✅ 限流触发(cooldown / window)
- ✅ 审计日志记录(每种事件类型)
- ✅ device_id 透传(全部端点 + 大小写)
- ⚠️ E2E 真账号需要腾讯云控制台预置

### 12.3 跑测试命令

```bash
# 单元 + 集成(快速)
ECAN_APP_ID=cn python3 -m pytest tests/unit/test_rate_limit_audit.py \
    tests/unit/test_auth_service.py tests/integration/test_auth_api.py

# 加 E2E(慢,需要真账号)
ECAN_APP_ID=cn python3 -m pytest tests/unit tests/integration tests/e2e/test_auth_flow.py
```

---

## 13. 常见问题排查

### 13.1 "登录一直 INVALID_CREDENTIALS"

```bash
# 1. 检查 yml 配置
cat config/default.yml | grep -A 5 cloudbase

# 2. 检查 env 是否覆盖
env | grep ECAN_TENCENT_CLOUDBASE

# 3. 看审计日志
tail -f runlogs/auth_audit.log | jq '.event, .error_code, .username'
```

### 13.2 "验证码收不到"

```bash
# 1. 看是不是被限流(返回 COOLDOWN)
tail -f runlogs/auth_audit.log | jq '.event, .extra.purpose'

# 2. 检查 SMS service 是否配置
curl -s http://127.0.0.1:{port}/api/auth/v1/config | jq '.data.sms_configured'

# 3. 看 SMS service 日志(独立 logger)
grep -i "sms" runlogs/*.log
```

### 13.3 "限流太严"

临时调整: `auth/tencent/rate_limiter.py::RULES` 直接改常量。
生产调整: 改成从 yml 读(下次重构)。

### 13.4 "audit log 没写"

```bash
# 检查目录权限
ls -la runlogs/
# 应该有写入权限,否则审计写入失败只写 stderr(见 §9.5)
```

### 13.5 "401 EXPIRED_TOKEN 但 refresh 也没用"

可能是 refresh_token 也过期了(默认 30 天),需要重新登录。

### 13.6 调试模式

设环境变量 `DEBUG_MODE=true`,CloudBase SDK 会打印更详细的请求日志。

---

## 14. 已知限制与改进方向

| 项 | 影响 | 改进方向 |
|---|---|---|
| Rate limiter 是 in-memory | 多进程需要换 Redis | 同接口换 Redis |
| audit log 没切分 | 单文件越写越大 | 按天切分: `auth_audit_2026-07-27.log` |
| 没接 SIEM | 不能进企业级安全平台 | 改成可对接 syslog / fluentd |
| 没 SLA 监控 | 无法自动报警 | 接入 Prometheus |
| refresh_token 滚动更新策略不可配 | 默认 CloudBase 行为 | 中等 |
| device_id 不参与限流 | 攻击者换 IP 不能跨设备识别 | 加到限流键 |
| 没记录 verification_token hash | 出事无法追溯是哪个验证码 | record extra 里记 hash |
| 没有 OpenAPI 自动生成 | 文档维护成本 | 用 Pydantic + 自定义 renderer |
| 前端还没接入 REST | 当前仅 IPC 在用 | 已记入 TODO |
| 没 CAPTCHA | 自动化攻击 | UI 层补 |
| 没 webhook 通知 | 邮件通知 | 端内 |

---

# 附录

## 附录 A:控制台详细配置步骤

### A.1 开通云开发 CloudBase(详细)

1. 登录 [腾讯云控制台](https://console.cloud.tencent.com/tcb)
2. **新建环境**:
   - 名称:`eCan-prod`(自定义)
   - 计费:按量付费(初期)/ 包年包月(规模大后)
   - 区域:选择华南 / 华东(根据用户地域)
3. 环境创建后,**记下 `env_id`**(形如 `eCan-abc123`),填入 `config/default.yml`:
   ```yaml
   auth:
     cloudbase:
       env_id: eCan-abc123
   ```

### A.2 配置登录方式

环境 → 用户管理 → 登录方式:

| 登录方式 | 推荐 | 备注 |
|---|---|---|
| 用户名密码 | ✅ 必开 | 用于 email/username 登录 |
| 手机号验证码 | ✅ 必开 | 短信登录/注册 |
| 邮箱验证码 | ✅ 必开 | CloudBase 自带,无需自配 |
| 微信小程序 | ❌ 按需 | 我们没用 |
| 微信公众号 | ❌ 按需 | 同上 |
| 匿名登录 | ❌ 默认关 | 需要时手动开 |

### A.3 配置短信签名/模板

如果走**我们自己的 SMS service**(推荐,更可控):

1. 进入 [腾讯云短信控制台](https://console.cloud.tencent.com/smsv2)
2. **创建签名**:`eCan.cn`(需 ICP 备案的网站/App 名)
3. **创建模板**:模板 ID 例如 `123456`,内容形如:
   ```
   【eCan】您的验证码是 {1},5 分钟内有效。
   ```
4. **创建子账号**(P0 安全):
   - 访问管理 → 用户 → 新建用户
   - 类型:**子账号**
   - 权限:**仅**授权 `QcloudSMSFullAccess`(或更细粒度的 SMS 权限)
   - 拿到 SecretId / SecretKey,填入 env 变量(见 §2.2)

### A.4 配置域名(可选,生产需要)

如果 web 前端部署在远端,需要在 CloudBase 配置"授权域名"。

---

## 附录 B:API 完整字段速查

### B.1 端点清单(13)

| 方法 | 路径 | 限流规则 | 关键入参 | 关键返回 |
|---|---|---|---|---|
| GET | `/health` | — | — | `status` |
| GET | `/config` | — | — | 配置状态 |
| POST | `/signin` | signin 5/15min | `username`, `password` | `access_token`, `refresh_token`, `user_info` |
| POST | `/signin/anonymously` | — | — | tokens |
| POST | `/signin/refresh` | — | `refresh_token` (body) | new tokens |
| POST | `/signup` | signup 3/1h | `phone_number`/`email`, `verification_token` | tokens |
| POST | `/verification/phone` | 60s + 10/1h | `phone_number`, `purpose` | `message` |
| POST | `/verification/email` | 60s + 20/1h | `email`, `purpose` | `message` |
| POST | `/password/forgot` | 60s + 5/1h | `phone_number`/`email` | `message` |
| POST | `/password/reset` | 3/1h | `phone_number`/`email`, `code`, `new_password` | `message` |
| POST | `/logout` | — | Bearer access_token | `message` |
| GET | `/user` | — | Bearer access_token | `user_info` |
| POST | `/verify` | — | Bearer access_token | `{valid, user}` |

### B.2 user_info 字段

`user_info` 出现在 login / signup / refresh / user / verify 返回的 `data` 里:

```json
{
  "sub": "user_abc123",          // 主键,等同于 user_id
  "email": "alice@example.com",  // 可为 null
  "phone_number": "+86...",      // 可为 null
  "username": "alice",           // 可为 null
  "nickname": null,              // 可为 null
  "avatar_url": null,            // 可为 null
  "login_type": "password"       // "password" / "otp" / "anonymous" / "signup" / "refresh"
}
```

### B.3 error 字段

失败响应:

```json
{
  "success": false,
  "error": {
    "code": "RATE_LIMITED",
    "message": "Too many requests. Try again in 47 seconds.",
    "retry_after": 47,         // 仅 RATE_LIMITED
    "purpose": "signup"        // 仅 verification/* 类
  }
}
```

---

## 相关文档

- [`ENVIRONMENT_VARIABLES.md`](./ENVIRONMENT_VARIABLES.md) — 环境变量分类与优先级
- [`TENCENT_CLOUD_ARCHITECTURE.md`](./TENCENT_CLOUD_ARCHITECTURE.md) — 整体腾讯云架构
- [`CN_CLOUDBASE_CONSOLE_SETUP.md`](./CN_CLOUDBASE_CONSOLE_SETUP.md) — 控制台截图配置步骤
- [`PRODUCTION_BUILD.md`](./PRODUCTION_BUILD.md) — 生产构建与签名
- [`CN_TENCENT_CLOUD_CAPABILITY_MAPPING.md`](./CN_TENCENT_CLOUD_CAPABILITY_MAPPING.md) — 能力映射

> **历史文档**(已合并):`CN_AUTH_DESIGN.md` / `CN_AUTH_REST_API.md` / `CN_AUTH_SECURITY.md` 现已合并到本文档,链接保留向后兼容。