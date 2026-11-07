# eCan.ai — 组件与交互规范 (Component & Interaction Spec)

> 状态：**待确认**。确认后我将按此规范全量执行。
> 适用范围：`gui_v2/`（React + TypeScript + Vite + antd v5 + emotion）。
> 单一事实来源：颜色/字体/间距/圆角仅存在于 `gui_v2/src/styles/global.css`
> （`:root` 为深色默认，`body.light` 为浅色覆盖）。JS/TS 只切换 `body.className` + `data-theme`。

---

## 0. 为什么需要这份规范（实测证据）

当前代码库的组件使用是**随机分布**的，不是设计决策的结果：

| 实测项 | 数量 | 问题 |
|---|---|---|
| `<Button size="small">` | **789** | |
| `<Button size="large">` | 75 | size 使用比例 789:75:29，`middle` 几乎不用 |
| `<Button size="middle">` | 29 | 说明"默认尺寸"没有承载语义 |
| `type="text"` | 177 | text 比 primary 还多，主次失衡 |
| `type="primary"` | 135 | |
| 内联 `style={{}}` | **3834** | 样式散落在 JSX 中 |
| `<Card size=...>` | 61 | |
| 采用 `.page-shell` 的文件 | **仅 9 / 数百** | 页面骨架未统一 |

**运行时实测到 2 个真实缺陷**（同一行内的控件高度不一致）：

| 控件 | 实测高度 | 应为 |
|---|---|---|
| `.ant-select-selector` | **40px** | 38px |
| `.ant-input` (单行) | **38px** | 38px |
| `.ant-input-affix-wrapper` | **36 / 38px** | 不一致 |
| `.ant-btn` (default) | 40px | 40px ✅ |
| `.ant-btn-sm` | 28px | 28px ✅ |

→ **同一表单行里，输入框比下拉框矮 2px，带前后缀的输入框又矮 2px。** 这是肉眼可见的错位。

---

## 1. 尺寸阶梯（唯一权威）

所有交互控件共用一条阶梯。`--control-height-*` 已存在于 `global.css`，规范要求**所有控件都遵从此阶梯**。

| 尺寸 | Token | 高度 | 字号 | 圆角 | 用法 |
|---|---|---|---|---|---|
| `sm` | `--control-height-sm` | **28px** | 12px | 8px | 表格行内操作、标签页工具条、卡片角落图标按钮 |
| `md` | `--control-height-md` | **32px** | 14px | 8px | 表单默认、紧凑工具条（**最常用**） |
| `lg` | `--control-height-lg` | **40px** | 14px | 8px | 页面主操作、登录页、Dialog 页脚 |

**关键修正**：输入框/下拉框当前是 38/40px 两个值 → 统一为 **`md = 32px`（表单默认）** 与 **`lg = 40px`（页面主表单/登录）**，且 `Input`、`Select`、`InputNumber`、`DatePicker`、`Input.Password`、`affix-wrapper` **必须同高**。

> 我倾向于：**表单默认 32px**（antd 的 `middle` 语义），页面级主操作 40px。
> 若你希望更宽松，可改为默认 36px —— 请在第 8 节选择。

---

## 2. 按钮规范

### 2.1 语义分层（每屏最多 1 个 primary）

| 层级 | 组件写法 | 用在哪 |
|---|---|---|
| **主操作** | `<Button type="primary">` | 每屏/每卡片最多**一个**。提交、创建、保存、确认 |
| **次操作** | `<Button>`（default） | 取消、返回、次要动作 |
| **行内/低权重** | `<Button type="text">` | 表格行内、图标按钮、工具条 |
| **纯导航** | `<Button type="link">` | 跳转、外链 |
| **危险** | `<Button danger>` | 删除。**必须配 `Popconfirm`** |

**规则**：禁止 `type="text"` 承担主操作（当前 177 个 text > 135 个 primary，主次颠倒）。改为图标按钮 + `Tooltip`。

### 2.2 图标按钮

```tsx
// 纯图标：必须给 Tooltip + aria-label
<Tooltip title={t('common.refresh')}>
  <Button type="text" icon={<ReloadOutlined />} aria-label={t('common.refresh')} />
</Tooltip>
```
- 纯图标按钮 **不加 `size`**（跟随父容器 32px），仅在表格行内用 `size="small"`。
- 图标与文字间距沿用 antd 的 8px，不额外写 `style`。

### 2.3 表单页脚（统一顺序）

```
[ 取消 (default) ]  [ 提交 (primary, loading) ]     ← 右对齐，间距 12px
```
- 提交中必须 `loading` + `disabled`，禁止用文字"提交中…"代替。
- 页面主操作放**右上角**，Dialog 页脚放**右下角**。

---

## 3. 输入类规范

### 3.1 统一高度（本轮修复重点）

`Input` / `Input.Password` / `InputNumber` / `Select` / `DatePicker` / `affix-wrapper` 在任何同一行内**必须等高**。以 `--control-height-md`(32px) 或 `--control-height-lg`(40px) 二者之一整行统一。

`TextArea` 例外：最小 3 行，`autoSize={{ minRows: 3, maxRows: 8 }}`。

### 3.2 表单布局

| 场景 | 布局 |
|---|---|
| 新建/编辑弹窗 | `<Form layout="vertical">`（label 在上，**默认选它**） |
| 搜索/筛选条 | `<Form layout="inline">`，控件 `size="small"` 或 `md`，**整条等高** |
| 设置页 | `layout="vertical"`，label 宽固定 |

**规则**：不再混用 `horizontal` + 自定义 label 宽度。每行 label 与控件间距 8px，字段间 20px (`--content-gap`)。

### 3.3 必填与校验

- 必填用 `<Form.Item required>`（红色星号），**不要**在 label 手写 `*`。
- 校验失败信息显示在控件下方 `help` 槽；错误态统一 `--error-color`。
- placeholder 只写**示例**，不重复 label 文字。

---

## 4. 间距与布局

### 4.1 页面骨架（强制）

每个页面根节点使用 `.page-shell`（或 `PageShell` 组件）：

```tsx
<div className="page-shell">
  <h1 className="page-title">{t('...')}</h1>   {/* 页面唯一主标题 */}
  <div className="page-toolbar">…</div>         {/* 右上角操作 */}
  <div className="page-body">…</div>
</div>
```

- 页面内边距：`--page-padding` (24px)
- 区块间距：`--content-gap` (20px)
- 卡片内边距：`--space-lg`
- **禁止**页面自己写 `padding: 24px` / `marginTop: 16` 之类的裸值。

### 4.2 间距阶梯

`4 / 8 / 12 / 16 / 20 / 24 / 32`（`--space-xs` … `--space-2xl`）。**禁止出现 5、7、13、15、18 这类无阶梯的值。**

### 4.3 卡片

- 默认 `<Card size="small">`（页面内区块）与 `<Card>`（页面级）两级，不再自定义 `headStyle`（当前 61 处）。
- 标题用 `<Card title={...}>`，不自己写 `<h3>` 塞进去。
- 圆角统一 `--radius-lg`，边框统一 `--border-color`，阴影统一 `--shadow-sm`。

---

## 5. 反馈与状态

| 场景 | 用什么 | 不用什么 |
|---|---|---|
| 操作成功/失败 | `App.useApp().message` ✅ | ❌ `import { message } from 'antd'`（**当前浏览器报错源**） |
| 需确认的删除 | `<Popconfirm>` | ❌ `window.confirm` |
| 二次确认弹窗 | `<Modal.confirm>`（经 `App.useApp()`） | |
| 空状态 | `<Empty>` + 一句引导文案 + 主操作按钮 | ❌ 只写"暂无数据" |
| 加载 | `<Spin>` / `Skeleton`（列表首屏） | ❌ 空白屏 |
| 危险操作 | `--error-color`，按钮 `danger` | |

### 5.1 修掉 antd 静态方法告警（本轮必做）

antd v5 下 `message.xxx()` 静态调用会告警且不继承主题。统一改为：

```tsx
const { message, modal, notification } = App.useApp();
```

---

## 6. 圆角与描边

| 元素 | 圆角 |
|---|---|
| 按钮/输入/下拉 | `--radius-control` (10px) |
| 卡片/面板 | `--radius-lg` |
| 标签 Tag | `--radius-sm` |
| 头像/圆形按钮 | `--radius-full` |

描边统一 `1px solid var(--border-color)`，聚焦态 `--border-color-focus` + `--shadow-focus`，**禁止**裸 `border: 1px solid #ddd`。

---

## 7. 国际化（本轮必做）

- 所有面向用户的字符串**必须**走 `t()`；`zh-CN.json` 与 `en-US.json` 同步补齐。
- **38 个文件**含硬编码中文且未使用 `t()`，本轮全部完成（含 `ScheduleFormModal`(82)、`FastDeploy/scenarios`(79)、`Knowledge/Analytics`(72)、`Collaboration`(68)、`VersionControl`(65)、`DocumentEditor`(57)、`OrgDoor`(55)、`AdvancedSearch`(53)、`VehicleDetails`(35)、`Agents`(35)、`RAGDocuments`(32)、`StyledForm`(30) 等）。
- key 命名：`<page>.<section>.<item>`，复用已有通用键 `common.*`，不重复造。
- 仅 `console.*` 调试日志、代码注释、GraphQL 字段名保持原文，不做翻译。
- `skill_editor` 按要求**跳过**（其崩溃为既有问题，不在本轮范围）。

---

## 8. 需要你拍板的 2 个点

1. **表单默认控件高度**：`32px`（antd middle 语义，紧凑）还是 `36px`（更宽松）？
2. **`type="text"` 按钮的收敛力度**：是否允许我把工具栏里的 text 按钮**大幅替换为图标按钮+Tooltip**（视觉更干净，但改动面较大）？

> 若无异议，我按：**表单默认 32px** + **收敛 text → 图标按钮** 执行。

---

## 9. 执行清单（确认后）

1. 修 `.ant-select-selector` / `.ant-input` / `affix-wrapper` 高度不一致（实测缺陷）。
2. 补全 `.page-shell` 到所有页面（9 → 全部）。
3. 按钮语义分层：每屏 ≤1 primary；text → 图标按钮。
4. antd `message` 静态调用 → `App.useApp()`。
5. 38 个文件 i18n 补完（zh-CN + en-US）。
6. 验证：`npx tsc --noEmit` 增量 ≤ 0；`npx vite build` 通过；路由冒烟 20 条；主题切换实测。
7. **不提交**（按你的要求保留在工作区）。
