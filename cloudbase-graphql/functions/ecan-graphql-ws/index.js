/**
 * ecan-graphql-ws — Standalone graphql-ws / AppSync-compatible WebSocket server.
 *
 * 部署方式: TCB 云托管 (TCS / TCC)
 * 入口: 直接 `node index.js` (非 SCF trigger)
 *
 * 环境变量:
 *   PORT              监听端口，默认 9102
 *   WS_PUSH_SECRET    SCF → WS 的推送密钥 (空=仅测试)
 *   ALLOW_INSECURE_AUTH  非生产跳过 JWT 验证 (默认 false)
 *   TCB_REGION        腾讯云区域，默认 ap-shanghai
 *
 * HTTP endpoints (alongside WebSocket on same port):
 *   GET  /healthz    — 健康检查
 *   POST /publish     — 跨实例推送 { topic, payload }
 */

'use strict';

const http = require('node:http');
const { WebSocketServer, WebSocket } = require('ws');
const path = require('node:path');
// Resolve event-bus and ws-protocol relative to THIS file.
// Local dev:  /cloudbase-graphql/functions/ecan-graphql-ws/index.js → ../../event-bus → cloudbase-graphql/event-bus
// Docker:     /app/index.js                           → /app/event-bus
const _dir = __dirname;
const _root = path.resolve(_dir, '../..');  // cloudbase-graphql/ (local) or / (docker) — just for readability
const eventBus = (() => {
  try { return require(path.resolve(_dir, '../../event-bus')); }    // local dev
  catch (_) { return require(path.resolve(_dir, 'event-bus')); }   // docker
})();
const { createConnectionState, handleClientMessage } = (() => {
  try { return require(path.resolve(_dir, '../../services/ws-protocol')); }
  catch (_) { return require(path.resolve(_dir, 'services/ws-protocol')); }
})();

const PORT        = parseInt(process.env.PORT || '9102', 10);
// WS_PUSH_SECRET:
//   - TCR 构建: 通过 Dockerfile ARG WS_PUSH_SECRET 注入
//   - 本地构建: 通过 --build-arg 注入
//   - TCB 云端构建 (--source): deploy-ws-tcs.sh 的 sed 占位符替换
const PUSH_SECRET = process.env.WS_PUSH_SECRET || '__WS_PUSH_SECRET__';
const ALLOW_INSECURE = process.env.ALLOW_INSECURE_AUTH === 'true' || '__ALLOW_INSECURE_AUTH__' === 'true';
// BUILD_VERSION: 由 TCR build-arg 或 CI 注入 (如 "20260812-abc1234")
const BUILD_VERSION = process.env.BUILD_VERSION || 'unknown';

/** 解析 TCB JWT token → identity 对象 */
async function resolveIdentity(token) {
  if (!token) return null;
  // Strip "Bearer " prefix if present (from Authorization header)
  const rawToken = String(token).replace(/^bearer\s+/i, '').trim();
  if (!rawToken) return null;

  // 方式1: 尝试解析 JWT token（支持本地登录产生的 JWT token）
  try {
    const parts = rawToken.split('.');
    if (parts.length === 3) {
      const payload = JSON.parse(Buffer.from(parts[1], 'base64').toString('utf8'));
      // JWT token 有 exp, iat, sub 等标准字段
      // TCB token 字段名: sub / uid / userId / user_id / openid
      const userId = payload.sub || payload.uid || payload.userId || payload.user_id || payload.openid;
      if (userId && payload.exp && payload.iat) {
        // 验证 JWT 未过期
        // TCB token 的 exp/iat 可能是秒或毫秒，兼容两种情况
        let exp = payload.exp;
        let now = Date.now();
        // 如果 exp 是秒级 (小于10^12)，转换为毫秒
        if (exp < 1e12) exp = exp * 1000;
        if (exp > now) {
          return { userId, raw: payload };
        }
      }
    }
  } catch (_) {
    // JWT 解析失败，继续尝试其他方式
  }

  // 方式2: TCB 自定义登录票据验证（用于微信登录等场景产生的票据）
  try {
    const CloudBase = require('@cloudbase/node-sdk');
    const tcb = CloudBase.init({ envId: process.env.TCB_ENV_ID || process.env.SCF_NAMESPACE });
    const auth = tcb.auth();
    const userInfo = await Promise.race([
      auth.getClientCredential({ token: rawToken }),
      new Promise((_, reject) => setTimeout(() => reject(new Error('getClientCredential timeout')), 5000)),
    ]);
    if (!userInfo) return null;
    // TCB 返回字段名: uid / openId / userId，兼容所有
    const uid = userInfo.uid || userInfo.openId || userInfo.openid || userInfo.userId;
    if (!uid) return null;
    return { userId: uid, raw: userInfo };
  } catch (err) {
    // 不使用 console.error — 容器 stdout 被 TCB 收集，console.log 可见
    console.log('[auth] token verification failed:', err.message);
    return null;
  }
}

/** 提取认证 token: AppSync URL auth / Authorization header (兼容多种格式).
 *
 * 服务端契约: 模仿 AWS AppSync realtime 接口 — 客户端总是用 ?header=&payload=
 * base64 编码的形式传 Authorization。这个函数兼容多种调用形式以避免
 * 客户端代码（Python / 浏览器 / 移动端）做 region-specific 分支。
 *
 *   方式1 (AppSync 标准): ?header=<base64>&payload=<base64>
 *     header 解码后通常是 { "host": "...", "Authorization": "<jwt>" }
 *   方式2 (简化):         直接 Authorization header
 *   方式3 (兜底):         ?token=<jwt>  (老 CLI / 调试用)
 */
function extractToken(req) {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);

  // 方式1 (AppSync 标准): ?header=<base64>&payload=<base64>
  const headerB64 = url.searchParams.get('header');
  if (headerB64) {
    try {
      const authData = JSON.parse(Buffer.from(headerB64, 'base64').toString('utf8'));
      if (authData.Authorization) return authData.Authorization;       // 裸 token
      if (authData.authorization) return authData.authorization;
      if (authData.token) return authData.token;
    } catch { /* ignore */ }
  }

  // 方式2: Authorization header
  const auth = req.headers['authorization'] || req.headers['Authorization'];
  if (auth) {
    const parts = auth.split(' ');
    if (parts.length === 2 && parts[0].toLowerCase() === 'bearer') return parts[1]; // 裸 token
    return auth; // 可能是其他格式
  }

  // 方式3 (兜底): ?token=<jwt> — 保留以兼容老 CLI / 调试脚本
  const qToken = url.searchParams.get('token');
  if (qToken) return qToken;

  return null;
}

/** 推送事件到指定连接的 WebSocket */
function sendToConnection(ws, frame) {
  if (ws.readyState === WebSocket.OPEN) {
    try {
      ws.send(JSON.stringify(frame));
    } catch (err) {
      console.error('[send] failed:', err.message);
    }
  }
}

// ─── 主程序 ────────────────────────────────────────────────────────────────

/**
 * @param {object} opts
 * @param {object} [opts.externalBus] - 可选，外部 event-bus (如测试中的全局 bus).
 *                                     如不传，WS 服务器使用自己的内部 pubsub.
 */
function createServer(opts = {}) {
  const externalBus = opts.externalBus;
  const connections = new Map(); // connectionId → { ws, state }
  let connCounter = 0;
  // event-bus: the shared async iterator pub/sub used for all WS subscriptions.
  // This is the same event-bus.js used by the GraphQL resolvers, so mutations
  // inside SCF and subscriptions inside this WS container share the same bus.
  const bus = opts.externalBus || eventBus;

  // HTTP server (handles /healthz, /publish alongside WebSocket upgrades)
  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);

    // ── GET /healthz ──────────────────────────────────────────────────────
    if (req.method === 'GET' && url.pathname === '/healthz') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        status: 'ok',
        service: 'ecan-graphql-ws',
        build: BUILD_VERSION,
        connections: connections.size,
        ts: Date.now(),
      }));
      return;
    }

    // ── POST /publish ─────────────────────────────────────────────────────
    if (req.method === 'POST' && url.pathname === '/publish') {
      // Cross-instance push: SCF → WS service (from ws-bridge-push.js)
      if (PUSH_SECRET) {
        // Header name `X-WS-Push-Secret` (matches WS_PUSH_SECRET env var name).
        // The query-param fallback `?secret=` is kept for callers that can't
        // set headers (e.g. some browser fetch wrappers).
        const secret = req.headers['x-ws-push-secret'] || url.searchParams.get('secret');
        if (secret !== PUSH_SECRET) {
          res.writeHead(401, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'Unauthorized' }));
          return;
        }
      }
      let body = '';
      req.on('data', c => { body += c; });
      req.on('end', async () => {
        try {
          const { topic, target, payload, connectionId } = JSON.parse(body);
          if (!topic || !payload) throw new Error('missing topic or payload');
          if (connectionId) {
            // Push to specific connection
            const conn = connections.get(connectionId);
            if (conn) {
              const { state } = conn;
              // Find subId for this topic
              for (const [t, subId] of state.subscriptions) {
                if (t === topic) {
                  sendToConnection(conn.ws, {
                    type: 'data',
                    id: subId,
                    payload: { data: { [topic]: payload } },
                  });
                  break;
                }
              }
            }
          } else {
            // Broadcast: bus.publish(topic, target, payload)
            bus.publish(topic, target || '__global__', payload);
          }
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ ok: true }));
        } catch (err) {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: err.message }));
        }
      });
      return;
    }

    // 404
    res.writeHead(404, { 'Content-Type': 'text/plain' });
    res.end('Not Found');
  });

  // ── WebSocket upgrade ────────────────────────────────────────────────────
  server.on('upgrade', async (req, socket, head) => {
    const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
    const urlPath = url.pathname;
    if (urlPath !== '/ws' && urlPath !== '/') {
      socket.write('HTTP/1.1 404\r\n\r\n');
      socket.destroy();
      return;
    }

  const token = extractToken(req);
  if (!token) {
    console.log('[auth] no token extracted');
    socket.write('HTTP/1.1 401 Unauthorized\r\n\r\n');
    socket.destroy();
    return;
  }
  const identity = await resolveIdentity(token);
  if (!identity) {
    console.log(`[auth] token verification failed: token=${token.substring(0, 30)}...`);
    socket.write('HTTP/1.1 401 Unauthorized\r\n\r\n');
    socket.destroy();
    return;
  }

    const connectionId = `conn-${++connCounter}-${Date.now()}`;
    const log = (...args) => console.log(`[${connectionId}]`, ...args);

    log(`Authenticated as ${identity.userId}`);

    // Verify graphql-ws subprotocol
    const protocols = (req.headers['sec-websocket-protocol'] || '').split(',').map(s => s.trim());
    if (!protocols.includes('graphql-ws')) {
      socket.write('HTTP/1.1 400 Bad Request\r\n\r\n');
      socket.destroy();
      return;
    }

    const wss = new WebSocketServer({ noServer: true });

    wss.on('connection', (ws) => {
      log('WS connection established');

      // State machine for this connection
      const state = createConnectionState({
        connectionId,
        send: (frame) => sendToConnection(ws, frame),
        log,
      });

      connections.set(connectionId, { ws, state, identity });

      // Delegate to ws-protocol handler
      ws.on('message', (raw) => {
        const result = handleClientMessage(state, raw.toString(), {
          identity,
          log,
          externalBus: bus,
          onStart(topic, subId, target) {
            // Register subscription on the shared event-bus
            const ctx = {
              connectionId,
              subId,
              topic,
              send(data) {
                sendToConnection(ws, {
                  type: 'data',
                  id: subId,
                  payload: { data: { [topic]: data } },
                });
              },
            };
            if (!state._busCtxs) state._busCtxs = new Map();
            state._busCtxs.set(topic, ctx);

            // Consume the event-bus async iterator asynchronously
            const iter = bus.subscribe(topic, target, ctx);
            ctx._iter = iter;
            (async () => {
              try {
                for await (const payload of iter) {
                  ctx.send(payload);
                }
              } catch (_) {
                // iterator closed or error
              }
            })();
            log(`Subscribed: topic=${topic} subId=${subId} target=${target}`);
          },
          onStop(topic) {
            if (state._busCtxs) {
              const ctx = state._busCtxs.get(topic);
              if (ctx && ctx._iter) {
                ctx._iter.return?.();
                state._busCtxs.delete(topic);
              }
            }
            log(`Unsubscribed: topic=${topic}`);
          },
        });

        if (result.close) {
          ws.close();
        }
      });

      ws.on('close', () => {
        log('WS closed');
        // Clean up all active subscriptions for this connection
        if (state._busCtxs) {
          for (const [, ctx] of state._busCtxs) {
            ctx._iter?.return?.();
          }
          state._busCtxs.clear();
        }
        connections.delete(connectionId);
      });

      ws.on('error', (err) => {
        log('WS error:', err.message);
        if (state._busCtxs) {
          for (const [, ctx] of state._busCtxs) {
            ctx._iter?.return?.();
          }
          state._busCtxs.clear();
        }
        connections.delete(connectionId);
      });

      // Handle ping/ka from client
      ws.on('pong', () => {
        log('pong received');
      });
    });

    // Perform the HTTP upgrade manually
    wss.handleUpgrade(req, socket, head, (ws) => {
      wss.emit('connection', ws, req);
    });
  });

  return server;
}

// ─── 入口 ──────────────────────────────────────────────────────────────────

if (require.main === module) {
  // 防止未捕获异常导致容器崩溃（502 错误）
  process.on('unhandledRejection', (reason) => {
    console.error('[unhandledRejection]', reason?.message || reason);
  });
  process.on('uncaughtException', (err) => {
    console.error('[uncaughtException]', err.message);
  });

  const server = createServer();
  server.listen(PORT, '0.0.0.0', () => {
    console.log(`[ws-server] Listening on 0.0.0.0:${PORT}`);
    console.log(`[ws-server] Build: ${BUILD_VERSION}`);
    console.log(`[ws-server] Push secret: ${PUSH_SECRET ? 'set' : 'none (insecure mode)'}`);
    console.log(`[ws-server] Insecure auth: ${ALLOW_INSECURE}`);
  });
}

module.exports = { createServer };
