/**
 * Cross-instance WebSocket publish bridge.
 *
 * 在 ecan-graphql-api 实例中, 业务 resolver 通过 `event-bus.publish(topic, target, payload)`.
 * 本模块把这条 publish 同步推送到自建的 WS 函数 `ecan-graphql-ws`, 由 WS 函数
 * 写到与自己同进程的所有 WS 客户端 (每个客户端已通过 graphql-ws `start` 帧订阅).
 *
 * 设计理由 (镜像 AWS AppSync realtime 拓扑):
 *   - SCF 函数实例之间不共享内存. 一个 GraphQL 实例上的 publish 默认只对同一实例上的
 *     WS 订阅者可见.
 *   - AppSync 在 `appsync-api` 和 `appsync-realtime-api` 之间通过内部 broker 转发.
 *     我们用同样的思路: mutation/query 处理时, 通过 HTTP POST 把 publish 同步发给
 *     runtime (WS) 函数.
 *   - WS 函数内部仍用 in-process event-bus. 跨实例边界由本 bridge 负责.
 *
 * 失败语义:
 *   - 跨实例推送失败不能影响 mutation 返回成功 (event-bus.publish 已在本地分发过).
 *   - 失败落到 warn 日志; 业务侧仍按已记录的 publish 路径处理.
 *   - 用 WS_PUSH_SECRET 鉴权, 防止任意 SCF 注入 publish.
 */

const https = require('node:https');

const WS_FUNCTION_NAME = process.env.WS_FUNCTION_NAME || 'ecan-graphql-ws';
const WS_PUSH_SECRET = process.env.WS_PUSH_SECRET;
const TCB_ENV_ID = process.env.TCB_ENV_ID || 'sccb0-d0gc5398xf028be6a';
const PUSH_TIMEOUT_MS = Number(process.env.WS_PUSH_TIMEOUT_MS) || 3000;
const WS_LOCAL_URL = process.env.WS_LOCAL_URL; // e.g. http://localhost:9103 — overrides TCB host

function pushToWs(topic, target, payload) {
  if (!WS_PUSH_SECRET) {
    // 没配 secret 就不推送, 但不报错 — 开发模式可接受.
    return Promise.resolve(0);
  }
  const body = JSON.stringify({ topic, target, payload });

  // Local dev: WS_LOCAL_URL=http://localhost:9103
  if (WS_LOCAL_URL) {
    const { URL } = require('node:url');
    const u = new URL('/publish', WS_LOCAL_URL);
    return postJson({
      http: u.protocol === 'https:' ? require('node:https') : require('node:http'),
      hostname: u.hostname,
      port: u.port,
      path: u.pathname,
      body,
      headers: { 'Content-Type': 'application/json' },
      secret: WS_PUSH_SECRET,
      timeout: PUSH_TIMEOUT_MS,
      label: `topic=${topic} target=${target}`,
    });
  }

  // Production: https://<ws-fn>-<env>.service.tcloudbase.com/publish
  const hostname = `${WS_FUNCTION_NAME}-${TCB_ENV_ID}.service.tcloudbase.com`;
  return postJson({
    http: https,
    hostname,
    path: '/publish',
    body,
    headers: {
      'Content-Type': 'application/json',
    },
    secret: WS_PUSH_SECRET,
    timeout: PUSH_TIMEOUT_MS,
    label: `topic=${topic} target=${target}`,
  });
}

function postJson({ http, hostname, port, path, body, headers, secret, timeout, label }) {
  const fullHeaders = {
    ...headers,
    'Content-Length': Buffer.byteLength(body),
    'X-ECAN-Push-Secret': secret,
  };
  return new Promise((resolve) => {
    const req = http.request({
      method: 'POST',
      hostname,
      port,
      path,
      headers: fullHeaders,
      timeout,
    }, (res) => {
      res.on('data', () => {});
      res.on('end', () => resolve(res.statusCode || 0));
    });
    req.on('timeout', () => req.destroy(new Error('ws push timeout')));
    req.on('error', (e) => {
      console.warn(`[ws-bridge] push failed ${label}: ${e.message}`);
      resolve(0);
    });
    req.write(body);
    req.end();
  });
}

/**
 * Attach the cross-instance WS bridge to the in-process event-bus.
 * After this call, every `bus.publish(topic, target, payload)` will also
 * be forwarded to the WS function. Idempotent.
 */
function attachWsBridge() {
  const bus = require('../event-bus');
  if (bus.getBridge()) return;
  bus.attachBridge(({ topic, target, payload }) => {
    pushToWs(topic, target, payload).catch(() => { /* logged in pushToWs */ });
  });
}

module.exports = { attachWsBridge, pushToWs };
