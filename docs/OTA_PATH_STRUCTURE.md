# OTA 路径结构文档

## 概述

本文档详细说明 eCan.ai 的 OTA 更新系统中，S3 上传路径和下载路径的完整结构。

---

## S3 存储结构

### 基础配置

- **S3 Bucket**: `ecan-releases`
- **S3 Region**: `us-east-1`
- **Base Path**: `` (空，直接使用环境前缀)

### 路径结构

```
s3://ecan-releases/
├── dev/                          # 开发环境
│   ├── releases/                 # 版本发布
│   │   ├── v1.0.0/              # 版本号
│   │   │   ├── macos/           # macOS 平台
│   │   │   │   ├── aarch64/     # ARM64 架构
│   │   │   │   │   ├── eCan-1.0.0-macos-aarch64.pkg
│   │   │   │   │   ├── eCan-1.0.0-macos-aarch64.pkg.sha256
│   │   │   │   │   └── eCan-1.0.0-macos-aarch64.pkg.sig
│   │   │   │   └── amd64/       # Intel 架构
│   │   │   │       ├── eCan-1.0.0-macos-amd64.pkg
│   │   │   │       ├── eCan-1.0.0-macos-amd64.pkg.sha256
│   │   │   │       └── eCan-1.0.0-macos-amd64.pkg.sig
│   │   │   └── windows/         # Windows 平台
│   │   │       └── amd64/       # x64 架构
│   │   │           ├── eCan-1.0.0-windows-amd64.exe
│   │   │           ├── eCan-1.0.0-windows-amd64.exe.sha256
│   │   │           └── eCan-1.0.0-windows-amd64.exe.sig
│   │   └── v1.0.1/              # 下一个版本
│   │       └── ...
│   └── channels/                 # 发布渠道
│       └── dev/                  # 开发渠道
│           ├── appcast-macos-aarch64.xml
│           ├── appcast-macos-amd64.xml
│           └── appcast-windows-amd64.xml
│
├── test/                         # 测试环境
│   ├── releases/
│   │   └── v1.0.0/
│   │       └── ...
│   └── channels/
│       └── beta/                 # Beta 渠道
│           └── ...
│
├── staging/                      # 预发布环境
│   ├── releases/
│   │   └── v1.0.0/
│   │       └── ...
│   └── channels/
│       └── stable/               # 稳定渠道
│           └── ...
│
└── production/                   # 生产环境
    ├── releases/
    │   └── v1.0.0/
    │       └── ...
    └── channels/
        └── stable/               # 稳定渠道
            └── ...
```

---

## 上传路径规则

### 构建脚本: `upload_to_s3.py`

#### macOS 安装包

**路径模板**:
```
{prefix}/releases/v{version}/{platform}/{arch}/{filename}
```

**实际示例**:
```
# 开发环境 - ARM64
dev/releases/v1.0.0/macos/aarch64/eCan-1.0.0-macos-aarch64.pkg
dev/releases/v1.0.0/macos/aarch64/eCan-1.0.0-macos-aarch64.pkg.sha256
dev/releases/v1.0.0/macos/aarch64/eCan-1.0.0-macos-aarch64.pkg.sig

# 生产环境 - Intel
production/releases/v1.0.0/macos/amd64/eCan-1.0.0-macos-amd64.pkg
production/releases/v1.0.0/macos/amd64/eCan-1.0.0-macos-amd64.pkg.sha256
production/releases/v1.0.0/macos/amd64/eCan-1.0.0-macos-amd64.pkg.sig
```

#### Windows 安装包

**路径模板**:
```
{prefix}/releases/v{version}/{platform}/{arch}/{filename}
```

**实际示例**:
```
# 开发环境
dev/releases/v1.0.0/windows/amd64/eCan-1.0.0-windows-amd64.exe
dev/releases/v1.0.0/windows/amd64/eCan-1.0.0-windows-amd64.exe.sha256
dev/releases/v1.0.0/windows/amd64/eCan-1.0.0-windows-amd64.exe.sig

# 生产环境
production/releases/v1.0.0/windows/amd64/eCan-1.0.0-windows-amd64.exe
production/releases/v1.0.0/windows/amd64/eCan-1.0.0-windows-amd64.exe.sha256
production/releases/v1.0.0/windows/amd64/eCan-1.0.0-windows-amd64.exe.sig
```

#### Appcast XML

**路径模板**:
```
{prefix}/channels/{channel}/appcast-{platform}-{arch}.xml
```

**实际示例**:
```
# 开发环境 (dev 渠道)
dev/channels/dev/appcast-macos-aarch64.xml
dev/channels/dev/appcast-macos-amd64.xml
dev/channels/dev/appcast-windows-amd64.xml

# 测试环境 (beta 渠道)
test/channels/beta/appcast-macos-aarch64.xml
test/channels/beta/appcast-macos-amd64.xml
test/channels/beta/appcast-windows-amd64.xml

# 生产环境 (stable 渠道)
production/channels/stable/appcast-macos-aarch64.xml
production/channels/stable/appcast-macos-amd64.xml
production/channels/stable/appcast-windows-amd64.xml
```

---

## 下载 URL 规则

### OTA 配置: `ota_config.yaml`

#### Appcast URL

**URL 构建逻辑** (`loader.py::get_appcast_url()`):
```python
# 模板
https://{bucket}.s3.{region}.amazonaws.com/{prefix}/channels/{channel}/appcast-{platform}-{arch}.xml

# 实际示例
https://ecan-releases.s3.us-east-1.amazonaws.com/dev/channels/dev/appcast-macos-aarch64.xml
https://ecan-releases.s3.us-east-1.amazonaws.com/production/channels/stable/appcast-macos-aarch64.xml
```

#### 安装包下载 URL

**URL 构建逻辑** (`generate_appcast.py::get_package_info()`):
```python
# 模板
https://{bucket}.s3.{region}.amazonaws.com/{prefix}/releases/v{version}/{platform}/{arch}/{filename}

# 实际示例
https://ecan-releases.s3.us-east-1.amazonaws.com/dev/releases/v1.0.0/macos/aarch64/eCan-1.0.0-macos-aarch64.pkg
https://ecan-releases.s3.us-east-1.amazonaws.com/production/releases/v1.0.0/macos/aarch64/eCan-1.0.0-macos-aarch64.pkg
```

---

## 环境配置对照表

| 环境 | Prefix | Channel | Appcast Base URL |
|------|--------|---------|------------------|
| **development** | `dev` | `dev` | `https://ecan-releases.s3.us-east-1.amazonaws.com/dev` |
| **test** | `test` | `beta` | `https://ecan-releases.s3.us-east-1.amazonaws.com/test` |
| **staging** | `staging` | `stable` | `https://ecan-releases.s3.us-east-1.amazonaws.com/staging` |
| **production** | `production` | `stable` | `https://ecan-releases.s3.us-east-1.amazonaws.com/production` |

---

## 完整示例流程

### 1. 构建和上传 (v1.0.0, production, macOS ARM64)

```bash
# 1. 构建应用
python3 build.py --version 1.0.0 --environment production

# 2. 上传到 S3
python3 build_system/scripts/upload_to_s3.py \
  --version 1.0.0 \
  --env production \
  --platform macos \
  --arch aarch64
```

**上传的文件**:
```
s3://ecan-releases/production/releases/v1.0.0/macos/aarch64/
├── eCan-1.0.0-macos-aarch64.pkg
├── eCan-1.0.0-macos-aarch64.pkg.sha256
└── eCan-1.0.0-macos-aarch64.pkg.sig
```

### 2. 生成 Appcast

```bash
python3 build_system/scripts/generate_appcast.py \
  --env production \
  --platform macos \
  --arch aarch64
```

**生成的文件**:
```
s3://ecan-releases/production/channels/stable/appcast-macos-aarch64.xml
```

**Appcast 内容示例**:
```xml
<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" 
     xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle"
     xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>eCan Updates - stable</title>
    <link>https://ecan-releases.s3.us-east-1.amazonaws.com/production/channels/stable/appcast-macos-aarch64.xml</link>
    <description>eCan application updates for macos-aarch64</description>
    <language>en</language>
    
    <item>
      <title>Version 1.0.0</title>
      <pubDate>Wed, 20 Nov 2024 18:00:00 +0800</pubDate>
      <sparkle:version>1.0.0</sparkle:version>
      <sparkle:shortVersionString>1.0.0</sparkle:shortVersionString>
      <description><![CDATA[
        <h2>What's New</h2>
        <ul>
          <li>Initial release</li>
        </ul>
      ]]></description>
      <enclosure 
        url="https://ecan-releases.s3.us-east-1.amazonaws.com/production/releases/v1.0.0/macos/aarch64/eCan-1.0.0-macos-aarch64.pkg"
        length="52428800"
        type="application/octet-stream"
        sparkle:version="1.0.0"
        sparkle:os="macos"
        sparkle:arch="aarch64"
        sparkle:edSignature="MEUCIQDx..." />
    </item>
  </channel>
</rss>
```

### 3. 客户端检查更新

```python
from ota.config.loader import ota_config

# 设置环境
ota_config.environment = 'production'

# 获取 Appcast URL
appcast_url = ota_config.get_appcast_url('macos', 'aarch64')
# → https://ecan-releases.s3.us-east-1.amazonaws.com/production/channels/stable/appcast-macos-aarch64.xml

# 下载并解析 Appcast
# 获取最新版本的下载 URL
# → https://ecan-releases.s3.us-east-1.amazonaws.com/production/releases/v1.0.0/macos/aarch64/eCan-1.0.0-macos-aarch64.pkg
```

---

## 关键代码位置

### 上传逻辑
- **文件**: `build_system/scripts/upload_to_s3.py`
- **类**: `S3Uploader`
- **方法**:
  - `upload_macos_artifacts()` - 上传 macOS 安装包
  - `upload_windows_artifacts()` - 上传 Windows 安装包

### Appcast 生成
- **文件**: `build_system/scripts/generate_appcast.py`
- **类**: `AppcastGenerator`
- **方法**:
  - `list_versions()` - 列出所有版本
  - `get_package_info()` - 获取包信息
  - `generate_appcast()` - 生成 XML

### OTA 配置
- **文件**: `ota/config/loader.py`
- **类**: `OTAConfig`
- **方法**:
  - `get_appcast_url()` - 获取 Appcast URL
  - `get_s3_url()` - 构建 S3 URL
  - `get_s3_prefix()` - 获取环境前缀

### 配置文件
- **文件**: `ota/config/ota_config.yaml`
- **关键配置**:
  - `common.s3_bucket` - S3 桶名
  - `common.s3_region` - S3 区域
  - `environments.{env}.s3_prefix` - 环境前缀
  - `environments.{env}.channel` - 发布渠道
  - `environments.{env}.appcast_base` - Appcast 基础 URL

---

## 路径变量说明

| 变量 | 说明 | 示例 |
|------|------|------|
| `{bucket}` | S3 桶名 | `ecan-releases` |
| `{region}` | S3 区域 | `us-east-1` |
| `{prefix}` | 环境前缀 | `dev`, `test`, `staging`, `production` |
| `{channel}` | 发布渠道 | `dev`, `beta`, `stable` |
| `{version}` | 版本号 | `1.0.0`, `1.0.1-rc.1` |
| `{platform}` | 平台 | `macos`, `windows` |
| `{arch}` | 架构 | `aarch64`, `amd64` |
| `{filename}` | 文件名 | `eCan-1.0.0-macos-aarch64.pkg` |

---

## 注意事项

### 1. 路径一致性
- 上传路径和下载路径必须完全一致
- 环境前缀、渠道、版本号必须匹配

### 2. 文件命名规范
- 格式: `{AppName}-{Version}-{Platform}-{Arch}.{Ext}`
- 示例: `eCan-1.0.0-macos-aarch64.pkg`

### 3. 签名文件
- SHA256: `.sha256` 后缀
- Ed25519: `.sig` 后缀
- 必须与主文件在同一目录

### 4. Appcast 位置
- 使用渠道路径，不是版本路径
- 一个渠道一个 Appcast 文件
- 包含该渠道所有版本信息

---

## 故障排查

### 问题: 找不到更新

**检查清单**:
1. ✅ Appcast URL 是否正确
2. ✅ 环境配置是否匹配
3. ✅ S3 文件是否存在
4. ✅ 文件权限是否公开可读

**验证命令**:
```bash
# 检查 Appcast
curl -I https://ecan-releases.s3.us-east-1.amazonaws.com/production/channels/stable/appcast-macos-aarch64.xml

# 检查安装包
curl -I https://ecan-releases.s3.us-east-1.amazonaws.com/production/releases/v1.0.0/macos/aarch64/eCan-1.0.0-macos-aarch64.pkg
```

### 问题: 签名验证失败

**检查清单**:
1. ✅ `.sig` 文件是否存在
2. ✅ 签名格式是否正确 (Base64 编码)
3. ✅ 公钥是否正确配置
4. ✅ 文件内容是否被修改

---

## 总结

eCan.ai 的 OTA 系统使用清晰的路径结构：
- **环境隔离**: 通过前缀 (`dev`, `test`, `staging`, `production`)
- **版本管理**: 通过 `releases/v{version}` 路径
- **平台架构**: 通过 `{platform}/{arch}` 子目录
- **渠道分发**: 通过 `channels/{channel}` 路径

所有路径都遵循统一的命名规范，确保上传和下载的一致性。
