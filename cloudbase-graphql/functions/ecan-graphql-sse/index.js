// CloudFunction entry point — dispatches:
//   GET  /api/events?topic=xxx&<key>=xxx     → SSE stream (client-facing)
//   POST /publish                            → cross-instance push (internal)
//   GET  /healthz                            → liveness
//
// At runtime, TCB places the deployed package at /var/user/. services/sse-bridge.js
// and event-bus.js are siblings of this index.js. Local dev (running via `node index.js`
// from this directory) uses the relative path fallback.

const path = require('path');

// Load the shared implementation. Try, in order:
//   1. /var/user/services/sse-bridge.js — TCB runtime layout
//   2. ./services/sse-bridge.js       — bundle layout (where this file's
//                                       siblings include services/)
//   3. ../services/sse-bridge.js      — repo layout, dev from functions/ecan-graphql-sse/
let bridge;
try {
  bridge = require('/var/user/services/sse-bridge.js');
} catch {
  try {
    bridge = require(path.join(__dirname, 'services', 'sse-bridge.js'));
  } catch {
    bridge = require(path.join(__dirname, '..', '..', 'services', 'sse-bridge.js'));
  }
}

// Lazy accessor for the cloudbase SDK. We isolate it so SSE can still boot
// when the SDK is missing (skips JWT verification — falls back to anonymous).
let _tcbApp = null;
function getTcbApp() {
  if (_tcbApp !== null) return _tcbApp;
  if (!process.env.TCB_REGION) { _tcbApp = undefined; return undefined; }
  try {
    const cloudbase = require('@cloudbase/node-sdk');
    _tcbApp = cloudbase.init({ env: cloudbase.SYMBOL_CURRENT_ENV });
    return _tcbApp;
  } catch (e) {
    console.warn('[sse] cloudbase init failed (anonymous mode):', e.message);
    _tcbApp = undefined;
    return undefined;
  }
}

async function main(event, context) {
  if (context && 'callbackWaitsForEmptyEventLoop' in context) {
    // SSE 长连接: 必须设为 false, 否则 SCF 会等到 event loop 空才返回 response.
    context.callbackWaitsForEmptyEventLoop = false;
  }

  const method = (event.httpMethod || event.method || 'GET').toUpperCase();
  const rawPath = event.path || event.rawPath || '';
  const cleanPath = rawPath.split('?')[0].replace(/^\//, '');
  const queryString = event.queryString
    || (event.queryStringParameters
      ? new URLSearchParams(event.queryStringParameters).toString()
      : '');

  // ─── GET /healthz ──────────────────────────────────────────────
  if (method === 'GET' && cleanPath === 'healthz') {
    return {
      statusCode: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ success: true, service: 'ecan-graphql-sse' }),
    };
  }

  // ─── POST /publish (internal) ─────────────────────────────────
  if (method === 'POST' && cleanPath === 'publish') {
    const expected = process.env.SSE_PUSH_SECRET;
    const supplied = event.headers?.['x-ecan-push-secret']
                 || event.headers?.['X-ECAN-Push-Secret'];
    if (!expected || supplied !== expected) {
      return {
        statusCode: 401,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ error: 'Unauthorized push' }),
      };
    }
    let body;
    try { body = JSON.parse(event.body || '{}'); }
    catch {
      return {
        statusCode: 400,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ error: 'Invalid JSON body' }),
      };
    }
    const { topic, target, payload } = body;
    if (!topic || !target || payload == null) {
      return {
        statusCode: 400,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ error: 'Missing topic, target, or payload' }),
      };
    }
    if (bridge.TOPIC_TARGET_KEY[topic] === undefined) {
      return {
        statusCode: 400,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          error: `Unknown topic: ${topic}`,
          validTopics: Object.keys(bridge.TOPIC_TARGET_KEY),
        }),
      };
    }
    const delivered = bridge.publish(topic, String(target), payload);
    return {
      statusCode: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ success: true, topic, target, delivered }),
    };
  }

  // ─── GET /api/events (client SSE) ─────────────────────────────
  if (method === 'GET' && cleanPath === 'api/events') {
    const params = new URLSearchParams(queryString);
    const topic = params.get('topic');
    let target = null;
    // 取第一个非 topic 的 query 参数作为 target (matches sse-bridge contract)
    for (const [k, v] of params) {
      if (k !== 'topic' && v) { target = v; break; }
    }
    const identity = await resolveSseIdentity(event, params);
    const ctx = { identity };

    const response = bridge.buildSSEResponse(topic, target || bridge.GLOBAL_TOPIC, ctx);
    // SCF header keys are case-insensitive — normalize to canonical case so
    // "Content-Type" shows up in the API Gateway response.
    const headers = {};
    for (const [k, v] of response.headers) {
      headers[k.split('-').map((s) => s[0].toUpperCase() + s.slice(1).toLowerCase()).join('-')] = v;
    }
    return {
      statusCode: response.status,
      headers,
      body: response.body, // ReadableStream
      isBase64Encoded: false,
    };
  }

  // ─── 兜底 ─────────────────────────────────────────────────────
  return {
    statusCode: 404,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      error: 'Not Found',
      service: 'ecan-graphql-sse',
      hint: 'GET /api/events | POST /publish | GET /healthz',
    }),
  };
}

// SSE 客户端 auth: 优先用 Authorization header, 兜底用 ?token=
async function resolveSseIdentity(event, params) {
  let token = '';
  const auth = event.headers?.authorization || event.headers?.Authorization || '';
  if (auth) token = auth.replace(/^Bearer\s+/i, '').trim();
  if (!token) token = params.get('token') || '';

  const allowInsecure = process.env.ALLOW_INSECURE_AUTH === 'true'
                      && process.env.NODE_ENV !== 'production';

  if (token) {
    const app = getTcbApp();
    if (app) {
      try {
        const verified = await app.auth().verifyJwt(token);
        const sub = verified?.uid || verified?.openid || verified?.sub;
        if (sub) return { sub };
      } catch {
        // fall through to insecure / anonymous
      }
    }
  }

  if (allowInsecure) {
    return { sub: params.get('testUser') || 'local-development-user' };
  }
  // 严格模式下, 缺 token 也会得到一个 anonymous context — SSE bridge 不会拒绝
  // 连接, 但订阅 resolver (走 GraphQL 那侧) 自己会拒绝.
  return { sub: 'sse-anonymous' };
}

exports.main = main;
