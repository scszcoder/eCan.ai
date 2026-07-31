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

const cloudbase = require('@cloudbase/node-sdk');

// TCB 环境初始化
let tcbApp = null;
if (process.env.TCB_REGION) {
  tcbApp = cloudbase.init({
    env: cloudbase.SyunWing,
  });
}

// Redis 配置（使用腾讯云 Redis）
const REDIS_HOST = process.env.REDIS_HOST || '127.0.0.1';
const REDIS_PORT = parseInt(process.env.REDIS_PORT || '6379');
const REDIS_PASSWORD = process.env.REDIS_PASSWORD || '';

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
 */
exports.onConnect = async (event, context) => {
  const connectionId = event.connectionId;
  
  try {
    // 获取用户身份
    let userId = 'anonymous';
    if (tcbApp && event.queryStringParameters?.token) {
      try {
        const auth = tcbApp.auth();
        const verified = await auth.verifyJwt(event.queryStringParameters.token);
        if (verified) {
          userId = verified.uid || verified.openid || 'anonymous';
        }
      } catch (e) {
        console.warn('Token verification failed:', e.message);
      }
    }
    
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
  const connectionId = event.connectionId;
  
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
 * 消息格式：
 * {
 *   "action": "subscribe" | "unsubscribe" | "publish" | "ping",
 *   "channel": "skill-editor-stream",
 *   "data": { ... }  // 仅 publish 时需要
 * }
 */
exports.onMessage = async (event, context) => {
  const connectionId = event.connectionId;
  
  try {
    const message = JSON.parse(event.body);
    const { action, channel, data } = message;
    
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
        if (channel && Object.values(EVENT_TYPES).includes(channel)) {
          conn.subscriptions.add(channel);
          console.log(`Subscribed: ${connectionId} -> ${channel}`);
          return {
            statusCode: 200,
            body: JSON.stringify({
              success: true,
              action: 'subscribed',
              channel,
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
          conn.subscriptions.delete(channel);
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
        // 发布消息到频道（仅允许特定操作）
        if (!channel || !data) {
          return {
            statusCode: 400,
            body: JSON.stringify({ error: 'Missing channel or data' }),
          };
        }
        
        // 广播给所有订阅该频道的连接
        await broadcast(channel, {
          type: channel,
          data,
          timestamp: Date.now(),
          publisher: conn.userId,
        });
        
        return {
          statusCode: 200,
          body: JSON.stringify({
            success: true,
            action: 'published',
            channel,
            recipientCount: countSubscribers(channel),
          }),
        };
        
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
async function broadcast(channel, message) {
  const messageStr = JSON.stringify(message);
  
  for (const [connectionId, conn] of connections) {
    if (conn.subscriptions.has(channel)) {
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
function countSubscribers(channel) {
  let count = 0;
  for (const conn of connections.values()) {
    if (conn.subscriptions.has(channel)) {
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
    const body = JSON.parse(event.body || '{}');
    const { channel, data, excludeConnection } = body;
    
    if (!channel || !data) {
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
    
    await broadcast(channel, {
      type: channel,
      data,
      timestamp: Date.now(),
    });
    
    return {
      statusCode: 200,
      body: JSON.stringify({
        success: true,
        channel,
        recipientCount: countSubscribers(channel),
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
