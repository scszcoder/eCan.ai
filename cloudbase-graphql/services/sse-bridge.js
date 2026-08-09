/**
 * SSE (Server-Sent Events) Bridge — CN 实时推送
 *
 * 为什么用 SSE 不用 WS：
 *   - 腾讯云 API 网关产品已停止售卖，WS 协议函数无对外入口
 *   - TCB 静态网关 (service.tcloudbase.com) 不支持 WS Upgrade
 *   - SSE 走纯 HTTP 触发器，和现有 /api/graphql 路由复用
 *
 * 协议：
 *   - 客户端 GET /api/events?channel=xxx&topic=xxx&token=xxx
 *   - 服务端 hold 连接，返回 text/event-stream
 *   - event-bus publish 时直接写到所有匹配 (topic, target) 的 SSE 连接
 *
 * 内存模型（与原 WS 路径共享 event-bus）：
 *   - subscriptions 存 event-bus 内存 Map
 *   - SSE 连接 register 时调用 bus.subscribe()
 *   - bus.publish() 触发时遍历 SSE 连接写流
 *   - 连接关闭时调用 iterator.return() 清理订阅
 *
 * AWS AppSync 对比：
 *   - AWS：client 连 wss://...appsync-realtime-api..., subscription resolver 路由
 *   - CN： client 连 https://.../api/events (SSE), SSE Bridge 在同一进程路由
 *   - 业务层 (wan_chat.py) 一字不改 — 只换 transport 层
 */

const bus = require('../event-bus');

// topic → 从 SSE URL 参数 (target) 推导 bus channel key
const TOPIC_TARGET_KEY = {
  onMessageReceived:       'chatID',
  onA2AMessageReceived:    'channelId',
  onAccountNotification:   'owner',
  onSkillEditorStreamEvent: 'sessionId',
  onPassiveCommand:        'runId',
  onPassiveHello:          'runId',
  onPassiveStepResult:     'runId',
  onPuzzleReceived:        null,           // 广播
  onPuzzleResultReceived:  'pzid',
  onLongLLMTaskComplete:   'id',
  onSceneComplete:         'request_id',
  onAgentSceneEvent:       'acctSiteID',
  onStoryUpdate:           'acctSiteID',
  onTaskStatus:            'runID',
};

const GLOBAL_TOPIC = '__global__';

/**
 * 构建 SSE Response。
 *
 * @param {string} topic   Subscription field name (e.g. "onTaskStatus")
 * @param {string} target  Channel/session/runID/etc; "__global__" for broadcast topics
 * @param {object} ctx     GraphQL context (identity) — for owner scoping
 * @returns {Response}     Node fetch Response with text/event-stream body
 */
function buildSSEResponse(topic, target, ctx) {
  const expectedKey = TOPIC_TARGET_KEY[topic];
  if (expectedKey === undefined) {
    return new Response(JSON.stringify({ error: `Unknown topic: ${topic}` }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }
  // broadcast topic 强制 target="__global__"，其它 topic 必须有 target
  if (expectedKey === null && target && target !== GLOBAL_TOPIC) {
    target = GLOBAL_TOPIC;
  }
  if (expectedKey !== null && (!target || target === GLOBAL_TOPIC)) {
    return new Response(JSON.stringify({
      error: `Topic ${topic} requires ?${expectedKey}=<value>`,
    }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  let closed = false;
  let interval = null;
  let iterator = null;

  const stream = new ReadableStream({
    async start(controller) {
      const enc = new TextEncoder();

      // 1. 立即发首条注释让客户端确认连接已建立
      controller.enqueue(enc.encode(`: connected topic=${topic} target=${target}\n\n`));

      // 2. 订阅 event-bus（与 resolvers/subscriptions.js 用同一 Map）
      iterator = bus.subscribe(topic, target, ctx);

      // 3. 心跳 — 25 秒一次，防止 SCF / 反向代理切断空闲连接
      const heartbeatMs = Number(process.env.SSE_HEARTBEAT_MS) || 25000;
      interval = setInterval(() => {
        if (closed) return;
        try {
          controller.enqueue(enc.encode(`: ping ${Date.now()}\n\n`));
        } catch {
          closed = true;
        }
      }, heartbeatMs);

      // 4. 主循环：阻塞等待 event-bus 推一条
      try {
        while (!closed) {
          const { value, done } = await iterator.next();
          if (done) break;
          // SSE 协议：event: <name>\ndata: <json>\n\n
          const data = JSON.stringify({ topic, payload: value });
          controller.enqueue(enc.encode(`event: ${topic}\ndata: ${data}\n\n`));
        }
      } catch (e) {
        try {
          controller.enqueue(enc.encode(`event: error\ndata: ${JSON.stringify({ message: e.message })}\n\n`));
        } catch { /* closed */ }
      } finally {
        clearInterval(interval);
        try { await iterator.return?.(); } catch { /* ignore */ }
        iterator = null;
        try { controller.close(); } catch { /* already closed */ }
      }
    },
    cancel() {
      closed = true;
      if (interval) clearInterval(interval);
      // 通知 event-bus 清理订阅 — 不能 await，必须 fire-and-forget
      if (iterator) {
        const it = iterator;
        iterator = null;
        try { Promise.resolve(it.return?.()); } catch { /* ignore */ }
      }
    },
  });

  return new Response(stream, {
    status: 200,
    headers: {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no',
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': 'Authorization, Content-Type',
    },
  });
}

module.exports = { buildSSEResponse, TOPIC_TARGET_KEY, GLOBAL_TOPIC };