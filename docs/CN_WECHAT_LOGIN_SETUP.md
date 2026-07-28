# 微信扫码登录接入指南（CloudBase 托管模式 / 无需公网回调）

> **目标场景**：PC 网页 → 显示二维码 → 用户用手机微信扫 → 登录完成
> **关键优势**：无需自有公网回调地址、无需备案回调域、无需本地 OAuth server
> **当前状态**：代码已实现完整流程，卡在 **CloudBase 控制台 provider 启用** + **开放平台网站应用 AppID**

---

## 1. 当前实现（已写好，无需改代码）

### 1.1 后端：生成授权 URL

```542:598:auth/tencent/cloudbase_auth.py
        # 根据 LOGIN_TYPE 选择 CloudBase provider_id 和默认 scope
        login_type = (self.config.wechat_login_type or "open_platform").lower()
        if login_type == "mp_official":
            provider_id = "wx_mp"
            default_scope = "snsapi_userinfo"
        else:  # 默认 / open_platform
            provider_id = "wx_open"
            default_scope = "snsapi_login"

        try:
            # 使用 GET 请求获取授权 URI
            url = f"{self.base_url}/auth/v1/provider/uri"
            params = {
                "provider_id": provider_id,
                "state": state or f"wechat_qr_{uuid.uuid4().hex[:16]}",
            }
            # redirect_uri 必须传给 CloudBase（微信会回调到这个地址）
            if redirect_uri:
                params["redirect_uri"] = redirect_uri
            # 把配置里的 scope 透传给 CloudBase；未填则用本模式默认值
            scope_to_send = self.config.wechat_scope or default_scope
            params["scope"] = scope_to_send
```

调 `GET /auth/v1/provider/uri?provider_id=wx_open&redirect_uri=...&scope=snsapi_login`，
CloudBase 返回带 `code/state` 占位符的微信扫码 URL。

### 1.2 后端 IPC handler

```887:934:gui/ipc/w2p_handlers/cloudbase_handler.py
@IPCHandlerRegistry.handler("cloudbase_wechat_h5_login")
def handle_cloudbase_wechat_h5_login(request: IPCRequest,
                                     params: Optional[Dict[str, Any]]) -> IPCResponse:
    """使用 CloudBase 托管登录页进行微信登录

    完整流程（CloudBase 托管模式，无需备案域名、无需本地 OAuth server）：

    1. App 调此接口（state 防 CSRF）
    2. 后端调 CloudBase genProviderRedirectUri：
       - 不传 provider_redirect_uri
       - CloudBase 用自己的备案回调域接收微信回调
    3. 返回微信授权 URL 给前端
    4. 前端跳转到该 URL → 微信扫码授权
    5. 微信回调到 CloudBase 的备案域名
    6. CloudBase 自动处理后，把 code/state 拼到回调 URL
    7. 前端页面加载时，CloudBase SDK detectSessionInUrl 自动捕获
    8. 完成 signInWithProvider 登录
    """
```

### 1.3 前端：拿 URL + 显示二维码 + 用 code 换 token

```370:395:gui_v2/src/services/auth/cloudbaseAuth.ts
    // 调后端获取微信授权 URI（必须传 redirect_uri，否则 CloudBase 返回的 URI 缺少回调地址，
    // 会导致微信回调时报 "redirect_uri 参数错误"）
    const resp = await apiRouter.execute<any>(
      { method: 'cloudbase_wechat_h5_login' },
      { state, redirect_uri: redirectUri || window.location.origin },
    );

    if (resp?.success && resp?.data?.url) {
      logger.info('[CloudBaseAuth] Redirecting to CloudBase WeChat login');
      window.location.href = resp.data.url;
```

```117:122:gui_v2/src/pages/Login/LoginCN.tsx
          const { provider_token } = await auth.grantProviderToken({
            provider_id: 'wx_open',
            provider_redirect_uri: window.location.origin,
            provider_code: code,
          });
```

---

## 2. 完整数据流（PC 扫码 + 无公网回调）

```
┌────────────────────────────────────────────────────────────────────┐
│ 阶段 1：获取授权 URL                                                │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  浏览器 (localhost:3000/login)                                      │
│    └─→ POST /api/cloudbase_wechat_h5_login                         │
│         └─→ CloudBase GET /auth/v1/provider/uri                   │
│              ?provider_id=wx_open                                   │
│              &redirect_uri=http://localhost:3000/login              │
│              &scope=snsapi_login                                    │
│                                                                    │
│  返回微信扫码 URL → 浏览器显示二维码                                 │
└────────────────────────────────────────────────────────────────────┘
                              ↓ 用户用手机微信扫
┌────────────────────────────────────────────────────────────────────┐
│ 阶段 2：微信回调 + 换 token（关键：CloudBase 中转，无需自有公网）      │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  手机微信 ──确认授权──→ 微信服务器                                   │
│  微信服务器 ──302──→ CloudBase 中转（CloudBase 备案域名）            │
│                       CloudBase 用 code 换 access_token             │
│  CloudBase ──302──→ http://localhost:3000/login                    │
│                     ?code=xxx&state=yyy                             │
│                     （URL 里直接带 code 给前端）                     │
│                                                                    │
│  前端 useEffect 截到 URL                                            │
│    └─→ auth.grantProviderToken({                                    │
│         provider_id: 'wx_open',                                     │
│         provider_code: code,                                        │
│       })                                                            │
│         └─→ CloudBase 用 code 换 provider_token                    │
│              └─→ signInWithProvider(provider_token) → 登录成功 ✓    │
└────────────────────────────────────────────────────────────────────┘
```

**重要：这套流程根本不需要自己有公网回调地址。** CloudBase 帮你中转了。

---

## 3. 必须做的两件事（才能跑通）

### 3.1 在 CloudBase 控制台启用「网站应用微信登录」provider

1. 登录 https://console.cloud.tencent.com/tcb
2. 选环境 `sccb0-d0gc5398xf028be6a`（确认环境 ID 匹配）
3. 左侧菜单：「用户管理」→「登录方式」
4. 找到「**网站应用微信登录**」（不是「微信公众号登录」）
5. 点「启用」→ 填入：
   - AppID：开放平台网站应用的 AppID（**不是当前的 `wx6c40318a4c843596`，要重新申请**）
   - AppSecret：同上
6. 保存

> ⚠️ 如果控制台「网站应用微信登录」开关是灰色 / 找不到 → 说明当前环境套餐不支持，需要升级或换环境。

### 3.2 申请开放平台「网站应用」AppID

去 [open.weixin.qq.com](https://open.weixin.qq.com)：

1. **注册开发者账号**（如果没注册过）
   - 用你的微信扫码
   - 选择主体类型：个人 / 企业
   - 个人：需身份证 + 微信扫码
   - 企业：需营业执照 + 对公验证（打款 1 分钱）
2. **开发者资质认证**（审核 1-3 天）
3. **创建网站应用**（管理中心 → 网站应用 → 创建网站应用）
   - 网站域名：必须已 ICP 备案（例：`ecan.cn`）
   - 网站备案号：填对应 ICP 备案号
   - 应用名称、简介、Logo（28×28 + 108×108）
4. **提交审核**（审核 7 个工作日）
5. 审核通过 → 拿到新的 AppID + AppSecret
6. 把新 AppID + AppSecret 回填到 3.1 步骤

### 3.3 回填到 yml

```yaml
WECHAT:
  LOGIN_TYPE: "open_platform"      # ← 已是这个，不用改
  APP_ID: "wx新拿到的网站应用AppID"  # ← 改这里
  SCOPE: "snsapi_login"             # ← 已是这个，不用改
```

重启服务，重新点击「微信登录」即可。

---

## 4. 临时验证（AppID 未到位期间）

可以先用以下方式验证流程是否正确（仍会报错，但能定位问题）：

### 4.1 检查 CloudBase provider 是否存在

```bash
curl -X GET "https://sccb0-d0gc5398xf028be6a.api.tcloudbasegateway.com/auth/v1/provider/uri?provider_id=wx_open" \
  -H "Content-Type: application/json"
```

返回 `provider wx_open not found` → 没启用（确认走 3.1）  
返回 `{uri: "..."}` → 已启用，AppID 写错了（走 3.2）

### 4.2 临时禁用微信登录按钮

yml 改：
```yaml
LOGIN:
  ENABLE_WECHAT_LOGIN: false
```

前端 `LoginCN.tsx` 会自动隐藏按钮，不影响其他登录方式。

---

## 5. 配置矩阵速查

| LOGIN_TYPE | provider_id | scope | CloudBase 控制台开关 | AppID 来源 | 适用场景 |
|---|---|---|---|---|---|
| `open_platform` | `wx_open` | `snsapi_login` | 「**网站应用**微信登录」 | open.weixin.qq.com 网站应用 | **PC 网页扫码** ← 目标 |
| `mp_official` | `wx_mp` | `snsapi_userinfo` | 「**微信公众号**登录」 | mp.weixin.qq.com 公众号 | H5 微信内打开 |

**当前 yml 配置**：`open_platform` → 等开放平台网站应用 AppID 到位。

---

## 6. 常见问题

### Q1: 我已经有 AppID `wx6c40318a4c843596`，为什么不能用？

A: 这个 AppID 不是「网站应用」类型。可能是公众号、小程序、移动应用。必须去 open.weixin.qq.com 注册「网站应用」才能拿到新的 AppID。

### Q2: 没有公网回调地址 / 没有 ICP 备案，能用吗？

A: **能！** CloudBase 托管模式用 CloudBase 自己的备案域名做中转，回调地址是 `localhost:3000/login`，不需要你的公网回调。  
但**网站应用申请时**必须填已备案域名（个人可以是 `yourname.com`），所以至少要有一个已备案的域名。

### Q3: `redirect_uri` 该填什么？

A: 当前开发环境填 `http://localhost:3000/login`，生产环境填你的正式登录页 URL（例 `https://ecan.cn/login`）。  
CloudBase 控制台不需要配回调域白名单（因为 CloudBase 中转了），但**网站应用**在开放平台申请时要填「授权回调域」= `cloudbase.com` 之类的中转域（具体看申请页提示）。

### Q4: 个人主体能申请网站应用吗？

A: 可以，但**不支持个人订阅号 / 个人小程序能用的某些接口**。扫码登录是基础接口，**个人能申请**，但企业主体的权限更多。

### Q5: 申请审核期间，怎么测试？

A: 走 4.2 临时禁用。也可以用 ngrok 把 localhost 暴露成公网，配合一个临时域名测试（但不推荐，CloudBase 托管模式已经覆盖这个场景）。

---

## 7. 验证 checklist

- [ ] CloudBase 控制台启用「网站应用微信登录」
- [ ] AppID + AppSecret 回填 CloudBase 控制台
- [ ] yml `WECHAT.APP_ID` 填新 AppID
- [ ] yml `WECHAT.LOGIN_TYPE` = `open_platform`
- [ ] yml `WECHAT.SCOPE` = `snsapi_login`
- [ ] 重启服务
- [ ] 点击「微信登录」→ 显示二维码
- [ ] 用手机微信扫 → 同意授权
- [ ] 跳回 `localhost:3000/login` 且 URL 带 `code=xxx`
- [ ] 前端自动 `grantProviderToken` → 登录成功

---

## 8. 相关代码索引

| 功能 | 文件 | 行 |
|---|---|---|
| provider_id 选择逻辑 | `auth/tencent/cloudbase_auth.py` | 542-548 |
| 后端 IPC handler | `gui/ipc/w2p_handlers/cloudbase_handler.py` | 887-934 |
| 前端跳转拿 URL | `gui_v2/src/services/auth/cloudbaseAuth.ts` | 370-395 |
| 前端用 code 换 token | `gui_v2/src/pages/Login/LoginCN.tsx` | 117-122 |
| yml 配置 | `apps/cn/config/auth_config.yml` | 42-57 |
