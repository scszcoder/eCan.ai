# ECBot OTA 使用说明（ota 目录）

本文档介绍 ota 目录下 OTA（Over‑The‑Air）更新能力的使用方法、开发模式配置、安全校验与测试方法。

## 目录结构

```
ota/
├── build/                    # 构建相关（样例/占位）
├── core/                     # OTA 核心：配置、错误、平台与包管理
│   ├── config.py             # 配置（支持开发模式）
│   ├── errors.py             # 统一错误码/异常
│   ├── package_manager.py    # 下载/校验/安装
│   ├── platforms.py          # Sparkle/WinSparkle/Generic 实现
│   └── updater.py            # OTAUpdater 调度器
├── dependencies/             # 本地依赖（含 Sparkle.framework）
├── gui/                      # PySide6 GUI 对话框
├── server/                   # Flask 测试/演示更新服务
│   ├── update_server.py      # /api/check, /appcast.xml 等
│   └── appcast.xml           # Sparkle/winSparkle appcast 示例
├── test_ota.py               # 简单自检脚本（本地桩）
└── README/本文件
```

## 快速开始

- 安装依赖（按需）
  - 可运行 server/update_server.py 需要 Flask
  - 数字签名验证推荐安装 cryptography
  - GUI 需要 PySide6（非必需）

- 最小示例
```python
from ota import OTAUpdater
u = OTAUpdater()
has_update = u.check_for_updates(silent=True)
if has_update:
    u.install_update()
```

## 开发模式（Dev Mode）

启用方式：设置环境变量

- macOS/Linux: `export ECBOT_DEV_MODE=1`
- Windows: `set ECBOT_DEV_MODE=1`

启用后默认行为：
- 默认更新服务器切换为本地 `http://127.0.0.1:8080`
- 强制使用通用更新器 GenericUpdater（避免 Sparkle/winSparkle 依赖）

可通过代码读取/设置：
```python
from ota.core.config import ota_config
print('dev?', ota_config.is_dev_mode())
ota_config.set('dev_update_server', 'http://127.0.0.1:8080')
```

关键配置项（ota_config.get/set）：
- update_server: 生产更新服务器（默认 https://updates.ecbot.com）
- dev_update_server: 开发模式更新服务器（默认 http://127.0.0.1:8080）
- force_generic_updater_in_dev: 开发模式强制使用 GenericUpdater（默认 True）
- allow_http_in_dev: 开发模式允许 HTTP（默认 True）
- public_key_path: 签名验证公钥 PEM
- dev_installer_enabled: 开发模式启用占位安装器（默认 False）
- dev_installer_quiet: 占位安装器尝试静默安装（默认 True）
- dmg_target_dir: macOS .dmg 安装目标目录（默认 /Applications）

## 测试更新服务器

运行演示服务（需 Flask）：
```bash
python ota/server/update_server.py
# 服务默认监听 http://0.0.0.0:8080
```
提供端点：
- GET /api/check 或 /api/check-update：检查更新（已实现语义版本比较）
- GET /appcast.xml：Sparkle/winSparkle appcast 文件
- GET /health：健康检查

语义版本比较已避免 1.10.0 与 1.2.0 的字符串误判。

## 签名与完整性校验

PackageManager.verify_package() 执行：
1) 计算 SHA256 哈希
2) 签名验证（如提供 signature）：
   - 若 signature 为 32/40/64 位 hex，视为简单哈希比对
   - 否则尝试数字签名验证（需要 cryptography）
     - 支持 RSA-PSS(SHA256)
     - 支持 Ed25519（Sparkle 2 的 edSignature，Base64 编码）
   - 公钥路径：参数 public_key_path 或配置 ota_config.public_key_path
3) 包格式校验（ZIP/TAR 完整性、路径安全）
4) 基础安全扫描（大小限制、扩展名白名单）

建议：
- Sparkle 使用 Ed25519，确保提供 PEM 格式的 Ed25519 公钥
- 生产环境安装 cryptography 并启用严格验证

## 安装策略与占位安装器

GenericUpdater 安装策略：
- .zip/.tar/.gz/.bz2：下载→验证→解压安装
- .dmg/.exe/.msi：在下载前即直接拒绝并提示“当前不支持”，避免无效下载

开发模式占位安装器（仅本地调试，默认关闭）：
- 开启：`ECBOT_DEV_MODE=1` 且 `ota_config.set('dev_installer_enabled', True)`
- macOS .dmg：hdiutil attach → 复制 .app 至 dmg_target_dir → hdiutil detach
- Windows .exe/.msi：尝试静默参数（/quiet 或 msiexec /quiet），实际参数依安装器而异
- 非测试环境请勿启用；执行安装器可能需要管理员权限

## GUI 使用

- 顶层导入已解耦 GUI：
  - `from ota import OTAUpdater` 不再强制要求 PySide6
  - GUI 组件可直接 `from ota import UpdateDialog, UpdateNotificationDialog`（懒加载）

## 自检与单元测试

- 快速自检（无依赖环境也可运行）
```bash
python ota/test_ota.py
```
该脚本对更新检查使用本地桩，避免联网/外部 CLI 依赖。

- 单元测试（推荐使用 python3）
```bash
python3 -m unittest -q tests/test_ota_core.py tests/test_ota_installers.py
```
覆盖内容：
- 权限异常映射（内建 PermissionError → PERMISSION_DENIED）
- 语义版本比较端点用例
- Ed25519 签名正反用例
- 安装器预检查与开发模式占位安装器开关

## 常见问题

- cryptography 未安装：将跳过严格签名验证（记录警告）。生产环境请安装 cryptography 并配置 public_key_path。
- HTTP/HTTPS：生产环境必须使用 HTTPS；仅在开发模式允许 HTTP（allow_http_in_dev=True）。
- Sparkle/WinSparkle 依赖：开发模式下默认使用 GenericUpdater，避免平台依赖。

## 变更摘要（相较于早期版本）
- 顶层 import 解耦 GUI（lazy import）
- 错误映射修正（内建 PermissionError 正确映射）
- 语义版本比较替换字符串比较
- 支持 Ed25519 数字签名验证
- 明确拒绝 .dmg/.exe/.msi（并提供开发模式占位安装器）
- 开发模式默认本地服务器与通用更新器

---
以上配置/接口仅供演示与开发使用。生产环境请按平台安全规范与签名策略完善构建与部署流程。