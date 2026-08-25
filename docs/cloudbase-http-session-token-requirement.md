# 后端修改需求：统一 HTTP Session Token 机制

**文档版本**: v1.0
**创建日期**: 2026-08-21
**状态**: 待评审

---

## 1. 背景与问题描述

### 1.1 当前认证机制

CN 版本存在两套并存的登录认证机制，导致不同登录方式有不同的用户体验：


| 登录方式 | Token 类型             | HTTP 请求是否需要预热 | 登录后首次 API 调用 |
| ---- | -------------------- | ------------- | ------------ |
| 微信登录 | 30-day Session Token | ❌ 无需预热        | ✅ 立即成功       |
| 密码登录 | JWT Bearer Token     | ✅ 需要 30-60s   | ❌ 返回 401     |


### 1.2 问题影响

密码登录用户在登录后立即调用云端 API 时，会遇到以下问题：

```
登录成功 (T+0s)
    ↓
立即调用 queryAgents (T+0.5s)
    ↓
SCF Gateway 401: "Bearer token required" (Auth Cache 未同步)
    ↓
等待 15s 后重试 (T+15.5s)
    ↓
再次 401 (Cache 仍未同步)
    ↓
等待 15s 后重试 (T+30.5s)
    ↓
终于成功 或 继续失败 (取决于缓存同步时间)
```

**用户感知**：

- 前 30-60 秒看不到 agent 列表
- 看到 "account info unavailable" 警告
- 影响 Phase 3 初始化时间



### 1.3 根因分析

SCF Gateway 的 JWT 验证依赖腾讯云内部的分布式 Auth Cache：

- 新登录的 JWT Token 需要传播到所有边缘节点
- 传播过程需要 **30-60 秒**（实测数据）
- 这是腾讯云 SCF 的内部行为，客户端无法干预

微信登录通过提前签发 **Session Token** 解决了这个问题：

- Session Token 由 eCan 后端签发
- 不依赖腾讯云 Auth Cache
- 验证逻辑完全在 eCan 后端 (`auth.js resolveIdentity`)

---



## 2. 目标

为所有登录方式（密码、手机、邮箱）提供与微信登录相同的 Session Token 机制，消除预热延迟。

### 2.1 成功标准

- [ ] 密码/手机/邮箱登录成功后，HTTP API 调用立即成功（无 401）
- [ ] Session Token 有效期 30 天
- [ ] Token 刷新机制与现有微信登录保持一致
- [ ] 向后兼容：现有微信登录不受影响

---



## 3. 现有微信 Session Token 机制参考



### 3.1 微信登录流程

```
用户扫码 → CloudBase Auth → 获取 access_token
                    ↓
         registerWeChatSession (GraphQL mutation)
                    ↓
         返回 sessionToken (30天有效)
                    ↓
         客户端保存 sessionToken
                    ↓
         HTTP 请求使用 sessionToken 作为 Bearer Token
```



### 3.2 现有 GraphQL Mutation

`registerWeChatSession`

```graphql
input RegisterWeChatSessionInput {
    wxAccessToken: String!  # CloudBase Auth 签发的 access token
}

type RegisterWeChatSessionResult {
    sessionToken: String!   # eCan 签发的 session token
    expiresIn: Int!        # 有效期（秒）
}
```

`refreshWeChatToken`

```graphql
input RefreshWeChatTokenInput {
    sessionToken: String!   # 现有的 session token
}

type RefreshWeChatTokenResult {
    accessToken: String!    # 新的 access token
    expiresIn: Int!         # 新 token 有效期
    sessionToken: String!   # 新的 session token (rotated)
}
```



### 3.3 SCF Gateway 验证逻辑

`cloudbase-graphql/scf/auth.js` 中的 `resolveIdentity` 函数：

```javascript
async function resolveIdentity(headers) {
    const authHeader = headers['Authorization'] || '';
    const token = authHeader.replace('Bearer ', '');

    // 1. 优先验证 eCan Session Token（不依赖 JWT Cache）
    const sessionUser = await verifySessionToken(token);
    if (sessionUser) {
        return sessionUser;  // 立即返回，无延迟
    }

    // 2. 回退到 CloudBase JWT（保持现有逻辑）
    const jwtUser = await verifyIdToken(token);
    if (jwtUser) {
        return jwtUser;
    }

    throw new Error("Invalid or expired access token");
}
```



### 3.4 客户端调用位置

客户端在 `auth/auth_manager.py` 中调用：

```python
def _finalize_wechat_session_token(self) -> bool:
    """登录成功后调用，签发 session token"""
    access_token = self.tokens.get("AccessToken")
    ok, result = self._register_wechat_session(access_token)
    if ok and result.get("sessionToken"):
        self._save_wechat_session_token(result["sessionToken"])
        return True
    return False
```

HTTP 请求使用 session token：

```python
def _http_auth_header(token: str) -> str:
    if is_cn_app():
        session_tok = _get_wechat_http_session_token()
        if session_tok:
            return f"Bearer {session_tok}"  # 优先使用 session token
        return f"Bearer {jwt}"  # 回退到 JWT
    return token
```

---



## 4. 修改方案



### 4.1 方案概述

新增一个统一的 GraphQL mutation，为所有登录方式签发 HTTP Session Token：

```
登录成功 → mintHttpSessionToken (GraphQL mutation) → 返回 sessionToken
                ↓
        客户端保存 sessionToken
                ↓
        HTTP 请求使用 sessionToken
```



### 4.2 GraphQL Schema 修改



#### 4.2.1 新增 Input Type

```graphql
input MintHttpSessionTokenInput {
    """
    CloudBase Auth 签发的 access token
    格式: <tenant_id>/@@/<jwt> 或纯 jwt
    """
    accessToken: String!

    """
    登录类型，用于审计和日志
    可选值: "password" | "phone" | "email" | "oauth_google" | "oauth_github"
    """
    loginType: String!

    """
    用户标识，可选
    用于调试和日志
    """
    userIdentifier: String
}
```



#### 4.2.2 新增 Result Type

```graphql
type MintHttpSessionTokenResult {
    """
    新签发的 session token
    格式: JWT (HS256 签名)
    Claims:
      - sub: 用户 ID
      - loginType: 登录类型
      - type: "http_session" (用于区分)
      - iat: 签发时间
      - exp: 过期时间
    """
    sessionToken: String!

    """
    有效期（秒）
    固定值: 2592000 (30天)
    """
    expiresIn: Int!
}
```



#### 4.2.3 新增 Mutation

在 `Mutation` 类型中添加：

```graphql
type Mutation {
    # ... existing mutations ...

    """
    签发 HTTP Session Token

    用于所有非微信登录方式（密码、手机、邮箱、OAuth等）
    签发的 session token 可以直接用于 HTTP GraphQL 请求，
    无需等待 SCF Gateway Auth Cache 同步。

    该 mutation 由客户端在登录成功后调用。

    权限: 需要有效的 accessToken

    返回: sessionToken (30天有效)
    """
    mintHttpSessionToken(
        input: MintHttpSessionTokenInput!
    ): MintHttpSessionTokenResult
}
```



#### 4.2.4 Schema 授权

```graphql
# 使用 @aws_cognito_user_pools 授权（与现有 mutations 一致）
mintHttpSessionToken(
    input: MintHttpSessionTokenInput!
): MintHttpSessionTokenResult
    @aws_cognito_user_pools
```



### 4.3 Resolver 实现

在 CloudBase SCF 中新增/修改 resolver：

```javascript
// cloudbase-graphql/scf/mutations/mintHttpSessionToken.js

const jwt = require('jsonwebtoken');
const { SESSION_SECRET } = process.env;

async function mintHttpSessionToken(event) {
    const { arguments: { input } } = event;
    const { accessToken, loginType, userIdentifier } = input;

    try {
        // 1. 验证 accessToken 有效性
        const auth = CloudBase.auth();
        const verifiedToken = await auth.verifyIdToken(accessToken);
        // 注意: verifyIdToken 在 accessToken 有效时应该成功
        // 如果失败，说明 token 无效或已过期

        const uid = verifiedToken.uid || verifiedToken.sub;
        if (!uid) {
            throw new Error('Invalid token: missing user ID');
        }

        // 2. 生成 session token
        // 使用与服务端共享的密钥签名，与 registerWeChatSession 相同
        const sessionToken = jwt.sign(
            {
                sub: uid,
                loginType: loginType,
                type: 'http_session',      // 标识类型，用于 verifySessionToken 区分
                userIdentifier: userIdentifier || null,
                iat: Math.floor(Date.now() / 1000),
            },
            SESSION_SECRET,
            {
                expiresIn: '30d',
                algorithm: 'HS256'
            }
        );

        // 3. 可选：存储到数据库（用于服务端验证/审计）
        // 如果 verifySessionToken 依赖数据库查询，则需要存储
        // 如果 verifySessionToken 仅依赖 JWT 验证，则不需要存储
        await db.collection('http_sessions').upsert({
            _id: `http_${uid}_${Date.now()}`,
            uid: uid,
            token: sessionToken,
            loginType: loginType,
            userIdentifier: userIdentifier,
            type: 'http_session',
            createdAt: new Date(),
            expiresAt: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000),
            lastUsedAt: new Date()
        });

        return {
            sessionToken: sessionToken,
            expiresIn: 2592000  // 30天 = 30 * 24 * 60 * 60
        };

    } catch (error) {
        console.error('[mintHttpSessionToken] Error:', error);

        if (error.code === 'Invalid token' || error.message.includes('Invalid token')) {
            throw new Error('UNAUTHORIZED: Invalid access token');
        }

        throw new Error(`Failed to mint session token: ${error.message}`);
    }
}

module.exports = mintHttpSessionToken;
```



### 4.4 SCF Gateway Auth 修改

修改 `cloudbase-graphql/scf/auth.js` 中的 `resolveIdentity` 函数：

```javascript
// cloudbase-graphql/scf/auth.js

async function resolveIdentity(headers) {
    const authHeader = headers['Authorization'] || '';
    if (!authHeader.startsWith('Bearer ')) {
        throw new Error('Missing or invalid Authorization header');
    }

    const token = authHeader.replace('Bearer ', '');

    try {
        // 1. 验证 eCan HTTP Session Token（与微信 Session Token 相同验证逻辑）
        // Session Token 使用 HS256 签名，服务端可自行验证，无需 CloudBase Auth Cache
        const sessionUser = await verifySessionToken(token);
        if (sessionUser) {
            return sessionUser;  // 立即返回，无延迟
        }

        // 2. 验证 eCan WeChat Session Token（保持现有逻辑）
        // 这个 token 由 registerWeChatSession 签发
        const wechatUser = await verifyWeChatSessionToken(token);
        if (wechatUser) {
            return wechatUser;
        }

        // 3. 回退到 CloudBase JWT（保持现有逻辑）
        // 这是最后的选择，因为需要等待 Auth Cache 同步
        const jwtUser = await verifyIdToken(token);
        if (jwtUser) {
            return jwtUser;
        }

        throw new Error('Invalid or expired access token');

    } catch (error) {
        console.error('[resolveIdentity] Error:', error);
        throw error;
    }
}

/**
 * 验证 eCan HTTP Session Token
 * @param {string} token - JWT token
 * @returns {Object|null} - 返回用户信息或 null
 */
async function verifySessionToken(token) {
    try {
        const decoded = jwt.verify(token, SESSION_SECRET, {
            algorithms: ['HS256']
        });

        // 验证 token 类型
        if (decoded.type !== 'http_session') {
            return null;
        }

        // 验证是否过期（jwt.verify 已自动验证）

        return {
            uid: decoded.sub,
            loginType: decoded.loginType,
            tokenType: 'http_session'
        };

    } catch (error) {
        // JWT 验证失败，返回 null 继续尝试其他验证方式
        // 不抛出异常，因为可能是其他类型的 token
        return null;
    }
}

/**
 * 验证 eCan WeChat Session Token（保持现有实现）
 * @param {string} token - Token
 * @returns {Object|null} - 返回用户信息或 null
 */
async function verifyWeChatSessionToken(token) {
    // 现有实现保持不变
    // ...
}
```



### 4.5 Session Token 刷新机制

与微信登录保持一致：

```javascript
// 可选：新增 refreshHttpSessionToken mutation
// 或复用现有 refreshWeChatToken（如果后端逻辑支持）

input RefreshHttpSessionTokenInput {
    sessionToken: String!
}

type RefreshHttpSessionTokenResult {
    sessionToken: String!
    expiresIn: Int!
}
```

**注意**：Session Token 刷新的目的是延长有效期，不需要刷新 access token。
如果将来需要刷新功能，可以参考 `refreshWeChatToken` 的实现。

---



## 5. 客户端配套修改



### 5.1 Python 客户端

在 `auth/auth_manager.py` 中新增方法：

```python
def _mint_http_session_token(self) -> bool:
    """为非微信登录签发 HTTP Session Token

    在登录成功后调用，与 _finalize_wechat_session_token 类似，
    但适用于所有登录方式。
    """
    if self._is_wechat_flow():
        # 微信登录使用现有的 _finalize_wechat_session_token
        return self._finalize_wechat_session_token()

    access_token = self.tokens.get("AccessToken") or self.tokens.get("access_token")
    if not access_token:
        logger.warning("[AuthManager] No access token for HTTP session")
        return False

    login_type = self._get_login_type()  # "password" | "phone" | "email"

    mutation = """
        mutation MintHttpSessionToken($input: MintHttpSessionTokenInput!) {
            mintHttpSessionToken(input: $input) {
                sessionToken
                expiresIn
            }
        }
    """

    try:
        import requests as _req
        from agent.cloud_api.cloud_api import get_appsync_endpoint

        endpoint = get_appsync_endpoint()
        jwt = access_token.split('/@@/', 1)[-1] if '/@@/' in access_token else access_token
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {jwt}',
        }

        resp = _req.post(endpoint, json={
            'query': mutation,
            'variables': {
                'input': {
                    'accessToken': access_token,
                    'loginType': login_type,
                    'userIdentifier': self.current_user
                }
            }
        }, headers=headers, timeout=30)

        body = resp.json() if resp.text else {}
        data = (body.get('data') or {}).get('mintHttpSessionToken')

        if data and data.get('sessionToken'):
            # 保存 session token，使用与微信相同的存储机制
            self._save_http_session_token(data['sessionToken'])
            logger.info(
                f"[AuthManager] HTTP session token minted "
                f"(expires in {data.get('expiresIn', 0)}s)"
            )
            return True

        errors = body.get('errors', [])
        logger.warning(f"[_mint_http_session_token] GraphQL errors: {errors}")
        return False

    except Exception as e:
        logger.warning(f"[_mint_http_session_token] failed: {e}")
        return False


def _save_http_session_token(self, session_token: str) -> bool:
    """保存 HTTP Session Token（与微信 session token 使用相同的存储）"""
    username = self.current_user
    if not username:
        return False

    # 使用与微信相同的存储机制
    # 如果需要区分，可以修改 _save_wechat_session_token 支持 type 参数
    return self._save_wechat_session_token(session_token)


def _get_http_session_token(self) -> str:
    """获取 HTTP Session Token（与微信 session token 使用相同的存储）"""
    username = self.current_user or self._get_saved_username()
    if not username:
        return ""

    # 使用与微信相同的存储机制
    ok, tok = self._get_wechat_session_token()
    if ok and tok:
        return tok
    return ""
```



### 5.2 Token 优先级修改

修改 `_http_auth_header` 以支持新 token：

```python
def _http_auth_header(token: str) -> str:
    if not token:
        return ""

    if is_cn_app():
        # 1. 优先使用 HTTP Session Token（非微信登录）
        http_session_tok = _get_http_session_token()
        if http_session_tok:
            return f"Bearer {http_session_tok}"

        # 2. 回退到 WeChat Session Token（微信登录）
        session_tok = _get_wechat_http_session_token()
        if session_tok:
            return f"Bearer {session_tok}"

        # 3. 最后回退到 JWT（不推荐，会遇到缓存延迟）
        jwt = token.split('/@@/', 1)[-1] if '/@@/' in token else token
        return f"Bearer {jwt}"

    return token
```



### 5.3 调用时机

在所有登录成功路径中调用 `_mint_http_session_token`：

```python
# 场景1: 密码登录成功
def login(self, username, password, ...):
    # ... 登录逻辑 ...
    if success:
        self._mint_http_session_token()

# 场景2: 手机验证码登录成功
def sign_up_with_otp(self, ...):
    # ... 登录逻辑 ...
    if success:
        self._mint_http_session_token()

# 场景3: OAuth 登录成功
def google_login(self, ...):
    # ... 登录逻辑 ...
    if success:
        self._mint_http_session_token()
```

---



## 6. 安全考虑



### 6.1 Token 安全

- [x] Session Token 使用 HS256 签名，密钥仅服务端持有
- [x] Token 包含用户 ID 和登录类型，可审计
- [x] Token 有效期 30 天，过期后需要重新登录
- [x] Token 存储在 Keychain/文件系统中（与现有微信登录一致）



### 6.2 验证安全

- [x] `verifySessionToken` 验证 token 签名
- [x] `verifySessionToken` 验证 token 类型（`type === 'http_session'`）
- [x] `verifySessionToken` 验证 token 有效期
- [x] 验证失败时返回 null，尝试其他验证方式（不直接抛出异常）



### 6.3 权限控制

- [x] `mintHttpSessionToken` 需要有效的 access token 才能调用
- [x] 使用 `@aws_cognito_user_pools` 授权
- [x] 验证 access token 的用户 ID 与签发的 session token 绑定

---



## 7. 向后兼容



### 7.1 微信登录

- [x] 微信登录不受影响
- [x] 微信登录继续使用 `registerWeChatSession`
- [x] HTTP 请求继续使用微信 session token



### 7.2 现有 JWT 验证

- [x] 如果 session token 验证失败，fallback 到 JWT 验证
- [x] 保持现有 JWT 验证逻辑不变



### 7.3 旧版本客户端

- [x] 新 mutation 仅在新版本客户端中调用
- [x] 旧版本客户端继续使用现有 JWT 验证（有缓存延迟，但功能正常）

---



## 8. 测试计划



### 8.1 单元测试

- [ ] 测试 `mintHttpSessionToken` mutation 签名
- [ ] 测试 `verifySessionToken` 验证逻辑
- [ ] 测试 token 过期验证



### 8.2 集成测试

- [ ] 密码登录 → 调用 mutation → HTTP API 立即成功
- [ ] 手机登录 → 调用 mutation → HTTP API 立即成功
- [ ] Session token 过期 → 降级到 JWT 验证
- [ ] 微信登录 → 不调用新 mutation → 继续使用现有机制



### 8.3 性能测试

- [ ] 登录后立即调用 queryAgents（应 < 1s 成功）
- [ ] 与微信登录性能对比

---



## 9. 部署计划



### 9.1 后端部署顺序

1. 部署 GraphQL Schema 更新（新增 mutation）
2. 部署 Resolver 实现
3. 部署 SCF Gateway Auth 修改
4. 验证所有登录方式



### 9.2 客户端部署

1. 先部署后端
2. 后端验证通过后，部署客户端更新
3. 客户端更新应向后兼容



### 9.3 回滚计划

- 如果新 mutation 调用失败，客户端应 fallback 到现有 JWT 验证
- SCF Gateway Auth 修改应保持 JWT 验证路径不变

---



## 10. 附录



### 10.1 相关文档

- [ ] 腾讯云 SCF 认证文档
- [ ] CloudBase Auth 文档
- [ ] 现有 `registerWeChatSession` 实现



### 10.2 联系人

- **前端负责人**: 待定
- **后端负责人**: 待定
- **测试负责人**: 待定



### 10.3 变更历史


| 版本   | 日期         | 作者     | 描述  |
| ---- | ---------- | ------ | --- |
| v1.0 | 2026-08-21 | Claude | 初稿  |


---



## 11. 问题与解答



### Q1: 为什么不直接复用 `registerWeChatSession`？

A: `registerWeChatSession` 是专门为微信登录设计的：

- 输入参数 `wxAccessToken` 暗示专属性
- 微信登录有特殊的 token 交换流程
- 保持职责分离，便于审计和维护



### Q2: Session Token 存放在哪里？

A: 与微信 session token 使用相同的存储机制：

- Keychain（优先）
- 文件系统 fallback
- 使用相同的 keyring service 和 key



### Q3: 如果后端修改失败怎么办？

A: 客户端需要处理两种情况：

1. mutation 调用成功 → 使用 session token
2. mutation 调用失败 → fallback 到 JWT（有缓存延迟，但功能正常）



### Q4: 为什么需要存储到数据库？

A: 这取决于 `verifySessionToken` 的实现方式：

- **仅 JWT 验证**：不需要存储，jwt.verify 可自行验证
- **数据库查询**：需要存储，用于查询用户信息

建议使用纯 JWT 验证，避免额外的数据库查询。

---

**文档结束**