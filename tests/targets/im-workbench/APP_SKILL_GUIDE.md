# IM Workbench Concurrency Test Skill

此目录承载“应用内 skill”所需的测试素材，目标是让主应用中的 skill/workflow 能直接驱动独立 IM 靶场，验证多并发会话处理能力。

## 目标页面
- `http://localhost:4173`

## 已提供内容
- `browser_automation_prompts.md`：完整版 prompt
- `node_prompt_snippets.md`：适合节点输入的精简 prompt

## 推荐 skill 结构
建议在应用的 `my_skills/im_workbench_concurrency_tester_skill/diagram_dir/` 下创建正式流程图 skill，并按下面最小链路搭建：

1. Start
2. Browser Automation / Browser-Use 节点
3. End

## 推荐输入参数
Start 节点可定义以下输入：
- `target_url`：默认 `http://localhost:4173`
- `mode`：`single_session` / `multi_session`
- `max_sessions`：默认 `3`
- `scenario`：默认 `burst`
- `reply_template`：默认英文短回复

## Browser Automation 节点建议
### 单会话
直接使用 `node_prompt_snippets.md` 中“单会话节点 Prompt”。

### 多并发
直接使用 `node_prompt_snippets.md` 中“多会话轮询节点 Prompt”。

## 关键 data-testid
- `im-workbench-page`
- `control-bar`
- `session-pool`
- `session-tab-urgent`
- `session-tab-active`
- `active-session`
- `reply-input`
- `send-button`
- `knowledge-card`
- `timeline`

## 测试目标
- 优先处理 urgent 会话
- 验证 burst 模式下的会话切换稳定性
- 验证知识建议注入/复制后的回复发送
- 验证 timeline 事件更新

## 注意
当前仓库里还没有现成的“应用技能 JSON 模板”能安全复用为 browser automation 流程骨架；因此本目录先提供可直接粘贴进应用 skill editor 的 prompt 资产，避免误造不兼容的 skill JSON。

下一步建议是在应用 skill editor 里新建 skill：
- 名称：`im_workbench_concurrency_tester`
- 类型：browser automation / browser-use
- 主 prompt：优先使用多会话轮询版
