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
├── build/                 # 构建工具
│   ├── __init__.py
│   ├── sparkle_build.py   # Sparkle构建脚本
│   └── build_with_ota.py  # OTA构建脚本
└── server/                # 更新服务器
    ├── __init__.py
    ├── update_server.py    # 测试服务器
    └── appcast.xml        # 更新配置
```

## 快速使用

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

### 4. 构建OTA组件

```bash
# 构建所有平台
python ota/build/sparkle_build.py build

# 构建特定平台
python ota/build/sparkle_build.py macos
python ota/build/sparkle_build.py windows

# 清理构建文件
python ota/build/sparkle_build.py clean
```

### 5. 启动测试服务器

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

## 平台支持

### macOS
- 使用Sparkle框架
- 支持DMG和ZIP更新包
- 数字签名验证

### Windows  
- 使用winSparkle
- 支持EXE和MSI更新包
- Authenticode代码签名

### Linux
- 通用HTTP API
- 支持TAR.GZ更新包
- 通过安装脚本更新

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

1. **Sparkle框架未找到**
   ```bash
   brew install sparkle
   ```

2. **winSparkle编译失败**
   - 检查Visual Studio安装
   - 验证依赖完整性

3. **更新检查失败**
   - 检查网络连接
   - 验证服务器URL
   - 查看日志文件

### 日志

OTA日志位置：
- macOS: `~/Library/Logs/ECBot/`
- Windows: `%LOCALAPPDATA%/ECBot/Logs/`
- Linux: `~/.local/share/ECBot/logs/`

## 许可证

© 2024 ECBot Team. All rights reserved. 