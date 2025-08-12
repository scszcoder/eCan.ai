# ECBot MCP 兼容性 Hooks

这个目录包含了解决 MCP 库在 PyInstaller 环境中兼容性问题的 Hook 文件。

## 📁 文件说明

### pyinstaller_hooks/ 目录
- `hook-mcp.py` - MCP 库主要 Hook，收集所有 MCP 模块和依赖
- `hook-pywintypes.py` - Windows 特定 Hook，解决 pywintypes 路径问题
- `hook-mcp-macos.py` - macOS 特定 Hook，处理 Unix 工具模块

### specs/ 目录
- `pyinstaller_windows.spec` - Windows 平台的完整配置
- `pyinstaller_macos.spec` - macOS 平台的完整配置

## 🚀 使用方法

### 推荐方式：使用统一构建系统

```bash
# 在项目根目录执行
python build.py

# 构建系统会自动：
# 1. 检测当前平台
# 2. 使用 pyinstaller_hooks 中的所有 hooks
# 3. PyInstaller 自动发现和执行 MCP 兼容性修复
# 4. 生成优化的可执行文件
```

### 手动方式：直接使用 hooks

```bash
# 使用 pyinstaller_hooks 目录
pyinstaller --additional-hooks-dir=build_system/pyinstaller_hooks gui/MainGUI.py

# 使用规格文件
pyinstaller build_system/specs/pyinstaller_windows.spec  # Windows
pyinstaller build_system/specs/pyinstaller_macos.spec    # macOS
```

## 🔧 工作原理

MCP 兼容性通过 PyInstaller hooks 自动实现：

1. **自动发现**: PyInstaller 扫描代码中的 `import mcp` 语句
2. **自动执行**: 发现导入时自动执行对应的 hook 文件
3. **自动收集**: hooks 自动收集所有必要的模块和依赖
4. **无需配置**: 不需要额外的配置，只需确保 hooks 在正确位置

## 🛠️ 解决的问题

1. **MCP 模块导入失败** - 通过 hook-mcp.py 收集所有必要模块
2. **pywintypes 路径检查失败** - 通过 hook-pywintypes.py 修复 Windows 特定问题
3. **隐藏导入缺失** - 自动添加所有 MCP 相关的隐藏导入
4. **动态库缺失** - 收集必要的 .dll/.dylib 文件

## 📋 验证方法

构建完成后，可以通过以下方式验证 MCP 功能：

```bash
# 运行可执行文件
./dist/MainGUI/MainGUI.exe  # Windows
./dist/MainGUI.app          # macOS

# 检查 MCP 模块是否正确导入
# 应用启动后，MCP 工具调用功能应该正常工作
```

## 🔍 故障排除

如果遇到问题：

1. **检查构建日志** - 查看是否有 hook 相关的警告
2. **验证 hooks 目录** - 确保 `build_system/pyinstaller_hooks/` 存在且包含 hook 文件
4. **测试导入** - 在开发环境中测试 MCP 模块是否可以正常导入

## 📚 技术细节

这些 hooks 解决了以下技术问题：

- **模块发现**: PyInstaller 无法自动发现 MCP 的动态导入
- **路径检查**: pywintypes 在 PyInstaller 环境中的严格路径验证
- **依赖收集**: 自动收集 MCP 库的所有依赖文件
- **平台适配**: 针对不同操作系统的特定处理
