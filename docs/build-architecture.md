# eCan.ai 构建系统架构设计

## 概述

eCan.ai构建系统采用分层架构设计，实现了统一入口、通用构建脚本和环境分离的目标。这种设计使得构建系统既可以在本地运行，也可以在CI/CD环境中运行，同时保持了良好的可维护性和扩展性。

## 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Actions                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  Windows    │  │   macOS     │  │   Linux     │        │
│  │ Environment │  │ Environment │  │ Environment │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    build.py (入口文件)                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ 环境检测    │  │ 参数解析    │  │ 构建执行    │        │
│  │Environment  │  │Arguments    │  │Executor     │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                ecan_build.py (通用构建脚本)                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ 环境管理    │  │ 配置管理    │  │ 前端构建    │        │
│  │Environment  │  │Config       │  │Frontend     │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ PyInstaller │  │ 安装包构建  │  │ 缓存管理    │        │
│  │Builder      │  │Installer    │  │Cache        │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
└─────────────────────────────────────────────────────────────┘
```

## 核心组件

### 1. build.py (入口文件)

**职责**：
- 统一的构建入口点
- 环境检测和验证
- 参数解析和管理
- 构建执行协调

**主要类**：
- `BuildEnvironment`: 环境检测和管理
- `BuildArguments`: 参数解析和管理
- `BuildExecutor`: 构建执行器

**特点**：
- 跨平台兼容
- CI环境自动检测
- 详细的错误处理和日志
- 支持环境检查模式

### 2. ecan_build.py (通用构建脚本)

**职责**：
- 跨平台构建逻辑
- 依赖管理
- 构建产物生成
- 缓存机制

**主要类**：
- `BuildConfig`: 配置管理
- `EnvironmentManager`: 环境管理
- `FrontendBuilder`: 前端构建
- `PyInstallerBuilder`: PyInstaller构建
- `InstallerBuilder`: 安装包构建
- `CacheManager`: 缓存管理

**特点**：
- 完全独立，可在任何环境运行
- 支持增量构建
- 平台特定优化
- 模块化设计

### 3. GitHub Actions (环境准备)

**职责**：
- 构建环境准备
- 依赖安装
- 工具配置
- 构建触发

**工作流**：
- `build-windows.yml`: Windows环境构建
- `build-macos.yml`: macOS环境构建
- `build-all.yml`: 多平台统一构建

**特点**：
- 环境隔离
- 并行构建
- 缓存优化
- 错误恢复

## 工作流程

### 本地构建流程

```bash
# 1. 环境检查
python build.py --check-env

# 2. 开发模式构建
python build.py dev

# 3. 生产模式构建
python build.py prod --force

# 4. 跳过前端构建
python build.py prod --skip-frontend
```

### CI构建流程

```yaml
# 1. 环境准备
- 设置Python 3.11
- 设置Node.js 18
- 安装平台特定依赖

# 2. 依赖安装
- 安装Python依赖
- 安装前端依赖
- 安装构建工具

# 3. 环境验证
- 运行环境检查
- 验证必要文件

# 4. 执行构建
- 调用构建脚本
- 监控构建过程
- 验证构建结果

# 5. 产物上传
- 上传构建产物
- 生成构建报告
```

## 设计原则

### 1. 单一职责原则

每个组件都有明确的职责：
- `build.py`: 入口和协调
- `ecan_build.py`: 构建逻辑
- GitHub Actions: 环境准备

### 2. 依赖倒置原则

构建脚本不依赖特定的CI环境，而是通过环境变量和配置文件进行适配。

### 3. 开闭原则

系统对扩展开放，对修改封闭：
- 新增平台只需添加环境配置
- 新增构建模式只需修改配置
- 核心构建逻辑保持不变

### 4. 接口隔离原则

每个模块都有清晰的接口：
- 环境检测接口
- 配置管理接口
- 构建执行接口

## 配置管理

### 构建配置 (build_config.json)

```json
{
  "app_info": {
    "name": "eCan.ai",
    "version": "1.0.0",
    "main_script": "main.py"
  },
  "data_files": {
    "directories": ["resource", "config", "bot"],
    "files": ["app_context.py", "eCan.ico"]
  },
  "pyinstaller": {
    "excludes": ["matplotlib", "jupyter"],
    "hidden_imports": ["PySide6.QtWebEngineCore"]
  }
}
```

### 环境配置

不同平台使用不同的依赖文件：
- `requirements-base.txt`: 基础依赖
- `requirements-windows.txt`: Windows特定依赖
- `requirements-macos.txt`: macOS特定依赖

## 扩展性

### 添加新平台

1. **创建环境配置**
   ```yaml
   # .github/workflows/build-new-platform.yml
   runs-on: new-platform-latest
   ```

2. **添加依赖文件**
   ```txt
   # requirements-new-platform.txt
   -r requirements-base.txt
   # 平台特定依赖
   ```

3. **更新构建脚本**
   ```python
   # 在EnvironmentManager中添加平台检测
   ```

### 添加新构建模式

1. **更新配置**
   ```json
   {
     "build_modes": {
       "new_mode": {
         "debug": false,
         "console": true
       }
     }
   }
   ```

2. **更新参数解析**
   ```python
   # 在BuildArguments中添加新选项
   ```

## 最佳实践

### 1. 本地开发

```bash
# 开发模式构建（快速）
python build.py dev

# 生产模式构建（完整）
python build.py prod --force

# 环境检查
python build.py --check-env
```

### 2. CI/CD集成

```yaml
# 使用统一构建工作流
- name: Build All Platforms
  uses: ./.github/workflows/build-all.yml

# 或使用特定平台工作流
- name: Build Windows
  uses: ./.github/workflows/build-windows.yml
```

### 3. 调试和故障排除

```bash
# 详细输出
python build.py prod --verbose

# 环境检查
python build.py --check-env

# 查看构建日志
cat build.log
```

## 优势

### 1. 统一性
- 单一入口点
- 统一的参数格式
- 一致的构建流程

### 2. 可移植性
- 构建脚本可在任何环境运行
- 不依赖特定CI平台
- 支持本地和远程构建

### 3. 可维护性
- 清晰的模块划分
- 详细的文档和注释
- 完善的错误处理

### 4. 可扩展性
- 易于添加新平台
- 支持自定义构建模式
- 灵活的配置系统

## 总结

这种架构设计实现了以下目标：

1. **分工明确**: 入口文件负责协调，构建脚本负责逻辑，Actions负责环境
2. **通用性**: 构建脚本可在任何环境运行
3. **可维护性**: 模块化设计，职责清晰
4. **可扩展性**: 易于添加新平台和功能
5. **一致性**: 本地和CI环境使用相同的构建逻辑

这种设计使得构建系统既简单易用，又强大灵活，能够满足不同场景的需求。 