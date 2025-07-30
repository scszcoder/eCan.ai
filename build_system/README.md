# ECBot 跨平台构建系统 v6.0

支持 macOS 和 Windows 双平台的统一构建系统，集成前端和后端构建流程。

## ✨ 功能特性

- 🌍 **跨平台支持** - 自动检测 macOS/Windows 平台并使用对应配置
- 🚀 **一键构建** - 自动构建前端 (React) 和后端 (Python)
- 📦 **智能缓存** - 基于文件哈希的增量构建
- 🔧 **多模式** - dev/dev-debug/prod 三种构建模式
- 📊 **详细报告** - 构建时间、文件大小、平台信息
- 🎯 **前提检查** - 自动检查依赖和环境

## 🚀 快速开始

### 日常开发（推荐）
```bash
# 增量构建 - 超快速度
python build.py dev

# 强制重建（首次或遇到问题）
python build.py dev --force
```

### 生产发布
```bash
# 完整优化构建
python build.py prod

# 强制重建
python build.py prod --force
```

### 工具命令
```bash
# 查看构建统计
python build.py --stats

# 清理构建缓存
python build.py --clean-cache

# 查看帮助
python build.py --help
```

## 📁 项目结构

```
项目根目录/
├── build.py                # 🌟 统一构建入口
└── build_system/
    ├── ecbot_build.py      # 🌟 单文件构建器
    ├── build_config.json   # 🌟 配置文件
    ├── verify_build_system.py  # 系统验证脚本
    ├── README.md           # 本文档
    └── CONFIG_GUIDE.md     # 配置指南
```

## 🔧 配置管理

### 配置文件
- **位置**: `build_system/build_config.json`
- **格式**: JSON格式，支持注释
- **修改**: 编辑后立即生效

### 配置示例
```json
{
  "_comment": "ECBot 构建配置文件",
  "app_info": {
    "name": "ECBot",
    "main_script": "main.py",
    "icon": "ECBot.ico"
  },
  "build_modes": {
    "dev": {"debug": true, "console": true, "clean": false},
    "prod": {"debug": false, "console": false, "clean": true}
  }
}
```

详细配置说明请参考：[CONFIG_GUIDE.md](CONFIG_GUIDE.md)

## 📊 构建模式对比

| 特性 | 开发模式 (dev) | 生产模式 (prod) |
|------|----------------|-----------------|
| **构建速度** | ⚡ 超快（增量） | 🐌 较慢（完整） |
| **包大小** | 📦 较大 | 📦 优化 |
| **调试信息** | ✅ 保留 | ❌ 移除 |
| **控制台** | ✅ 显示 | ❌ 隐藏 |
| **适用场景** | 日常开发调试 | 正式发布 |

## 🔧 构建流程

1. **🔍 加载配置** - 从 `build_config.json` 读取配置
2. **📊 变更检测** - (开发模式) 检测文件变更
3. **🧹 清理目录** - (生产模式) 清理构建目录
4. **🔨 执行构建** - 使用PyInstaller构建
5. **📊 结果分析** - 显示构建结果和包大小

## 💡 最佳实践

### 开发工作流
1. **首次构建**: `python build.py dev --force`
2. **日常开发**: `python build.py dev`
3. **发布前验证**: `python build.py prod`

### 配置管理
1. **修改配置**: 编辑 `build_system/build_config.json`
2. **验证配置**: `python build.py --stats`
3. **版本控制**: 将配置文件提交到Git

### 团队协作
- ✅ 提交配置文件到版本控制
- ✅ 统一使用相同的构建命令
- ✅ 定期更新和同步配置

## 🔍 故障排除

### 常见问题

#### 1. 配置文件格式错误
```
❌ 加载配置文件失败: Expecting ',' delimiter
```
**解决方案**: 检查JSON格式，确保语法正确

#### 2. 模块导入失败
```
ModuleNotFoundError: No module named 'your_module'
```
**解决方案**: 将模块添加到配置文件的 `hidden_imports` 列表

#### 3. 增量构建不生效
**解决方案**: 清理缓存后重新构建
```bash
python build.py --clean-cache
python build.py dev --force
```

### 获取帮助
- 📖 **配置指南**: [CONFIG_GUIDE.md](CONFIG_GUIDE.md)
- 🔧 **系统验证**: `python build_system/verify_build_system.py`
- 📊 **构建统计**: `python build.py --stats`

---

**🎯 记住**: 开发用 `dev` 模式，发布用 `prod` 模式！
