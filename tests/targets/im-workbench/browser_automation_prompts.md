# IM Workbench Browser Automation Prompts

下面提供两套可直接用于 browser automation / skill 的操作模板。

- 模板 A：单会话稳定处理版
- 模板 B：多会话并发轮询版

目标页面：`http://localhost:4173`

---

## 模板 A：单会话稳定处理版

适用场景：
- 验证 skill 是否能稳定处理一个紧急客户会话
- 适合 smoke test / demo / 基础成功率验证

可直接使用的 Prompt：

```text
你现在要操作一个独立 IM 客服测试靶场。

目标地址：
http://localhost:4173

你的任务是稳定处理 1 个紧急会话，并验证从“发现消息”到“发送回复”的完整流程。

请严格按下面步骤执行：

1. 打开页面 `http://localhost:4173`
2. 确认页面根节点 `[data-testid="im-workbench-page"]` 存在
3. 确认控制栏 `[data-testid="control-bar"]` 可见
4. 点击紧急会话 tab：`[data-testid="session-tab-urgent"]`
5. 在会话池 `[data-testid="session-pool"]` 中寻找第一个会话项：`[data-testid^="session-item-"]`
6. 点击该会话
7. 确认中间消息区 `[data-testid="message-column"]` 出现
8. 确认当前活跃会话 `[data-testid="active-session"]` 存在
9. 读取最后一条客户消息，目标元素是：`[data-testid^="message-bubble-customer-"]`
10. 检查右侧知识面板 `[data-testid="knowledge-card"]`
11. 优先点击第一个可用的 knowledge use 按钮：`[data-testid^="knowledge-use-"]`
12. 检查回复输入框 `[data-testid="reply-input"]` 是否已有内容
13. 如果没有内容，则手动输入一条简短客服回复，例如：
    `Hello, I have checked your request and I am helping you now.`
14. 确认发送按钮 `[data-testid="send-button"]` 可点击
15. 点击发送按钮
16. 检查是否出现新的 agent 消息：`[data-testid^="message-bubble-agent-"]`
17. 检查事件时间线 `[data-testid="timeline"]` 是否出现新的 timeline item：`[data-testid^="timeline-event-"]`
18. 最终输出：
    - 处理的 session 名称
    - 最后一条 customer message 内容
    - 是否成功发送 reply
    - 是否看到 timeline 更新
    - 是否遇到阻塞

执行要求：
- 优先使用 data-testid 定位
- 每完成一步再做下一步，不要盲点
- 若页面状态变化，先重新观察再操作
- 如果遇到找不到元素，先确认上一步是否真的成功
- 不要修改页面代码，只做页面交互验证
```

---

## 模板 B：多会话并发轮询版

适用场景：
- 验证 skill 在高并发 IM 页面中的处理能力
- 验证多 session 切换、读取消息、发送回复、SLA 观察能力
- 适合长时间轮询测试

可直接使用的 Prompt：

```text
你现在要操作一个独立 IM 客服并发测试靶场。

目标地址：
http://localhost:4173

你的任务是模拟一个客服 agent，在多会话并发场景下轮询处理会话。

总体目标：
- 优先处理 urgent 会话
- 然后处理 active 会话
- 每轮处理最多 3 个会话
- 每个会话都要完成“读取最新客户消息 -> 参考知识面板 -> 发送回复 -> 验证 timeline 更新”

请严格按以下流程执行：

1. 打开页面 `http://localhost:4173`
2. 确认页面根节点 `[data-testid="im-workbench-page"]` 存在
3. 确认控制栏 `[data-testid="control-bar"]` 存在
4. 切换场景到 burst：`[data-testid="scenario-option-burst"]`
5. 确认会话池 `[data-testid="session-pool"]` 可见
6. 先点击 `[data-testid="session-tab-urgent"]`
7. 收集 urgent tab 下前 3 个会话项：`[data-testid^="session-item-"]`
8. 如果 urgent 会话不足 3 个，则补充 active tab 中的前几个会话：`[data-testid="session-tab-active"]`

对每个选中的会话，重复执行以下步骤：

A. 点击该会话项
B. 确认 `[data-testid="active-session"]` 已切换
C. 读取最新一条客户消息：`[data-testid^="message-bubble-customer-"]` 中最后一个
D. 读取该会话的 SLA 指示器：`[data-testid^="sla-timer-"]`
E. 检查右侧知识卡 `[data-testid="knowledge-card"]`
F. 如果存在建议知识项，则优先点击第一个 use 按钮：`[data-testid^="knowledge-use-"]`
G. 检查输入框 `[data-testid="reply-input"]`
H. 如果输入框为空，则填入一条简短回复，例如：
   `Thanks for your message. I have reviewed this and will help you right away.`
I. 点击 `[data-testid="send-button"]`
J. 确认出现新的 agent 消息：`[data-testid^="message-bubble-agent-"]`
K. 检查事件时间线 `[data-testid="timeline"]` 是否有新增事件：`[data-testid^="timeline-event-"]`
L. 记录本会话结果：
   - session 标题
   - customer 最新消息
   - SLA 状态
   - 是否成功发送回复
   - 是否更新 timeline

全部处理完成后，输出汇总：
- 本轮共处理多少个 session
- 哪些 session 成功处理
- 哪些 session 失败或阻塞
- 失败原因是什么
- urgent/active 中还剩多少未处理会话

执行要求：
- 必须优先使用 data-testid
- 一次只处理一个会话，不要同时编辑多个输入框
- 每点击一个 session 后，先确认 active-session 已变化，再继续
- 如果页面因为 burst 模式发生刷新或重排，先重新观察列表，再继续
- 若某次点击失败，不要连续重复盲点，先重新抓取页面结构
- 不要修改页面代码，只做页面交互与验证
```

---

## 推荐选择器

### 页面级
- `[data-testid="im-workbench-page"]`
- `[data-testid="control-bar"]`
- `[data-testid="session-pool"]`
- `[data-testid="message-column"]`
- `[data-testid="knowledge-card"]`
- `[data-testid="timeline"]`

### 控制级
- `[data-testid="scenario-option-normal"]`
- `[data-testid="scenario-option-burst"]`
- `[data-testid="scenario-option-refund_wave"]`
- `[data-testid="scenario-option-multilingual"]`
- `[data-testid="auto-reply-switch"]`
- `[data-testid="run-pause-button"]`
- `[data-testid="concurrent-slider"]`

### 会话级
- `[data-testid="session-tab-urgent"]`
- `[data-testid="session-tab-active"]`
- `[data-testid="session-tab-waiting"]`
- `[data-testid="session-tab-resolved"]`
- `[data-testid^="session-item-"]`
- `[data-testid="active-session"]`
- `[data-testid^="sla-timer-"]`

### 消息级
- `[data-testid^="message-bubble-customer-"]`
- `[data-testid^="message-bubble-agent-"]`
- `[data-testid^="message-bubble-system-"]`
- `[data-testid="reply-input"]`
- `[data-testid="reply-char-count"]`
- `[data-testid="send-button"]`
- `[data-testid^="suggested-reply-"]`

### 知识与时间线
- `[data-testid^="knowledge-hit-"]`
- `[data-testid^="knowledge-use-"]`
- `[data-testid^="knowledge-copy-"]`
- `[data-testid^="timeline-event-"]`

---

## 建议执行策略

### 单会话模式
- 用于验证基础能力
- 先看 urgent，再处理第一个会话
- 每一步都确认状态变化

### 多会话模式
- 一轮最多处理 3 个会话
- 顺序建议：urgent -> active
- 避免一次抓太多会话，防止 burst 模式下 DOM 重排导致引用失效
- 每处理完一个会话后重新观察当前页面，再选下一个
