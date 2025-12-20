# OTA 更新系统

eCan 应用的 OTA（Over-The-Air）更新系统

---

## 📁 目录结构

```
ota/
├── config/          # 配置
├── core/            # 核心功能
├── gui/             # 用户界面
├── server/          # 更新服务器
├── platforms/       # 平台支持
├── scripts/         # 脚本工具
├── tests/           # 测试
└── docs/            # 文档
```

---

## 🚀 快速开始

### 测试配置
```bash
python3 ota/tests/test_config.py
```

### 启动服务器
```bash
./ota/scripts/start_ota_server.sh
```

### 设置环境
```bash
./ota/scripts/set_environment.sh --environment development
```

### 代码使用
```python
from ota.config import ota_config, is_ota_enabled

if is_ota_enabled():
    server = ota_config.get_update_server()
```

---

## 📋 配置文件

**位置**: `ota/config/ota_config.yaml`

```yaml
ota_enabled: true
environment: development

environments:
  development:
    ota_server: "http://127.0.0.1:8080"
  production:
    ota_server: "https://updates.ecan.ai"
```

---

## 📚 文档

- **[docs/README.md](docs/README.md)** - 文档索引
- **[docs/OTA_QUICK_START.md](docs/OTA_QUICK_START.md)** - 快速开始 ⭐
- **[docs/OTA_SIMPLE_CONFIG_GUIDE.md](docs/OTA_SIMPLE_CONFIG_GUIDE.md)** - 完整指南
