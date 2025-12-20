# OTA 开发测试服务器

## 概述

这个目录包含用于**本地开发和测试**的 OTA 服务器工具，**不是构建工具**。

## 目录说明

### 🌐 本地测试服务器

**`update_server.py`** - Flask 本地测试服务器
- **用途**: 在本地开发环境模拟 OTA 更新服务器
- **功能**: 
  - 提供 appcast.xml 端点
  - 提供安装包下载
  - 动态生成测试数据
- **运行**: `python3 ota/server/update_server.py`
- **依赖**: 应用代码（utils, config 等）

**`appcast_generator.py`** - 动态 Appcast 生成器
- **用途**: 为本地测试服务器动态生成 appcast.xml
- **功能**: 
  - 扫描本地文件
  - 生成测试用 appcast
  - 计算文件哈希
- **依赖**: 应用代码（utils.logger_helper）

**`appcast_template.xml`** - Appcast 模板
- **用途**: 本地测试服务器使用的 Jinja2 模板

**`appcast.xml`** - 测试数据
- **用途**: 本地测试用的静态 appcast 文件

### 🚀 启动脚本

**`../scripts/start_ota_server.sh`** - 启动脚本
- **用途**: 快速启动本地测试服务器
- **运行**: `./ota/scripts/start_ota_server.sh`

## 与构建系统的区别

### ❌ 这不是构建工具

这个目录的文件：
- ✅ 在**本地开发环境**运行
- ✅ 可以依赖应用代码
- ✅ 用于开发和测试
- ❌ **不在 CI/CD 环境运行**
- ❌ **不参与发布流程**

### ✅ 构建工具在 build_system/

真正的构建工具在 `build_system/scripts/`：
- `upload_to_s3.py` - 上传到 S3
- `generate_appcast.py` - 生成生产环境 appcast
- `auto_update_signatures.py` - 自动更新签名（已移动）
- 这些工具：
  - 在 CI/CD 环境运行
  - 不依赖应用代码
  - 只依赖 boto3 和 PyYAML
  - 生成发布产物

## 使用场景

### 本地开发测试

1. **启动测试服务器**:
   ```bash
   python3 ota/server/update_server.py
   ```

2. **配置应用使用本地服务器**:
   在 `ota/config/ota_config.yaml` 中设置：
   ```yaml
   environment: development
   environments:
     development:
       ota_server: "http://127.0.0.1:8080"
       appcast_base: "http://127.0.0.1:8080"
   ```

3. **测试更新流程**:
   - 将构建的安装包放到 `ota/server/` 目录
   - 启动应用，触发更新检查
   - 验证更新流程

### 开发新功能

- 修改 `appcast_generator.py` 测试新的 appcast 格式
- 修改 `update_server.py` 测试新的服务器端点
- 使用本地服务器快速迭代

## 架构说明

```
开发环境:
  应用 → 本地测试服务器 (ota/server/update_server.py)
       → 动态生成 appcast
       → 提供本地文件下载

生产环境:
  应用 → AWS S3
       → 静态 appcast.xml (由 build_system/scripts/generate_appcast.py 生成)
       → 安装包 (由 build_system/scripts/upload_to_s3.py 上传)
```

## 注意事项

1. **不要在生产环境使用**: 这些工具仅用于开发测试
2. **依赖应用代码**: 这些工具可以导入应用的其他模块
3. **不需要解耦**: 与构建工具不同，这些工具不需要与应用代码解耦
4. **不打包到应用**: 这些文件不会被 PyInstaller 打包到最终应用中

## 相关文档

- [OTA 系统文档](../../docs/OTA_SYSTEM.md)
- [构建系统文档](../../build_system/docs/)
- [Appcast 管理指南](../../build_system/docs/APPCAST_MANAGEMENT.md)
