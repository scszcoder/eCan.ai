/**
 * TCB WebSocket 服务
 * 
 * 用于模拟 AWS AppSync Subscriptions 的实时推送功能
 * 
 * 架构：
 *   客户端 → WebSocket 连接 → 云函数 → Redis Pub/Sub → 消息广播
 * 
 * 支持的事件类型：
 *   - skill-editor-stream: 技能编辑器流式事件
 *   - task-status: 任务状态更新
 *   - a2a-message: Agent 间消息
 *   - passive-command: 被动命令
 *   - account-notification: 账号通知
 */

// ============ SCF WebSocket Handler ============

/**
 * SCF WebSocket 主入口
 * 
 * cloudbaserc.json 中配置的 handler: websocket.main
 * 
 * @param {object} event - SCF 事件
 * @param {object} context - SCF 上下文
 */
exports.main = async (event, context) => {
  const { action, connectionId, connectionContext, messageBody } = event;
  
  switch (action) {
    case 'Connect':
      return await this.onConnect(event, context);
    case 'Disconnect':
      return await this.onDisconnect(event, context);
    case 'Message':
      return await this.onMessage(event, context);
    default:
      return {
        statusCode: 400,
        body: JSON.stringify({ error: `Unknown action: ${action}` }),
      };
  }
};

const cloudbase = require('@cloudbase/node-sdk');

// TCB 环境初始化
let tcbApp = null;
if (process.env.TCB_REGION) {
  tcbApp = cloudbase.init({
    env: cloudbase.SYMBOL_CURRENT_ENV,
  });
}

// 不安全认证仅在非生产环境启用
const ALLOW_INSECURE_AUTH = process.env.ALLOW_INSECURE_AUTH === 'true' && process.env.NODE_ENV !== 'production';

// 事件类型
const EVENT_TYPES = {
  SKILL_EDITOR_STREAM: 'skill-editor-stream',
  TASK_STATUS: 'task-status',
  A2A_MESSAGE: 'a2a-message',
  PASSIVE_COMMAND: 'passive-command',
  ACCOUNT_NOTIFICATION: 'account-notification',
  SCENE_EVENT: 'scene-event',
  LLM_COMPLETE: 'llm-complete',
  PUZZLE_RESULT: 'puzzle-result',
};

// 连接管理
const connections = new Map(); // connectionId -> { userId, subscriptions }

// ============ WebSocket 处理函数 ============

/**
 * 连接建立时调用
 * 
 * 支持两种调用方式：
 * 1. TCB WebSocket 触发器 (action: 'Connect')
 * 2. HTTP 触发器测试
 */
exports.onConnect = async (event, context) => {
  // 适配 SCF WebSocket 事件格式
  const connectionId = event.connectionId || event.connectionContext?.connectionId;
  const queryStringParameters = event.queryStringParameters || event.connectionContext?.queryString;
  
  try {
    // 获取用户身份
    let userId = null;
    if (tcbApp && queryStringParameters?.token) {
      try {
        const auth = tcbApp.auth();
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
    
    // 存储连接
    connections.set(connectionId, {
      userId,
      subscriptions: new Set(),
      connectedAt: Date.now(),
    });
    
    console.log(`WebSocket connected: ${connectionId}, user: ${userId}`);
    
    return {
      statusCode: 200,
      body: JSON.stringify({
        success: true,
        connectionId,
        message: 'Connected to TCB WebSocket',
      }),
    };
  } catch (error) {
    console.error('Connection error:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({
        success: false,
        error: error.message,
      }),
    };
  }
};

/**
 * 连接断开时调用
 */
exports.onDisconnect = async (event, context) => {
  const connectionId = event.connectionId || event.connectionContext?.connectionId;
  
  if (connections.has(connectionId)) {
    const conn = connections.get(connectionId);
    console.log(`WebSocket disconnected: ${connectionId}, user: ${conn.userId}`);
    connections.delete(connectionId);
  }
  
  return {
    statusCode: 200,
    body: JSON.stringify({ success: true }),
  };
};

/**
 * 接收客户端消息
 * 
 * 支持两种调用方式：
 * 1. TCB WebSocket 触发器 (action: 'Message', messageBody)
 * 2. HTTP 触发器测试 (event.body)
 * 
 * 消息格式：
 * {
 *   "action": "subscribe" | "unsubscribe" | "publish" | "ping",
 *   "channel": "skill-editor-stream",
 *   "data": { ... }  // 仅 publish 时需要
 * }
 */
exports.onMessage = async (event, context) => {
  // 适配 SCF WebSocket 事件格式
  const connectionId = event.connectionId || event.connectionContext?.connectionId;
  const messageBodyStr = event.messageBody || event.body;
  
  try {
    const message = JSON.parse(messageBodyStr);
    const { action, channel, data, target } = message;
    
    const conn = connections.get(connectionId);
    if (!conn) {
      return {
        statusCode: 400,
        body: JSON.stringify({ error: 'Connection not found' }),
      };
    }
    
    switch (action) {
      case 'subscribe':
        // 订阅频道
        if (channel && target && Object.values(EVENT_TYPES).includes(channel)) {
          const subscription = `${channel}:${String(target)}`;
          conn.subscriptions.add(subscription);
          console.log(`Subscribed: ${connectionId} -> ${subscription}`);
          return {
            statusCode: 200,
            body: JSON.stringify({
              success: true,
              action: 'subscribed',
              channel, target,
            }),
          };
        } else {
          return {
            statusCode: 400,
            body: JSON.stringify({
              success: false,
              error: `Invalid channel: ${channel}`,
              validChannels: Object.values(EVENT_TYPES),
            }),
          };
        }
        
      case 'unsubscribe':
        // 取消订阅
        if (channel) {
          conn.subscriptions.delete(`${channel}:${String(target || conn.userId)}`);
          console.log(`Unsubscribed: ${connectionId} -> ${channel}`);
        } else {
          conn.subscriptions.clear();
          console.log(`Unsubscribed all: ${connectionId}`);
        }
        return {
          statusCode: 200,
          body: JSON.stringify({
            success: true,
            action: 'unsubscribed',
            channel,
          }),
        };
        
      case 'publish':
        return { statusCode: 403, body: JSON.stringify({ error: 'Client publishing is forbidden' }) };
        
      case 'ping':
        // 心跳检测
        return {
          statusCode: 200,
          body: JSON.stringify({
            success: true,
            action: 'pong',
            timestamp: Date.now(),
          }),
        };
        
      default:
        return {
          statusCode: 400,
          body: JSON.stringify({
            success: false,
            error: `Unknown action: ${action}`,
          }),
        };
    }
  } catch (error) {
    console.error('Message error:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({
        success: false,
        error: error.message,
      }),
    };
  }
};

/**
 * 向所有订阅指定频道的连接广播消息
 */
async function broadcast(channel, target, message) {
  const messageStr = JSON.stringify(message);
  const subscription = `${channel}:${String(target)}`;
  
  for (const [connectionId, conn] of connections) {
    if (conn.subscriptions.has(subscription)) {
      try {
        // 通过 TCB API 发送消息给客户端
        if (tcbApp) {
          const wsService = tcbApp.ws();
          await wsService.send(connectionId, messageStr);
        }
      } catch (e) {
        console.error(`Failed to send to ${connectionId}:`, e.message);
        // 移除无效连接
        if (e.message.includes('connection') || e.message.includes('不存在')) {
          connections.delete(connectionId);
        }
      }
    }
  }
}

/**
 * 统计订阅指定频道的连接数
 */
function countSubscribers(channel, target) {
  const subscription = `${channel}:${String(target)}`;
  let count = 0;
  for (const conn of connections.values()) {
    if (conn.subscriptions.has(subscription)) {
      count++;
    }
  }
  return count;
}

// ============ HTTP API（用于推送服务调用） ============

/**
 * HTTP 触发器：推送事件到 WebSocket 频道
 * 
 * 用于 SCF/云函数之间的事件推送
 */
exports.push = async (event, context) => {
  try {
    const expectedSecret = process.env.WEBSOCKET_PUSH_SECRET;
    const suppliedSecret = event.headers?.['x-ecan-push-secret'] || event.headers?.['X-ECAN-Push-Secret'];
    if (!expectedSecret || suppliedSecret !== expectedSecret) return { statusCode: 401, body: JSON.stringify({ error: 'Unauthorized push' }) };
    const body = JSON.parse(event.body || '{}');
    const { channel, target, data } = body;
    
    if (!channel || !target || !data) {
      return {
        statusCode: 400,
        body: JSON.stringify({ error: 'Missing channel or data' }),
      };
    }
    
    if (!Object.values(EVENT_TYPES).includes(channel)) {
      return {
        statusCode: 400,
        body: JSON.stringify({
          error: `Invalid channel: ${channel}`,
          validChannels: Object.values(EVENT_TYPES),
        }),
      };
    }
    
    await broadcast(channel, target, {
      type: channel,
      target,
      data,
      timestamp: Date.now(),
    });
    
    return {
      statusCode: 200,
      body: JSON.stringify({
        success: true,
        channel,
        recipientCount: countSubscribers(channel, target),
      }),
    };
  } catch (error) {
    console.error('Push error:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({
        success: false,
        error: error.message,
      }),
    };
  }
};

/**
 * HTTP 触发器：获取连接状态
 */
exports.status = async (event, context) => {
  const expectedSecret = process.env.WEBSOCKET_PUSH_SECRET;
  const suppliedSecret = event.headers?.['x-ecan-push-secret'] || event.headers?.['X-ECAN-Push-Secret'];
  if (!expectedSecret || suppliedSecret !== expectedSecret) return { statusCode: 401, body: JSON.stringify({ error: 'Unauthorized status request' }) };
  const connectionsList = [];
  for (const [id, conn] of connections) {
    connectionsList.push({
      connectionId: id,
      userId: conn.userId,
      subscriptions: Array.from(conn.subscriptions),
      connectedAt: new Date(conn.connectedAt).toISOString(),
    });
  }
  
  return {
    statusCode: 200,
    body: JSON.stringify({
      totalConnections: connections.size,
      connections: connectionsList,
    }),
  };
};
