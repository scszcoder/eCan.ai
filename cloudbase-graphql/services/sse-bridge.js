/**
 * SSE (Server-Sent Events) Bridge — CN 实时推送
 *
 * 与 AWS AppSync realtime 对照:
 *   - AWS: client 连 wss://...appsync-realtime-api..., subscription resolver 路由
 *   - CN:  client 连 https://.../api/events (SSE), 业务层一字不改, 只换 transport
 *
 * 在 ecan-graphql-sse 进程内:
 *   - buildSSEResponse() 接受客户端 GET, hold 连接, 注册 event-bus 订阅
 *   - publish() 由 /publish HTTP POST 调用 (来自 ecan-graphql-api 的 cross-instance push)
 *   - bus.publish() 内部 fan-out 到所有匹配 (topic, target) 的 SSE 连接
 *
 * 注意: ecan-graphql-api 进程内的 subscription (graphql-yoga ws/http) 也用同一个 event-bus,
 * 但 SSE 路径默认是独立云函数, 实际只走 publish() 这条入口.
 */

const bus = require('../event-bus');

// 14 个 subscription topic 对应的 (topic, target) → bus channel key.
// null = 广播 (target 强制 __global__).
const TOPIC_TARGET_KEY = {
  onMessageReceived:       'chatID',
  onA2AMessageReceived:    'channelId',
  onAccountNotification:   'owner',
  onSkillEditorStreamEvent: 'sessionId',
  onPassiveCommand:        'runId',
  onPassiveHello:          'runId',
  onPassiveStepResult:     'runId',
  onPuzzleReceived:        null,
  onPuzzleResultReceived:  'pzid',
  onLongLLMTaskComplete:   'id',
  onSceneComplete:         'request_id',
  onAgentSceneEvent:       'acctSiteID',
  onStoryUpdate:           'acctSiteID',
  onTaskStatus:            'runID',
};

const GLOBAL_TOPIC = '__global__';

function heartbeatMs() {
  return Number(process.env.SSE_HEARTBEAT_MS) || 25000;
}

function sseHeaders() {
  return {
    'Content-Type': 'text/event-stream; charset=utf-8',
    'Cache-Control': 'no-cache, no-transform',
    'Connection': 'keep-alive',
    'X-Accel-Buffering': 'no',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Authorization, Content-Type',
  };
}

/**
 * Build an SSE Response for the client.
 * @param {string} topic   Subscription field name (e.g. "onTaskStatus")
 * @param {string} target  Channel/session/runID/etc; "__global__" for broadcast
 * @param {object} ctx     Resolver context (identity) — for owner scoping
 */
function buildSSEResponse(topic, target, ctx) {
  const expectedKey = TOPIC_TARGET_KEY[topic];
  if (expectedKey === undefined) {
    return jsonError(400, `Unknown topic: ${topic}`);
  }
  // Broadcast topics ignore whatever target the client sent.
  if (expectedKey === null) target = GLOBAL_TOPIC;
  else if (!target || target === GLOBAL_TOPIC) {
    return jsonError(400, `Topic ${topic} requires ?${expectedKey}=<value>`);
  }

  const enc = new TextEncoder();
  let closed = false;
  let interval = null;
  let iterator = null;

  const stream = new ReadableStream({
    async start(controller) {
      // 1. Immediate ":connected" comment so client confirms link.
      controller.enqueue(enc.encode(`: connected topic=${topic} target=${target}\n\n`));
      // 2. Subscribe to the bus.
      iterator = bus.subscribe(topic, target, ctx);
      // 3. Heartbeat — keeps the long-lived connection alive across proxies.
      interval = setInterval(() => {
        if (closed) return;
        try { controller.enqueue(enc.encode(`: ping ${Date.now()}\n\n`)); }
        catch { closed = true; }
      }, heartbeatMs());
      // 4. Drain events from the bus into SSE frames.
      try {
        while (!closed) {
          const { value, done } = await iterator.next();
          if (done) break;
          const data = JSON.stringify({ topic, payload: value });
          controller.enqueue(enc.encode(`event: ${topic}\ndata: ${data}\n\n`));
        }
      } catch (e) {
        try { controller.enqueue(enc.encode(`event: error\ndata: ${JSON.stringify({ message: e.message })}\n\n`)); }
        catch { /* closed */ }
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
      if (iterator) {
        const it = iterator;
        iterator = null;
        try { Promise.resolve(it.return?.()); } catch { /* ignore */ }
      }
    },
  });

  return new Response(stream, { status: 200, headers: sseHeaders() });
}

function jsonError(status, message) {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

/**
 * Publish a single event to all in-process subscribers of (topic, target).
 * Called from /publish when an ecan-graphql-api instance pushes a cross-instance event.
 * @returns {number} in-process delivery count
 */
function publish(topic, target, payload) {
  return bus.publish(topic, String(target), payload);
}

module.exports = { buildSSEResponse, publish, TOPIC_TARGET_KEY, GLOBAL_TOPIC, sseHeaders, jsonError };