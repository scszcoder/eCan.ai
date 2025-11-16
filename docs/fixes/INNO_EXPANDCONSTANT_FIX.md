# Inno Setup ExpandConstant 语法修复

## 🐛 问题

**构建失败**：
```
Error on line 74 in setup.iss: Column 37:
Invalid number of parameters.
Compile aborted.
```

## 🔍 根本原因

**Inno Setup Pascal Code 中的 ExpandConstant 语法错误**

### 问题代码

```pascal
// 错误：在 [Code] 段中使用双大括号
SplashLabel.Caption := ExpandConstant('{{cm:InitializeCaption}}');
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

### 修复内容

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

## 📚 详细说明

### Python 字符串转义

在 Python 中生成 Inno Setup 脚本时：

```python
# Python 代码
f"SplashLabel.Caption := ExpandConstant('{{{{cm:InitializeCaption}}}}');"

# 生成的字符串
"SplashLabel.Caption := ExpandConstant('{{cm:InitializeCaption}}');"

# 写入文件后
SplashLabel.Caption := ExpandConstant('{{cm:InitializeCaption}}');
```

**问题**：
- Python f-string 中 `{{` → `{`
- 所以 `{{cm:...}}` 在文件中变成 `{cm:...}`
- 但 Pascal Code 需要 `{{{cm:...}}}`

**正确做法**：
```python
# Python 代码（三层大括号）
f"SplashLabel.Caption := ExpandConstant('{{{{{{cm:InitializeCaption}}}}}}');"

# 生成的字符串
"SplashLabel.Caption := ExpandConstant('{{{cm:InitializeCaption}}}');"

# 写入文件后
SplashLabel.Caption := ExpandConstant('{{{cm:InitializeCaption}}}');
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

| 行号 | 函数 | 用途 | 状态 |
|------|------|------|------|
| 476 | `InitializeSetup()` | 启动画面标题 | ✅ 已修复 |
| 525 | `InitializeUninstall()` | 卸载提示消息 | ✅ 已修复 |
| 527 | `InitializeUninstall()` | 检查用户数据目录 | ✅ 已修复 |
| 529 | `InitializeUninstall()` | 删除用户数据目录 | ✅ 已修复 |

## 🎓 经验总结

### 关键教训

1. **理解转义层次**
   - Python f-string: `{{` → `{`
   - Inno Setup 预处理: `{{{` → `{`
   - 需要计算好层数

2. **区分使用场景**
   - 配置段（[Setup], [Files]）：`{constant}`
   - Pascal 代码（[Code]）：`{{{constant}}}`

3. **测试不同版本**
   - Inno Setup 6.6.0 更严格
   - 旧版本可能容忍错误语法

### 最佳实践

✅ **DO:**
- 在 Pascal Code 中使用 `{{{constant}}}`
- 在配置段中使用 `{constant}`
- 仔细检查大括号数量

❌ **DON'T:**
- 不要在 Pascal Code 中使用 `{{constant}}`
- 不要混淆不同段的语法
- 不要忽略编译器警告

## 🔗 参考资料

- [Inno Setup Constants](https://jrsoftware.org/ishelp/index.php?topic=consts)
- [Inno Setup Pascal Scripting](https://jrsoftware.org/ishelp/index.php?topic=scriptintro)
- [ExpandConstant Function](https://jrsoftware.org/ishelp/index.php?topic=isxfunc_expandconstant)

---

**问题发现**: 2024-11-16  
**修复完成**: 2024-11-16  
**状态**: ✅ 已修复  
**影响**: 修复 4 处 ExpandConstant 调用
