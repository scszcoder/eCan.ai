# 🚀 OTA 本地测试快速开始

## 最快速的测试方法

### 方法 1：使用启动脚本（推荐）
```bash
cd /Users/liuqiang/WorkSpace/ecan/eCan.ai
./ota/start_ota_test.sh
```

选择 **选项 3** "同时启动服务器和测试"，一键完成所有测试！

### 方法 2：手动两步测试
```bash
# Terminal 1: 启动服务器
cd /Users/liuqiang/WorkSpace/ecan/eCan.ai/ota/server
python3 update_server.py

# Terminal 2: 运行测试
cd /Users/liuqiang/WorkSpace/ecan/eCan.ai
export ECBOT_DEV_MODE=1
python3 ota/test_local_ota.py
```

---

## 测试前准备

### 1. 安装依赖
```bash
pip3 install flask requests cryptography
```

### 2. 验证环境
```bash
# 检查 Python
python3 --version

# 检查依赖
python3 -c "import flask, requests, cryptography; print('✅ 依赖完整')"
```

---

## 快速测试命令

### API 测试
```bash
# 检查更新（应该返回有更新）
curl "http://127.0.0.1:8080/api/check?version=1.0.0&platform=darwin"

# 查看 appcast.xml
curl "http://127.0.0.1:8080/appcast.xml"

# 服务器健康检查
curl "http://127.0.0.1:8080/health"
```

### 单元测试
```bash
cd /Users/liuqiang/WorkSpace/ecan/eCan.ai

# 运行核心测试
python3 -m unittest tests.test_ota_core

# 运行扩展测试
python3 -m unittest tests.test_ota_more

# 运行所有测试
python3 -m unittest discover tests -p "test_ota*.py"
```

---

## 常见问题快速解决

### 端口被占用
```bash
# 查找占用进程
lsof -i :8080

# 杀死进程
kill -9 <PID>
```

### 服务器无响应
```bash
# 检查服务器是否运行
ps aux | grep update_server

# 检查端口监听
netstat -an | grep 8080
# 或
lsof -i :8080
```

### 签名验证失败
```python
# 临时禁用签名验证（仅测试用）
from ota.core.config import ota_config
ota_config.set("signature_verification", False)
ota_config.save_config()
```

---

## 测试结果预期

### ✅ 成功的测试输出
```
📋 第一步：配置本地 OTA 服务器
============================================================
✅ 更新服务器: http://127.0.0.1:8080
✅ 开发模式: True
✅ 本地服务器: True

🚀 第二步：初始化 OTA 更新器
============================================================
✅ 平台: Darwin
✅ 当前版本: 1.0.0

🔍 第三步：检查更新
============================================================
✅ 发现新版本!
   最新版本: 1.1.0
   更新描述: Added OTA update functionality and bug fixes
```

### ❌ 常见错误和解决
| 错误 | 原因 | 解决方案 |
|------|------|----------|
| `ConnectionRefusedError` | 服务器未启动 | 运行 `python3 ota/server/update_server.py` |
| `ModuleNotFoundError: flask` | 缺少依赖 | 运行 `pip3 install flask` |
| `HTTPS required` | 未启用开发模式 | 设置 `export ECBOT_DEV_MODE=1` |
| `Address already in use` | 端口占用 | 使用 `lsof -i :8080` 查找并杀死进程 |

---

## 下一步

测试成功后，你可以：

1. **查看详细文档**
   ```bash
   cat ota/LOCAL_TEST_GUIDE.md
   ```

2. **集成到应用**
   - 在 MainGUI 中添加 OTA 更新检查
   - 添加更新通知 UI
   - 配置自动更新策略

3. **准备生产环境**
   - 生成 appcast.xml
   - 配置远程更新服务器
   - 签名安装包

---

## 相关文件

- **详细指南**: `ota/LOCAL_TEST_GUIDE.md`
- **测试脚本**: `ota/test_local_ota.py`
- **启动脚本**: `ota/start_ota_test.sh`
- **服务器**: `ota/server/update_server.py`
- **配置**: `ota/core/config.py`

---

**祝测试愉快！** 🎉

有问题？查看 `LOCAL_TEST_GUIDE.md` 获取更多帮助。
