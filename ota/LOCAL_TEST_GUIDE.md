# 📋 eCan.ai OTA 功能本地测试指南

本指南将帮助你在本地环境测试 OTA（Over-The-Air）更新功能。

## 🎯 测试目标

- 启动本地 OTA 更新服务器
- 配置应用使用本地服务器
- 测试更新检查、下载和安装流程
- 验证签名和安全机制

---

## 📦 前置准备

### 1. 安装依赖
```bash
pip install flask requests cryptography
```

### 2. 检查项目结构
确保以下目录和文件存在：
```
eCan.ai/
├── ota/
│   ├── server/
│   │   ├── update_server.py      # 本地测试服务器
│   │   ├── appcast_generator.py  # appcast 生成器
│   │   └── appcast.xml           # appcast 配置文件
│   ├── certificates/
│   │   └── ed25519_public_key.pem # 公钥（用于验证）
│   └── core/
│       ├── updater.py
│       └── config.py
└── tests/
    ├── test_ota_core.py
    └── test_ota_more.py
```

---

## 🚀 第一步：启动本地 OTA 服务器

### 方法 1：直接运行服务器
```bash
cd /Users/liuqiang/WorkSpace/ecan/eCan.ai/ota/server
python update_server.py
```

服务器将在 `http://127.0.0.1:8080` 启动。

### 方法 2：使用 Flask 命令
```bash
cd /Users/liuqiang/WorkSpace/ecan/eCan.ai/ota/server
export FLASK_APP=update_server.py
export FLASK_ENV=development
flask run --host=0.0.0.0 --port=8080
```

### 验证服务器运行
在浏览器或使用 curl 访问：
```bash
# 检查更新 API
curl "http://127.0.0.1:8080/api/check?version=1.0.0&platform=darwin"

# 查看 appcast.xml
curl "http://127.0.0.1:8080/appcast.xml"

# 列出签名文件
curl "http://127.0.0.1:8080/admin/signatures"
```

---

## ⚙️ 第二步：配置应用使用本地服务器

### 方法 1：环境变量配置（推荐）
```bash
# 启用开发模式
export ECBOT_DEV_MODE=1

# 或在启动应用时设置
ECBOT_DEV_MODE=1 python main.py
```

### 方法 2：修改配置文件
配置文件位置：
- **macOS**: `~/Library/Application Support/ECBot/ota_config.json`
- **Windows**: `%USERPROFILE%/AppData/Local/ECBot/ota_config.json`
- **Linux**: `~/.config/ecbot/ota_config.json`

编辑配置文件：
```json
{
  "use_local_server": true,
  "local_server_url": "http://127.0.0.1:8080",
  "dev_mode": true,
  "allow_http_in_dev": true,
  "force_generic_updater_in_dev": true,
  "signature_verification": false
}
```

### 方法 3：代码中动态设置
```python
from ota.core.config import ota_config

# 切换到本地服务器
ota_config.set_use_local_server(True)
ota_config.set_local_server_url("http://127.0.0.1:8080")

# 启用开发模式
ota_config.set("dev_mode", True)
```

---

## 🧪 第三步：运行测试

### 1. 运行单元测试
```bash
cd /Users/liuqiang/WorkSpace/ecan/eCan.ai

# 运行所有 OTA 测试
python -m pytest tests/test_ota_core.py -v
python -m pytest tests/test_ota_more.py -v
# 或使用 unittest
python -m unittest ota/tests/test_ota_core.py
python -m unittest ota/tests/test_ota_more.py
```
### 交互式测试脚本
使用现成的测试脚本 `ota/test_local_ota.py`：
```python
#!/usr/bin/env python3
"""本地 OTA 功能测试脚本"""

import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径（当前文件在 ota 目录下）
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 设置开发模式
os.environ['ECBOT_DEV_MODE'] = '1'

{{ ... }}
from ota.core.updater import OTAUpdater
from ota.core.config import ota_config

def test_local_ota():
    """测试本地 OTA 功能"""
    
    # 1. 配置本地服务器
    print("=" * 60)
    print("📋 配置本地 OTA 服务器")
    print("=" * 60)
    ota_config.set_use_local_server(True)
    ota_config.set_local_server_url("http://127.0.0.1:8080")
    
    update_server = ota_config.get_update_server()
    print(f"✅ 更新服务器: {update_server}")
    print(f"✅ 开发模式: {ota_config.is_dev_mode()}")
    print(f"✅ 本地服务器: {ota_config.is_using_local_server()}")
    print()
    
    # 2. 创建更新器
    print("=" * 60)
    print("🚀 初始化 OTA 更新器")
    print("=" * 60)
    updater = OTAUpdater()
    status = updater.get_status()
    print(f"✅ 平台: {status['platform']}")
    print(f"✅ 当前版本: {status['app_version']}")
    print()
    
    # 3. 检查更新
    print("=" * 60)
    print("🔍 检查更新...")
    print("=" * 60)
    has_update, update_info = updater.check_for_updates(return_info=True)
    
    if has_update:
        print(f"✅ 发现新版本!")
        print(f"   最新版本: {update_info.get('latest_version', 'N/A')}")
        print(f"   更新描述: {update_info.get('description', 'N/A')}")
        print(f"   下载地址: {update_info.get('download_url', 'N/A')}")
        print(f"   文件大小: {update_info.get('file_size', 0)} bytes")
    else:
        print("ℹ️  当前已是最新版本")
        if update_info:
            print(f"   错误信息: {update_info}")
    print()
    
    # 4. 显示状态
    print("=" * 60)
    print("📊 更新器状态")
    print("=" * 60)
    status = updater.get_status()
    for key, value in status.items():
        print(f"   {key}: {value}")
    print()
    
    print("=" * 60)
    print("✅ 测试完成!")
    print("=" * 60)

if __name__ == "__main__":
    try:
        test_local_ota()
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
```

运行测试脚本：
```bash
python ota/test_local_ota.py
# 或从 ota 目录运行
cd ota && python test_local_ota.py
```

---

## 🔧 第四步：高级测试场景

### 1. 测试更新检查 API
```bash
# 检查是否有更新（当前版本 1.0.0）
curl "http://127.0.0.1:8080/api/check?version=1.0.0&platform=darwin"

# 检查是否有更新（当前版本 1.1.0，应该无更新）
curl "http://127.0.0.1:8080/api/check?version=1.1.0&platform=darwin"
```

### 2. 测试 appcast.xml 生成
```bash
# 获取默认 appcast
curl "http://127.0.0.1:8080/appcast.xml"

# 手动触发生成（POST 请求）
curl -X POST http://127.0.0.1:8080/admin/generate-appcast \
  -H "Content-Type: application/json" \
  -d '{"version": "1.1.0", "base_url": "http://127.0.0.1:8080"}'
```

### 3. 测试签名验证
```python
# 在 Python 中测试签名验证
from ota.core.package_manager import PackageManager
from pathlib import Path

pm = PackageManager()

# 测试文件的签名验证
test_file = Path("test_package.zip")
signature_b64 = "your_signature_here"
public_key_path = "ota/certificates/ed25519_public_key.pem"

is_valid = pm._verify_digital_signature(
    test_file, 
    signature_b64, 
    public_key_path
)
print(f"签名验证结果: {'✅ 有效' if is_valid else '❌ 无效'}")
```

---

## 📝 常见问题排查

### 问题 1：服务器启动失败
```
Error: Address already in use
```
**解决方案**：
```bash
# 查找占用 8080 端口的进程
lsof -i :8080

# 杀死进程
kill -9 <PID>

# 或使用其他端口
python update_server.py --port 8081
```

### 问题 2：无法连接到本地服务器
**检查清单**：
1. 确认服务器正在运行：`curl http://127.0.0.1:8080/api/check`
2. 检查防火墙设置
3. 确认配置正确：`ota_config.is_using_local_server()` 返回 `True`
4. 检查环境变量：`echo $ECBOT_DEV_MODE`

### 问题 3：签名验证失败
```
UpdateError: SIGNATURE_VERIFICATION_FAILED
```
**解决方案**：
```python
# 临时禁用签名验证（仅用于测试）
ota_config.set("signature_verification", False)
ota_config.save_config()
```

### 问题 4：HTTPS 要求错误
```
NetworkError: HTTPS required in production mode
```
**解决方案**：
```bash
# 确保开发模式已启用
export ECBOT_DEV_MODE=1

# 或在配置中允许 HTTP
ota_config.set("allow_http_in_dev", True)
```

---

## 🎨 推荐测试流程

### 完整测试流程
1. **启动服务器** → 运行 `python ota/server/update_server.py`
2. **配置环境** → 设置 `ECBOT_DEV_MODE=1`
3. **运行单元测试** → 验证核心功能正常
4. **运行交互测试** → 使用 `test_local_ota.py`
5. **API 测试** → 使用 curl 测试各个端点
6. **UI 测试** → 启动应用，测试 GUI 更新对话框

### 快速测试命令
```bash
# 一键启动测试环境
cd /Users/liuqiang/WorkSpace/ecan/eCan.ai

# Terminal 1: 启动服务器
python ota/server/update_server.py

# Terminal 2: 运行功能测试
ECBOT_DEV_MODE=1 python ota/test_local_ota.py

# 或运行单元测试
ECBOT_DEV_MODE=1 python -m pytest tests/test_ota_more.py -v
```

---

## 📚 相关文档

- **快速开始**: `/ota/QUICK_START.md`
- **测试脚本**: `/ota/test_local_ota.py`
- **启动脚本**: `/ota/start_ota_test.sh`
- **OTA 配置**: `/ota/core/config.py`
- **更新器实现**: `/ota/core/updater.py`
- **包管理**: `/ota/core/package_manager.py`
- **单元测试**: `/tests/test_ota_*.py`
- **证书说明**: `/ota/certificates/README.md`

---

## 🆘 需要帮助？

如果遇到问题：
1. 查看日志：应用日志会显示详细的 OTA 操作信息
2. 检查服务器日志：`update_server.py` 会输出请求日志
3. 运行诊断：`python -c "from ota.core.config import ota_config; print(ota_config.validate_config())"`

---

**祝测试顺利！** 🚀
