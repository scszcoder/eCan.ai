# OTA 自动更新快速参考

## 🚀 一分钟快速开始

### 部署更新

```bash
# 1. 更新版本号
echo "1.0.1" > VERSION

# 2. 提交并推送标签
git add VERSION
git commit -m "Bump version to 1.0.1"
git tag -a v1.0.1 -m "Release 1.0.1"
git push origin v1.0.1

# 3. GitHub Actions 自动构建并部署到 S3
```

### 测试更新

```bash
# 运行测试
python3 tests/test_ota_platforms.py
```

---

## 📋 核心 API

### 检查更新

```python
from ota.core.updater import OTAUpdater

updater = OTAUpdater()
has_update, info = updater.check_for_updates(return_info=True)

if has_update:
    print(f"新版本: {info['latest_version']}")
    updater.install_update()
```

### 配置管理

```python
from ota.core.config import ota_config

# 查看当前版本
from config.app_info import app_info
print(f"当前版本: {app_info.version}")

# 获取 Appcast URL
url = ota_config.get_appcast_url('amd64')
print(f"Appcast: {url}")
```

---

## 🔧 GitHub Secrets 配置

必需的 Secrets:

```
AWS_ACCESS_KEY_ID          # AWS 访问密钥
AWS_SECRET_ACCESS_KEY      # AWS 密钥
S3_BUCKET                  # S3 bucket 名称 (例如: ecbot-updates)
AWS_REGION                 # AWS 区域 (例如: us-east-1)
ED25519_PRIVATE_KEY        # Ed25519 私钥
WIN_CERT_PFX              # Windows 签名证书 (Base64)
WIN_CERT_PASSWORD         # Windows 证书密码
MAC_CERT_P12              # macOS 签名证书 (Base64)
MAC_CERT_PASSWORD         # macOS 证书密码
MAC_CODESIGN_IDENTITY     # macOS 签名身份
APPLE_ID                  # Apple ID
APPLE_APP_SPECIFIC_PASSWORD  # Apple 应用专用密码
TEAM_ID                   # Apple Team ID
```

---

## 📁 文件结构

### S3 Bucket 结构

```
s3://ecbot-updates/
├── releases/
│   └── v1.0.1/
│       ├── windows/
│       │   ├── eCan-1.0.1-windows-amd64.exe
│       │   └── eCan-1.0.1-windows-amd64-Setup.exe
│       ├── macos/
│       │   ├── eCan-1.0.1-macos-amd64.pkg
│       │   └── eCan-1.0.1-macos-aarch64.pkg
│       ├── checksums/SHA256SUMS
│       └── version-metadata.json
└── appcast/
    ├── appcast-windows.xml
    ├── appcast-macos.xml
    ├── appcast-windows-amd64.xml
    ├── appcast-macos-amd64.xml
    └── appcast-macos-aarch64.xml
```

### 代码结构

```
ota/
├── core/
│   ├── updater.py          # 主更新器
│   ├── config.py           # 配置管理
│   ├── installer.py        # 安装管理器 (支持 PKG/EXE)
│   ├── package_manager.py  # 包管理和验证
│   └── platforms.py        # 平台适配器
config/
└── app_info.py            # 版本管理 (读取 VERSION 文件)
build_system/
└── generate_appcast.py    # Appcast 生成 (Setup.exe 优先)
.github/workflows/
└── release.yml            # 构建和部署 (--acl public-read)
```

---

## ✅ 验证清单

### 部署前检查

- [ ] GitHub Secrets 已配置
- [ ] S3 bucket 已创建
- [ ] VERSION 文件已更新
- [ ] Ed25519 密钥对已生成

### 部署后验证

```bash
# 1. 检查 S3 文件
aws s3 ls s3://ecbot-updates/releases/v1.0.1/ --recursive

# 2. 测试文件访问
curl -I https://ecbot-updates.s3.us-east-1.amazonaws.com/appcast/appcast-windows.xml

# 3. 运行测试
python3 tests/test_ota_platforms.py
```

---

## 🐛 常见问题

### 403 Forbidden

**问题**: 无法下载更新包

**解决**:
```bash
# 检查文件 ACL
aws s3api get-object-acl --bucket ecbot-updates --key releases/v1.0.1/windows/eCan.exe

# 确保 workflow 中有 --acl public-read
```

### 版本号不一致

**问题**: 应用显示的版本号不正确

**解决**:
```python
# 确保从 VERSION 文件读取
from config.app_info import app_info
print(app_info.version)  # 应该显示 VERSION 文件中的版本
```

### PKG 安装失败

**问题**: macOS PKG 无法安装

**解决**:
```bash
# 检查 installer.py 是否有 _install_pkg 方法
grep -n "_install_pkg" ota/core/installer.py

# 确保使用 AppleScript 请求权限
```

---

## 📚 完整文档

| 文档 | 说明 |
|------|------|
| [OTA_COMPLETE_GUIDE.md](./OTA_COMPLETE_GUIDE.md) | 完整使用指南 |
| [OTA_IMPLEMENTATION_SUMMARY.md](./OTA_IMPLEMENTATION_SUMMARY.md) | 实现总结 |
| [OTA_DEPLOYMENT_CHECKLIST.md](./OTA_DEPLOYMENT_CHECKLIST.md) | 33项部署检查清单 |
| [OTA_PLATFORM_SUPPORT.md](./OTA_PLATFORM_SUPPORT.md) | 平台支持详解 |
| [S3_BUCKET_POLICY_SETUP.md](./S3_BUCKET_POLICY_SETUP.md) | S3 配置指南 |

---

## 🔗 关键 URL

### 生产环境

```
# Appcast (S3 主要源)
https://ecbot-updates.s3.us-east-1.amazonaws.com/appcast/appcast-windows.xml
https://ecbot-updates.s3.us-east-1.amazonaws.com/appcast/appcast-macos.xml

# Appcast (GitHub Pages 备份)
https://scszcoder.github.io/ecbot/appcast-windows.xml
https://scszcoder.github.io/ecbot/appcast-macos.xml

# 下载 URL
https://ecbot-updates.s3.us-east-1.amazonaws.com/releases/v{version}/{platform}/{filename}
```

---

## 💡 最佳实践

### 1. 版本号管理

```bash
# 始终更新 VERSION 文件
echo "1.0.1" > VERSION
git add VERSION
git commit -m "Bump version to 1.0.1"
```

### 2. 测试流程

```bash
# 本地测试
python3 tests/test_ota_platforms.py

# 推送标签前先测试构建
python build.py --mode prod --platform windows
python build.py --mode prod --platform macos --arch amd64
```

### 3. 发布流程

```bash
# 1. 更新 VERSION
# 2. 更新 CHANGELOG
# 3. 提交代码
# 4. 创建标签
# 5. 推送标签
# 6. 监控 GitHub Actions
# 7. 验证 S3 文件
# 8. 测试应用更新
```

---

**最后更新**: 2025-10-10  
**状态**: ✅ 生产就绪
