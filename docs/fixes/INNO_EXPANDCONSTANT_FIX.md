# Inno Setup 大括号规则（本仓库实测结论）

> 这份文档此前记录过一条**错误规则**（"配置段四层大括号、Pascal Code 六层"），
> 它造成过至少三次"修好了又坏"的反复。以下规则是**渲染产物实测**得到的，
> 并有测试兜底：`tests/unit/test_installer_lease_contract.py`。
> 改任何花括号之前，先跑那个测试，不要靠数层数。

## 一句话

`build_system/ecan_build.py` 里的 `.iss` 模板是 **`rf"""` f-string**。所以：

**模板里写 `{{X}}` → 渲染出的 setup.iss 里是 `{X}` → ISCC 才会展开它。**

模板里写几层花括号，和"配置段 / Pascal Code"**无关**，只和"你想在 setup.iss
里得到几层"有关。渲染是纯文本替换，不存在"配置段多转义一次"这回事。

## 真值表（实测）

| 模板源码（f-string 内） | 渲染出的 setup.iss | ISCC 看到的东西 | 结果 |
|---|---|---|---|
| `{{app}}` | `{app}` | 一个常量 | ✅ 展开成安装目录 |
| `{{{{app}}}}` | `{{app}}` | 转义的**字面量** `{app}` | ❌ 永不展开（静默） |
| `{app}` | — | — | ❌ 渲染期 `NameError: name 'app' is not defined` |
| `{appdata_dir_name}` | `eCan`（Python 变量值） | 普通文本 | ✅ 这是 Python 插值，故意如此 |

两条推论，也是所有历史事故的根因：

- **少一层花括号** → Python 把 `{app}` 当变量 → 渲染期 `NameError` →
  构建在 PyInstaller 跑完之后才失败（`[ERROR] Failed to create Inno Setup script: name 'localappdata' is not defined`）。
- **多一层花括号** → 渲染成 `{{app}}`，Inno 当转义字面量 → 该分支**永远不执行，
  且没有任何报错**。曾经的 `InstallPath := ExpandConstant('{{app}}')` 就是这样：
  卸载时 `InstallPath` 等于字面量 `{app}`，由它派生的 5 个 `UserDataDirs[]`
  全是死路径，"卸载时删除用户数据"一直是空操作。

## 三种合法写法（本仓库都在用，产物一致）

1. **内联双花括号**（最常见的 [Code] 写法）

   ```python
   LeaseDir := ExpandConstant('{{localappdata}}') + '\\' + ...
   ```

   → 渲染出 `ExpandConstant('{localappdata}')`。

2. **Python 变量插入**（绕开 f-string 转义，最不容易写错）

   ```python
   cm_create_desktop = "{cm:CreateDesktopIcon}"   # 普通字符串，单花括号
   ...
   Name: "desktopicon"; Description: "{cm_create_desktop}"
   ```

   → 渲染出 `Description: "{cm:CreateDesktopIcon}"`。`cm_*`、`const_*`、
   `run_target`、`default_dir` 都走这条路，注释里写明就是为了"avoid
   f-string interpretation issues"。

3. **确实想要字面量花括号**（只有两处，别动）

   ```python
   AppId={app_id_wrapped}                                        # 渲染成 AppId={{GUID}}
   ...Uninstall\{{{{{app_id}}}}}_is1                              # 渲染成 ...\{{GUID}}_is1
   ```

   渲染产物里的 `{{GUID}}` 会被 ISCC 变成字面量 `{GUID}`，这正是 Inno 官方
   `AppId={{...}}` 的惯用法，也和**已安装机器的卸载项注册表键**一致。
   改成单花括号会让老用户的卸载项/OTA 查找全部失配，风险远大于收益。

## 怎么验证（不要靠读源码）

```bash
# 三份 config 都真渲染一遍，并检查产物里的花括号（1 秒内）
python3 -m pytest tests/unit/test_installer_lease_contract.py -q
```

这个文件里的测试直接调 `InstallerBuilder._create_inno_script()`（ISCC 真正
消费的东西），覆盖 base / cn / intl 三份 config，断言：

- 模板能渲染（少花括号 → 这里 `NameError` 直接红）
- 任何 `ExpandConstant('...')` 参数里都不许出现 `{{`（多花括号 → 死代码，红）
- 渲染产物里出现双花括号的行，只允许是 AppId 和卸载注册表键这两类
- `InstallPath := ExpandConstant('{app}');` 必须存在
- 文件仍是 UTF-8 **BOM**（中文串需要）

手工渲染：

```bash
python3 -c "import sys,tempfile;sys.path.insert(0,'.');from pathlib import Path;\
from build_system.ecan_build import BuildConfig,BuildEnvironment,InstallerBuilder;\
b=InstallerBuilder(BuildConfig(Path('apps/cn/build/build_config_cn.json')),BuildEnvironment(),Path(tempfile.mkdtemp()),mode='prod');\
b._ensure_windows_icon_quality=lambda:True;print(b._create_inno_script())"
```

`_create_inno_script()` 返回 `None` = 渲染失败（异常被 `except` 吞掉并打印
`[ERROR] ...`），CI 上表现为 `[ERROR] Installer creation failed`。

## 症状对照表

| 症状 | 真正原因 | 怎么改 |
|---|---|---|
| `[ERROR] Failed to create Inno Setup script: name 'xxx' is not defined` | 模板里少写了花括号（单花括号被当 Python 变量） | 改成 `{{xxx}}` |
| 某个分支/路径永远不生效，且无报错 | 写多了花括号，渲染成字面量 | 改成 `{{xxx}}`，并跑上面的测试 |
| `Invalid number of parameters` / 未知常量 | 产物里留下字面量 `{{...}}`，或常量名拼错 | 同上看渲染产物 |
| 中文乱码 | 编码/BOM 或 `.isl` 语言包 | 检查 UTF-8 BOM（测试已覆盖） |

## 历史教训（为什么反复）

| 曾经的做法 | 后果 |
|---|---|
| 把配置段一律改成四层、[Code] 改成六层 | 产物里全是字面量 `{{X}}`，多处清理逻辑静默失效；后来又逐条回退 |
| 用 `grep` 断言模板源码里"有 `{{app}}`" | 源码看起来完全正确，但渲染/展开行为可以完全不同——测试与故障点无关 |
| 只跑 `python -m py_compile` / 只读源码 | f-string 的合法性在渲染时才暴露，编译期永远看不出 |

结论：**花括号的正确性只能看渲染产物**，所以规则写进测试，而不是写进注释里数层数。

---

**首次事故**：2024-11-16（`name 'cm' is not defined`）
**最近事故**：2026-10-24（`name 'localappdata' is not defined`，CN 构建 `[INSTALLER]` 阶段失败）
**状态**：规则已实测确认，并由 `tests/unit/test_installer_lease_contract.py` 渲染型测试锁定。
