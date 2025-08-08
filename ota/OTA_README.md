# ECBot OTA 更新功能

本文档介绍了如何使用和配置ECBot的OTA（Over-The-Air）更新功能。

## 功能概述

ECBot的OTA更新功能支持：

- **自动更新检查** - 定期检查新版本
- **手动更新检查** - 通过菜单手动检查
- **跨平台支持** - macOS (Sparkle)、Windows (winSparkle)、Linux (通用)
- **安全更新** - 数字签名验证
- **用户友好界面** - 直观的更新对话框

## 文件结构

```
ECBot/
├── utils/
│   └── ota_updater.py              # OTA更新管理器
├── gui/
│   └── UpdateDialog.py             # 更新对话框GUI
├── build_system/
│   ├── sparkle_integration.swift   # macOS Sparkle集成
│   ├── winsparkle_integration.cpp  # Windows winSparkle集成
│   ├── sparkle_build.py           # 构建脚本
│   ├── build_with_ota.py          # OTA构建脚本
│   ├── update_server.py           # 测试更新服务器
│   └── appcast.xml                # 更新配置文件
└── VERSION                        # 版本文件
```

## 快速开始

### 1. 构建OTA组件

```bash
# 安装依赖
cd build_system
python sparkle_build.py deps

# 构建所有组件
python sparkle_build.py build

# 或者针对特定平台
python sparkle_build.py macos    # macOS only
python sparkle_build.py windows  # Windows only
```

### 2. 构建带OTA功能的应用

```bash
# 构建完整应用
python build_with_ota.py build

# 创建更新包
python build_with_ota.py package

# 一键构建和打包
python build_with_ota.py all
```

### 3. 启动测试服务器

```bash
# 启动本地更新服务器
python build_with_ota.py server
```

服务器将在 `http://localhost:8080` 启动，提供以下端点：

- `GET /api/check-update` - 检查更新
- `GET /api/download-latest` - 下载最新版本
- `GET /appcast.xml` - Sparkle/winSparkle配置
- `GET /health` - 健康检查

## 使用方法

### 代码集成

在您的主应用程序中：

```python
from utils.ota_updater import ota_updater

# 设置更新回调
def on_update_available(has_update):
    if has_update:
        # 显示更新通知
        pass

ota_updater.set_update_callback(on_update_available)

# 启动自动更新检查（生产模式下）
if not app_settings.is_dev_mode:
    ota_updater.start_auto_check()

# 手动检查更新
has_update = ota_updater.check_for_updates()

# 安装更新
success = ota_updater.install_update()
```

### GUI集成

更新功能已集成到主菜单：

1. **帮助菜单** -> **检查更新** - 手动检查更新
2. **帮助菜单** -> **关于ECBot** - 查看版本信息

### 自动更新

应用程序会：

- 每小时自动检查一次更新（可配置）
- 在开发模式下禁用自动检查
- 发现更新时显示通知对话框
- 允许用户选择立即安装或稍后安装

## 配置

### 环境变量

- `ECBOT_UPDATE_SERVER` - 更新服务器URL（默认：https://updates.ecbot.com）

### 版本管理

版本号存储在根目录的 `VERSION` 文件中：

```
1.0.0
```

### 更新服务器配置

编辑 `build_system/appcast.xml` 来配置更新信息：

```xml
<item>
    <title>ECBot 1.1.0</title>
    <description>新功能和错误修复</description>
    <pubDate>Mon, 01 Jan 2024 12:00:00 +0000</pubDate>
    <enclosure url="https://updates.ecbot.com/downloads/ECBot-1.1.0.dmg"
               sparkle:version="1.1.0"
               sparkle:os="macos"
               length="52428800"
               type="application/octet-stream"
               sparkle:edSignature="ABC123..." />
</item>
```

## 平台特定说明

### macOS (Sparkle)

- 需要安装Xcode和Sparkle框架
- 使用 `brew install sparkle` 安装依赖
- 支持DMG和ZIP格式的更新包
- 支持Ed25519数字签名

### Windows (winSparkle)

- 需要Visual Studio或MSVC编译器
- 自动下载winSparkle依赖
- 支持EXE和MSI格式的更新包
- 支持Authenticode代码签名

### Linux (通用)

- 使用HTTP API进行更新检查
- 支持TAR.GZ格式的更新包
- 通过安装脚本进行更新

## 安全性

### 数字签名

所有更新包都应该进行数字签名：

- **macOS**: 使用Ed25519签名
- **Windows**: 使用Authenticode签名
- **Linux**: 使用GPG签名

### HTTPS

生产环境必须使用HTTPS：

```python
# 配置HTTPS更新服务器
os.environ['ECBOT_UPDATE_SERVER'] = 'https://updates.ecbot.com'
```

## 故障排除

### 常见问题

1. **Sparkle框架未找到**
   ```bash
   brew install sparkle
   ```

2. **winSparkle编译失败**
   - 确保安装了Visual Studio
   - 检查winSparkle依赖是否下载完整

3. **更新检查失败**
   - 检查网络连接
   - 验证更新服务器URL
   - 查看日志文件

### 日志

OTA更新日志将记录在：

- **macOS**: `~/Library/Logs/ECBot/`
- **Windows**: `%LOCALAPPDATA%/ECBot/Logs/`
- **Linux**: `~/.local/share/ECBot/logs/`

## 开发和测试

### 本地测试

1. 启动测试服务器：
   ```bash
   python build_system/update_server.py
   ```

2. 设置环境变量：
   ```bash
   export ECBOT_UPDATE_SERVER=http://localhost:8080
   ```

3. 运行应用程序并测试更新功能

### 构建发布版本

```bash
# 完整构建流程
python build_system/build_with_ota.py all

# 验证构建结果
ls dist/
```

## 部署

### 更新服务器部署

1. 部署更新服务器到云平台
2. 配置HTTPS和域名
3. 上传更新包和appcast.xml
4. 测试更新流程

### 应用程序发布

1. 构建签名的更新包
2. 上传到更新服务器
3. 更新appcast.xml
4. 通知用户新版本可用

## 支持

如有问题，请查看：

1. [ECBot GitHub Issues](https://github.com/ecbot/ecbot/issues)
2. [Sparkle文档](https://sparkle-project.org/)
3. [winSparkle文档](https://winsparkle.org/)

---

© 2024 ECBot Team. All rights reserved.