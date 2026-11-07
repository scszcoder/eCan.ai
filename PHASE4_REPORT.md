# Phase 4 — 布局/样式/交互收敛 + 浏览器错误 + 国际化补完

分支：`feat/ui-polish`（基于 `origin/master` @ `49e2deef7`，**0 提交**，全部改动未提交）
落地范围：`gui_v2/`（React + TS + Vite + emotion）

---

## 1. 决策点确认（用户拍板）

| # | 决策 | 结论 |
|---|---|---|
| 1 | 表单默认控件高度 | **32px**（= antd `middle` 语义） |
| 2 | text 按钮收敛 | **允许大幅收敛为「图标 + Tooltip」** |
| 3 | 国际化范围 | **全部页面补完** |

---

## 2. 布局 / 样式 / 交互体系（哪种更合理，为什么）

### 2.1 尺寸阶梯（唯一真相源：`gui_v2/src/styles/global.css`）

| Token | 值 | 用途 |
|---|---|---|
| `--control-height-sm` | 28px | 表格行内、紧凑工具条 |
| `--control-height-md` | **32px** | **表单默认**（Input / Select / InputNumber / DatePicker / affix-wrapper） |
| `--control-height-lg` | 40px | 页面主 CTA |
| `--control-radius` | 10px | 所有控件圆角 |
| `--page-padding` | 24px | 页面统一内边距 |
| `--content-gap` | 20px | 区块间距 |
| `--header-height` | 64px | 顶栏 |

**为什么是 32px**：antd 的 `middle` 默认即 32px。收敛到语义默认值后，`<Input>` 与 `<Select>` 不再需要各自 `size` 覆写就能对齐——这是「更合理」的核心：**少写样式而不是多写样式**。

**为什么 XS/S 一档 28px 而不是 30/32**：28px 与 32px 差 4px，肉眼可辨但又不至于让小表格行高塌陷；用 30px 会与默认档只差 2px，视觉上无法区分档位。

### 2.2 反模式与修正

| 反模式 | 修正前 | 修正后 |
|---|---|---|
| 控件高度硬编码 | `min-height: 38px`（`StyledForm.tsx` 5 处） | `var(--control-height-md)` |
| 同一行高宽不一致 | Input 38px vs Select 36px vs affix 40px | 全部 32px |
| 圆角各写各的 | 6px / 8px / 10px / 12px 混用 | `var(--control-radius)` |
| 深色写死 | `rgba(255,255,255,0.06)` 等深色专用色 | `var(--control-bg-hover)` 等 token，浅色自动适配 |
| 矛盾声明 | 多选框同时 `min-height` + `height` | 删除失效的一侧 |

**修复文件**：`StyledForm.tsx`（根因）、`SearchFilter.tsx`、`ToolFilters.tsx`、`TaskFilters.tsx`、`SkillFilters.tsx`、`ConsoleFilters.tsx`、`TaskDetail.tsx`、`PageBackBreadcrumb.tsx`、`LightRAGPorted/Tabs.tsx`、`Settings.tsx`、`global.css`。

### 2.3 `.page-shell` 契约

每个路由页根节点**必须**使用 `.page-shell`（或 `<PageShell>`），不得自行声明根内边距；填充型页面用 `.page-shell--fill`。当前 **24 个页面** 已遵循。

**为什么**：此前每页各写 `padding: 16px/20px/24px/32px`，切换路由时内容会左右跳动。收敛到单一 `--page-padding` 后，所有页面共享同一节律。

### 2.4 按钮层级（收敛结果）

| 指标 | Phase 4 前 | 现在 |
|---|---|---|
| `<Button type="text">` | 177 | **33**（−81%） |
| `<Button type="primary">` | — | 135 |
| 未标注的纯图标按钮 | 存在 | **0**（全部带 `aria-label`/`Tooltip`） |

**交互原则**：一屏之内最多 1 个 `primary`；次要操作用 `default`；三线操作（编辑/删除/更多）收敛为图标按钮 + `Tooltip`，避免长文案挤压表格列宽。实测 Tasks 页：**1 primary / 10 default / 3 text**。

---

## 3. 浏览器错误信息

审计结论：**零 React / antd 警告**。浏览器控制台只剩后端 HTTP 500（`[APIRouter] Local GraphQL error`、`[AppConfig] fetchConfig failed`），属环境性——dev server 无后端，非前端缺陷。

一并修掉的真实缺陷：

| 缺陷 | 文件 | 处理 |
|---|---|---|
| 生产环境仍挂 console 过滤器 | `main.tsx` | 加 prod-only 守卫 |
| console 补丁重复注册 | `Settings.tsx` | 幂等化（`FORM_WARNING_MARKER`） |
| 未捕获 Promise rejection | `ProductSearchNotification.tsx` | 补 catch |
| `ResizeObserver` 循环告警 | `VirtualList.tsx` | 补 rAF 节流 |
| antd 静态 `message` 告警 | — | **非缺陷**：`ConfigProvider theme` 非空即已抑制，无静态调用点 |

> 附注：CDP `console` action 会把两个 listener 合并输出，导致每行「重复」——**工具伪影，非应用缺陷**（已核对 `main.tsx` 守卫与 `Settings.tsx` 幂等逻辑均正确）。

---

## 4. 国际化补完

### 4.1 结果

| 指标 | 结果 |
|---|---|
| 非 skill-editor 代码中字面 `t()` key | 2815 |
| **两语均缺失的 key** | **0** |
| zh / en key 数 | **4933 / 4933** |
| key 对称性 | **完全对称（0 单侧）** |
| skill-editor（超范围） | 751 个 key，670 缺失（按用户要求不动） |

本轮新增：**+534 键**（12 文件扫描补全）→ **+93 键**（98 项缺失清单）→ **+31 键**（源侧冲突消解 + 对称性补齐）。

### 4.2 关键修复：命名空间 / 叶子 冲突

5 个 key 无法直接加进 locale——源码把它们当**叶子字符串**调用，而同一 JSON 路径已被用作**对象命名空间**。这类问题必须在**源码层**修（符合「修在正确的层」原则）：

| 源码位置 | 冲突 | 修法 |
|---|---|---|
| `Console.tsx:252`、`ConsoleFilters.tsx:233` | `pages.console.status` 已是 `{active,maintenance,offline}` | 改用新叶子 `pages.console.statusLabel` |
| `Knowledge/CategoryManagement.tsx`（6 处） | `pages.knowledge.categoryManagement` 已是对象，且被**重复定义的 `knowledge` 键遮蔽** | 命名空间重命名为 `pages.knowledge.titleManagement.*` |
| `SkillDetails.tsx:1167` | `pages.skills.needInputs` 是占位符对象 | → `pages.skills.needInputsLabel` |
| `SkillMarketplaceGrid.tsx:435` | `pages.skills.reportReason` 是原因枚举对象 | → `pages.skills.reportReasonLabel` |
| `SkillMarketplaceList.tsx:501` | `pages.skills.favorites` 是叶子字符串 | → `pages.skills.favoritesEmpty` |

同时消解了 `zh-CN.json` / `en-US.json` 中**重复键** `pages.knowledge.categoryManagement` 与 `pages.knowledge.permissionManager.permissionsCount`（JSON 后者遮蔽前者，导致子键**永不可达**——这是隐性 bug，不只是 tidy-up）。

### 4.3 其他

- 补齐 27 个 zh-only 键的英文（`pages.settings.*`、`pages.tasks.cloudRun` 等）。
- 移除 1 处 **zh-only 死数据** `pages.prompts.examples.write_a_marketing_email.techniques`（真实调用路径是 `pages.prompts.guide.techniques.*`，该块无任何引用），从而达成 4933/4933 完全对称。
- 交互确认：`SkillFilters.tsx` 的编辑过程曾误删一行 `color:`，已恢复。

---

## 5. 验证证据

| 检查 | 命令 | 结果 |
|---|---|---|
| TypeScript | `npx tsc --noEmit` | **633** errors（HEAD 基线 646，**−13**） |
| 真实回归 | file+code 签名集合 `comm` | **0 条新增**；另消除 `TS2304` 两类 |
| 构建 | `npx vite build` | **✓ built in 32.01s** |
| 单测 | `npx jest` | 8 失败 / 5 通过，16/16 用例通过 = **基线一致**，无新增 |
| locale 解析 | Node 逐键 probe（22 键） | 全部命中 zh+en |
| key 扫描 | 2815 个静态 `t()` key | 缺失 **0** |
| 实时 token | CDP 计算样式 | `--control-height-md`=32px、`--control-radius`=10px、`--primary-color`=#3b82f6 |
| 实时布局 | CDP | `.page-shell` 24px padding / 20px gap / 64px header |
| 构建产物 | grep `dist/assets` | 新键 `statusLabel`/`needInputsLabel`/`favoritesEmpty`/`titleManagement` 均已打包 |
| CSS 完整性 | 花括号计数 | 197 / 197 平衡 |

> **验证方法学**：tsc 的行号会随增删行漂移，直接 diff 行列表会产生假阳性。本报告用 **file+`: error TSxxxx` 签名集合**比较，这才是真实回归判据。

---

## 6. 遗留 / 阻塞（不属本轮范围）

1. **浅色模式 logo 资源**缺设计稿，无法替换。
2. **skill-editor 670 个缺失 key** — 按用户明确要求保持原样（且该模块当前有崩溃，不动）。
3. **全仓约 4,700 处硬编码颜色** — 绝大多数在废弃的 `gui/`（PyQt5）与 vendored 目录，`gui_v2/` 范围外。
4. **dev server 无后端** → 路由被 auth 守卫弹回登录壳，无法对受保护页面做真实 DOM 断言；已改用 locale 层逐键 probe + 构建产物 grep 作为等价证据。
5. 8 个 Jest 套件失败为**既有基线**（导入/环境问题），非本轮引入。

**未提交**：全部改动保留在工作区，`git diff --shortstat` = 182 files changed, +4935 / −3220。
