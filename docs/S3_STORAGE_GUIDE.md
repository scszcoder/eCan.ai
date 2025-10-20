# S3 云存储完整指南

> eCan.ai 项目的 S3 云存储架构、实现和使用文档

---

## 📋 核心问题解答

### 1. 文件用户标识

**✅ 有两种方式标识**：

1. **S3 路径隔离**：`avatars/{owner}/{file_category}s/{file_hash}.{ext}`
2. **S3 元数据**：`metadata = {'owner': 'user@example.com', ...}`

**查询方式**：
- AWS Console：直接浏览 `avatars/{username}/`
- 编程查询：使用 S3 prefix 查询
- DynamoDB 索引：毫秒级复杂查询（推荐生产环境）

### 2. 统一标准上传工具

**✅ 已创建**：`/agent/cloud/standard_s3_uploader.py`

**核心类**：
- `S3PathGenerator`：标准化路径生成器
- `StandardS3Uploader`：统一上传/下载/删除工具

**使用示例**：
```python
from agent.cloud import create_standard_uploader

uploader = create_standard_uploader()

# 上传
success, url, error = uploader.upload(
    local_path='/path/to/file.png',
    owner='user@example.com',
    resource_type='avatar',
    resource_id='avatar_123',
    file_category='image',
    file_hash='abc123'
)

# 下载
success, error = uploader.download(
    owner='user@example.com',
    resource_type='avatar',
    file_category='image',
    file_hash='abc123',
    file_ext='.png',
    local_path='/tmp/file.png'
)

# 删除
success, error = uploader.delete(
    owner='user@example.com',
    resource_type='avatar',
    file_category='image',
    file_hash='abc123',
    file_ext='.png'
)
```

### 3. S3 地址定义和生成

**标准路径结构**：
```
{resource_type}s/{owner}/{file_category}s/{file_hash}.{ext}
```

**示例**：
```
avatars/user@example.com/images/abc123.png
avatars/user@example.com/videos/xyz789.mp4
documents/user@example.com/pdfs/2025-01-19/report.pdf
```

**路径生成**：
```python
from agent.cloud import S3PathGenerator

path = S3PathGenerator.generate_path(
    resource_type='avatar',
    owner='user@example.com',
    file_category='image',
    file_hash='abc123',
    file_ext='.png'
)
# 结果: avatars/user@example.com/images/abc123.png
```

### 4. AWSCredentialsProvider 的必要性

**核心区别**：认证 vs 授权

| 功能 | auth_manager | AWSCredentialsProvider |
|------|--------------|------------------------|
| **职责** | 用户认证 | AWS 服务授权 |
| **输入** | username/password | ID Token |
| **输出** | ID Token | AWS 临时凭证 |
| **使用** | 登录、验证身份 | 访问 S3、DynamoDB |
| **服务** | Cognito User Pool | Cognito Identity Pool |

**为什么不能合并**：
1. **职责分离**：认证（我是谁）vs 授权（我能做什么）
2. **技术依赖不同**：User Pool SDK vs boto3
3. **安全优势**：临时凭证（1小时过期）vs 长期密钥
4. **细粒度权限**：基于身份的 IAM 策略

---

## 🏗️ 架构设计

### 目录结构

```
agent/
├── cloud/                          # 云服务模块（公共）
│   ├── __init__.py
│   ├── standard_s3_uploader.py     # 统一 S3 上传工具
│   └── s3_storage_service.py       # S3 存储服务（boto3 封装）
│
├── avatar/                         # Avatar 专用模块
│   ├── avatar_cloud_sync.py        # 使用 cloud 模块
│   └── avatar_manager.py
│
auth/
└── aws_credentials_provider.py     # AWS 凭证提供者
```

### 核心组件

1. **S3StorageService**：boto3 客户端封装，基础 S3 操作
2. **StandardS3Uploader**：统一上传接口，自动路径生成和元数据
3. **S3PathGenerator**：标准化路径生成和解析
4. **AWSCredentialsProvider**：获取 AWS 临时凭证

---

## 🚀 使用指南

### 快速开始

```python
from agent.cloud import create_standard_uploader

# 1. 创建上传器
uploader = create_standard_uploader()

# 2. 上传文件
success, url, error = uploader.upload(
    local_path='/path/to/avatar.png',
    owner='user@example.com',
    resource_type='avatar',
    resource_id='avatar_123',
    file_category='image',
    file_hash='abc123def456',
    extra_metadata={'avatar_type': 'uploaded'}
)

if success:
    print(f"✅ 上传成功: {url}")
else:
    print(f"❌ 上传失败: {error}")
```

### 集成到现有代码

```python
# agent/avatar/avatar_cloud_sync.py

from agent.cloud import StandardS3Uploader

class AvatarCloudSync:
    def _sync_file_to_cloud(self, avatar_resource, local_path, file_type):
        uploader = StandardS3Uploader(self.cloud_service)
        
        file_hash = (avatar_resource.image_hash 
                    if file_type == 'image' 
                    else avatar_resource.video_hash)
        
        success, cloud_url, error = uploader.upload(
            local_path=local_path,
            owner=avatar_resource.owner,
            resource_type='avatar',
            resource_id=avatar_resource.id,
            file_category=file_type,
            file_hash=file_hash
        )
        
        return success
```

---

## 🔧 配置说明

### 环境变量

```bash
AWS_REGION=us-east-1
AVATAR_CLOUD_BUCKET=ecan-avatars
AWS_COGNITO_IDENTITY_POOL_ID=us-east-1:xxxxx
```

### S3 Bucket CORS

```json
[{
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["GET", "PUT", "POST", "DELETE"],
    "AllowedOrigins": ["*"],
    "ExposeHeaders": ["ETag"]
}]
```

### IAM 策略（基于身份）

```json
{
    "Effect": "Allow",
    "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
    "Resource": [
        "arn:aws:s3:::ecan-avatars/avatars/${cognito-identity.amazonaws.com:sub}/*"
    ]
}
```

---

## ❓ 常见问题

### Q1: 如何切换到新工具？

```python
# 旧代码
cloud_key = f"{owner}/{file_type}s/{file_hash}{file_ext}"
success, url, error = s3_service.upload_file(local_path, cloud_key)

# 新代码
uploader = create_standard_uploader()
success, url, error = uploader.upload(
    local_path=local_path,
    owner=owner,
    resource_type='avatar',
    resource_id=resource_id,
    file_category=file_type,
    file_hash=file_hash
)
```

### Q2: 如何查询用户文件？

```python
import boto3

s3_client = boto3.client('s3')
response = s3_client.list_objects_v2(
    Bucket='ecan-avatars',
    Prefix=f'avatars/{username}/'
)
```

### Q3: 如何实现 CDN 加速？

1. 创建 CloudFront Distribution
2. 使用 CDN 域名：`https://d123456.cloudfront.net/{s3_key}`

---

## 📚 相关文件

- **标准上传工具**：`/agent/cloud/standard_s3_uploader.py`
- **S3 存储服务**：`/agent/cloud/s3_storage_service.py`
- **AWS 凭证提供者**：`/auth/aws_credentials_provider.py`
- **测试脚本**：`/tests/test_standard_s3_uploader.py`

---

## 🎯 总结

### 已完成
- ✅ 统一的标准 S3 上传工具
- ✅ 标准化路径生成器
- ✅ Avatar 云同步集成
- ✅ 完整测试脚本

### 下一步
1. 运行测试：`python tests/test_standard_s3_uploader.py`
2. 配置 AWS（S3 Bucket + Cognito Identity Pool）
3. 可选优化：DynamoDB 索引、CloudFront CDN、文件版本管理
