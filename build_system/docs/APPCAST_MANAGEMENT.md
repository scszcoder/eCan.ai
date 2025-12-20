# Appcast 管理指南

## 概述

Appcast (应用更新订阅源) 是 OTA 更新系统的核心组件，包含应用的版本信息、下载链接和签名数据。

**注意：** eCan 使用自包含的 OTA 系统，采用业界标准的 Sparkle-format appcast.xml，但不依赖 Sparkle/WinSparkle 框架。所有更新逻辑由独立实现的 Python 代码处理。

## Appcast 文件管理

### 1. 双重发布策略

Appcast 文件同时发布到两个位置，提供冗余和灵活性：

#### **GitHub Pages (主要)**
- **URL**: `https://scszcoder.github.io/ecbot/appcast-*.xml`
- **优势**: 免费、稳定、自动 HTTPS
- **更新**: 通过 gh-pages 分支自动部署
- **缓存**: GitHub CDN 自动缓存

#### **AWS S3 (备用/主要)**
- **URL**: `https://{bucket}.s3.{region}.amazonaws.com/appcast/appcast-*.xml`
- **优势**: 更快、可控、支持 CloudFront CDN
- **更新**: 每次发布自动上传
- **缓存**: 5 分钟 (`max-age=300`)

### 2. Appcast 文件列表

| 文件名 | 平台 | 架构 | 用途 |
|--------|------|------|------|
| `appcast-macos.xml` | macOS | 全部 | macOS 通用更新源（包含所有架构） |
| `appcast-macos-amd64.xml` | macOS | Intel x86_64 | Intel Mac 专用更新源 |
| `appcast-macos-aarch64.xml` | macOS | Apple Silicon ARM64 | Apple Silicon 专用更新源 |
| `appcast-windows.xml` | Windows | 全部 | Windows 通用更新源 |
| `appcast-windows-amd64.xml` | Windows | x64 | Windows x64 专用更新源 |

### 3. Appcast XML 结构

```xml
<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" 
     xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle"
     xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>eCan AI Assistant</title>
    <link>https://github.com/scszcoder/ecbot</link>
    <description>eCan AI Assistant Updates</description>
    <language>en</language>
    
    <item>
      <title>eCan 0.0.1</title>
      <sparkle:version>0.0.1</sparkle:version>
      <sparkle:shortVersionString>0.0.1</sparkle:shortVersionString>
      <description>eCan AI Assistant 0.0.1 for macos (x86_64)</description>
      <pubDate>Sat, 04 Oct 2025 14:30:00 +0000</pubDate>
      <link>https://bucket.s3.region.amazonaws.com/releases/v0.0.1/macos/eCan-0.0.1-macos-amd64.pkg</link>
      
      <enclosure 
        url="https://bucket.s3.region.amazonaws.com/releases/v0.0.1/macos/eCan-0.0.1-macos-amd64.pkg"
        length="98765432"
        type="application/octet-stream"
        sparkle:version="0.0.1"
        sparkle:os="macos"
        sparkle:arch="x86_64"
        sparkle:edSignature="base64_signature_here"
        sparkle:sha256="sha256_hash_here"
      />
    </item>
  </channel>
</rss>
```

## 应用配置

### Python OTA 客户端配置

eCan 使用自包含的 Python OTA 客户端，配置在 `ota/config/ota_config.yaml`：

```yaml
environments:
  production:
    appcast_base: "https://ecan-releases.s3.us-east-1.amazonaws.com/production"
    channel: "stable"
    signature_required: true
```

**架构特定 Appcast URL 自动生成：**
```python
# ota/config/loader.py
def get_appcast_url(self, arch: str) -> str:
    """
    返回格式: {appcast_base}/channels/{channel}/appcast-{platform}-{arch}.xml
    
    Examples:
    - macOS Intel: .../production/channels/stable/appcast-macos-amd64.xml
    - macOS ARM:   .../production/channels/stable/appcast-macos-aarch64.xml
    - Windows:     .../production/channels/stable/appcast-windows-amd64.xml
    """
```

**客户端集成：**
```python
from ota.core.updater import OTAUpdater

# 启动自动更新检查
OTAUpdater.start_auto_check_in_background(
    ctx=AppContext,
    logger_instance=logger
)
```

## 签名管理

### 1. 生成密钥对

```bash
# 生成 ED25519 密钥对
openssl genpkey -algorithm ED25519 -out private_key.pem
openssl pkey -in private_key.pem -pubout -out public_key.pem

# 查看公钥（用于应用配置）
cat public_key.pem
```

### 2. 配置私钥

将私钥添加到 GitHub Secrets：

```bash
# 读取私钥内容
cat private_key.pem

# 添加到 GitHub Secrets
# 名称: ED25519_PRIVATE_KEY
# 值: 完整的 PEM 格式私钥（包括 BEGIN/END 行）
```

### 3. 签名验证流程

```
1. 发布时：
   - 使用私钥对安装包签名
   - 签名写入 appcast.xml 的 sparkle:edSignature 属性

2. 更新时：
   - 客户端下载 appcast.xml
   - 使用内置公钥验证签名
   - 验证通过才下载和安装更新
```

## URL 管理策略

### 策略 1: GitHub Pages 主，S3 备用

**应用配置：**
```
Primary: https://scszcoder.github.io/ecbot/appcast-macos.xml
Fallback: https://ecan-releases.s3.us-east-1.amazonaws.com/appcast/appcast-macos.xml
```

**优势：**
- 免费、稳定
- 自动 HTTPS
- GitHub CDN 加速

**劣势：**
- 更新延迟（gh-pages 部署需要时间）
- 无法自定义缓存策略

### 策略 2: S3 主，GitHub Pages 备用

**应用配置：**
```
Primary: https://ecan-releases.s3.us-east-1.amazonaws.com/appcast/appcast-macos.xml
Fallback: https://scszcoder.github.io/ecbot/appcast-macos.xml
```

**优势：**
- 更新即时（S3 上传立即生效）
- 可控缓存策略
- 支持 CloudFront CDN

**劣势：**
- 需要 AWS 成本
- 需要管理 S3 权限

### 策略 3: CloudFront CDN（推荐生产环境）

**配置 CloudFront：**
```
Origin: ecan-releases.s3.us-east-1.amazonaws.com
Path: /appcast/*
Cache Policy: CachingOptimized (5 分钟 TTL)
```

**应用配置：**
```
Primary: https://d1234567890.cloudfront.net/appcast-macos.xml
Fallback: https://scszcoder.github.io/ecbot/appcast-macos.xml
```

**优势：**
- 全球 CDN 加速
- HTTPS 自动配置
- 自定义域名支持
- 低延迟更新

## 缓存策略

### GitHub Pages
```
Cache-Control: max-age=600 (10 分钟)
自动由 GitHub 设置，无法修改
```

### S3
```bash
# 当前配置（5 分钟）
aws s3 sync dist/appcast/ s3://bucket/appcast/ \
  --cache-control "max-age=300"

# 更激进的缓存（1 小时）
--cache-control "max-age=3600"

# 禁用缓存（测试用）
--cache-control "no-cache, no-store, must-revalidate"
```

### CloudFront
```
Default TTL: 300 秒 (5 分钟)
Min TTL: 0 秒
Max TTL: 86400 秒 (24 小时)
```

**推荐配置：**
- **开发/测试**: 5 分钟（快速迭代）
- **生产环境**: 1 小时（减少请求）
- **紧急更新**: 手动清除 CDN 缓存

## 版本管理

### 1. 多版本共存

Appcast 支持多个版本条目：

```xml
<channel>
  <!-- 最新版本 -->
  <item>
    <sparkle:version>0.0.2</sparkle:version>
    ...
  </item>
  
  <!-- 上一版本（回滚用） -->
  <item>
    <sparkle:version>0.0.1</sparkle:version>
    ...
  </item>
</channel>
```

### 2. 版本过滤

客户端自动选择：
- 比当前版本更新的版本
- 匹配当前平台和架构的版本
- 签名验证通过的版本

### 3. 增量更新（可选）

```xml
<enclosure 
  url="https://bucket.s3.region.amazonaws.com/releases/v0.0.2/macos/eCan-0.0.2-macos-amd64.pkg"
  sparkle:deltaFrom="0.0.1"
  sparkle:deltaUrl="https://bucket.s3.region.amazonaws.com/releases/v0.0.2/delta/eCan-0.0.1-to-0.0.2-delta.pkg"
/>
```

## 监控和调试

### 1. 验证 Appcast 可访问性

```bash
# GitHub Pages
curl -I https://scszcoder.github.io/ecbot/appcast-macos.xml

# S3
curl -I https://ecan-releases.s3.us-east-1.amazonaws.com/appcast/appcast-macos.xml

# CloudFront
curl -I https://d1234567890.cloudfront.net/appcast-macos.xml
```

### 2. 检查 Appcast 内容

```bash
# 下载并格式化
curl https://scszcoder.github.io/ecbot/appcast-macos.xml | xmllint --format -

# 提取版本信息
curl -s https://scszcoder.github.io/ecbot/appcast-macos.xml | \
  grep -o 'sparkle:version="[^"]*"' | head -1

# 提取下载 URL
curl -s https://scszcoder.github.io/ecbot/appcast-macos.xml | \
  grep -o 'url="[^"]*"' | head -1
```

### 3. 验证签名

```bash
# 下载文件和签名
curl -O https://bucket.s3.region.amazonaws.com/releases/v0.0.1/macos/eCan-0.0.1-macos-amd64.pkg

# 从 appcast 提取签名
SIGNATURE=$(curl -s https://scszcoder.github.io/ecbot/appcast-macos.xml | \
  grep -o 'sparkle:edSignature="[^"]*"' | cut -d'"' -f2)

# 验证签名：可使用自定义的 Ed25519 校验脚本（参见 OTA_SYSTEM.md / signing_manager.py）
# 此处不再依赖 Sparkle/WinSparkle 提供的工具
```

### 4. 测试更新流程

```bash
# macOS - 强制检查更新
defaults write com.yourcompany.ecan SUScheduledCheckInterval 0
open /Applications/eCan.app

# Windows - 通过应用内 OTA 菜单触发检查更新（例如“检查更新...”按钮）
# 具体触发方式由 eCan 客户端的 OTA 集成逻辑决定
```

## 故障排除

### 问题 1: 客户端检测不到更新

**检查清单：**
- [ ] Appcast URL 可访问（curl 测试）
- [ ] XML 格式正确（xmllint 验证）
- [ ] 版本号格式正确（语义化版本）
- [ ] 签名验证通过
- [ ] 平台/架构匹配

**调试：**
```bash
# 检查应用日志
tail -f ~/Library/Logs/eCan/update.log
```

### 问题 2: 签名验证失败

**原因：**
- 私钥/公钥不匹配
- 文件在签名后被修改
- 签名算法不支持

**解决：**
```bash
# 重新生成密钥对
openssl genpkey -algorithm ED25519 -out private_key.pem
openssl pkey -in private_key.pem -pubout -out public_key.pem

# 更新 GitHub Secret: ED25519_PRIVATE_KEY
# 更新应用中的公钥
```

### 问题 3: Appcast 缓存问题

**症状：**
- 发布新版本后，客户端仍显示旧版本

**解决：**
```bash
# 清除 CloudFront 缓存
aws cloudfront create-invalidation \
  --distribution-id E1234567890ABC \
  --paths "/appcast/*"

# 或等待 TTL 过期（5-60 分钟）
```

## 最佳实践

### 1. 版本发布流程

```
1. 构建新版本
2. 上传到 S3
3. 生成 appcast.xml（自动签名）
4. 上传 appcast 到 S3 和 GitHub Pages
5. 验证 appcast 可访问
6. 测试更新流程
7. 公告发布
```

### 2. 安全建议

- ✅ 始终使用 HTTPS
- ✅ 启用签名验证
- ✅ 定期轮换密钥（每年）
- ✅ 私钥仅存储在 GitHub Secrets
- ✅ 监控异常更新请求

### 3. 性能优化

- 使用 CDN（CloudFront）
- 设置合理的缓存时间
- 压缩 XML 文件（gzip）
- 使用增量更新（大文件）

### 4. 监控指标

跟踪以下指标：
- Appcast 请求量
- 更新下载量
- 更新成功率
- 平均更新时间
- 错误率

## 相关文档

- [AWS_S3_RELEASE_SETUP.md](./AWS_S3_RELEASE_SETUP.md) - S3 配置指南
- [RELEASE_S3_MIGRATION.md](./RELEASE_S3_MIGRATION.md) - S3 迁移总结
- Sparkle Appcast XML Format（仅作为协议格式参考，不使用 Sparkle/WinSparkle 二进制框架）
