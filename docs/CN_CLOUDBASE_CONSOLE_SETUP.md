# CloudBase 控制台配置清单（eCan.ai CN 版）

本文档是 **运维向 checklist**：把 eCan.ai CN 版本用到的每一个腾讯云/微信/短信资源，逐项列在腾讯云控制台上怎么开通、如何拿到凭证。

> 配套文档：
> - [`CN_CLOUDBASE_AUTH_GUIDE.md`](./CN_CLOUDBASE_AUTH_GUIDE.md) —— 认证流程、架构、API 调用细节
> - [`PRODUCTION_BUILD.md`](./PRODUCTION_BUILD.md) —— 配置分层（公开/私密）+ CI 注入
> - [`ENVIRONMENT_VARIABLES.md`](./ENVIRONMENT_VARIABLES.md) —— 环境变量参考

---

## 0. 一图概览

```
┌──────────────────────────────────────────────────────────────┐
│                  腾讯云控制台需要开通的资源                      │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ① CloudBase 环境      ② 短信服务(可选)  ③ CAM 密钥(可选)  │
│   - EnvId               - SDK AppID*      - SecretId*       │
│   - 登录方式（邮箱/手机） - 签名*           - SecretKey*      │
│                          - 验证码模板*                        │
│                                                          │
│  * 表示：如果使用 CloudBase 内置 SMS，则不需要单独配置        │
│                                                              │
│  ④ 微信公众平台（可选）                                       │
│   - 服务号 AppID/AppSecret                                 │
│   - 网页授权域名                                            │
│                                                              │
│  ⑤ COS 对象存储（可选）                                      │
│   - 文件桶                                                  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│                    注入到 eCan.ai                               │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  apps/cn/config/auth_config.yml    (公开字段)               │
│   ├ CLOUDBASE.ENV_ID     ← ① EnvId                        │
│   ├ CLOUDBASE.REGION     ← ① ap-guangzhou                 │
│   ├ SMS.sdk_app_id       ← ② SDK AppID                    │
│   ├ SMS.template_id      ← ② 模板 ID                       │
│   ├ SMS.sign_name        ← ② 签名                          │
│   ├ WECHAT.APP_ID        ← ④ 微信 AppID                   │
│   ├ WECHAT.CALLBACK_URL  ← ④ 回调地址                      │
│   └ WECHAT.SCOPE         ← ④ snsapi_userinfo             │
│                                                              │
│  GitHub Actions Secrets            (私密字段)               │
│   ├ ECAN_JWT_SECRET                ← 自定义（必须）           │
│   ├ ECAN_WECHAT_APP_SECRET         ← ④ 微信 AppSecret       │
│   ├ ECAN_TENCENT_SECRET_ID         ← ③ SecretId（仅当调用其他腾讯云服务时需要）│
│   └ ECAN_TENCENT_SECRET_KEY        ← ③ SecretKey（仅当调用其他腾讯云服务时需要）│
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 1. CloudBase 环境（必做）

### 1.1 开通 CloudBase 服务

| 步骤 | 操作 |
|------|------|
| 1 | 登录 [腾讯云控制台](https://console.cloud.tencent.com/) |
| 2 | 顶部搜索框输入「**云开发 CloudBase**」 |
| 3 | 进入产品页 → 点击「**立即开通**」（会提示实名认证，未认证先完成） |
| 4 | 开通成功后会跳转到 [CloudBase 控制台](https://console.cloud.tencent.com/tcb) |

### 1.2 创建环境

| 步骤 | 操作 |
|------|------|
| 1 | CloudBase 控制台 → 左侧「**环境**」→「**创建环境**」 |
| 2 | 填写：<br>• 环境名称：`ecan-cn-prod`（或任意可识别名）<br>• 区域：**ap-guangzhou**（与 eCan.ai 默认配置一致）<br>• 计费方式：**基础套餐**（前期够用；后续按调用量升级） |
| 3 | 提交后等待 ~30s → 状态变为「**运行中**」 |
| 4 | 复制「**环境 ID**」（形如 `ecan-cn-prod-9xxxxxxx`），填到 `apps/cn/config/auth_config.yml` 的 `CLOUDBASE.ENV_ID` |

### 1.3 开通登录方式

CloudBase → 选中环境 → 左侧「**用户管理**」→「**登录方式**」：

| 登录方式 | 开关 | 是否必开 | 说明 |
|----------|------|---------|------|
| 邮箱密码 | ✅ 启用 | ✅ 必开 | `LoginCN.tsx` 邮箱登录/注册用 |
| 手机号 | ✅ 启用 | 推荐开 | 配合下面 §2 短信服务才能用 |
| 微信公众号 | ⚪ 可选 | 选开 | 配合 §4 微信公众平台才能用 |
| 匿名登录 | ⚪ 默认关 | 不开 | 业务不需要 |
| 自定义登录 | ⚪ 可选 | 选开 | 用于与现有账号体系对接 |

> 💡 每个登录方式展开后有「**启用状态**」开关，点击启用即可。eCan.ai 通过 `ENABLE_EMAIL_LOGIN / ENABLE_PHONE_LOGIN / ENABLE_WECHAT_LOGIN` 等 yml 字段控制**前端**是否展示入口；这里需要两边都开启才能真正使用。

### 1.4 安全域名（防止 Web 端 SDK 被恶意调用）

| 步骤 | 操作 |
|------|------|
| 1 | CloudBase → 用户管理 → 「**设置**」→「**安全域名**」 |
| 2 | 添加：<br>• `localhost`（开发）<br>• `https://www.fastprecisiontech.com`（生产域名） |
| 3 | 保存 |

---

## 2. 短信服务（可选 —— CloudBase 内置 SMS 不需要此配置）

### 2.1 开通短信服务

| 步骤 | 操作 |
|------|------|
| 1 | 进入 [短信 SMS 控制台](https://console.cloud.tencent.com/smsv2) |
| 2 | 第一次进入会提示「**开通短信服务**」→ 点击开通 |
| 3 | 完成企业认证（个人开发者需升级为企业） |

> **CloudBase 内置 SMS**：如果 CloudBase 平台已配置短信，则**不需要**单独配置腾讯云短信服务。手机号登录走 CloudBase 内置 API (`POST /auth/v1/verification`)，无需 `ECAN_TENCENT_SMS_*` 环境变量。

### 2.2 创建短信应用

| 步骤 | 操作 |
|------|------|
| 1 | 短信控制台 → 左侧「**应用管理**」→「**应用列表**」→「**创建应用**」 |
| 2 | 填写：<br>• 应用名称：`eCan-Production`（任意可识别）<br>• 用途说明：用户登录验证码 |
| 3 | 创建成功后，**复制 SDK AppID**（形如 `1400000099`），填到 `apps/cn/config/auth_config.yml` 的 `SMS.sdk_app_id` |

### 2.3 申请短信签名

| 步骤 | 操作 |
|------|------|
| 1 | 短信控制台 → 「**签名管理**」→「**创建签名**」 |
| 2 | 签名类型选择「**网站**」或「**APP**」（根据你的产品形态） |
| 3 | 签名内容：`eCan`（**必须与工信部备案/APP 名称一致**） |
| 4 | 提交审核 → 通常 1~2 小时通过 |
| 5 | 审核通过后，签名名称填到 `apps/cn/config/auth_config.yml` 的 `SMS.sign_name` |

### 2.4 申请验证码模板

| 步骤 | 操作 |
|------|------|
| 1 | 短信控制台 → 「**正文模板管理**」→「**创建正文模板**」 |
| 2 | 模板名称：eCan 登录验证码 |
| 3 | 短信内容（**变量必须用 `{1}` `{2}` 形式**）：<br>`您的验证码是{1}，{2}分钟内有效，请勿泄露于他人。` |
| 4 | 提交审核 → 通常 1~2 小时通过 |
| 5 | 审核通过后，**复制模板 ID**，填到 `apps/cn/config/auth_config.yml` 的 `SMS.template_id` |

### 2.5 验证

发送一条测试短信（短信控制台 → 签名/模板详情页有"发送测试"按钮）：

```bash
# 或通过 eCan 后端（DEBUG_MODE=true）触发
curl -X POST http://localhost:4668/api/auth/send_code \
  -H "Content-Type: application/json" \
  -d '{"phone": "13800138000", "purpose": "login"}'
```

---

## 3. CAM 访问密钥（可选 —— CloudBase Auth API 不需要）

> ⚠️ **注意**：CloudBase Auth API 使用 Bearer token 认证，**不需要** CAM SecretId/Key。只有调用其他腾讯云服务（如云存储 COS）时才需要。
> 强烈推荐：如果需要配置，用子账号最小权限。创建 [CAM 子账号](https://console.cloud.tencent.com/cam) + 自定义策略，仅授权 eCan 需要的 API。

### 3.1 创建 CAM 子账号

| 步骤 | 操作 |
|------|------|
| 1 | 进入 [CAM 用户列表](https://console.cloud.tencent.com/cam) → 「**用户列表**」→「**新建用户**」→「**自定义创建**」 |
| 2 | 访问方式：仅勾选「**编程访问**」（不要勾选控制台访问，避免登录风险） |
| 3 | 用户名：`ecan-app-service` |
| 4 | 完成创建 → **复制 SecretId 和 SecretKey**（SecretKey 只显示一次！） |

### 3.2 授权最小权限

| 步骤 | 操作 |
|------|------|
| 1 | CAM → 用户列表 → 找到 `ecan-app-service` → 「**关联策略**」 |
| 2 | 「**新建自定义策略**」→ 粘贴以下 JSON： |

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

| 3 | 关联给 `ecan-app-service` |

> 上述权限是 eCan.ai 实际用到的最小集。其他读类权限（`tcb:Describe*`）按需添加。

### 3.3 把凭证注入 eCan

| 字段 | 填到哪里 |
|------|---------|
| `SecretId` | GitHub Actions Secret → `ECAN_TENCENT_SECRET_ID`（仅当需要时） |
| `SecretKey` | GitHub Actions Secret → `ECAN_TENCENT_SECRET_KEY`（仅当需要时） |

> CloudBase Auth API 本身不需要 SecretId/Key。

---

## 4. 微信公众平台（可选，需要微信登录时必做）

> 微信登录有两种形态：「**微信公众平台**」（H5 网页授权）或「**微信开放平台**」（PC 扫码、移动 App）。eCan.ai 当前代码走「**网页授权**」路径，所以这里讲前者。

### 4.1 注册服务号

| 步骤 | 操作 |
|------|------|
| 1 | 进入 [微信公众平台](https://mp.weixin.qq.com) → 「**立即注册**」 |
| 2 | 选择「**服务号**」（不是订阅号，订阅号没有网页授权能力） |
| 3 | 完成主体认证（企业/个体工商户） |

### 4.2 获取 AppID 和 AppSecret

| 步骤 | 操作 |
|------|------|
| 1 | 微信公众平台 → 「**开发**」→「**基本配置**」 |
| 2 | 复制「**开发者 ID（AppID）**」→ 填到 `apps/cn/config/auth_config.yml` 的 `WECHAT.APP_ID` |
| 3 | 复制「**开发者密码（AppSecret）**」→ 填到 GitHub Actions Secret `ECAN_WECHAT_APP_SECRET` |

### 4.3 配置网页授权域名

| 步骤 | 操作 |
|------|------|
| 1 | 微信公众平台 → 「**设置**」→「**公众号设置**」→「**功能设置**」 |
| 2 | 「**网页授权域名**」→ 「**设置**」 |
| 3 | 填写 `fastprecisiontech.com`（不带协议、不带路径） |
| 4 | 下载校验文件放到域名根目录下：`https://www.fastprecisiontech.com/MP_verify_xxx.txt` |
| 5 | 验证通过 |

### 4.4 配置回调 URL（eCan.ai 端）

在 `apps/cn/config/auth_config.yml` 设置：

```yaml
WECHAT:
  APP_ID: "wx你的AppID"
  CALLBACK_URL: "https://www.fastprecisiontech.com/auth/wechat/callback"
  SCOPE: "snsapi_userinfo"
```

> **必须**与微信公众平台「**授权回调页面域名**」一致（域名部分，不含路径）。

### 4.5 验证

```bash
# 在浏览器中触发（应能跳转到微信授权页）
open "https://open.weixin.qq.com/connect/oauth2/authorize?appid=YOUR_APPID&redirect_uri=https%3A%2F%2Fwww.fastprecisiontech.com%2Fauth%2Fwechat%2Fcallback&response_type=code&scope=snsapi_userinfo&state=test#wechat_redirect"
```

---

## 5. COS 对象存储（可选，需要用户上传文件时）

如果业务需要用户上传头像/文件：

### 5.1 创建存储桶

| 步骤 | 操作 |
|------|------|
| 1 | 进入 [COS 控制台](https://console.cloud.tencent.com/cos) |
| 2 | 「**存储桶列表**」→「**创建存储桶**」 |
| 3 | 名称：`ecan-cn-files`（全局唯一） |
| 4 | 地域：`ap-guangzhou` |
| 5 | 访问权限：**公有读私有写**（用户头像/文件用） |
| 6 | 创建 |

### 5.2 配置 CORS（前端直传需要）

| 步骤 | 操作 |
|------|------|
| 1 | 存储桶 → 「**安全管理**」→「**跨域访问 CORS 设置**」→「**添加规则**」 |
| 2 | 来源 Origin：`https://www.fastprecisiontech.com` |
| 3 | 操作：PUT、POST、GET、HEAD、DELETE |
| 4 | 允许 Headers：`*` |
| 5 | 保存 |

### 5.3 凭证

`utils/storage/tencent_cos.py` 需要 `ECAN_TENCENT_SECRET_ID / KEY`（与 §3 同源）或 COS 单独的 COSAPI 密钥。

填到 `apps/cn/config/cloud_endpoints.json`：

```json
{
  "backend_storage_region": "ap-guangzhou",
  "backend_storage_bucket": "ecan-cn-files"
}
```

---

## 6. 完整 checklist（运维）

按顺序打勾即可，每项完成后在左侧 `[ ]` 改成 `[x]`。

### 阶段 A：核心（必做）

- [ ] **A1** 实名认证腾讯云账号（[控制台](https://console.cloud.tencent.com/setting) → 账号信息）
- [ ] **A2** 开通 CloudBase 服务（§1.1）
- [ ] **A3** 创建 CloudBase 环境 `ecan-cn-prod`，区域 `ap-guangzhou`（§1.2）
- [ ] **A4** CloudBase → 用户管理 → 启用「**邮箱密码**」登录方式（§1.3）
- [ ] **A5** CloudBase → 用户管理 → 启用「**手机号**」登录方式（§1.3）
> CloudBase 平台已内置短信发送能力，**不需要**额外配置腾讯云短信。
- [ ] **A6** CloudBase → 用户管理 → 安全域名添加 `www.fastprecisiontech.com`（§1.4）
- [ ] **A7** `apps/cn/config/auth_config.yml` 填入 `CLOUDBASE.ENV_ID`
- [ ] **A8** GitHub → Settings → Secrets 添加：
  - [ ] `ECAN_JWT_SECRET`（必须）

### 阶段 B：手机号登录（可选 —— CloudBase 内置 SMS 不需要单独配置）

> **CloudBase 内置 SMS**：如果 CloudBase 控制台已配置短信，则**不需要**以下步骤 §2。手机号登录走 CloudBase 内置 API。

- [ ] **B1** 开通短信服务（§2.1）（仅当 CloudBase 内置 SMS 不可用时）
- [ ] **B2** 创建短信应用，记录 SDK AppID（§2.2）
- [ ] **B3** 申请签名 `eCan`（§2.3）
- [ ] **B4** 申请验证码模板（§2.4）
- [ ] **B5** `apps/cn/config/auth_config.yml` 填入 `SMS.sdk_app_id / template_id / sign_name`

### 阶段 C：微信登录（可选）

- [ ] **C1** 注册微信服务号（§4.1）
- [ ] **C2** 获取 AppID + AppSecret（§4.2）
- [ ] **C3** 微信公众平台配置网页授权域名 `fastprecisiontech.com`（§4.3）
- [ ] **C4** `apps/cn/config/auth_config.yml` 填入 `WECHAT.APP_ID / CALLBACK_URL`
- [ ] **C5** GitHub Secret 添加 `ECAN_WECHAT_APP_SECRET`

### 阶段 D：用户文件存储（可选）

- [ ] **D1** 创建 COS 存储桶 `ecan-cn-files`（§5.1）
- [ ] **D2** 配置 CORS（§5.2）
- [ ] **D3** `apps/cn/config/cloud_endpoints.json` 填入 `backend_storage_bucket / region`

### 阶段 E：JWT（必做）

- [ ] **E1** 生成 JWT 密钥：
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(64))"
  ```
- [ ] **E2** GitHub Secret 添加 `ECAN_JWT_SECRET`

### 阶段 F：验证（必做）

- [ ] **F1** 触发 CI/CD 构建：
  ```bash
  git tag v0.7.0-test && git push origin v0.7.0-test
  ```
- [ ] **F2** 下载构建好的桌面 App 安装
- [ ] **F3** 启动后访问 `http://localhost:4668/api/config`，确认返回：
  ```json
  {
    "is_cn": true,
    "auth_type": "cloudbase",
    "auth": {
      "cloudbase_env_id": "ecan-cn-prod-9xxxxxxx",
      "wechat_app_id": "wx..."
    }
  }
  ```
- [ ] **F4** 测试邮箱注册 / 登录（应能正常进入主界面）
- [ ] **F5** 测试手机号登录（输入手机号，收到短信，登录成功）
- [ ] **F6**（如启用微信）测试微信扫码登录

---

## 7. 故障排查

| 现象 | 排查 |
|------|------|
| `CLOUDBASE_NOT_CONFIGURED` 报错 | §3 私密 Secret 未注入 / 拼写错；`/api/config` 是否返回 env_id |
| `AuthFailure` / `UserNotFound` | §1.3 邮箱密码登录方式未启用 |
| 短信发不出去 | §2.2-2.4 短信签名/模板未审核通过；账号余额不足；手机号格式必须 `+86` |
| `Signature` 签名失败 | §3 CAM 子账号权限不够；SecretId/Key 拼错 |
| 微信 `redirect_uri 域名与后台配置不一致` | §4.3 网页授权域名未配；回调 URL 必须用相同主域名 |
| `invalid appid` | §4.2 AppID 拼错；§4.3 服务号未认证 |
| COS 上传 403 | §5.2 CORS 未配；§5.1 存储桶权限设置错 |

---

## 8. 相关文件 / 配置入口

```
apps/cn/config/
├── auth_config.yml            # CN 公开字段（推送此文件即可改配置）
└── cloud_endpoints.json       # COS / OTA 桶

auth/tencent/
├── cloudbase_config.py        # 配置加载逻辑
├── cloudbase_auth.py          # 认证服务
├── sms_service.py             # 短信服务
└── code_store.py              # 验证码存储

gui/ipc/w2p_handlers/
└── cloudbase_handler.py       # IPC 入口

docs/
├── CN_CLOUDBASE_AUTH_GUIDE.md # 认证架构
├── PRODUCTION_BUILD.md        # 部署 & CI
├── ENVIRONMENT_VARIABLES.md   # 环境变量
└── CN_CLOUDBASE_CONSOLE_SETUP.md  # 本文档
```
