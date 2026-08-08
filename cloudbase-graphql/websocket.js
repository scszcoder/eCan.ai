/**
 * TCB WebSocket 服务（CN 端 Intl 兼容）
 *
 * 用于模拟 AWS AppSync Subscriptions 的实时推送功能。
 *
 * 支持两种客户端协议：
 *   - `graphql-ws` (subprotocol): 与 Intl AppSync 完全一致。任何走
 *        `subscription { onXxx(...) { ... } }` 的客户端都能用同一份代码
 *        跨 CN/Intl 直接切换（实现 CN = Intl 功能完全一致）。
 *   - `tcb` (legacy subprotocol): 旧的 TCB JSON 协议（chat-message / a2a-message
 *        频道 + action=subscribe/unsubscribe/ping）。保留以兼容历史客户端。
 *
 * 跨实例投递：上层业务（GraphQL API SCF）的 resolver 通过 HTTP POST
 *   POST /ws/push  body={topic, target, payload}
 *   头 X-ECAN-Push-Secret=$WEBSOCKET_PUSH_SECRET
 * 把事件推到这个 WebSocket SCF，再由本模块分发给所有订阅了 (topic, target)
 * 的连接。
 *
 * 在实例内部，业务 resolver 也可以直接走 event-bus.publish(topic, target, ...)。
 * 这里我们维护一份 in-process 订阅索引（subscriptionHandlers），让 SCF 内部
 * 任何 topic→target 的 publish 都能直接触发对应客户端消息。
 *
 * 兼容的事件类型（保持旧的频道名以便灰度过渡）：
 *   - skill-editor-stream: onSkillEditorStreamEvent
 *   - task-status: onTaskStatus
 *   - a2a-message: onA2AMessageReceived
 *   - passive-command: onPassiveCommand
 *   - passive-hello: onPassiveHello
 *   - passive-step-result: onPassiveStepResult
 *   - account-notification: onAccountNotification
 *   - scene-event: onAgentSceneEvent
 *   - chat-message: onMessageReceived
 *   - llm-complete: onLongLLMTaskComplete
 *   - puzzle-result: onPuzzleResultReceived
 *   - puzzle-received: onPuzzleReceived
 *   - story-update: onStoryUpdate
 *   - scene-complete: onSceneComplete
 */

// ============ SCF WebSocket Handler ============

/**
 * SCF WebSocket 主入口
 *
 * cloudbaserc.json 中配置的 handler: websocket.main
 */
exports.main = async (event, context) => {
  const { action } = event;
  switch (action) {
    case 'Connect':
      return await exports.onConnect(event, context);
    case 'Disconnect':
      return await exports.onDisconnect(event, context);
    case 'Message':
      return await exports.onMessage(event, context);
    default:
      return {
        statusCode: 400,
        body: JSON.stringify({ error: `Unknown action: ${action}` }),
      };
  }
};

// cloudbase SDK 是可选的：仅当我们真的有 WebSocket 连接要发送消息时才需要。
// 在 HTTP-only 模式（无 ProtocolType: WS）下，懒加载避免启动时 peer deps 缺失。
let cloudbase = null;
let tcbApp = null;
let _cloudbaseLoadFailed = false;
function getTcbApp() {
  if (_cloudbaseLoadFailed) return null;
  if (tcbApp) return tcbApp;
  if (!process.env.TCB_REGION) return null;
  try {
    cloudbase = require('@cloudbase/node-sdk');
    tcbApp = cloudbase.init({
      env: cloudbase.SYMBOL_CURRENT_ENV,
    });
  } catch (e) {
    console.warn('cloudbase.init failed (continuing without it):', e.message);
    _cloudbaseLoadFailed = true;
  }
  return tcbApp;
}

const ALLOW_INSECURE_AUTH = process.env.ALLOW_INSECURE_AUTH === 'true' && process.env.NODE_ENV !== 'production';

// 订阅字段名 → 内部频道名（兼容旧 CHAT_MESSAGE 等命名）
const SUBSCRIPTION_REGISTRY = {
  onMessageReceived:       { channel: 'chat-message',         argName: 'chatID' },
  onA2AMessageReceived:    { channel: 'a2a-message',          argName: 'channelId' },
  onAccountNotification:   { channel: 'account-notification', argName: 'owner' },
  onSkillEditorStreamEvent:{ channel: 'skill-editor-stream',  argName: 'sessionId' },
  onPassiveCommand:        { channel: 'passive-command',      argName: 'runId' },
  onPassiveHello:          { channel: 'passive-hello',        argName: 'runId' },
  onPassiveStepResult:     { channel: 'passive-step-result',  argName: 'runId' },
  onPuzzleReceived:        { channel: 'puzzle-received',      argName: null /* global */ },
  onPuzzleResultReceived:  { channel: 'puzzle-result',        argName: 'pzid' },
  onLongLLMTaskComplete:   { channel: 'llm-complete',         argName: 'id' },
  onSceneComplete:         { channel: 'scene-complete',       argName: 'request_id' },
  onAgentSceneEvent:       { channel: 'scene-event',          argName: 'acctSiteID' },
  onStoryUpdate:           { channel: 'story-update',         argName: 'acctSiteID' },
  onTaskStatus:            { channel: 'task-status',          argName: 'runID' },
};

const ALL_CHANNELS = new Set(Object.values(SUBSCRIPTION_REGISTRY).map((s) => s.channel));

// 连接管理：connectionId -> { userId, protocol, subscriptions: Set<subscriptionKey>, handlers: Map<opId, unsubscribe> }
const connections = new Map();

// In-process publish indices (mirrors event-bus for our internal subscriptions).
// Map<`${topic}:${target}`, Set<opId>>
const topicSubscribers = new Map();

function subscriptionKey(topic, target) {
  return `${topic}:${String(target)}`;
}

function addTopicSubscriber(topic, target, opId) {
  const key = subscriptionKey(topic, target);
  let set = topicSubscribers.get(key);
  if (!set) { set = new Set(); topicSubscribers.set(key, set); }
  set.add(opId);
}

function removeTopicSubscriber(topic, target, opId) {
  const key = subscriptionKey(topic, target);
  const set = topicSubscribers.get(key);
  if (!set) return;
  set.delete(opId);
  if (set.size === 0) topicSubscribers.delete(key);
}

// ============ WebSocket 处理函数 ============

/**
 * 连接建立时调用
 */
exports.onConnect = async (event, context) => {
  const connectionId = event.connectionId || event.connectionContext?.connectionId;
  const queryStringParameters = event.queryStringParameters || event.connectionContext?.queryString;
  // SCF 把客户端请求的 Sec-WebSocket-Protocol 放在 headers 里
  const headerProto = pickSubprotocol(event);
  // 也兼容 query 参数（部分客户端不支持 header 协商）
  const queryProto = queryStringParameters?.protocol;

  const protocol = headerProto || queryProto || 'tcb';

  try {
    let userId = null;
    const app = getTcbApp();
    if (app && queryStringParameters?.token) {
      try {
        const auth = app.auth();
        const verified = await auth.verifyJwt(queryStringParameters.token);
        if (verified) {
          userId = verified.uid || verified.openid || verified.sub || null;
        }
      } catch (e) {
        return { statusCode: 401, body: JSON.stringify({ error: 'Invalid or expired access token' }) };
      }
    }
    if (!userId && ALLOW_INSECURE_AUTH) userId = queryStringParameters?.testUser || 'local-development-user';
    if (!userId) return { statusCode: 401, body: JSON.stringify({ error: 'Bearer token required' }) };

    connections.set(connectionId, {
      userId,
      protocol,
      subscriptions: new Set(),
      opHandlers: new Map(), // opId -> { topic, target, unsubscribe }
      connectedAt: Date.now(),
    });

    console.log(`WebSocket connected: ${connectionId}, user: ${userId}, protocol=${protocol}`);
    return {
      statusCode: 200,
      body: JSON.stringify({
        success: true,
        connectionId,
        protocol,
      }),
    };
  } catch (error) {
    console.error('Connection error:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({ success: false, error: error.message }),
    };
  }
};

/**
 * 连接断开时调用
 */
exports.onDisconnect = async (event, context) => {
  const connectionId = event.connectionId || event.connectionContext?.connectionId;
  const conn = connections.get(connectionId);
  if (conn) {
    // 清理所有订阅
    for (const unsubscribe of (conn.opHandlers?.values() || [])) {
      try { unsubscribe(); } catch { /* swallow */ }
    }
    connections.delete(connectionId);
    console.log(`WebSocket disconnected: ${connectionId}, user: ${conn.userId}`);
  }
  return {
    statusCode: 200,
    body: JSON.stringify({ success: true }),
  };
};

/**
 * 接收客户端消息
 *
 * - graphql-ws 子协议的客户端：发送 {type: connection_init|start|...}
 * - tcb（legacy）子协议的客户端：发送 {action: subscribe|unsubscribe|ping}
 */
exports.onMessage = async (event, context) => {
  const connectionId = event.connectionId || event.connectionContext?.connectionId;
  const messageBodyStr = event.messageBody || event.body;

  const conn = connections.get(connectionId);
  if (!conn) {
    return { statusCode: 400, body: JSON.stringify({ error: 'Connection not found' }) };
  }

  let message;
  try {
    message = JSON.parse(messageBodyStr);
  } catch (e) {
    return { statusCode: 400, body: JSON.stringify({ error: 'Invalid JSON' }) };
  }

  if (conn.protocol === 'graphql-ws') {
    return await handleGraphQLWsMessage(conn, connectionId, message);
  }
  // legacy TCB JSON 协议
  return await handleTcbJsonMessage(conn, connectionId, message);
};

// ============ graphql-ws protocol ============

async function handleGraphQLWsMessage(conn, connectionId, message) {
  const type = message.type;
  // 1. connection_init
  if (type === 'connection_init' || type === 'ConnectionInit') {
    return {
      statusCode: 200,
      body: JSON.stringify({
        type: 'connection_ack',
        payload: { connectionTimeoutMs: 300000 },
      }),
    };
  }

  // 2. start: 客户端开始一个 subscription
  if (type === 'start' || type === 'Start') {
    const opId = message.id || message.payload?.id || String(Date.now());
    const payload = message.payload || {};
    let query = payload.query;
    let variables = payload.variables || {};
    // AppSync 客户端习惯把整个 {query, variables} 序列化为 data 字符串
    if (typeof payload.data === 'string') {
      try {
        const parsed = JSON.parse(payload.data);
        query = parsed.query || query;
        variables = parsed.variables || variables;
      } catch { /* ignore */ }
    }
    const { topic, target, error } = parseSubscription(query, variables);
    if (error) {
      return {
        statusCode: 200, // graphql-ws 仍用 200，错误通过 error 消息回传
        body: JSON.stringify({
          id: opId,
          type: 'error',
          payload: [{ message: error }],
        }),
      };
    }
    // 立即回 start_ack
    const ack = {
      id: opId,
      type: 'start_ack',
    };
    // 注册订阅：把事件映射到 connection 发送
    const unsubscribe = () => {
      removeTopicSubscriber(topic, target, opId);
      conn.opHandlers.delete(opId);
      conn.subscriptions.delete(subscriptionKey(topic, target));
    };
    addTopicSubscriber(topic, target, opId);
    conn.opHandlers.set(opId, { topic, target, unsubscribe });
    conn.subscriptions.add(subscriptionKey(topic, target));

    // 异步发送给客户端 ack
    sendToConnection(connectionId, ack).catch((e) => {
      console.warn(`[ws] failed to send start_ack: ${e.message}`);
    });
    return { statusCode: 200, body: JSON.stringify({ success: true }) };
  }

  // 3. stop / complete: 客户端取消一个订阅
  if (type === 'stop' || type === 'complete' || type === 'Stop' || type === 'Complete') {
    const opId = message.id || message.payload?.id;
    if (opId && conn.opHandlers.has(opId)) {
      try { conn.opHandlers.get(opId).unsubscribe(); } catch { /* swallow */ }
    }
    return { statusCode: 200, body: JSON.stringify({ success: true }) };
  }

  // 4. connection_terminate
  if (type === 'connection_terminate' || type === 'ConnectionTerminate') {
    return { statusCode: 200, body: JSON.stringify({ type: 'complete' }) };
  }

  // 5. ping (some clients use this)
  if (type === 'ping' || type === 'Ping') {
    return { statusCode: 200, body: JSON.stringify({ type: 'pong' }) };
  }

  return { statusCode: 400, body: JSON.stringify({ error: `Unknown graphql-ws message type: ${type}` }) };
}

/**
 * 把 GraphQL subscription 字符串解析成 (topic, target)。
 * 不依赖完整的 GraphQL 解析器（subscriptions-transport-ws 风格的简单 grammar）。
 * 支持：
 *   `subscription { onXxx($var: Type!) { ... } }`
 *   `subscription Name { onXxx(...) { ... } }`
 *   `subscription { onXxx(arg: "literal") { ... } }`
 */
function parseSubscription(query, variables) {
  if (!query || typeof query !== 'string') {
    return { error: 'Empty subscription query' };
  }
  // 找第一个 field call 形如 onXxx(...)
  const fieldRe = /\b(on[A-Z][A-Za-z0-9]+)\s*(?:\(([^)]*)\))?/g;
  const match = fieldRe.exec(query);
  if (!match) {
    return { error: 'No subscription field found in query' };
  }
  const fieldName = match[1];
  const argList = match[2] || '';
  const reg = SUBSCRIPTION_REGISTRY[fieldName];
  if (!reg) {
    return { error: `Unsupported subscription field: ${fieldName}` };
  }
  const topic = fieldName; // event-bus topic == subscription field name
  const argName = reg.argName;
  if (!argName) {
    // 全局订阅（如 onPuzzleReceived）
    return { topic, target: '__global__' };
  }
  // 1. 优先从 variables 拿
  if (variables && variables[argName] != null) {
    return { topic, target: String(variables[argName]) };
  }
  // 2. 解析 query 里的字面量，e.g. onA2AMessageReceived(channelId: "abc")
  // 支持 $var 引用 和 字面量
  const argRe = new RegExp(`\\b${argName}\\s*:\\s*("[^"]*"|\\$\\w+)`);
  const argMatch = argRe.exec(argList);
  if (argMatch) {
    const raw = argMatch[1];
    if (raw.startsWith('"')) {
      return { topic, target: raw.slice(1, -1) };
    }
    // 形如 $channelId —— 已经在上面 variables 处理；这里兜底
    if (variables && variables[raw.slice(1)] != null) {
      return { topic, target: String(variables[raw.slice(1)]) };
    }
  }
  return { error: `Missing argument ${argName} for ${fieldName}` };
}

// ============ tcb (legacy) protocol ============

async function handleTcbJsonMessage(conn, connectionId, message) {
  const { action, channel, data, target } = message;
  switch (action) {
    case 'subscribe':
      if (channel && target && ALL_CHANNELS.has(channel)) {
        // 旧协议里 channel 是字符串频道名（chat-message / a2a-message ...）
        // 因为我们统一用 topic 命名（event-bus 风格），保留旧频道名作为 topic 的别名
        const opId = `sub-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const topic = channelToTopic(channel);
        const unsubscribe = () => {
          removeTopicSubscriber(topic, target, opId);
          conn.opHandlers.delete(opId);
          conn.subscriptions.delete(subscriptionKey(topic, target));
        };
        addTopicSubscriber(topic, target, opId);
        conn.opHandlers.set(opId, { topic, target, unsubscribe });
        conn.subscriptions.add(subscriptionKey(topic, target));
        return {
          statusCode: 200,
          body: JSON.stringify({ success: true, action: 'subscribed', channel, target }),
        };
      }
      return {
        statusCode: 400,
        body: JSON.stringify({
          success: false,
          error: `Invalid channel: ${channel}`,
          validChannels: Array.from(ALL_CHANNELS),
        }),
      };

    case 'unsubscribe':
      if (channel) {
        const topic = channelToTopic(channel);
        const subKey = subscriptionKey(topic, target || conn.userId);
        // 找到该 subKey 对应 opId 并清理
        for (const [opId, h] of conn.opHandlers) {
          if (subscriptionKey(h.topic, target || conn.userId) === subKey) {
            try { h.unsubscribe(); } catch { /* swallow */ }
            break;
          }
        }
      } else {
        for (const unsubscribe of (conn.opHandlers?.values() || [])) {
          try { unsubscribe(); } catch { /* swallow */ }
        }
      }
      return {
        statusCode: 200,
        body: JSON.stringify({ success: true, action: 'unsubscribed', channel }),
      };

    case 'publish':
      return { statusCode: 403, body: JSON.stringify({ error: 'Client publishing is forbidden' }) };

    case 'ping':
      return {
        statusCode: 200,
        body: JSON.stringify({ success: true, action: 'pong', timestamp: Date.now() }),
      };

    default:
      return {
        statusCode: 400,
        body: JSON.stringify({ success: false, error: `Unknown action: ${action}` }),
      };
  }
}

function channelToTopic(channel) {
  // 旧协议 channel 是频道名（如 chat-message）；把频道名映射回 topic
  // （频道名通常跟 topic 名很接近，但 onMessageReceived -> chat-message）
  for (const [field, reg] of Object.entries(SUBSCRIPTION_REGISTRY)) {
    if (reg.channel === channel) return field;
  }
  return channel; // 兜底
}

// ============ 发送消息给客户端 ============

async function sendToConnection(connectionId, message) {
  const conn = connections.get(connectionId);
  if (!conn) return;
  const messageStr = JSON.stringify(message);
  const app = getTcbApp();
  if (!app) {
    console.warn('[ws] tcbApp not available; cannot send to client');
    return;
  }
  try {
    const wsService = app.ws();
    await wsService.send(connectionId, messageStr);
  } catch (e) {
    console.error(`[ws] failed to send to ${connectionId}: ${e.message}`);
    if (e.message.includes('connection') || e.message.includes('不存在')) {
      connections.delete(connectionId);
    }
    throw e;
  }
}

/**
 * 内部 dispatch：当某个 (topic, target) 有 publish 时调用，按 connection 协议分发。
 * - graphql-ws 客户端：发送 {type: 'data', id: opId, payload: {data: {topic: payload}}}
 * - tcb 客户端：发送 {type: channel, target, data, timestamp}
 */
async function dispatch(topic, target, payload) {
  const key = subscriptionKey(topic, target);
  const opIds = topicSubscribers.get(key);
  if (!opIds || opIds.size === 0) return 0;

  let delivered = 0;
  for (const opId of [...opIds]) {
    // 找到该 opId 所属的 connection
    let targetConn = null;
    let targetConnId = null;
    for (const [connId, conn] of connections) {
      if (conn.opHandlers.has(opId)) {
        targetConn = conn;
        targetConnId = connId;
        break;
      }
    }
    if (!targetConn) {
      // 可能已断开
      removeTopicSubscriber(topic, target, opId);
      continue;
    }
    let message;
    if (targetConn.protocol === 'graphql-ws') {
      // 注意：graphql-ws 需要 client 实际请求的 selection set 字段；
      // 因为我们不解析 query selection，这里直接以 GraphQL 字段名包装 payload
      message = {
        id: opId,
        type: 'data',
        payload: { data: { [topic]: payload } },
      };
    } else {
      // tcb legacy
      const channel = SUBSCRIPTION_REGISTRY[topic]?.channel || topic;
      message = {
        type: channel,
        target,
        data: payload,
        timestamp: Date.now(),
      };
    }
    try {
      await sendToConnection(targetConnId, message);
      delivered += 1;
    } catch (e) {
      console.warn(`[ws] dispatch failed: ${e.message}`);
    }
  }
  return delivered;
}

/**
 * 统计订阅指定频道的连接数
 */
function countSubscribers(topic, target) {
  const set = topicSubscribers.get(subscriptionKey(topic, target));
  return set ? set.size : 0;
}

// ============ HTTP API（用于 SCF 之间的推送） ============

/**
 * HTTP 触发器：推送事件到 WebSocket 订阅者
 *
 * Body: {topic, target, payload}
 * Header: X-ECAN-Push-Secret: $WEBSOCKET_PUSH_SECRET
 */
exports.push = async (event, context) => {
  try {
    const expectedSecret = process.env.WEBSOCKET_PUSH_SECRET;
    const suppliedSecret = event.headers?.['x-ecan-push-secret'] || event.headers?.['X-ECAN-Push-Secret'];
    if (!expectedSecret || suppliedSecret !== expectedSecret) {
      return { statusCode: 401, body: JSON.stringify({ error: 'Unauthorized push' }) };
    }
    const body = JSON.parse(event.body || '{}');
    const { topic, target, payload } = body;

    if (!topic || !target || payload == null) {
      return {
        statusCode: 400,
        body: JSON.stringify({ error: 'Missing topic, target, or payload' }),
      };
    }
    if (!SUBSCRIPTION_REGISTRY[topic]) {
      return {
        statusCode: 400,
        body: JSON.stringify({
          error: `Unknown topic: ${topic}`,
          validTopics: Object.keys(SUBSCRIPTION_REGISTRY),
        }),
      };
    }

    const delivered = await dispatch(topic, target, payload);
    return {
      statusCode: 200,
      body: JSON.stringify({
        success: true,
        topic,
        target,
        delivered,
      }),
    };
  } catch (error) {
    console.error('Push error:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({ success: false, error: error.message }),
    };
  }
};

/**
 * HTTP 触发器：获取连接状态
 */
exports.status = async (event, context) => {
  const expectedSecret = process.env.WEBSOCKET_PUSH_SECRET;
  const suppliedSecret = event.headers?.['x-ecan-push-secret'] || event.headers?.['X-ECAN-Push-Secret'];
  if (!expectedSecret || suppliedSecret !== expectedSecret) {
    return { statusCode: 401, body: JSON.stringify({ error: 'Unauthorized status request' }) };
  }
  const connectionsList = [];
  for (const [id, conn] of connections) {
    connectionsList.push({
      connectionId: id,
      userId: conn.userId,
      protocol: conn.protocol,
      subscriptions: Array.from(conn.subscriptions),
      connectedAt: new Date(conn.connectedAt).toISOString(),
    });
  }
  return {
    statusCode: 200,
    body: JSON.stringify({
      totalConnections: connections.size,
      topicChannels: topicSubscribers.size,
      connections: connectionsList,
    }),
  };
};

/**
 * 提取客户端请求的 Sec-WebSocket-Protocol
 * SCF 事件里可能叫 'Sec-WebSocket-Protocol' 或 'sec-websocket-protocol'
 */
function pickSubprotocol(event) {
  const headers = event.headers || {};
  const raw = headers['Sec-WebSocket-Protocol'] || headers['sec-websocket-protocol'];
  if (!raw) return null;
  // 客户端可能发送多个：'graphql-ws, tcb'
  const parts = raw.split(',').map((s) => s.trim()).filter(Boolean);
  if (parts.includes('graphql-ws')) return 'graphql-ws';
  if (parts.includes('tcb')) return 'tcb';
  return parts[0] || null;
}

// 暴露给测试或同进程的 subscriber
module.exports = {
  ...exports,
  // 单元测试钩子
  _subscriptions: SUBSCRIPTION_REGISTRY,
  _parseSubscription: parseSubscription,
  _dispatch: dispatch,
  _connections: connections,
  _topicSubscribers: topicSubscribers,
};
