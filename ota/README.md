# ECBot OTA 更新包

ECBot的OTA（Over-The-Air）更新功能包，提供跨平台的自动更新支持。

## 包结构

```
ota/
├── __init__.py              # 包初始化，导出主要接口
├── README.md               # 本文件
├── OTA_README.md          # 详细使用文档
├── core/                  # 核心功能模块
│   ├── __init__.py
│   ├── updater.py         # OTA更新管理器
│   └── platforms.py       # 平台特定更新器
├── gui/                   # GUI组件
│   ├── __init__.py
│   └── dialog.py          # 更新对话框
├── platforms/             # 平台特定集成
│   ├── __init__.py
│   ├── sparkle_integration.swift    # macOS Sparkle
│   └── winsparkle_integration.cpp   # Windows winSparkle
├── build/                 # 构建工具（示例/占位）
│   ├── __init__.py
│   ├── sparkle_build.py   # Sparkle构建脚本（示例）
│   └── build_with_ota.py  # OTA构建脚本（示例）
└── server/                # 更新服务器
    ├── __init__.py
    ├── update_server.py    # 测试服务器
    └── appcast.xml        # 更新配置
```

## 快速使用

### 0. 构建应用程序

**重要**：在生产环境中，Sparkle/winSparkle依赖会自动打包到应用程序中，用户无需手动安装。

详细构建指南请参见：**[BUILD_GUIDE.md](../BUILD_GUIDE.md)**

```bash
# 一键构建（包含所有依赖）
python build_app.py
```

### 1. 基本导入

```python
from ota import ota_updater

# 检查更新
has_update = ota_updater.check_for_updates()

# 安装更新
success = ota_updater.install_update()

# 启动自动检查
ota_updater.start_auto_check()
```

### 2. 设置回调

```python
def on_update_available(has_update):
    if has_update:
        print("Update available!")
        # 显示更新通知

ota_updater.set_update_callback(on_update_available)
```

### 3. GUI集成

```python
from ota.gui.dialog import UpdateDialog

# 显示更新对话框
dialog = UpdateDialog(parent_window)
dialog.exec()
```

### 4. 安装依赖

```bash
# 自动安装所有依赖（推荐）
python ota/install_dependencies.py

# 或手动安装Python依赖
pip install -r requirements-windows.txt  # Windows
pip install -r requirements-macos.txt    # macOS
pip install -r requirements-base.txt     # Linux
```

**注意**: Sparkle和winSparkle不是Python包，需要单独安装。详见平台特定的安装指南。

### 5. 构建OTA组件（示例/占位）

**注意**: 以下构建脚本为示例代码，默认禁用。如需使用请设置环境变量：

```bash
# 启用示例构建脚本
export ECBOT_ALLOW_BUILD_SCRIPTS=1

# 构建所有平台
python ota/build/sparkle_build.py build

# 构建特定平台
python ota/build/sparkle_build.py macos
python ota/build/sparkle_build.py windows

# 清理构建文件
python ota/build/sparkle_build.py clean
```

**重要**: 这些脚本仅用于参考与本地实验，不建议在生产/CI中直接执行。

### 6. 启动测试服务器

```bash
python ota/server/update_server.py
```

## 主要组件

### OTAUpdater

核心更新管理器，提供统一的更新接口：

- `check_for_updates(silent=False)` - 检查更新
- `install_update()` - 安装更新
- `start_auto_check()` - 启动自动检查
- `set_update_callback(callback)` - 设置更新回调

### 平台更新器

- `SparkleUpdater` - macOS Sparkle集成
- `WinSparkleUpdater` - Windows winSparkle集成
- `GenericUpdater` - Linux通用HTTP API

### GUI组件

- `UpdateDialog` - 完整的更新对话框
- `UpdateNotificationDialog` - 更新通知对话框

## 配置

### 环境变量

```bash
export ECBOT_UPDATE_SERVER=https://updates.ecbot.com
```

### 版本管理

在项目根目录创建 `VERSION` 文件：

```
1.0.0
```


## 使用 GitHub Pages + Releases + CI 签名发布 appcast

以下流程已在本仓库中配置完成（见 .github/workflows）：

- 发布产物：
  - Windows/macOS 在 CI 中构建，Windows 使用 signtool（如配置证书）进行 Authenticode 签名；macOS 可在 CI 中 codesign + notarize（如配置证书/账户）
  - 构建完成后上传为 Release assets
- 生成 appcast：
  - 发布 Release 后触发 Publish Appcast 工作流，scripts/generate_appcast.py 将根据 Release assets 生成 appcast.xml 并发布到 gh-pages
  - 如配置 ED25519_PRIVATE_KEY（PEM 或 Base64）为仓库 Secret，会对每个 assets 计算 Sparkle 2 的 edSignature
- 默认 appcast URL：
  - https://scszcoder.github.io/ecbot/appcast.xml
  - 已在 ota/core/config.py 默认指向此地址；macOS/Windows 使用 Sparkle/winSparkle 时亦可直接配置该 URL

必备/可选 Secrets（Settings -> Secrets and variables -> Actions）
- ED25519_PRIVATE_KEY（可选）：Ed25519 私钥 PEM/BASE64，用于为 appcast enclosure 生成 edSignature
- Windows（可选）：WIN_CERT_PFX（Base64 的 .pfx），WIN_CERT_PASSWORD
- macOS（可选）：
  - MAC_CERT_P12（Base64 的 .p12），MAC_CERT_PASSWORD，MAC_CODESIGN_IDENTITY（例如：Developer ID Application: Your Company (TEAMID)）
  - APPLE_ID，APPLE_APP_SPECIFIC_PASSWORD，TEAM_ID（用于 notarytool 公证）

客户端校验
- macOS：Info.plist 配置 SUPublicEDKey（见 ota/platforms/SPARKLE_SETUP.md）
- GenericUpdater：在 ota_config.json 配置 public_key_path 指向 Ed25519 公钥 PEM

注意
- edSignature 必须在“最终签名后的产物”上计算；当前流程即：构建→签名→上传 Release→生成 appcast
- 大型二进制请放在 Releases，appcast.xml 放在 gh-pages（Pages 发布为静态文件）

## 使用 Ed25519（Sparkle 2）签名与客户端验签

本项目支持在 appcast 的 enclosure 上写入 Sparkle 2 的 edSignature（Ed25519）。流程如下：

1) 生成 Ed25519 密钥对（Python）
- 依赖：pip install cryptography
- 运行脚本：
  - python scripts/gen_ed25519_keys.py
- 脚本输出：
  - ed25519-private.pem（私钥，勿公开）
  - ed25519-public.pem（公钥，可随客户端分发）
  - 适合粘贴到 GitHub Secrets 的 Base64 私钥（ED25519_PRIVATE_KEY）

2) CI 中启用 edSignature 生成
- 仓库 Settings → Secrets → Actions → 新建 ED25519_PRIVATE_KEY，粘贴上一步打印的 Base64 私钥
- 发布 Release 后，Publish Appcast Job 会：
  - 下载 Release 资产
  - 计算每个下载包的 edSignature（Ed25519）
  - 写入 appcast 的 enclosure@\n    - sparkle:edSignature
    - sparkle:version, sparkle:os, sparkle:arch, length, type

3) 客户端启用签名校验（GenericUpdater）
- 在 ota_config.json 或运行时配置中设置：
  - signature_verification: true
  - public_key_path: 指向 ed25519-public.pem 的路径
- 默认会尝试以下路径（若未显式设置）：
  - 项目 keys/public_key.pem
  - 用户目录 ~/.ecbot/public_key.pem
  - /etc/ecbot/public_key.pem
- 下载后，PackageManager.verify_package() 将：
  - 读取公钥
  - 解码 enclosure 的 sparkle:edSignature（Base64）
  - 对下载包内容做 Ed25519 验签

4) Sparkle/winSparkle 客户端
- macOS 原生 Sparkle 2：可在 Info.plist 设置 SUPublicEDKey（如需，我们可提供示例）
- Windows winSparkle：依赖自身的签名校验机制（与 Authenticode 配合）。建议同时启用 appcast 的 edSignature，以便在我们的 GenericUpdater 逻辑中统一处理

注意：
- edSignature 必须基于“最终签名后的产物”计算；因此本项目在 Create Release 完成后再生成 appcast
- 私钥仅存放在 CI Secrets，不要提交到仓库；公钥可公开分发/随应用安装


## 平台支持

### macOS
- 使用Sparkle框架
- 支持DMG和ZIP更新包
- 数字签名验证
- **安装说明**: 参见 [platforms/SPARKLE_SETUP.md](platforms/SPARKLE_SETUP.md)

### Windows
- 使用winSparkle

### 按平台与架构拆分 appcast（推荐）

- 为避免不同平台/架构交叉升级，建议发布以下多个 feed：
  - appcast-macos-amd64.xml, appcast-macos-aarch64.xml
  - appcast-windows-amd64.xml, appcast-windows-aarch64.xml
- CI（release.yml）已在 Create Release 之后生成以上文件并发布到 gh-pages（并生成 appcast-macos.xml / appcast-windows.xml 聚合 feed）
- 客户端配置建议：
  - macOS Intel:  https://scszcoder.github.io/ecbot/appcast-macos-amd64.xml
  - macOS Apple:  https://scszcoder.github.io/ecbot/appcast-macos-aarch64.xml
  - Windows x64:  https://scszcoder.github.io/ecbot/appcast-windows-amd64.xml
  - Windows ARM64:https://scszcoder.github.io/ecbot/appcast-windows-aarch64.xml
- 我们的 GenericUpdater 会：
  1) 优先读取 platforms.<os>.appcast_urls[arch]
  2) 其次读取 platforms.<os>.appcast_url（若为平台 feed，自动探测 -<arch> 后缀）
  3) 最后回退到全局 appcast_url 或 JSON /api/check

- 支持EXE和MSI更新包
- Authenticode代码签名
- **安装说明**: 参见 [platforms/WINSPARKLE_SETUP.md](platforms/WINSPARKLE_SETUP.md)

### Linux
- 通用HTTP API
- 支持TAR.GZ更新包
- 通过安装脚本更新
- **无需额外安装**: 使用标准Python库

## 开发

### 添加新平台支持

1. 在 `ota/core/platforms.py` 中添加新的更新器类
2. 在 `ota/core/updater.py` 中注册新平台
3. 添加相应的构建脚本

### 自定义GUI

继承 `UpdateDialog` 类并重写相关方法：

```python
class CustomUpdateDialog(UpdateDialog):
    def setup_ui(self):
        super().setup_ui()
        # 添加自定义UI元素
```

## 测试

### 单元测试

```bash
python -m pytest tests/test_ota.py
```

### 集成测试

1. 启动测试服务器
2. 运行应用程序
3. 测试更新流程

## 部署

### 生产环境

1. 配置HTTPS更新服务器
2. 设置数字签名证书
3. 上传更新包和配置文件
4. 测试更新流程

### 监控

- 更新检查频率
- 更新成功率
- 用户反馈

## 故障排除

### 常见问题

1. **依赖安装错误**
   ```
   ERROR: No matching distribution found for pywinsparkle>=1.6.0
   ERROR: No matching distribution found for sparkle>=0.9.4
   ```
   **解决方案**: 这些不是Python包，需要单独安装：
   - macOS: 参见 [platforms/SPARKLE_SETUP.md](platforms/SPARKLE_SETUP.md)
   - Windows: 参见 [platforms/WINSPARKLE_SETUP.md](platforms/WINSPARKLE_SETUP.md)

2. **Sparkle框架未找到**
   ```bash
   brew install sparkle
   ```

3. **winSparkle编译失败**
   - 检查Visual Studio安装
   - 验证依赖完整性

4. **更新检查失败**
   - 检查网络连接
   - 验证服务器URL
   - 查看日志文件

5. **开发环境HTTPS错误**
   ```bash
   export ECBOT_DEV_MODE=true
   ```

### 日志

OTA日志位置：
- macOS: `~/Library/Logs/ECBot/`
- Windows: `%LOCALAPPDATA%/ECBot/Logs/`
- Linux: `~/.local/share/ECBot/logs/`

## 许可证

© 2024 ECBot Team. All rights reserved.