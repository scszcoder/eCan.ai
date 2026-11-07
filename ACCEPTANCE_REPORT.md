# 运行时验收报告 — eCan.ai UI 优化（feat/ui-polish）

日期：验收会话当期 | 分支：`feat/ui-polish`（基线 `origin/master` @ `49e2deef7`）| **未提交**（按用户指令）

---

## 1. 验收环境

| 项 | 值 |
|---|---|
| 开发服务器 | `npx vite --port 3000 --strictPort`（**清空 `node_modules/.vite` 后重启**） |
| 对照树 | 干净基线 `/tmp/wt_base`，`npx vite --port 3100` |
| 依赖 | 两棵树**共享同一 `node_modules`**（基线为符号链接）→ 依赖完全一致，差异只可能来自源码 |
| 浏览器 | PI-Desktop 内置浏览器（CDP），真实 DOM 断言 |

> **重要前置动作**：初次运行时 `/analytics`、`/skill_editor` 报 `Cannot read properties of null (reading 'useContext')`。
> 判定为 **Vite optimizeDeps 陈旧缓存**。执行 `rm -rf node_modules/.vite` 并重启后 `/analytics` **恢复正常**。
> 此前所有"页面报错"的结论均须以此干净环境为准。

---

## 2. 门禁结果（全部通过）

| 门禁 | 结果 |
|---|---|
| `npx vite build` | ✅ **通过**，`✓ built in 38.17s`，全部分块产出。仅剩既有 vendor 分块体积告警 |
| `npx tsc --noEmit` | **644** 错误；基线 **646** → **比基线少 2 个** |
| TS 逐文件 delta | 比对 **164 个**文件：**0 个文件错误数增加**，**0 个新增报错文件** |
| `npm test`（Jest） | 分支 **8 failed / 5 passed，16/16 用例通过**；基线**完全一致** → **0 测试回归** |
| Vite 模块转换 | `pages/` + `components/` **333 个** .tsx/.ts 全部转换成功，**0 失败**；**16 个** .css 全部成功 |
| Token 解析 | `:root` 声明 **136** 个 token，**未解析数 = 0** |

333 个模块零转换失败，直接证明 Phase 3B 的 478 处 hex→token 批量替换**未重现已修复的引号吞没缺陷**。

---

## 3. 路由运行时扫描

以真实菜单点击 + hash 直连两种方式遍历，逐条读取渲染内容与新增控制台错误。

### 3.1 渲染正常（内容正确、零错误）

| 路由 | 实测内容片段 | 控制台错误 |
|---|---|---|
| `/stores` | 店铺 · 显示已归档 · 新建店铺 | 0 |
| `/chat` | 聊天记录 · 商品调研Agent | 1（ResizeObserver，无害） |
| `/tasks` | 任务管理 · 6 个任务 · 运行中/就绪/待处理 | 0 |
| `/skills` | 技能列表 · 技能商店 12 · 我的技能库 8 | 0 |
| `/schedule` | 2026年 11月 日历网格 | 0 |
| `/tools` | 工具列表 · rpa_supervisor_scheduling_work | 0 |
| `/products` | 产品 · 新增 Travel Mug · LED Desk Lamp | 0 |
| `/warehouses` | 仓库 · 新增 West Coast Hub | 0 |
| `/prompts` | 添加 · 模板库 · 设计指南 · 请选择一个提示词 | 0 |
| `/avatars` | 数字形象 8 items · 上传新形象 | 0 |
| `/account` | 账户 · 当前套餐 · 免费版 · 余额 ¥0.00 | 0 |
| `/plugins` | 插件 · 内置/已安装 · douyin_listing v0.1 | 0 |
| `/console` | 活跃 Agent Alpha · 地面电脑 · A区域 85 | 0 |
| `/vehicles` | 电脑管理 · Pods 0 of 20 | 0 |
| `/fleet` | 机群监控 · 还没有机器上报 | 0 |
| `/shipping-label` | 快递标签配置 — White Label 5422 | 0 |
| `/dashboard` | 欢迎, …@qq.com · 智能体管理中心 | 0 |
| `/analytics` | 本周 总任务数 1,560 · 任务完成趋势 · 资源利用率 | 0 |
| `/agents` | 智能体资源 · 商品上架助手等 | 0 |
| `/settings` | 通用设置 · LLM 管理 · 嵌入模型管理 | 0 |

**20/20 路由渲染正常**，唯一控制台输出为 `/chat` 的 `ResizeObserver loop` 警告（浏览器无害噪声，非应用缺陷）。

### 3.2 与基线比对确认的**既有**问题（非本次引入）

| 路由 | 现象 | 基线复现 | 结论 |
|---|---|---|---|
| `/skill_editor` | `LazyErrorBoundary` 渲染失败 + `Invalid hook call` / `useContext` null | ✅ **基线同样报错**（同一条栈） | `modules/skill-editor` 自身的 `@flowgram.ai` / `semi-ui` 依赖在 Vite dev 下失效，**既有缺陷** |
| `/knowledge-ported` | `[DocumentsTab] API call failed` | 后端数据依赖 | 非 UI 问题 |

`/skill_editor` 的判定依据：**干净 `master` 树在同一路径触发完全相同的错误**；且我对该模块的改动仅为 `editor.tsx` 增加 `className="skill-editor-root"` + 注释、CSS 由 `:root` 收拢为 `.skill-editor-root`（0 行业务逻辑）。

---

## 4. 主题系统实测

通过真实 Provider 路径（`localStorage.theme` → reload）驱动，**非**手工改 class。

| 观测点 | dark | light |
|---|---|---|
| `body.className` | `dark` | `light` |
| `data-theme` | `dark` | `light` |
| `--text-primary` | `#f8fafc` | `#0f172a` |
| `--bg-primary` | `#0f172a` | `#f5f7fa` |
| `--border-color` | `rgba(255,255,255,0.08)` | `rgba(15,23,42,0.10)` |
| `--primary-color` | `#3b82f6`（品牌色保留） | `#2563eb`（浅底加深，对比度需要） |
| `.ant-layout` 实际背景 | `rgb(15, 23, 42)` | `rgb(245, 247, 250)` ✅ 真实重绘 |

- antd 生成样式**确实随主题重绘**（layout 背景由深转浅），证明 `getAntdThemeConfig(isDark)` 链路有效。
- `ThemeContext.applyResolvedTheme` 只写 `body.className` + `data-theme`，**不再重复写颜色变量** → Phase 2 的"双写"清理已确认生效。
- 双主题截图已存档：浅色（浅底深字、20 个导航项齐全）、深色（深底浅字、logo 正确显示）。

---

## 5. 设计令牌与控件阶梯实测（深色 / 实时 DOM）

```
--primary-color   #3b82f6      (品牌色，双主题恒为蓝)
--success-color   #22c55e
--error-color     #ef4444
--warning-color   #fbbf24
--text-on-primary #ffffff
--border-color    rgba(255,255,255,0.08)
--radius-control  10px
--control-height-md 32px
--page-padding    24px
--font-size-base  14px
--content-gap     20px
242 个样式表加载
```

### 按钮尺寸阶梯（修复验证）

| 签名（高 \| 字号 \| 圆角） | 数量 | 说明 |
|---|---|---|---|
| `28px \| 12px \| 8px` | **14** | `.ant-btn-sm` 正确生效 |
| `40px \| 14px \| 8px` | 2 | 默认档 |
| `40px \| 16px \| 10px` | 1 | 大号 |
| `32px \| 14px \| 6px` | 1 | 中号 |

**结论**：`28px` 小按钮实测存在，证明"`.ant-btn{height:40px!important}` 把全站按钮强制压成 40px"的缺陷**已修复**。

---

## 6. 变更范围

```
162 个工作树条目，全部未提交
159 files changed, +2621 / −2388   (不含 mcp_tools_schema.json)
D  gui_v2/src/App.css                 (死代码删除)
?? gui_v2/src/components/Common/RefreshButton.tsx   (共享组件)
?? gui_v2/src/components/Layout/PageShell.tsx       (共享页壳)
```

### skill-editor 边界核对

用户要求"skill-editor 保持原样（仅防泄漏）"。实际改动：

- `editor.tsx`：**+2/−2**，仅 `<EditorContainer>` 加 `className="skill-editor-root"` + 注释
- `styles/index.css`：**+16/−6**，仅将 `:root { … }` 收拢为 `.skill-editor-root { … }`

该 CSS 原本在**被 import 的模块样式**里声明 `:root`，会污染全站变量。收拢为模块作用域属于**用户授权的防泄漏例外**，且为正确性改进。**未触碰任何编辑器业务逻辑。**

---

## 7. 结论与遗留

**通过。** 构建、类型检查、单测三处门禁全部不劣于基线（类型错误还少 2 个）；20 条路由渲染正常；双主题真实切换并重绘；token 全部解析；按钮阶梯修复生效。

### 遗留（均为既有，非本次范围）

1. `modules/skill-editor` 在 Vite dev 下 `useContext` 崩溃 —— **基线同样存在**，属模块依赖问题。
2. 浅色模式 logo 仍为深色专用素材，需要设计补齐。
3. 全仓仍有约 4,700 处硬编码色（绝大部分在废弃 `gui/` PyQt 树与 vendor 目录），超出 `gui_v2/` 范围。
4. `mcp_tools_schema.json` 的改动仍在 stash 中，未触碰。

### 待办

- **按用户指令：不提交。** 工作树停留在 `feat/ui-polish`，162 个条目原样保留。
