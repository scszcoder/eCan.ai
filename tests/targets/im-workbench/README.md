# IM Workbench Target

独立 IM 客服并发测试靶场。用于验证 browser automation skills 在高并发消息、多会话切换、FAQ/RAG 检索场景下的稳定性。

## 启动

```bash
cd tests/targets/im-workbench
npm install
npm run dev
```

默认运行在 `http://localhost:4173`

## 用途

- **主工程角色**：只负责创建 skill、执行 browser automation、做并发控制
- **靶场角色**：作为被操作目标，承载 IM 场景，由主工程 skill 控制

两者完全解耦，各自独立运行。

## 场景模式

| 模式 | 说明 |
|------|------|
| Normal Traffic | 常规流量，每 3-5 秒一条消息 |
| Promo Burst | 促销突发，5-10 条/秒，模拟高峰期 |
| Refund Wave | 退款高峰，大量退款相关消息涌入 |
| Mixed Languages | 中英文混合消息流 |

## 自动化锚点 (data-testid)

### 核心区域
- `im-workbench-page` - 页面根节点
- `control-bar` - 控制栏
- `session-pool` - 会话池
- `message-column` - 消息列
- `knowledge-card` - 知识卡片
- `timeline` - 事件时间线
- `customer-profile` - 客户画像

### 会话操作
- `session-item-{id}` - 会话项（按 ID）
- `session-tab-{status}` - 按状态切换 tab（urgent/active/waiting/resolved）
- `active-session` - 当前活跃会话

### 消息交互
- `reply-input` - 回复输入框
- `send-button` - 发送按钮
- `suggested-reply-{index}` - 建议回复（0-4）
- `message-bubble-{sender}-{id}` - 消息气泡（sender: customer/agent/system）

### 知识辅助
- `knowledge-hit-{source}-{id}` - 知识命中（source: faq/rag/db）
- `knowledge-use-{id}` - 使用该知识辅助

### 控制
- `scenario-option-{mode}` - 切换场景（normal/burst/refund_wave/multilingual）
- `auto-reply-switch` - 自动回复开关
- `run-pause-button` - 运行/暂停按钮
- `concurrent-slider` - 并发会话数滑块
- `metrics-row` - KPI 指标行
- `sla-timer-{sessionId}` - SLA 倒计时

## Skill 操作热路径

1. 打开靶场页面
2. 读取 urgent tab 中的会话列表
3. 点击最紧急会话
4. 读取最新客户消息内容
5. 检查 knowledge-card 中的建议答案
6. 填入 reply-input
7. 点击 send-button
8. 检查 timeline 更新
9. 切换下一会话，重复

## 目录结构

```
tests/targets/im-workbench/
├── src/
│   ├── main.tsx      # 应用入口
│   └── App.tsx       # 完整 IM 靶场页面
├── index.html
├── package.json
├── vite.config.ts
└── tsconfig.json
```
