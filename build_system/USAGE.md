# ECBot 构建系统使用示例

## 🚀 快速使用

### 1. 直接构建

#### macOS 平台
```bash
# 构建 macOS app
python3 build.py prod

# 开发模式构建
python3 build.py dev

# 强制重新构建
python3 build.py prod --force
```

#### Windows 平台
```bash
# 构建 Windows exe
python build.py prod

# 开发模式构建
python build.py dev

# 强制重新构建
python build.py prod --force
```

### 2. Docker 构建（macOS 上构建 Windows exe）

```bash
# 生产模式构建 Windows exe
./build_system/scripts/build_windows_docker.sh prod

# 开发模式构建 Windows exe
./build_system/scripts/build_windows_docker.sh dev

# 强制重新构建
./build_system/scripts/build_windows_docker.sh prod --force

# 重新构建 Docker 镜像
./build_system/scripts/build_windows_docker.sh --rebuild prod

# 清理 Docker 资源
./build_system/scripts/build_windows_docker.sh --clean
```

### 3. 系统测试

```bash
# 运行构建系统测试
python3 build_system/scripts/test_build_system.py
```

## 📁 文件结构

```
build_system/
├── ecbot_build.py                    # 核心构建器
├── build_config.json                 # 构建配置
├── Dockerfile.windows-build          # Docker 构建环境
├── docker-compose.windows-build.yml  # Docker Compose 配置
├── scripts/
│   ├── build_windows_docker.sh      # Docker 构建脚本
│   └── test_build_system.py         # 系统测试脚本
├── README.md                         # 构建系统说明
├── CONFIG_GUIDE.md                   # 配置指南
└── USAGE.md                          # 本文档
```

## 🎯 使用场景

### 场景 1: macOS 开发者
```bash
# 日常开发 - 构建 macOS app
python3 build.py dev

# 发布准备 - 构建 macOS app
python3 build.py prod

# 跨平台发布 - 构建 Windows exe
./build_system/scripts/build_windows_docker.sh prod
```

### 场景 2: Windows 开发者
```bash
# 日常开发 - 构建 Windows exe
python build.py dev

# 发布准备 - 构建 Windows exe
python build.py prod
```

### 场景 3: 跨平台发布
```bash
# macOS 上构建所有平台版本
python3 build.py prod                    # macOS app
./build_system/scripts/build_windows_docker.sh prod   # Windows exe
```

## 🔧 故障排除

### 权限问题
```bash
# 设置执行权限
chmod +x build.py
chmod +x build_system/scripts/build_windows_docker.sh
```

### Docker 构建问题
```bash
# 清理并重新构建
./build_system/scripts/build_windows_docker.sh --clean
./build_system/scripts/build_windows_docker.sh --rebuild prod
```

### 系统测试
```bash
# 运行完整系统测试
python3 build_system/scripts/test_build_system.py
```

## 📊 构建模式

| 模式 | 控制台 | 优化 | 适用场景 |
|------|--------|------|----------|
| `dev` | ✅ 显示 | ❌ 不优化 | 日常开发调试 |
| `dev-debug` | ✅ 显示 | ❌ 不优化 | 问题调试 |
| `prod` | ❌ 隐藏 | ✅ 优化 | 正式发布 |

## 🎉 特性总结

- ✅ **统一入口**: 一个 `build.py` 支持所有平台
- ✅ **自动检测**: 根据平台自动选择构建目标
- ✅ **Docker 支持**: macOS 上构建 Windows exe
- ✅ **增量构建**: 智能缓存提升构建速度
- ✅ **详细报告**: 构建时间、文件大小、平台信息
- ✅ **跨平台**: 支持 macOS 和 Windows 双平台
- ✅ **模块化**: 所有构建脚本统一在 `build_system` 目录

---

**🎯 记住**: 开发用 `dev` 模式，发布用 `prod` 模式！ 