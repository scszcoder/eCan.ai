# 现有微信 Session Token 机制参考文档

**文档版本**: v1.0
**创建日期**: 2026-08-21
**用途**: 为实现统一的 HTTP Session Token 机制提供参考

---

## 1. 概述

微信登录使用一套独立的 Session Token 机制，用于解决 SCF Gateway JWT Auth Cache 延迟问题。该机制包含：

1. **Session Token 签发** (`registerWeChatSession` mutation)
2. **Session Token 刷新** (`refreshWeChatToken` mutation)
3. **Token 验证** (`verifySessionToken` in `auth.js`)
4. **客户端存储** (Keychain + 文件系统)

---

## 2. 流程图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              微信登录流程                                      │
└─────────────────────────────────────────────────────────────────────────────┘

    用户扫码
        │
        ▼
┌─────────────────┐
│  CloudBase Auth  │
│  (微信 OAuth)    │
└────────┬────────┘
         │ access_token + openid
         ▼
┌─────────────────────────────────────────────────────────────┐
│  _finalize_wechat_session_token()                          │
│  调用 registerWeChatSession mutation                        │
└────────────────────────┬──────────────────────────────────┘
                         │ wxAccessToken
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  GraphQL Resolver: registerWeChatSession                    │
│  后端验证 wxAccessToken，签发 sessionToken                    │
└────────────────────────┬──────────────────────────────────┘
                         │ { sessionToken, expiresIn }
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  客户端保存 sessionToken                                    │
│  - Keychain: ecan_wechat_session_<username>                 │
│  - 文件: ~/.ecan/data/ecnst_<base64(username)>              │
└────────────────────────┬──────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  HTTP 请求使用 sessionToken                                  │
│  Authorization: Bearer <sessionToken>                      │
└────────────────────────┬──────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  SCF Gateway: auth.js resolveIdentity()                     │
│  1. verifySessionToken(sessionToken) → 立即返回用户          │
│  2. verifyWeChatSessionToken(sessionToken) → 立即返回用户    │
│  3. verifyIdToken(jwt) → 可能需要等待 Auth Cache             │
└─────────────────────────────────────────────────────────────┘

───────────────────────────────────────────────────────────────

┌─────────────────────────────────────────────────────────────────────────────┐
│                              Token 刷新流程                                  │
└─────────────────────────────────────────────────────────────────────────────┘

    access_token 即将过期
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  AuthManager._wechat_refresh_loop()                          │
│  或 SessionSupervisor 检测到 401                             │
└────────────────────────┬──────────────────────────────────┘
                         │ sessionToken
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  调用 refreshWeChatToken mutation                            │
│  输入: { sessionToken: "..." }                              │
└────────────────────────┬──────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  GraphQL Resolver: refreshWeChatToken                        │
│  验证 sessionToken，返回新的 access_token                     │
│  可能同时返回 rotated sessionToken                          │
└────────────────────────┬──────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  客户端更新:                                                 │
│  - self.tokens['AccessToken'] = new_access_token            │
│  - 如果返回了新 sessionToken，保存                           │
│  - 调用 sup.notify_token_installed()                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. GraphQL Mutations

### 3.1 registerWeChatSession

**目的**: 在微信登录成功后签发 session token

**客户端调用**:
```python
# auth/auth_manager.py

mutation = """
    mutation RegisterWeChatSession($input: RegisterWeChatSessionInput!) {
        registerWeChatSession(input: $input) {
            sessionToken
            expiresIn
        }
    }
"""

variables = {
    'input': {
        'wxAccessToken': access_token  # CloudBase 签发的 access token
    }
}
```

**服务端返回**:
```json
{
    "data": {
        "registerWeChatSession": {
            "sessionToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "expiresIn": 2592000
        }
    }
}
```

### 3.2 refreshWeChatToken

**目的**: 刷新 access token（使用 session token 作为凭证）

**客户端调用**:
```python
# auth/auth_manager.py

mutation = """
    mutation RefreshWeChatToken($input: RefreshWeChatTokenInput!) {
        refreshWeChatToken(input: $input) {
            accessToken
            expiresIn
            sessionToken
        }
    }
"""

variables = {
    'input': {
        'sessionToken': session_token  # 现有的 session token
    }
}
```

**服务端返回**:
```json
{
    "data": {
        "refreshWeChatToken": {
            "accessToken": "new_access_token...",
            "expiresIn": 3600,
            "sessionToken": "rotated_new_session_token..."
        }
    }
}
```

**注意**: 服务端会轮换 session token（rotation），客户端必须保存新的 session token。

---

## 4. 客户端实现

### 4.1 签发时机

在登录成功后立即调用：

```python
# auth/auth_manager.py

def complete_login_from_provider(self, tokens, user_profile, role, ...):
    # ... 登录成功后的处理 ...
    if success:
        # 签发 session token
        self._finalize_wechat_session_token()

def wechat_login(self, ...):
    # ... 登录成功后的处理 ...
    if success:
        # 签发 session token
        self._finalize_wechat_session_token()
```

### 4.2 _finalize_wechat_session_token

```python
def _finalize_wechat_session_token(self) -> bool:
    """签发并保存微信 session token"""
    if not self._is_wechat_flow():
        return True  # 非微信登录不执行

    access_token = self.tokens.get("AccessToken") or self.tokens.get("access_token")
    ok, result = self._register_wechat_session(access_token)

    if ok and isinstance(result, dict):
        st = result.get("sessionToken") or ""
        if st:
            self._save_wechat_session_token(st)
            logger.info(f"[AuthManager] Session token registered for {self.current_user}")
            return True

    return False
```

### 4.3 _register_wechat_session

```python
def _register_wechat_session(self, access_token: str) -> tuple[bool, Any]:
    """调用 registerWeChatSession mutation"""

    mutation = """
        mutation RegisterWeChatSession($input: RegisterWeChatSessionInput!) {
            registerWeChatSession(input: $input) {
                sessionToken
                expiresIn
            }
        }
    """

    try:
        import requests as _req
        from agent.cloud_api.cloud_api import get_appsync_endpoint

        endpoint = get_appsync_endpoint()
        # 提取纯 JWT（如果有 /@@/ 前缀）
        jwt = access_token.split('/@@/', 1)[-1] if '/@@/' in access_token else access_token

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {jwt}',  # 使用 JWT 作为 Authorization
        }

        resp = _req.post(endpoint, json={
            'query': mutation,
            'variables': {
                'input': {'wxAccessToken': access_token}
            }
        }, headers=headers, timeout=30)

        body = resp.json() if resp.text else {}
        data = (body.get('data') or {}).get('registerWeChatSession')

        if data:
            return True, data

        errors = body.get('errors', [])
        logger.warning(f"[_register_wechat_session] GraphQL errors: {errors}")
        return False, errors

    except Exception as e:
        logger.warning(f"[_register_wechat_session] failed: {e}")
        return False, str(e)
```

### 4.4 Token 存储

#### 4.4.1 Keyring 存储

```python
_WECHAT_SESSION_TOKEN_SERVICE = "ecan_wechat_session"
_WECHAT_SESSION_TOKEN_FILE_PREFIX = "ecnst"

def _save_wechat_session_token(self, session_token: str) -> bool:
    """保存 session token 到 Keychain"""
    username = self.current_user
    if not username:
        return False

    safe = self._sanitize_username_for_keyring(username)

    # Keyring
    try:
        keyring.set_password(
            self._WECHAT_SESSION_TOKEN_SERVICE,
            safe,
            session_token
        )
    except Exception:
        pass

    # 文件 fallback
    safe_file = base64.b64encode(username.encode('utf-8')).decode('ascii')
    path = os.path.join(self.ecb_data_homepath, f"{self._WECHAT_SESSION_TOKEN_FILE_PREFIX}_{safe_file}")
    try:
        with open(path, 'w') as f:
            f.write(session_token)
    except Exception as e:
        logger.warning(f"[_save_wechat_session_token] file fallback failed: {e}")

    return True
```

#### 4.4.2 Token 读取

```python
def _get_wechat_session_token(self) -> tuple[bool, str]:
    """从 Keychain 读取 session token"""
    username = self.current_user or self._get_saved_username()
    if not username:
        return False, "no username"

    safe = self._sanitize_username_for_keyring(username)

    # Keyring first
    try:
        token = keyring.get_password(self._WECHAT_SESSION_TOKEN_SERVICE, safe)
        if token and len(token.strip()) > 10:
            return True, token
    except Exception:
        pass

    # File fallback
    return self._get_wechat_session_token_file(username)

def _get_wechat_session_token_file(self, username: str) -> tuple[bool, str]:
    """从文件读取 session token"""
    safe = base64.b64encode(username.encode('utf-8')).decode('ascii')
    path = os.path.join(self.ecb_data_homepath, f"{self._WECHAT_SESSION_TOKEN_FILE_PREFIX}_{safe}")

    if not os.path.exists(path):
        return False, "no file"

    try:
        with open(path, 'r') as f:
            return True, f.read().strip()
    except Exception:
        return False, "read error"
```

---

## 5. HTTP 认证

### 5.1 _http_auth_header

```python
def _http_auth_header(token: str) -> str:
    """
    CN: 优先使用 30-day session token，否则用 JWT

    Session token 是 eCan 自签的 HS256 token，SCF Gateway 的
    resolveIdentity 可以自行验证，不依赖 CloudBase Auth Cache。
    JWT 需要等待 Auth Cache 同步。
    """
    if not token:
        return ""

    if is_cn_app():
        # 优先使用 session token
        session_tok = _get_wechat_http_session_token()
        if session_tok:
            return f"Bearer {session_tok}"

        # 回退到 JWT
        jwt = token.split('/@@/', 1)[-1] if '/@@/' in token else token
        return f"Bearer {jwt}"

    return token
```

### 5.2 _get_wechat_http_session_token

```python
_wechat_session_auth_mgr = None
_wechat_session_token_announced = False

def _get_wechat_http_session_token() -> str:
    """
    返回 30-day WeChat session token

    这个函数会创建新的 AuthManager 实例来读取 saved_username，
    因为缓存的实例的 current_user 可能在切换账户后过期。
    """
    global _wechat_session_auth_mgr, _wechat_session_token_announced

    try:
        if _wechat_session_auth_mgr is None:
            from auth.auth_manager import AuthManager
            _wechat_session_auth_mgr = AuthManager()

        # 每次都从文件重新读取 username，避免缓存问题
        saved_user = _wechat_session_auth_mgr._get_saved_username()
        if saved_user:
            _wechat_session_auth_mgr.current_user = saved_user

        ok, tok = _wechat_session_auth_mgr._get_wechat_session_token()
        if ok and tok:
            if not _wechat_session_token_announced:
                _wechat_session_token_announced = True
                logger_helper.info("[AppSync] Using WeChat 30-day session token for CN HTTP auth")
            return tok

    except Exception as e:
        logger_helper.debug(f"[AppSync] WeChat session token unavailable: {e}")

    return ""
```

---

## 6. SCF Gateway 验证

### 6.1 auth.js resolveIdentity

```javascript
async function resolveIdentity(headers) {
    const authHeader = headers['Authorization'] || '';
    const token = authHeader.replace('Bearer ', '');

    // 1. 验证 eCan Session Token（微信 session token）
    // 不依赖 CloudBase Auth Cache，直接验证 JWT 签名
    const sessionUser = await verifySessionToken(token);
    if (sessionUser) {
        return sessionUser;  // 立即返回
    }

    // 2. 验证 CloudBase JWT（最后的选择）
    // 需要等待 Auth Cache 同步
    const jwtUser = await verifyIdToken(token);
    if (jwtUser) {
        return jwtUser;
    }

    throw new Error('Invalid or expired access token');
}

async function verifySessionToken(token) {
    try {
        // 使用 HS256 验证 eCan 自签的 JWT
        const decoded = jwt.verify(token, SESSION_SECRET, {
            algorithms: ['HS256']
        });

        // 验证 token 类型
        if (decoded.type !== 'wechat_session') {
            return null;
        }

        return {
            uid: decoded.sub,
            openid: decoded.openid,
            tokenType: 'wechat_session'
        };

    } catch (error) {
        return null;  // 验证失败，继续尝试其他验证方式
    }
}

async function verifyIdToken(token) {
    // 验证 CloudBase JWT（依赖 Auth Cache）
    // 实现取决于 CloudBase SDK
}
```

---

## 7. Token 刷新机制

### 7.1 刷新循环

```python
def _wechat_refresh_loop(self):
    """后台刷新 WeChat access token"""
    while not self._stop_refresh:
        try:
            # 等待到 token 即将过期
            wait_seconds = self._get_refresh_interval()
            time.sleep(wait_seconds)

            # 获取 session token
            ok, session_tok = self._get_wechat_session_token()
            if not ok:
                logger.warning("[AuthManager] No session token - stopping refresh")
                break

            # 调用 refreshWeChatToken
            ok2, result = self._refresh_wechat_token(session_tok)

            if ok2:
                # 更新 access token
                self.tokens['AccessToken'] = result.get('accessToken')
                self.tokens['access_token'] = result.get('accessToken')

                # 保存 rotated session token
                if result.get('sessionToken'):
                    self._save_wechat_session_token(result['sessionToken'])

                # 通知 supervisor
                sup.notify_token_installed()
            else:
                # 处理失败
                if result.get('code') == 'SESSION_EXPIRED':
                    break  # 需要重新扫码

        except Exception as e:
            logger.error(f"[AuthManager] Refresh loop error: {e}")
            time.sleep(60)  # 等待后重试
```

### 7.2 SessionSupervisor 的 401 处理

```python
def _handle_401_from_cloud(self, endpoint: str, exp: float) -> None:
    """
    处理 SCF Gateway 返回的 401

    策略:
    1. 如果是新鲜 token (< 60s)，认为是 Cache 延迟，不处理
    2. 否则尝试 session token 刷新
    3. 如果刷新失败，emit session_expired
    """
    FRESH_TOKEN_GRACE_SECONDS = 60
    wall_now = time.time()

    token_age = wall_now - self._last_token_installed_at
    remaining = exp - wall_now

    # 情况1: 新鲜 token → 认为是 Cache 延迟
    if token_age < FRESH_TOKEN_GRACE_SECONDS and remaining > FRESH_TOKEN_GRACE_SECONDS:
        logger.info("[SessionSupervisor] 401 for fresh token - likely cache lag")
        # 等待后重试，不 emit expired
        return

    # 情况2: 尝试 session token 刷新
    ok, session_tok = self._get_wechat_session_token()
    if ok:
        ok2, result = self._refresh_wechat_token(session_tok)
        if ok2:
            self._install_token(result.get('accessToken'))
            return

    # 情况3: 刷新失败 → emit expired
    self._emit_session_expired()
```

---

## 8. 关键设计决策

### 8.1 为什么需要 Session Token？

| 方案 | 优点 | 缺点 |
|-----|------|------|
| 等待 JWT Cache 同步 | 无需额外实现 | 需要 30-60s 预热 |
| Session Token | 立即生效 | 需要额外实现和存储 |

### 8.2 为什么使用 HS256？

- JWT 有多种签名算法（HS256, RS256, ES256）
- HS256 使用对称密钥，签名和验证使用相同密钥
- 适合服务端内部使用，无需公钥基础设施
- 腾讯云 SCF 可以持有密钥进行验证

### 8.3 Session Token 存储位置

| 存储 | 优点 | 缺点 |
|-----|------|------|
| Keychain | 安全，系统级加密 | 跨平台实现不同 |
| 文件系统 | 简单，跨平台一致 | 安全性较低 |

微信登录使用 Keychain + 文件 fallback，平衡安全性和兼容性。

### 8.4 Token 轮换（Rotation）

`refreshWeChatToken` 可能返回新的 session token，客户端必须保存新的 token。
这提供了额外的安全性：即使旧 token 泄露，过期后自动失效。

---

## 9. 复用建议

如果要实现统一的 HTTP Session Token 机制，建议：

1. **复用现有存储机制** - 使用相同的 Keychain service 和文件路径
2. **复用现有验证逻辑** - `verifySessionToken` 可以同时验证两种 session token
3. **新增 mutation** - 复用 `registerWeChatSession` 的模式，但使用通用输入
4. **Token 类型区分** - 在 JWT payload 中添加 `type` 字段区分来源

---

## 10. 相关代码位置

| 文件 | 行号 | 功能 |
|-----|------|------|
| `auth/auth_manager.py` | 2515-2540 | `_get_wechat_session_token` |
| `auth/auth_manager.py` | 2542-2561 | `_save_wechat_session_token` |
| `auth/auth_manager.py` | 2611-2645 | `_finalize_wechat_session_token` |
| `auth/auth_manager.py` | 2647-2678 | `_register_wechat_session` |
| `auth/auth_manager.py` | 2685-2732 | `_refresh_wechat_token` |
| `agent/cloud_api/cloud_api.py` | 1378-1405 | `_get_wechat_http_session_token` |
| `agent/cloud_api/cloud_api.py` | 1422-1443 | `_http_auth_header` |

---

**文档结束**
