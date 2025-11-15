# S3 路径适配说明

## 📋 背景

由于 GitHub Secrets 中的 `S3_BASE_PATH` 已设置为 `releases` 且无法修改，我们调整了代码以适配现有配置。

---

## 🎯 当前配置

```bash
S3_BUCKET = "ecan-releases"
S3_BASE_PATH = "releases"  # 无法修改
AWS_REGION = "us-east-1"
```

---

## 🗂️ 实际 S3 路径结构

```
s3://ecan-releases/releases/
├── v{version}/
│   ├── windows/
│   │   ├── eCan-{version}-windows-amd64-Setup.exe
│   │   └── eCan-{version}-windows-amd64.msi
│   ├── macos/
│   │   ├── eCan-{version}-macos-amd64.pkg
│   │   ├── eCan-{version}-macos-aarch64.pkg
│   │   └── eCan-{version}-macos-aarch64.zip
│   ├── metadata.json
│   └── release-notes.md
└── channels/
    └── stable/
        ├── appcast-windows.xml
        ├── appcast-windows-amd64.xml
        ├── appcast-macos.xml
        ├── appcast-macos-amd64.xml
        ├── appcast-macos-aarch64.xml
        └── latest.json
```

---

## 🔗 实际 URL 格式

### 文件下载 URL
```
https://ecan-releases.s3.us-east-1.amazonaws.com/releases/v{version}/windows/eCan-{version}-windows-amd64-Setup.exe
https://ecan-releases.s3.us-east-1.amazonaws.com/releases/v{version}/macos/eCan-{version}-macos-aarch64.pkg
```

### Appcast URL（OTA 更新）
```
https://ecan-releases.s3.us-east-1.amazonaws.com/releases/channels/stable/appcast-macos.xml
https://ecan-releases.s3.us-east-1.amazonaws.com/releases/channels/stable/appcast-windows-amd64.xml
```

### Metadata URL
```
https://ecan-releases.s3.us-east-1.amazonaws.com/releases/v{version}/metadata.json
https://ecan-releases.s3.us-east-1.amazonaws.com/releases/channels/stable/latest.json
```

---

## ✅ 已修改的文件

### 1. Workflow 文件
- ✅ `.github/workflows/release.yml`
  - Windows/macOS 上传路径: `v{version}/{platform}/`
  - Metadata 上传路径: `v{version}/metadata.json`
  - 所有下载链接 URL
  
- ✅ `.github/workflows/release-simulate.yml`
  - 下载链接 URL 同步更新

### 2. Python 脚本
- ✅ `build_system/generate_all_appcasts.py`
  - Appcast 中的文件 URL: `{base_url}/v{version}/{platform}/{filename}`
  
- ✅ `build_system/generate_metadata.py`
  - 文件 URL: `{base_url}/v{version}/{platform}/{filename}`
  - Release notes URL: `{base_url}/v{version}/release-notes.md`
  
- ✅ `build_system/generate_latest_json.py`
  - Metadata URL: `{base_url}/v{version}/metadata.json`
  - Quick download URLs: `{base_url}/v{version}/{platform}/{filename}`

---

## 🔄 路径逻辑

### 原设计（理想状态）
```
S3_BASE_PATH = ""
路径: {base}/releases/v{version}/{platform}/
```

### 当前适配（实际状态）
```
S3_BASE_PATH = "releases"
路径: {base}/v{version}/{platform}/
完整路径: releases/v{version}/{platform}/
```

**关键点**: 由于 `S3_BASE_PATH` 已包含 `releases`，代码中不再添加 `releases/` 前缀。

---

## 📝 示例

### 版本 0.0.0-sim 的实际路径

#### 上传路径
```bash
# Windows
s3://ecan-releases/releases/v0.0.0-sim/windows/eCan-0.0.0-sim-windows-amd64-Setup.exe

# macOS
s3://ecan-releases/releases/v0.0.0-sim/macos/eCan-0.0.0-sim-macos-aarch64.pkg

# Metadata
s3://ecan-releases/releases/v0.0.0-sim/metadata.json

# Appcast
s3://ecan-releases/releases/channels/stable/appcast-macos.xml
```

#### 下载 URL
```
https://ecan-releases.s3.us-east-1.amazonaws.com/releases/v0.0.0-sim/windows/eCan-0.0.0-sim-windows-amd64-Setup.exe
https://ecan-releases.s3.us-east-1.amazonaws.com/releases/v0.0.0-sim/macos/eCan-0.0.0-sim-macos-aarch64.pkg
```

---

## 🎯 OTA 升级配置

### 客户端 Appcast URL（固定）

#### macOS (Sparkle)
```swift
// Info.plist
<key>SUFeedURL</key>
<string>https://ecan-releases.s3.us-east-1.amazonaws.com/releases/channels/stable/appcast-macos.xml</string>

// 或架构特定
<string>https://ecan-releases.s3.us-east-1.amazonaws.com/releases/channels/stable/appcast-macos-aarch64.xml</string>
```

#### Windows (WinSparkle)
```cpp
win_sparkle_set_appcast_url("https://ecan-releases.s3.us-east-1.amazonaws.com/releases/channels/stable/appcast-windows-amd64.xml");
```

### Appcast 内容示例
```xml
<enclosure 
  url="https://ecan-releases.s3.us-east-1.amazonaws.com/releases/v1.0.0/macos/eCan-1.0.0-macos-aarch64.pkg"
  sparkle:version="1.0.0"
  sparkle:os="macos"
  sparkle:arch="aarch64"
  length="52428800"
  sparkle:edSignature="MC0CFQ..."
/>
```

---

## ✅ 验证

### 测试 Appcast
```bash
# 获取 Appcast
curl "https://ecan-releases.s3.us-east-1.amazonaws.com/releases/channels/stable/appcast-macos.xml"

# 获取 latest.json
curl "https://ecan-releases.s3.us-east-1.amazonaws.com/releases/channels/stable/latest.json" | jq .

# 测试下载链接
curl -I "https://ecan-releases.s3.us-east-1.amazonaws.com/releases/v0.0.0-sim/windows/eCan-0.0.0-sim-windows-amd64-Setup.exe"
```

### 检查 S3 文件
```bash
# 列出版本文件
aws s3 ls s3://ecan-releases/releases/v0.0.0-sim/windows/
aws s3 ls s3://ecan-releases/releases/v0.0.0-sim/macos/

# 列出 channel 文件
aws s3 ls s3://ecan-releases/releases/channels/stable/
```

---

## 🎁 核心优势

1. **版本隔离** - 每个版本独立目录 `v{version}/`
2. **固定 OTA URL** - Appcast URL 永不改变
3. **易于管理** - 删除版本: `aws s3 rm --recursive s3://ecan-releases/releases/v0.1.0/`
4. **多渠道支持** - 未来可添加 `channels/beta/`
5. **适配现有配置** - 无需修改 GitHub Secrets

---

## 📊 对比

| 项目 | 原设计 | 当前适配 |
|------|--------|----------|
| S3_BASE_PATH | `""` | `"releases"` |
| 代码路径 | `releases/v{version}/` | `v{version}/` |
| 实际 S3 路径 | `releases/v{version}/` | `releases/v{version}/` |
| 最终 URL | 相同 | 相同 |

**结论**: 虽然实现方式不同，但最终的 S3 路径和 URL 完全一致！

---

## ⚠️ 注意事项

1. **不要修改 S3_BASE_PATH** - 代码已适配当前值 `"releases"`
2. **路径一致性** - 所有脚本和 workflow 都已同步更新
3. **Appcast URL** - 客户端配置时使用完整路径，包含 `releases/`
4. **测试验证** - 每次发布后验证 URL 可访问性

---

## 🚀 下一步

1. ✅ 提交所有改动
2. ✅ 运行测试发布
3. ✅ 验证 S3 路径正确
4. ✅ 验证 Appcast URL 可访问
5. ✅ 更新客户端 Appcast URL（如需要）

**所有改动已完成，路径适配成功！** 🎉
