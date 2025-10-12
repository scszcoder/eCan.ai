# 📦 eCan OTA (Over-The-Air) 自动更新系统

eCan 应用的完整 OTA 自动更新模块，支持 Windows 和 macOS 平台的全自动更新流程。

## 🎯 功能特性

- ✅ **Windows 支持**: EXE (Setup.exe 优先) / MSI 安装包
- ✅ **macOS 支持**: PKG (推荐) / DMG 安装包
- ✅ **签名验证**: Ed25519 数字签名 + SHA256 哈希验证
- ✅ **S3 分发**: AWS S3 作为主要更新源，GitHub Pages 作为备份
- ✅ **自动更新**: 后台定时检查、自动下载、静默安装
- ✅ **版本管理**: 统一从 VERSION 文件读取版本号
- ✅ **安全机制**: 代码签名、HTTPS 传输、文件完整性验证

---

## 📁 目录结构

{{ ... }}
```
ota/
├── README.md                  # 本文档
├── QUICK_START.md            # 快速开始指南 ⭐
├── LOCAL_TEST_GUIDE.md       # 详细测试文档
├── test_local_ota.py         # 本地测试脚本 ⭐
├── start_ota_test.sh         # 一键测试启动脚本 ⭐
│
├── core/                      # OTA 核心功能
│   ├── updater.py            # 主更新器
│   ├── config.py             # 配置管理
│   ├── package_manager.py    # 包管理和验证
│   ├── generic_updater.py    # 通用更新器（Linux）
│   ├── darwin_updater.py     # macOS Sparkle 更新器
│   ├── windows_updater.py    # Windows WinSparkle 更新器
│   └── errors.py             # 错误定义
│
├── server/                    # 本地测试服务器
│   ├── update_server.py      # Flask 测试服务器
│   ├── appcast_generator.py  # Appcast XML 生成器
│   └── appcast.xml           # Appcast 配置文件
│
├── gui/                       # GUI 组件
│   └── dialog.py             # 更新对话框
│
└── certificates/              # 公钥证书
    ├── README.md             # 证书说明
    └── ed25519_public_key.pem # Ed25519 公钥
```

---

## 🚀 快速开始

### 1. 安装依赖
```bash
pip3 install flask requests cryptography
```

### 2. 一键测试（推荐）
```bash
cd /Users/liuqiang/WorkSpace/ecan/eCan.ai
./ota/start_ota_test.sh
```

选择 **选项 3** 即可自动完成所有测试！

### 3. 手动测试
```bash
# Terminal 1: 启动测试服务器
python3 ota/server/update_server.py

# Terminal 2: 运行功能测试
export ECBOT_DEV_MODE=1
python3 ota/test_local_ota.py
```

---

## 📚 文档导航

### 生产环境文档（推荐）

| 文档 | 用途 | 推荐指数 |
|------|------|---------|
| **[docs/README.md](docs/README.md)** | OTA 系统完整文档 - 项目概述 | ⭐⭐⭐⭐⭐ |
| **[docs/QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md)** | 快速参考 - 常用命令和 API | ⭐⭐⭐⭐⭐ |
| **[docs/COMPLETE_GUIDE.md](docs/COMPLETE_GUIDE.md)** | 完整指南 - 详细使用说明 | ⭐⭐⭐⭐ |
| **[docs/DEPLOYMENT_CHECKLIST.md](docs/DEPLOYMENT_CHECKLIST.md)** | 部署清单 - 33 项检查项 | ⭐⭐⭐⭐ |
| **[docs/PLATFORM_SUPPORT.md](docs/PLATFORM_SUPPORT.md)** | 平台支持 - Windows/macOS 详解 | ⭐⭐⭐ |
| **[docs/S3_SETUP.md](docs/S3_SETUP.md)** | S3 配置 - AWS 配置指南 | ⭐⭐⭐ |

### 开发测试文档

| 文档 | 用途 | 推荐指数 |
|------|------|---------|
| [QUICK_START.md](QUICK_START.md) | 快速上手，5分钟启动测试 | ⭐⭐⭐⭐⭐ |
| [LOCAL_TEST_GUIDE.md](LOCAL_TEST_GUIDE.md) | 详细的本地测试指南 | ⭐⭐⭐⭐ |
| [certificates/README.md](certificates/README.md) | 数字签名证书说明 | ⭐⭐⭐ |

---

## 🔧 核心 API

### 基本使用
```python
from ota.core.updater import OTAUpdater
from ota.core.config import ota_config

# 配置本地服务器（测试用）
ota_config.set_use_local_server(True)

# 创建更新器
updater = OTAUpdater()

# 检查更新
has_update = updater.check_for_updates()
if has_update:
    print("发现新版本！")
    
# 获取状态
status = updater.get_status()
print(f"当前版本: {status['app_version']}")
```

### 配置管理
```python
from ota.core.config import ota_config

# 切换到本地服务器
ota_config.set_use_local_server(True)
ota_config.set_local_server_url("http://127.0.0.1:8080")

# 切换到远程服务器
ota_config.set_use_local_server(False)

# 启用开发模式
ota_config.set("dev_mode", True)

# 保存配置
ota_config.save_config()
```

---

## 🧪 测试

### 单元测试
```bash
# 运行核心测试
python3 -m unittest tests.test_ota_core

# 运行扩展测试
python3 -m unittest tests.test_ota_more

# 运行所有测试
python3 -m unittest discover tests -p "test_ota*.py"
```

### 功能测试
```bash
# 使用测试脚本
python3 ota/test_local_ota.py

# 或使用启动脚本
./ota/start_ota_test.sh
```

### API 测试
```bash
# 检查更新
curl "http://127.0.0.1:8080/api/check?version=1.0.0&platform=darwin"

# 查看 appcast
curl "http://127.0.0.1:8080/appcast.xml"

# 健康检查
curl "http://127.0.0.1:8080/health"
```

---

## 🔐 安全机制

### 签名验证
- **算法**: Ed25519 椭圆曲线数字签名
- **公钥**: `certificates/ed25519_public_key.pem`
- **私钥**: `build_system/certificates/` (构建时使用)
- **验证**: 自动验证下载的更新包签名

### 配置选项
```python
# 启用签名验证（生产环境推荐）
ota_config.set("signature_verification", True)

# 要求签名（缺少签名时拒绝更新）
ota_config.set("signature_required", True)

# 仅在开发环境允许 HTTP
ota_config.set("allow_http_in_dev", True)
```

---

## 🌐 平台支持

| 平台 | 更新器 | 状态 | 特性 |
|------|--------|------|------|
| **macOS** | Sparkle | ✅ | 原生 macOS 更新框架 |
| **Windows** | WinSparkle | ✅ | Sparkle 的 Windows 移植版 |
| **Linux** | GenericUpdater | ✅ | HTTP API 通用更新器 |

---

## 📋 开发流程

### 1. 本地开发测试
```bash
# 启动本地测试服务器
./ota/start_ota_test.sh

# 应用中启用开发模式
export ECBOT_DEV_MODE=1
```

### 2. 生成安装包
```bash
# 使用构建系统生成安装包
cd build_system
python3 build.py --platform darwin --arch amd64
```

### 3. 生成签名
```bash
# 签名文件会自动生成在 dist/ 目录
# 格式: signatures_<version>.json
```

### 4. 部署更新
```bash
# 上传安装包到服务器
# 上传签名文件
# 生成并部署 appcast.xml
```

---

## ⚙️ 配置文件

配置文件位置：
- **macOS**: `~/Library/Application Support/ECBot/ota_config.json`
- **Windows**: `%USERPROFILE%/AppData/Local/ECBot/ota_config.json`
- **Linux**: `~/.config/ecbot/ota_config.json`

配置示例：
```json
{
  "use_local_server": false,
  "local_server_url": "http://127.0.0.1:8080",
  "remote_server_url": "https://updates.ecbot.com",
  "dev_mode": false,
  "signature_verification": true,
  "signature_required": true,
  "auto_check": true,
  "check_interval": 3600
}
```

---

## 🐛 故障排查

### 服务器无法启动
```bash
# 检查端口占用
lsof -i :8080

# 杀死占用进程
kill -9 <PID>
```

### 签名验证失败
```bash
# 检查公钥文件
ls -l ota/certificates/ed25519_public_key.pem

# 临时禁用签名验证（仅测试）
ota_config.set("signature_verification", False)
```

### 连接被拒绝
```bash
# 确保开发模式已启用
export ECBOT_DEV_MODE=1

# 确保允许 HTTP
ota_config.set("allow_http_in_dev", True)
```

---

## 📞 技术支持

- **详细文档**: [LOCAL_TEST_GUIDE.md](LOCAL_TEST_GUIDE.md)
- **快速参考**: [QUICK_START.md](QUICK_START.md)
- **单元测试**: `/tests/test_ota_*.py`
- **代码示例**: `test_local_ota.py`

---

## 📄 许可证

本项目遵循与 eCan.ai 主项目相同的许可证。

---

**开始使用**: 运行 `./ota/start_ota_test.sh` 快速体验！ 🚀
