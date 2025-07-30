# ECBot 构建配置指南

## 📋 配置文件说明

### 配置文件位置
- **文件路径**: `build_system/build_config.json`
- **格式**: JSON格式，支持注释（使用 `_comment` 字段）
- **编码**: UTF-8

### 配置结构

#### 1. 应用信息 (`app_info`)
```json
{
  "app_info": {
    "name": "ECBot",                    // 应用名称
    "main_script": "main.py",           // 主入口脚本
    "icon": "ECBot.ico",                // 应用图标
    "description": "ECBot Desktop Application"  // 应用描述
  }
}
```

#### 2. 数据文件 (`data_files`)
```json
{
  "data_files": {
    "directories": [                    // 需要打包的目录
      "resource", "config", "bot", "gui", "common", "utils",
      "agent", "tests", "knowledge", "settings", "skills", 
      "telemetry", "gui_v2/dist", "ecbot-ui/dist"
    ],
    "files": [                          // 需要打包的单个文件
      "app_context.py", "ECBot.ico", "ecbot.qm", 
      "ecbot_zh.qm", "role.json", "uli.json"
    ]
  }
}
```

#### 3. PyInstaller配置 (`pyinstaller`)
```json
{
  "pyinstaller": {
    "excludes": [                       // 排除的模块
      "matplotlib", "jupyter", "notebook", "ipython", "pytest",
      "django", "flask", "tornado", "bokeh", "plotly", 
      "tensorflow", "keras", "test", "tests", "testing",
      "tkinter", "_tkinter", "setuptools", "distutils", "pip"
    ],
    "hidden_imports": [                 // 隐藏导入的模块
      "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", 
      "PySide6.QtWebChannel", "PySide6.QtCore", "PySide6.QtGui",
      "PySide6.QtWidgets", "PySide6.QtNetwork", "shiboken6",
      "unittest", "unittest.mock", "doctest", "qasync",
      "browser_use", "playwright", "crawl4ai", "langchain"
    ]
  }
}
```

#### 4. 构建模式 (`build_modes`)
```json
{
  "build_modes": {
    "dev": {                            // 开发模式
      "debug": true,                    // 启用调试
      "console": true,                  // 显示控制台
      "clean": false,                   // 不清理构建目录
      "optimize": false,                // 不优化
      "onefile": false                  // 不打包成单文件
    },
    "prod": {                           // 生产模式
      "debug": false,                   // 禁用调试
      "console": false,                 // 隐藏控制台
      "clean": true,                    // 清理构建目录
      "optimize": true,                 // 启用优化
      "onefile": false                  // 不打包成单文件
    }
  }
}
```

## 🔧 配置修改指南

### 常见修改场景

#### 1. 添加新的数据目录
```json
{
  "data_files": {
    "directories": [
      "resource", "config", "bot", "gui", "common", "utils",
      "your_new_directory"              // 添加新目录
    ]
  }
}
```

#### 2. 排除新的模块
```json
{
  "pyinstaller": {
    "excludes": [
      "matplotlib", "jupyter", "notebook",
      "your_unwanted_module"            // 添加要排除的模块
    ]
  }
}
```

#### 3. 添加隐藏导入
```json
{
  "pyinstaller": {
    "hidden_imports": [
      "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
      "your_hidden_module"              // 添加隐藏导入的模块
    ]
  }
}
```

#### 4. 修改构建模式
```json
{
  "build_modes": {
    "dev": {
      "debug": true,
      "console": true,
      "clean": false,
      "optimize": false,
      "onefile": true                   // 改为单文件模式
    }
  }
}
```

### 配置验证

修改配置后，可以通过以下方式验证：

```bash
# 检查配置是否正确加载
python build.py --stats

# 测试开发模式配置
python build.py dev --stats

# 测试生产模式配置  
python build.py prod --stats
```

## 💡 最佳实践

### 1. 配置管理
- ✅ **版本控制**: 将 `build_config.json` 提交到版本控制
- ✅ **备份配置**: 修改前备份原配置
- ✅ **渐进修改**: 一次只修改一个配置项
- ✅ **测试验证**: 修改后立即测试

### 2. 模块管理
- **排除原则**: 只排除确定不需要的模块
- **隐藏导入**: 遇到 `ModuleNotFoundError` 时添加到隐藏导入
- **测试验证**: 构建后测试应用功能是否正常

### 3. 数据文件
- **必需文件**: 确保所有必需的数据文件都被包含
- **路径检查**: 确认文件路径相对于项目根目录正确
- **大小优化**: 排除不必要的大文件

## 🚨 注意事项

### 1. JSON格式要求
- 使用双引号，不能使用单引号
- 最后一个元素后不能有逗号
- 注释使用 `_comment` 字段，不能使用 `//` 或 `/* */`

### 2. 路径规范
- 所有路径都相对于项目根目录
- 使用正斜杠 `/`，即使在Windows上
- 目录路径不要以斜杠结尾

### 3. 模块名称
- 模块名称必须准确，区分大小写
- 使用完整的模块路径，如 `PySide6.QtCore`
- 排除模块时要小心，避免排除必需的依赖

## 🔍 故障排除

### 常见问题

#### 1. 配置文件格式错误
```
❌ 加载配置文件失败: Expecting ',' delimiter: line 10 column 5
```
**解决方案**: 检查JSON格式，确保语法正确

#### 2. 模块导入失败
```
ModuleNotFoundError: No module named 'your_module'
```
**解决方案**: 将模块添加到 `hidden_imports` 列表

#### 3. 数据文件缺失
```
FileNotFoundError: [Errno 2] No such file or directory: 'your_file'
```
**解决方案**: 检查文件路径，确保文件存在

---

**💡 提示**: 配置文件修改后立即生效，无需重启或重新加载！
