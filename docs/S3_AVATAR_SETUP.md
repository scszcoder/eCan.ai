# Avatar S3 上传配置指南

## 🎯 概述

本文档详细说明如何配置 AWS S3 用于 eCan.ai 的 Avatar 图片上传功能，特别是 Cognito 用户的权限配置。

## 📋 前置条件

- AWS 账号
- AWS CLI 已安装并配置
- 已创建 Cognito User Pool 和 Identity Pool

## 🔧 配置步骤

### 1. 创建 S3 Bucket

#### 1.1 通过 AWS Console 创建

1. 登录 AWS Console
2. 进入 S3 服务
3. 点击 "Create bucket"
4. 配置 Bucket：
   ```
   Bucket name: ecan-avatars (或你的自定义名称)
   Region: us-east-1 (或你的首选区域)
   ```

#### 1.2 通过 AWS CLI 创建

```bash
# 创建 Bucket
aws s3 mb s3://ecan-avatars --region us-east-1

# 验证创建
aws s3 ls | grep ecan-avatars
```

### 2. 配置 CORS 策略

Avatar 上传需要浏览器直接上传到 S3，必须配置 CORS。

#### 2.1 创建 CORS 配置文件

创建 `s3-cors-config.json`:

```json
[
    {
        "AllowedHeaders": [
            "*"
        ],
        "AllowedMethods": [
            "GET",
            "PUT",
            "POST",
            "DELETE",
            "HEAD"
        ],
        "AllowedOrigins": [
            "http://localhost:*",
            "http://127.0.0.1:*",
            "https://yourdomain.com"
        ],
        "ExposeHeaders": [
            "ETag",
            "x-amz-server-side-encryption",
            "x-amz-request-id",
            "x-amz-id-2"
        ],
        "MaxAgeSeconds": 3000
    }
]
```

#### 2.2 应用 CORS 配置

```bash
aws s3api put-bucket-cors \
    --bucket ecan-avatars \
    --cors-configuration file://s3-cors-config.json
```

#### 2.3 验证 CORS 配置

```bash
aws s3api get-bucket-cors --bucket ecan-avatars
```

### 3. 配置 Bucket 策略

#### 3.1 基础 Bucket 策略

创建 `s3-bucket-policy.json`:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AllowCognitoAuthenticatedUsers",
            "Effect": "Allow",
            "Principal": {
                "AWS": "arn:aws:iam::YOUR_ACCOUNT_ID:role/Cognito_eCanIdentityPoolAuth_Role"
            },
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:DeleteObject"
            ],
            "Resource": "arn:aws:s3:::ecan-avatars/avatars/*"
        },
        {
            "Sid": "AllowPublicRead",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::ecan-avatars/avatars/*"
        }
    ]
}
```

**注意**：
- 替换 `YOUR_ACCOUNT_ID` 为你的 AWS 账号 ID
- 替换 `Cognito_eCanIdentityPoolAuth_Role` 为你的 Cognito 认证角色名称

#### 3.2 应用 Bucket 策略

```bash
aws s3api put-bucket-policy \
    --bucket ecan-avatars \
    --policy file://s3-bucket-policy.json
```

### 4. 配置 Cognito Identity Pool IAM 角色

#### 4.1 查找 Cognito 角色

```bash
# 列出所有 IAM 角色
aws iam list-roles | grep Cognito

# 或者在 Cognito Identity Pool 中查看
aws cognito-identity describe-identity-pool \
    --identity-pool-id YOUR_IDENTITY_POOL_ID
```

#### 4.2 创建 IAM 策略

创建 `cognito-s3-policy.json`:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:PutObjectAcl",
                "s3:GetObject",
                "s3:DeleteObject"
            ],
            "Resource": [
                "arn:aws:s3:::ecan-avatars/avatars/${cognito-identity.amazonaws.com:sub}/*",
                "arn:aws:s3:::ecan-avatars/avatars/shared/*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:ListBucket"
            ],
            "Resource": "arn:aws:s3:::ecan-avatars",
            "Condition": {
                "StringLike": {
                    "s3:prefix": [
                        "avatars/${cognito-identity.amazonaws.com:sub}/*",
                        "avatars/shared/*"
                    ]
                }
            }
        }
    ]
}
```

**说明**：
- `${cognito-identity.amazonaws.com:sub}` 会自动替换为用户的 Cognito Identity ID
- 用户只能访问自己的目录和共享目录

#### 4.3 创建 IAM 策略

```bash
aws iam create-policy \
    --policy-name eCanAvatarS3Access \
    --policy-document file://cognito-s3-policy.json
```

#### 4.4 附加策略到 Cognito 角色

```bash
# 获取策略 ARN
POLICY_ARN=$(aws iam list-policies --query 'Policies[?PolicyName==`eCanAvatarS3Access`].Arn' --output text)

# 附加到认证用户角色
aws iam attach-role-policy \
    --role-name Cognito_eCanIdentityPoolAuth_Role \
    --policy-arn $POLICY_ARN
```

### 5. 配置 Bucket 加密（可选但推荐）

```bash
# 启用默认加密
aws s3api put-bucket-encryption \
    --bucket ecan-avatars \
    --server-side-encryption-configuration '{
        "Rules": [{
            "ApplyServerSideEncryptionByDefault": {
                "SSEAlgorithm": "AES256"
            }
        }]
    }'
```

### 6. 配置生命周期策略（可选）

创建 `s3-lifecycle-policy.json`:

```json
{
    "Rules": [
        {
            "Id": "DeleteOldTempFiles",
            "Status": "Enabled",
            "Prefix": "avatars/temp/",
            "Expiration": {
                "Days": 7
            }
        },
        {
            "Id": "TransitionToIA",
            "Status": "Enabled",
            "Prefix": "avatars/",
            "Transitions": [
                {
                    "Days": 90,
                    "StorageClass": "STANDARD_IA"
                }
            ]
        }
    ]
}
```

```bash
aws s3api put-bucket-lifecycle-configuration \
    --bucket ecan-avatars \
    --lifecycle-configuration file://s3-lifecycle-policy.json
```

## 🔐 权限验证

### 验证 Cognito 用户权限

创建测试脚本 `test_s3_upload.py`:

```python
import boto3
from botocore.exceptions import ClientError

def test_s3_upload(identity_id, credentials):
    """测试 S3 上传权限"""
    
    # 使用 Cognito 临时凭证创建 S3 客户端
    s3_client = boto3.client(
        's3',
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretKey'],
        aws_session_token=credentials['SessionToken']
    )
    
    bucket = 'ecan-avatars'
    key = f'avatars/{identity_id}/test.txt'
    
    try:
        # 测试上传
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=b'Test content'
        )
        print(f"✅ Upload successful: {key}")
        
        # 测试读取
        response = s3_client.get_object(Bucket=bucket, Key=key)
        print(f"✅ Read successful")
        
        # 测试删除
        s3_client.delete_object(Bucket=bucket, Key=key)
        print(f"✅ Delete successful")
        
        return True
        
    except ClientError as e:
        print(f"❌ Error: {e}")
        return False

# 使用方法：
# 1. 从 Cognito Identity Pool 获取临时凭证
# 2. 调用 test_s3_upload(identity_id, credentials)
```

## 🌍 环境变量配置

在 eCan.ai 应用中配置以下环境变量：

```bash
# S3 配置
export AVATAR_CLOUD_BUCKET=ecan-avatars
export AVATAR_CLOUD_REGION=us-east-1
export AVATAR_CLOUD_PATH_PREFIX=avatars/

# AWS 凭证（如果使用 IAM 用户）
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key

# 或者使用 Cognito Identity Pool
export AWS_COGNITO_IDENTITY_POOL_ID=us-east-1:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
export AWS_COGNITO_REGION=us-east-1
```

## 📊 目录结构规划

```
s3://ecan-avatars/
└── avatars/
    ├── {cognito_identity_id}/        # 用户私有目录
    │   ├── images/
    │   │   ├── {hash}_original.png
    │   │   └── {hash}_thumb.png
    │   └── videos/
    │       └── {hash}_video.mp4
    └── shared/                        # 共享资源
        ├── system/                    # 系统默认头像
        │   ├── A001.png
        │   └── A001.mp4
        └── templates/                 # 模板资源
```

## 🔍 故障排查

### 1. 检查 Bucket 是否存在

```bash
aws s3 ls s3://ecan-avatars/
```

### 2. 检查 CORS 配置

```bash
aws s3api get-bucket-cors --bucket ecan-avatars
```

### 3. 检查 Bucket 策略

```bash
aws s3api get-bucket-policy --bucket ecan-avatars
```

### 4. 检查 IAM 角色权限

```bash
aws iam get-role --role-name Cognito_eCanIdentityPoolAuth_Role
aws iam list-attached-role-policies --role-name Cognito_eCanIdentityPoolAuth_Role
```

### 5. 测试上传权限

```bash
# 使用 AWS CLI 测试上传
aws s3 cp test.txt s3://ecan-avatars/avatars/test/test.txt

# 测试读取
aws s3 cp s3://ecan-avatars/avatars/test/test.txt downloaded.txt

# 测试删除
aws s3 rm s3://ecan-avatars/avatars/test/test.txt
```

## ⚠️ 常见错误

### 错误 1: Access Denied

**原因**：
- Bucket 策略未正确配置
- IAM 角色缺少必要权限
- Cognito Identity Pool 配置错误

**解决**：
1. 检查 Bucket 策略中的 Principal ARN
2. 验证 IAM 角色已附加正确的策略
3. 确认 Cognito Identity Pool 的角色映射

### 错误 2: CORS Error

**原因**：
- CORS 配置未设置或不正确
- AllowedOrigins 不包含你的域名

**解决**：
1. 重新应用 CORS 配置
2. 确保 AllowedOrigins 包含你的应用域名
3. 清除浏览器缓存

### 错误 3: Invalid Bucket Name

**原因**：
- Bucket 名称不符合 S3 命名规则
- Bucket 名称已被占用

**解决**：
1. 使用符合规则的名称（小写字母、数字、连字符）
2. 选择唯一的 Bucket 名称

## 📚 相关文档

- [AWS S3 文档](https://docs.aws.amazon.com/s3/)
- [Cognito Identity Pool 文档](https://docs.aws.amazon.com/cognito/latest/developerguide/identity-pools.html)
- [S3 Bucket 策略示例](https://docs.aws.amazon.com/AmazonS3/latest/userguide/example-bucket-policies.html)

## 🔒 安全最佳实践

1. **最小权限原则**：只授予必要的权限
2. **使用临时凭证**：通过 Cognito Identity Pool 获取临时凭证
3. **启用加密**：使用 S3 服务端加密
4. **启用版本控制**：防止意外删除
5. **启用访问日志**：监控 S3 访问
6. **定期审计**：检查权限配置

## 📝 检查清单

- [ ] S3 Bucket 已创建
- [ ] CORS 配置已应用
- [ ] Bucket 策略已配置
- [ ] Cognito IAM 角色已配置
- [ ] IAM 策略已创建并附加
- [ ] 环境变量已设置
- [ ] 权限测试通过
- [ ] 应用可以成功上传
- [ ] 应用可以成功下载
- [ ] 应用可以成功删除

---

**最后更新**: 2025-10-19
**维护者**: eCan.ai Team
