# Google OAuth + AWS Cognito 完整配置指南

## 概述

实现 Google 账号授权登录并使用 AWS Cognito API 需要配置以下组件：
1. Google Cloud Platform OAuth 2.0 客户端
2. AWS Cognito User Pool（用户池）
3. AWS Cognito Identity Pool（身份池）
4. IAM 角色和权限
5. 应用配置文件

---

## 📋 配置文件清单

### 1. 应用配置文件

#### `auth/auth_config.yml`
```yaml
# Authentication Configuration
# Centralized configuration for all authentication providers

COGNITO:
  USER_POOL_ID: "us-east-1_uUmKJUfB3"  # 从 AWS Cognito User Pool 获取
  CLIENT_ID: "5400r8q5p9gfdhln2feqcpljsh"  # 从 User Pool App Client 获取
  CLIENT_SECRET: ""  # 如果 App Client 启用了 Client Secret，填入这里
  IDENTITY_POOL_ID: "us-east-1:8d4a089c-ffbc-4110-a9f2-2b11630b16ef"  # 从 Identity Pool 获取
  REGION: "us-east-1"  # AWS 区域
  
  # Google Identity Provider Configuration for Cognito
  GOOGLE_PROVIDER:
    PROVIDER_NAME: "accounts.google.com"  # 固定值
    CLIENT_ID: "363461562508-a5kdd4nlhgke3b2b96pqkqn3isn19r2t.apps.googleusercontent.com"  # 必须与 GOOGLE.CLIENT_ID 一致

# Google OAuth Configuration
GOOGLE:
  CLIENT_ID: "363461562508-a5kdd4nlhgke3b2b96pqkqn3isn19r2t.apps.googleusercontent.com"  # 从 Google Cloud Console 获取
  CLIENT_SECRET: "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"  # 从 Google Cloud Console 获取
  SCOPES: ["openid", "email", "profile"]  # OAuth 权限范围
  REDIRECT_URI_BASE: "http://127.0.0.1"  # 本地回调地址
  CALLBACK_PORT_RANGE: [8080, 8090]  # 回调端口范围
```

### 2. 环境变量（可选）
```bash
# .env 文件或系统环境变量
AWS_COGNITO_USER_POOL_ID=us-east-1_uUmKJUfB3
AWS_COGNITO_CLIENT_ID=5400r8q5p9gfdhln2feqcpljsh
AWS_COGNITO_IDENTITY_POOL_ID=us-east-1:8d4a089c-ffbc-4110-a9f2-2b11630b16ef
AWS_REGION=us-east-1
GOOGLE_CLIENT_ID=363461562508-a5kdd4nlhgke3b2b96pqkqn3isn19r2t.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=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
```

---

## 🔧 AWS 平台配置步骤

### 步骤 1: 创建 Cognito User Pool

1. **登录 AWS 控制台** → **Cognito** → **User pools**
2. **点击 "Create user pool"**
3. **配置用户池**：
   ```
   Pool name: ecbot-user-pool
   Username attributes: Email
   Password policy: 根据需要设置
   MFA: 可选
   ```
4. **配置 App client**：
   ```
   App client name: ecbot-app-client
   Generate client secret: 根据需要选择
   Auth flows: ALLOW_USER_SRP_AUTH, ALLOW_REFRESH_TOKEN_AUTH
   ```
5. **配置 Identity providers**：
   - 点击 "Add identity provider"
   - 选择 "Google"
   - 输入：
     ```
     Google app ID: 363461562508-a5kdd4nlhgke3b2b96pqkqn3isn19r2t.apps.googleusercontent.com
     Google app secret: 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
     Authorized scopes: openid email profile
     ```
6. **配置 Attribute mapping**：
   ```
   Google attribute → User pool attribute
   email → email
   name → name
   given_name → given_name
   family_name → family_name
   ```
7. **配置 Hosted UI**（推荐）：
   ```
   Domain name: ecbot-auth-domain
   Callback URLs: http://localhost:3000/callback
   Sign out URLs: http://localhost:3000/logout
   OAuth 2.0 grant types: Authorization code grant
   OAuth 2.0 scopes: openid, email, profile
   ```

### 步骤 2: 创建 Cognito Identity Pool

1. **Cognito** → **Identity pools** → **Create identity pool**
2. **基本配置**：
   ```
   Identity pool name: ecbot-identity-pool
   Enable access to unauthenticated identities: 根据需要选择
   ```
3. **Authentication providers**：
   - **User pool**: 选择上面创建的 User Pool
   - **Google+**: 
     ```
     Google+ app ID: 363461562508-a5kdd4nlhgke3b2b96pqkqn3isn19r2t.apps.googleusercontent.com
     ```

### 步骤 3: 创建 IAM 角色

#### 3.1 创建 Authenticated Role

1. **IAM** → **Roles** → **Create role**
2. **Trusted entity type**: Web identity
3. **Identity provider**: Cognito
4. **Audience**: 选择你的 Identity Pool ID
5. **角色名称**: `Cognito_ecbot_Auth_Role`
6. **信任策略**：
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Principal": {
           "Federated": "cognito-identity.amazonaws.com"
         },
         "Action": "sts:AssumeRoleWithWebIdentity",
         "Condition": {
           "StringEquals": {
             "cognito-identity.amazonaws.com:aud": "us-east-1:8d4a089c-ffbc-4110-a9f2-2b11630b16ef"
           },
           "ForAnyValue:StringLike": {
             "cognito-identity.amazonaws.com:amr": "authenticated"
           }
         }
       }
     ]
   }
   ```
7. **权限策略**：
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "cognito-identity:GetCredentialsForIdentity",
           "cognito-identity:GetId",
           "cognito-sync:*",
           "mobileanalytics:PutEvents"
         ],
         "Resource": "*"
       }
     ]
   }
   ```

#### 3.2 分配角色到 Identity Pool

1. **返回 Identity Pool** → **IAM roles**
2. **Authenticated role**: 选择 `Cognito_ecbot_Auth_Role`
3. **保存更改**

---

## 🌐 Google Cloud Platform 配置

### 步骤 1: 创建 OAuth 2.0 客户端

1. **登录 Google Cloud Console**
2. **选择项目** 或 **创建新项目**
3. **APIs & Services** → **Credentials**
4. **Create Credentials** → **OAuth 2.0 Client IDs**
5. **Application type**: Web application
6. **Name**: ecbot-oauth-client
7. **Authorized redirect URIs**:
   ```
   http://127.0.0.1:8080/callback
   http://127.0.0.1:8081/callback
   http://127.0.0.1:8082/callback
   http://localhost:3000/callback  # 如果使用 Hosted UI
   ```
8. **保存并获取**:
   - Client ID: `363461562508-a5kdd4nlhgke3b2b96pqkqn3isn19r2t.apps.googleusercontent.com`
   - Client Secret: `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`

### 步骤 2: 启用必要的 API

1. **APIs & Services** → **Library**
2. **搜索并启用**:
   - Google+ API
   - Google Identity and Access Management (IAM) API
   - Google Cloud Resource Manager API

---

## 🔍 配置验证清单

### ✅ Google Cloud Platform
- [ ] OAuth 2.0 客户端已创建
- [ ] Client ID 和 Client Secret 已获取
- [ ] 重定向 URI 已正确配置
- [ ] 必要的 API 已启用

### ✅ AWS Cognito User Pool
- [ ] User Pool 已创建
- [ ] App Client 已配置
- [ ] Google Identity Provider 已添加
- [ ] Attribute Mapping 已配置
- [ ] Hosted UI 已配置（推荐）

### ✅ AWS Cognito Identity Pool
- [ ] Identity Pool 已创建
- [ ] User Pool Provider 已配置
- [ ] Google+ Provider 已配置
- [ ] IAM 角色已分配

### ✅ IAM 角色
- [ ] Authenticated Role 已创建
- [ ] 信任策略正确（包含正确的 Identity Pool ID）
- [ ] 权限策略包含必要的 Cognito 权限
- [ ] 角色已分配给 Identity Pool

### ✅ 应用配置
- [ ] `auth_config.yml` 所有字段已正确填写
- [ ] Google Client ID 在所有配置中保持一致
- [ ] Identity Pool ID 和 User Pool ID 正确

---

## 🚀 测试验证

### 1. 基本连接测试
```python
# 运行测试脚本
python3 auth/debug_cognito_detailed.py
```

### 2. 完整登录流程测试
```python
# 运行应用并测试 Google 登录
python3 main.py
```

### 3. 预期成功日志
```
✅ Google OAuth authentication successful
✅ Got identity ID: us-east-1:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
✅ AWS credentials obtained successfully
✅ Cognito authentication successful
```

---

## 🔧 常见问题排查

### 问题 1: "Token is not from a supported provider"
**原因**: Identity Pool 中 Google Provider 未配置或 Client ID 不匹配
**解决**: 检查 Identity Pool → Authentication providers → Google+

### 问题 2: "Invalid identity pool configuration"
**原因**: IAM 角色未配置或信任策略错误
**解决**: 检查 Identity Pool → IAM roles → Authenticated role

### 问题 3: "Access denied"
**原因**: IAM 角色权限不足
**解决**: 检查角色权限策略，确保包含 `cognito-identity:GetCredentialsForIdentity`

### 问题 4: Google OAuth 回调失败
**原因**: 重定向 URI 配置错误
**解决**: 检查 Google Cloud Console 中的 Authorized redirect URIs

---

## 📚 相关文档

- [AWS Cognito User Pools](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-identity-pools.html)
- [AWS Cognito Identity Pools](https://docs.aws.amazon.com/cognito/latest/developerguide/identity-pools.html)
- [Google OAuth 2.0](https://developers.google.com/identity/protocols/oauth2)
- [AWS IAM Roles](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles.html)

---

## 🎯 推荐架构

**生产环境推荐使用 Cognito Hosted UI 方案**：
1. 用户点击 Google 登录
2. 重定向到 Cognito Hosted UI
3. 用户在 Google 完成认证
4. 返回 Cognito User Pool ID Token
5. 使用 User Pool Token 获取 Identity Pool 临时凭证
6. 使用临时凭证调用 AWS API

这种方案更安全、更稳定，减少了客户端直接处理 OAuth 的复杂性。
