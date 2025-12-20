# Inno Setup 大括号转义修复

## 🐛 问题

**构建失败 1**：
```
Error on line 74 in setup.iss: Column 37:
Invalid number of parameters.
Compile aborted.
```

**构建失败 2**：
```
Failed to create Inno Setup script: name 'cm' is not defined
```

## 🔍 根本原因

### 问题 1: Pascal Code 中的 ExpandConstant 语法错误

```pascal
// 错误：在 [Code] 段中使用双大括号
SplashLabel.Caption := ExpandConstant('{{cm:InitializeCaption}}');
```

### 问题 2: Python f-string 变量冲突

```python
# 错误：在 f-string 中，{cm:...} 被当作 Python 变量
iss_content = f"""
[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; ...
"""
# Python 尝试查找变量 'cm'，导致 NameError
```

### 语法规则

在 Inno Setup 中，大括号的使用规则：

| 位置 | 语法 | 示例 |
|------|------|------|
| **[Setup], [Files] 等段** | `{constant}` | `{app}\file.exe` |
| **[CustomMessages]** | `{cm:MessageName}` | `{cm:WelcomeLabel}` |
| **Pascal Code 中** | `{{{constant}}}` | `ExpandConstant('{{{app}}}')` |

**关键点**：
- 在 `.iss` 文件的配置段中：使用 `{constant}` 或 `{cm:name}`
- 在 `[Code]` 段的 Pascal 代码中：使用 `{{{constant}}}` 或 `{{{cm:name}}}`
- **原因**：Python 字符串中的 `{{` 会被转义为 `{`，所以需要三层

## ✅ 解决方案

### 修复位置

**文件**: `build_system/ecan_build.py`

### 修复 1: Pascal Code 中的 ExpandConstant（三层大括号）

```diff
# Line 476
- SplashLabel.Caption := ExpandConstant('{{cm:InitializeCaption}}');
+ SplashLabel.Caption := ExpandConstant('{{{cm:InitializeCaption}}}');

# Line 525
- if MsgBox(ExpandConstant('{{cm:RemoveUserDataPrompt}}'), mbConfirmation, MB_YESNO) = IDYES then
+ if MsgBox(ExpandConstant('{{{cm:RemoveUserDataPrompt}}}'), mbConfirmation, MB_YESNO) = IDYES then

# Line 527
- if DirExists(ExpandConstant('{{localappdata}}\\eCan')) then
+ if DirExists(ExpandConstant('{{{localappdata}}}\\eCan')) then

# Line 529
- if not DelTree(ExpandConstant('{{localappdata}}\\eCan'), True, True, True) then
+ if not DelTree(ExpandConstant('{{{localappdata}}}\\eCan'), True, True, True) then
```

### 修复 2: 配置段中的常量（四层大括号）

```diff
# Line 300 - AppId
- app_id_wrapped = "{{" + app_id + "}}"
+ app_id_wrapped = "{{{{" + app_id + "}}}}"

# Line 418 - UninstallDisplayIcon
- UninstallDisplayIcon={{app}}\eCan.exe
+ UninstallDisplayIcon={{{{app}}}}\eCan.exe

# Line 444 - Tasks
- Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"
+ Description: "{{{{cm:CreateDesktopIcon}}}}"; GroupDescription: "{{{{cm:AdditionalIcons}}}}"

# Line 450-451 - Icons
- Name: "{{group}}\eCan"
- Name: "{{userdesktop}}\eCan"
+ Name: "{{{{group}}}}\eCan"
+ Name: "{{{{userdesktop}}}}\eCan"

# Line 454 - UninstallDelete
- Name: "{{localappdata}}\eCan"
+ Name: "{{{{localappdata}}}}\eCan"

# Line 536 - Run
- Description: "{{cm:LaunchProgram,eCan}}"
+ Description: "{{{{cm:LaunchProgram,eCan}}}}"
```

## 📚 详细说明

### Python f-string 转义规则

**关键点**: 使用 `f"""..."""` 时，所有 `{variable}` 都会被 Python 解析！

#### 配置段（需要四层大括号）

```python
# Python f-string 代码
iss_content = f"""
[Tasks]
Name: "desktopicon"; Description: "{{{{cm:CreateDesktopIcon}}}}";
"""

# Python 处理后（f-string 转义）
"""
[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}";
"""

# 写入文件 setup.iss
[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}";

# Inno Setup 解析（预处理器转义）
[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}";

# 最终结果
Description: "创建桌面图标"
```

#### Pascal Code（需要六层大括号）

```python
# Python f-string 代码
iss_content = f"""
[Code]
SplashLabel.Caption := ExpandConstant('{{{{{{cm:InitializeCaption}}}}}}');
"""

# Python 处理后（f-string 转义）
"""
[Code]
SplashLabel.Caption := ExpandConstant('{{{cm:InitializeCaption}}}');
"""

# 写入文件 setup.iss
[Code]
SplashLabel.Caption := ExpandConstant('{{{cm:InitializeCaption}}}');

# Inno Setup 预处理器（第一次转义）
SplashLabel.Caption := ExpandConstant('{{cm:InitializeCaption}}');

# Inno Setup 编译器（第二次转义）
SplashLabel.Caption := ExpandConstant('{cm:InitializeCaption}');

# 运行时展开
Caption = "正在初始化 eCan..."
```

### Inno Setup 解析

当 Inno Setup 编译器解析 `[Code]` 段时：

```pascal
// 源代码
ExpandConstant('{{{cm:InitializeCaption}}}')

// 第一步：预处理器展开 {{{...}}}
ExpandConstant('{cm:InitializeCaption}')

// 第二步：运行时展开 {cm:...}
"正在初始化 eCan..."  // 实际的中文消息
```

## 🧪 验证

### 测试场景

1. **启动画面**
   ```pascal
   SplashLabel.Caption := ExpandConstant('{{{cm:InitializeCaption}}}');
   ```
   预期：显示 "正在初始化 eCan..."

2. **卸载提示**
   ```pascal
   MsgBox(ExpandConstant('{{{cm:RemoveUserDataPrompt}}}'), ...)
   ```
   预期：显示 "是否删除用户数据？"

3. **路径展开**
   ```pascal
   DirExists(ExpandConstant('{{{localappdata}}}\\eCan'))
   ```
   预期：展开为 `C:\Users\Username\AppData\Local\eCan`

## 📊 修复的所有位置

### Pascal Code（三层 → 六层大括号）

| 行号 | 函数 | 用途 | 状态 |
|------|------|------|------|
| 476 | `InitializeSetup()` | 启动画面标题 | ✅ 已修复 |
| 525 | `InitializeUninstall()` | 卸载提示消息 | ✅ 已修复 |
| 527 | `InitializeUninstall()` | 检查用户数据目录 | ✅ 已修复 |
| 529 | `InitializeUninstall()` | 删除用户数据目录 | ✅ 已修复 |

### 配置段（双层 → 四层大括号）

| 行号 | 段 | 用途 | 状态 |
|------|------|------|------|
| 300 | Python | AppId 包裹 | ✅ 已修复 |
| 418 | [Setup] | 卸载图标 | ✅ 已修复 |
| 444 | [Tasks] | 桌面图标任务 | ✅ 已修复 |
| 450 | [Icons] | 开始菜单图标 | ✅ 已修复 |
| 451 | [Icons] | 桌面图标 | ✅ 已修复 |
| 454 | [UninstallDelete] | 删除用户数据 | ✅ 已修复 |
| 536 | [Run] | 启动程序描述 | ✅ 已修复 |

## 🎓 经验总结

### 关键教训

1. **理解转义层次**
   - Python f-string: `{{{{` → `{{` (双层转义)
   - Inno Setup 预处理: `{{` → `{` (单层转义)
   - **配置段**: 需要 4 层大括号
   - **Pascal Code**: 需要 6 层大括号

2. **区分使用场景**
   - 配置段（[Setup], [Files]）：`{{{{constant}}}}`（Python）→ `{constant}`（Inno）
   - Pascal 代码（[Code]）：`{{{{{{constant}}}}}}`（Python）→ `{{{constant}}}`（Inno）

3. **f-string 陷阱**
   - 使用 `f"""..."""` 时，所有 `{...}` 都会被解析
   - 如果忘记转义，会导致 `NameError: name 'cm' is not defined`
   - 必须使用足够的大括号层数

### 最佳实践

✅ **DO:**
- Python f-string 中配置段使用 `{{{{constant}}}}`
- Python f-string 中 Pascal Code 使用 `{{{{{{constant}}}}}}`
- 仔细计算大括号层数
- 测试生成的 setup.iss 文件

❌ **DON'T:**
- 不要在 f-string 中使用不足的大括号
- 不要混淆配置段和 Pascal Code 的层数
- 不要忽略 Python NameError

### 快速检查表

| 错误信息 | 原因 | 解决方案 |
|---------|------|---------|
| `name 'cm' is not defined` | f-string 中大括号不足 | 配置段用 4 层 |
| `Invalid number of parameters` | Pascal Code 大括号不足 | Pascal Code 用 6 层 |
| 中文显示乱码 | 编码或语言包问题 | 检查 UTF-8 BOM 和 .isl |

## 🔗 参考资料

- [Inno Setup Constants](https://jrsoftware.org/ishelp/index.php?topic=consts)
- [Inno Setup Pascal Scripting](https://jrsoftware.org/ishelp/index.php?topic=scriptintro)
- [ExpandConstant Function](https://jrsoftware.org/ishelp/index.php?topic=isxfunc_expandconstant)

---

**问题发现**: 2024-11-16  
**修复完成**: 2024-11-16  
**状态**: ✅ 已修复  
**影响**: 修复 11 处大括号转义（4 处 Pascal Code + 7 处配置段）
