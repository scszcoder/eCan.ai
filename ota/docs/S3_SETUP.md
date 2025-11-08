# AWS S3 Bucket Policy 配置指南

## 概述

为了让 OTA 自动更新系统正常工作，需要配置 S3 bucket 允许公共读取访问。本文档提供两种配置方法。

## 方法 1: 使用 --acl public-read (推荐)

GitHub Actions workflow 已经配置了 `--acl public-read` 参数，会在上传时自动设置文件为公共可读。

**优点**:
- 简单直接
- 每个文件独立控制
- 无需额外配置

**缺点**:
- 需要 IAM 用户有 `s3:PutObjectAcl` 权限
- 每次上传都需要设置

### 所需 IAM 权限

确保用于 GitHub Actions 的 IAM 用户具有以下权限：

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
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::your-bucket-name/*",
        "arn:aws:s3:::your-bucket-name"
      ]
    }
  ]
}
```

## 方法 2: 使用 Bucket Policy (备选)

如果不想在每次上传时设置 ACL，可以配置 Bucket Policy 使整个目录公共可读。

### 步骤 1: 禁用"阻止公共访问"

1. 登录 AWS Console
2. 进入 S3 服务
3. 选择你的 bucket
4. 点击 "Permissions" 标签
5. 编辑 "Block public access (bucket settings)"
6. **取消勾选** "Block public access to buckets and objects granted through new public bucket or access point policies"
7. 保存更改

### 步骤 2: 添加 Bucket Policy

在 "Bucket policy" 部分，添加以下策略：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadGetObject",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": [
        "arn:aws:s3:::your-bucket-name/releases/*",
        "arn:aws:s3:::your-bucket-name/appcast/*"
      ]
    }
  ]
}
```

**注意**: 将 `your-bucket-name` 替换为你的实际 bucket 名称。

### 步骤 3: 验证配置

使用浏览器访问测试 URL：

```
https://your-bucket-name.s3.us-east-1.amazonaws.com/appcast/appcast-macos.xml
```

如果能正常访问，说明配置成功。

## 方法 3: 使用 CloudFront (生产环境推荐)

对于生产环境，建议使用 CloudFront CDN 来分发更新文件。

### 优点
- 更快的下载速度（全球 CDN）
- 更好的安全性（可以保持 S3 bucket 私有）
- HTTPS 支持
- 自定义域名
- 降低 S3 流量成本

### 配置步骤

1. **创建 CloudFront Distribution**:
   - Origin: 你的 S3 bucket
   - Origin Access Identity: 创建新的 OAI
   - Viewer Protocol Policy: Redirect HTTP to HTTPS
   - Allowed HTTP Methods: GET, HEAD, OPTIONS
   - Cache Policy: CachingOptimized

2. **更新 S3 Bucket Policy**:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::cloudfront:user/CloudFront Origin Access Identity YOUR-OAI-ID"
      },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::your-bucket-name/*"
    }
  ]
}
```

3. **更新 OTA 配置**:

修改 `ota/core/config.py`:
```python
"appcast_url": "https://your-cloudfront-domain.cloudfront.net/appcast/appcast-macos.xml"
```

或使用自定义域名:
```python
"appcast_url": "https://updates.yourdomain.com/appcast/appcast-macos.xml"
```

## 安全最佳实践

### 1. 最小权限原则

只开放必要的路径：
```json
"Resource": [
  "arn:aws:s3:::your-bucket-name/releases/*",
  "arn:aws:s3:::your-bucket-name/appcast/*"
]
```

**不要开放**:
```json
"Resource": "arn:aws:s3:::your-bucket-name/*"  // ❌ 太宽泛
```

### 2. 使用 HTTPS

确保所有 URL 使用 HTTPS：
```python
# ✅ 正确
"appcast_url": "https://bucket.s3.region.amazonaws.com/appcast/appcast.xml"

# ❌ 错误
"appcast_url": "http://bucket.s3.region.amazonaws.com/appcast/appcast.xml"
```

### 3. 启用 S3 访问日志

监控谁在访问你的更新文件：

1. 创建日志 bucket
2. 在主 bucket 的 "Properties" 中启用 "Server access logging"
3. 定期审查日志

### 4. 设置合理的缓存策略

```yaml
# GitHub Actions workflow 中已配置
--cache-control "max-age=31536000"  # 版本文件（1年）
--cache-control "max-age=300"       # Appcast 文件（5分钟）
```

## 故障排查

### 问题 1: 403 Forbidden

**症状**: 应用无法下载更新包，返回 403 错误

**解决方案**:
1. 检查 Bucket Policy 是否正确
2. 检查"阻止公共访问"设置
3. 检查 IAM 用户权限
4. 验证文件 ACL: `aws s3api get-object-acl --bucket your-bucket --key releases/v1.0.0/windows/eCan.exe`

### 问题 2: 404 Not Found

**症状**: URL 返回 404

**解决方案**:
1. 检查文件是否成功上传: `aws s3 ls s3://your-bucket/releases/`
2. 检查 URL 路径是否正确
3. 检查 region 是否匹配

### 问题 3: CORS 错误

**症状**: 浏览器控制台显示 CORS 错误

**解决方案**:

添加 CORS 配置（如果需要从浏览器直接访问）:

```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedOrigins": ["*"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3000
  }
]
```

## 验证清单

在部署到生产环境前，请验证：

- [ ] S3 bucket 已创建
- [ ] Bucket Policy 已配置（或 ACL 权限已设置）
- [ ] IAM 用户具有必要权限
- [ ] GitHub Actions secrets 已配置（AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET）
- [ ] 测试文件可以通过 HTTPS 访问
- [ ] Appcast XML 文件可以下载
- [ ] 更新包文件可以下载
- [ ] OTA 配置中的 URL 正确
- [ ] 应用可以检测到更新
- [ ] 应用可以下载更新包
- [ ] 签名验证通过

## 成本估算

### S3 存储成本
- 标准存储: $0.023/GB/月
- 每个版本约 200-300MB
- 保留 10 个版本: 约 3GB = $0.07/月

### S3 传输成本
- 前 10TB: $0.09/GB
- 1000 次下载 × 300MB = 300GB = $27/月

### CloudFront 成本（推荐）
- 前 10TB: $0.085/GB
- 1000 次下载 × 300MB = 300GB = $25.5/月
- **优势**: 更快 + 更便宜

## 相关文档

- [AWS S3 Bucket Policy 文档](https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-policies.html)
- [AWS CloudFront 文档](https://docs.aws.amazon.com/cloudfront/)
- [GitHub Actions Workflow](../.github/workflows/release.yml)
- [OTA 配置](../ota/core/config.py)

## 联系方式

如有问题，请提交 GitHub Issue:
https://github.com/scszcoder/ecbot/issues

---

**最后更新**: 2025-10-09
**文档版本**: 1.0.0
