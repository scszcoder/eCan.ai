# Avatar S3 上传功能实现指南

## 📋 功能概述

自定义 avatar 上传功能已完整实现，包括：

1. ✅ **本地文件保存**：上传的 avatar 保存到本地目录
2. ✅ **数据库记录**：avatar 信息保存到数据库
3. ✅ **S3 自动上传**：上传成功后自动同步到 S3（异步，不阻塞）
4. ✅ **Cognito 认证**：使用 Cognito ID Token 获取 AWS 临时凭证
5. ✅ **安全访问**：基于用户身份的 S3 访问控制

## 🔧 实现架构

### 1. 认证流程

```
用户登录 → Cognito User Pool → ID Token
                                    ↓
                        Cognito Identity Pool → AWS 临时凭证
                                                      ↓
                                                   S3 访问
```

### 2. 上传流程

```
前端上传 → avatar_handler.upload_avatar()
              ↓
          avatar_manager.upload_avatar()
              ↓
          本地保存 + 数据库保存
              ↓
          _upload_avatar_files_to_cloud() (后台异步)
              ↓
          AvatarCloudSync.sync_avatar_to_cloud()
              ↓
          S3StorageService.upload_file()
              ↓
          使用 Cognito 临时凭证上传到 S3
```

## 🔑 核心组件

### 1. AWS Credentials Provider

**文件**：`auth/aws_credentials_provider.py`

**功能**：
- 使用 Cognito ID Token 获取 AWS 临时凭证
- 自动缓存凭证（有效期内复用）
- 支持凭证过期自动刷新

**使用示例**：
```python
from auth.aws_credentials_provider import create_credentials_provider

provider = create_credentials_provider()
credentials = provider.get_credentials(id_token)

# credentials = {
#     'AccessKeyId': 'ASIA...',
#     'SecretKey': '...',
#     'SessionToken': '...',
#     'Expiration': datetime(...)
# }
```

### 2. S3 Storage Service

**文件**：`agent/avatar/cloud_storage.py`

**更新**：
- 支持使用 Cognito 临时凭证
- 自动从 AppContext 获取认证信息
- 优先使用 Cognito 凭证，降级到静态配置

**使用示例**：
```python
from agent.avatar.cloud_storage import create_s3_storage_service

# 自动使用 Cognito 凭证（如果用户已登录）
storage_service = create_s3_storage_service(use_cognito_credentials=True)

# 上传文件
success, url, error = storage_service.upload_file(
    local_path='/path/to/avatar.png',
    cloud_key='user123/avatars/abc123.png',
    content_type='image/png'
)
```

### 3. Avatar Handler

**文件**：`gui/ipc/w2p_handlers/avatar_handler.py`

**更新**：
- 在 `upload_avatar()` 成功后自动触发 S3 上传
- 后台异步上传，不阻塞用户操作
- 上传失败不影响本地保存

## ⚙️ 配置要求

### 1. Cognito 配置

**文件**：`auth/auth_config.yml`

```yaml
COGNITO:
  USER_POOL_ID: "us-east-1_uUmKJUfB3"
  CLIENT_ID: "5400r8q5p9gfdhln2feqcpljsh"
  IDENTITY_POOL_ID: "us-east-1:ccfa987f-2eee-45c9-ac59-b698f6cbda8e"  # ✅ 已配置
  REGION: "us-east-1"
  DOMAIN: "https://maipps.auth.us-east-1.amazoncognito.com"
```

### 2. S3 配置

**环境变量**（可选，如果使用 Cognito 凭证则不需要 ACCESS_KEY）：

```bash
# S3 Bucket 配置（必需）
export AVATAR_CLOUD_BUCKET=ecan-avatars
export AVATAR_CLOUD_REGION=us-east-1
export AVATAR_CLOUD_PATH_PREFIX=avatars/

# 静态凭证（可选，有 Cognito 凭证时不需要）
export AVATAR_CLOUD_ACCESS_KEY=your_access_key
export AVATAR_CLOUD_SECRET_KEY=your_secret_key

# CDN 配置（可选）
export AVATAR_CLOUD_CDN_DOMAIN=d1234567890.cloudfront.net
```

## 🔐 AWS 配置

### 1. S3 Bucket 设置

#### 创建 Bucket

```bash
aws s3 mb s3://ecan-avatars --region us-east-1
```

#### 配置 CORS

```json
[
    {
        "AllowedHeaders": ["*"],
        "AllowedMethods": ["GET", "PUT", "POST", "DELETE"],
        "AllowedOrigins": ["*"],
        "ExposeHeaders": ["ETag"]
    }
]
```

```bash
aws s3api put-bucket-cors \
    --bucket ecan-avatars \
    --cors-configuration file://cors-config.json
```

### 2. Cognito Identity Pool 配置

#### 认证角色 IAM Policy

为 Cognito Identity Pool 的认证角色附加以下策略：

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:DeleteObject"
            ],
            "Resource": [
                "arn:aws:s3:::ecan-avatars/avatars/${cognito-identity.amazonaws.com:sub}/*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::ecan-avatars"
            ],
            "Condition": {
                "StringLike": {
                    "s3:prefix": [
                        "avatars/${cognito-identity.amazonaws.com:sub}/*"
                    ]
                }
            }
        }
    ]
}
```

**说明**：
- `${cognito-identity.amazonaws.com:sub}` 会自动替换为用户的 Cognito Identity ID
- 每个用户只能访问自己的目录
- 支持上传、下载、删除操作

#### 应用策略

```bash
# 获取认证角色 ARN
aws cognito-identity get-identity-pool-roles \
    --identity-pool-id us-east-1:ccfa987f-2eee-45c9-ac59-b698f6cbda8e

# 创建策略
aws iam create-policy \
    --policy-name eCan-Avatar-S3-Access \
    --policy-document file://avatar-s3-policy.json

# 附加到角色
aws iam attach-role-policy \
    --role-name Cognito_eCanAuthRole \
    --policy-arn arn:aws:iam::ACCOUNT_ID:policy/eCan-Avatar-S3-Access
```

### 3. S3 目录结构

```
s3://ecan-avatars/
└── avatars/
    ├── {cognito_identity_id}/        # 用户私有目录
    │   ├── images/
    │   │   ├── {hash}_original.png
    │   │   └── {hash}_thumb.png
    │   └── videos/
    │       └── {hash}_video.mp4
    └── shared/                        # 共享资源（系统头像）
        └── system/
            ├── A001.png
            └── A001.mp4
```

## 🧪 测试

### 1. 测试 Cognito 凭证

```bash
# 设置测试 ID Token（从登录后获取）
export TEST_ID_TOKEN="eyJraWQ..."

# 运行测试
python tests/test_cognito_s3_upload.py
```

### 2. 测试 Avatar 上传

1. 启动应用并登录
2. 在前端上传自定义 avatar
3. 检查日志：

```
[AvatarManager] ✅ Avatar uploaded successfully: avatar_abc123
[AvatarHandler] Triggering S3 upload for avatar: avatar_abc123
[S3Storage] ✅ Using Cognito temporary credentials
[S3Storage] Uploaded: avatars/user123/images/abc123_original.png
[AvatarCloudSync] ✅ Avatar avatar_abc123 synced to cloud
```

4. 验证 S3：

```bash
aws s3 ls s3://ecan-avatars/avatars/ --recursive
```

## 📊 工作流程

### 用户上传 Avatar

1. **前端**：用户选择图片 → Base64 编码 → 调用 `avatar.upload_avatar` IPC
2. **后端**：
   - 验证图片格式和大小
   - 保存到本地 `{appdata}/resource/avatars/uploaded/`
   - 生成缩略图
   - 保存到数据库（DBAvatarResource）
   - **触发 S3 上传**（后台线程）
3. **S3 上传**：
   - 从 AppContext 获取 auth_manager
   - 使用 ID Token 获取 AWS 临时凭证
   - 创建 S3 客户端
   - 上传图片和缩略图到 S3
   - 更新数据库记录（cloud_image_url, cloud_synced）

### Agent 使用 Avatar

1. **创建/更新 Agent**：选择 avatar → 关联 avatar_resource_id
2. **保存 Agent**：
   - 保存 Agent 数据到数据库
   - **触发 S3 上传**（如果 avatar 还未上传）
   - 同步 Agent 数据到云端（AppSync）

## 🔍 故障排查

### 问题 1: S3 上传失败 "Access Denied"

**原因**：Cognito Identity Pool 角色权限不足

**解决**：
1. 检查 Identity Pool 认证角色的 IAM 策略
2. 确保策略包含 `s3:PutObject` 权限
3. 验证资源路径匹配：`arn:aws:s3:::ecan-avatars/avatars/${cognito-identity.amazonaws.com:sub}/*`

### 问题 2: 无法获取 Cognito 凭证

**原因**：ID Token 无效或过期

**解决**：
1. 检查用户是否已登录：`auth_manager.is_signed_in()`
2. 验证 ID Token：`auth_manager.get_tokens()`
3. 刷新 Token：`auth_manager.refresh_tokens()`

### 问题 3: S3 上传不触发

**原因**：配置缺失或 auth_manager 不可用

**解决**：
1. 检查环境变量：`AVATAR_CLOUD_BUCKET`
2. 检查 AppContext：`AppContext.get_auth_manager()`
3. 查看日志：搜索 `[S3Storage]` 和 `[AvatarCloudSync]`

## 📝 开发注意事项

### 1. 凭证缓存

- AWS 临时凭证有效期通常为 1 小时
- `AWSCredentialsProvider` 会自动缓存凭证
- 过期前 5 分钟会自动刷新

### 2. 异步上传

- S3 上传在后台线程执行，不阻塞 UI
- 上传失败不影响本地保存
- 可以稍后重新同步

### 3. 安全性

- 使用 Cognito 临时凭证，无需存储长期密钥
- 每个用户只能访问自己的 S3 目录
- 凭证自动过期，降低安全风险

### 4. 性能优化

- 凭证缓存减少 Cognito API 调用
- 异步上传不影响用户体验
- 可选的 CDN 加速下载

## 🚀 后续优化

1. **批量上传**：支持一次上传多个 avatar
2. **进度显示**：显示 S3 上传进度
3. **重试机制**：上传失败自动重试
4. **离线队列**：离线时缓存上传任务
5. **CDN 集成**：使用 CloudFront 加速访问

## 📚 相关文档

- [S3 Avatar Setup Guide](./S3_AVATAR_SETUP.md)
- [Cognito Authentication](../auth/README.md)
- [Avatar Manager API](../agent/avatar/README.md)
