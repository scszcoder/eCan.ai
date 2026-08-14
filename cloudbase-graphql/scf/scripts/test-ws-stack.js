#!/usr/bin/env node
/**
 * End-to-end local stack test — verifies the self-built graphql-ws function
 * receives cross-instance pushes from the GraphQL API.
 *
 * Topology:
 *   port 9103 → ecan-graphql-ws function (self-built WS bridge)
 *   port 9100 → ecan-graphql-api function (publishes via HTTP POST to 9103)
 *
 * The GraphQL API has its bridge wired to WS_LOCAL_URL=http://localhost:9103
 * so every `bus.publish(...)` is forwarded to the WS function via HTTP POST.
 *
 * Tests:
 *   1. WS function /healthz returns 200 + metrics
 *   2. /publish with correct secret returns 200 + delivery count
 *   3. /publish with wrong secret returns 401
 *   4. WebSocket client connects with graphql-ws subprotocol
 *   5. Handshake: connection_init → connection_ack
 *   6. Subscribe: start → start_ack + bus.subscribe
 *   7. End-to-end: GraphQL mutation publishTaskStatus → WS client data frame
 *
 * Run: node scripts/test-ws-stack.js
 */

'use strict';

const assert = require('node:assert/strict');
const http = require('node:http');
const WebSocket = require('ws');
const bus = require('../event-bus');

const WS_PORT = 9103;
const API_PORT = 9100;
const PUSH_SECRET = 'test-ws-stack-secret';

function startWsServer() {
  // All env vars must be set BEFORE the module is required — `createServer`
  // captures ALLOW_INSECURE / PUSH_SECRET from process.env at require time.
  process.env.WS_PUSH_SECRET = PUSH_SECRET;
  process.env.ALLOW_INSECURE_AUTH = 'true';
  const { createServer } = require('../functions/ecan-graphql-ws');
  const server = createServer();
  return new Promise((resolve) => server.listen(WS_PORT, () => resolve(server)));
}

function startApiFunction() {
  const apiModule = require('../index.js');
  const server = http.createServer(async (req, res) => {
    let body = '';
    req.on('data', (c) => { body += c; });
    req.on('end', async () => {
      const event = {
        httpMethod: req.method,
        path: req.url.split('?')[0],
        headers: req.headers,
        body: body || undefined,
        queryStringParameters: Object.fromEntries(new URL(req.url, 'http://x').searchParams),
      };
      const ctx = { callbackWaitsForEmptyEventLoop: false };
      try {
        const r = await apiModule.main(event, ctx);
        res.statusCode = r.statusCode || 200;
        for (const [k, v] of Object.entries(r.headers || {})) res.setHeader(k, v);
        res.end(r.body || '');
      } catch (e) {
        res.statusCode = 500;
        res.end(JSON.stringify({ error: e.message }));
      }
    });
  });
  return new Promise((resolve) => server.listen(API_PORT, () => resolve(server)));
}

function postJson(url, body, extraHeaders = {}) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const data = JSON.stringify(body);
    const req = http.request({
      method: 'POST', hostname: u.hostname, port: u.port, path: u.pathname,
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(data),
        ...extraHeaders,
      },
    }, (res) => {
      let raw = '';
      res.on('data', (c) => { raw += c; });
      res.on('end', () => resolve({ statusCode: res.statusCode, body: raw }));
    });
    req.on('error', reject);
    req.write(data);
    req.end();
  });
}

function get(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => {
      let body = '';
      res.on('data', (c) => { body += c; });
      res.on('end', () => resolve({ statusCode: res.statusCode, headers: res.headers, body }));
    }).on('error', reject);
  });
}

const waitFor = (predicate, timeoutMs = 3000) => new Promise((resolve, reject) => {
  const t0 = Date.now();
  const tick = () => {
    if (predicate()) return resolve();
    if (Date.now() - t0 > timeoutMs) return reject(new Error('waitFor timeout'));
    setTimeout(tick, 20);
  };
  tick();
});

let pass = 0, fail = 0;
const ok = (m) => { pass++; console.log(`  ✓ ${m}`); };
const bad = (m) => { fail++; console.log(`  ✗ ${m}`); };

async function main() {
  // 1. Start WS server
  bus.reset();
  const wsServer = await startWsServer();
  ok(`WS server on :${WS_PORT}`);

  // 2. Start GraphQL API — wire bridge to our local WS
  // These env vars are read at module load time (bus.attachBridge fires on
  // require), so they must be set BEFORE startApiFunction() runs.
  process.env.WS_PUSH_SECRET = PUSH_SECRET;
  process.env.WS_LOCAL_URL = `http://localhost:${WS_PORT}`;
  process.env.ALLOW_INSECURE_AUTH = 'true';
  process.env.NODE_ENV = 'development';
  const apiServer = await startApiFunction();
  ok(`API server on :${API_PORT}`);

  // 3. /healthz
  let r = await get(`http://localhost:${WS_PORT}/healthz`);
  if (r.statusCode === 200 && r.body.includes('ecan-graphql-ws')) ok('WS /healthz → 200');
  else bad(`/healthz: ${r.statusCode} ${r.body}`);

  // 4. /publish wrong secret
  r = await postJson(`http://localhost:${WS_PORT}/publish`,
    { topic: 'onTaskStatus', target: 'x', payload: { s: 1 } });
  if (r.statusCode === 401) ok('/publish wrong secret → 401');
  else bad(`/publish wrong secret: ${r.statusCode} ${r.body}`);

  // 5. /publish correct secret
  r = await postJson(`http://localhost:${WS_PORT}/publish`,
    { topic: 'onTaskStatus', target: 'e2e-1', payload: { runID: 'e2e-1', status: 'completed' } },
    { 'X-WS-Push-Secret': PUSH_SECRET });
  if (r.statusCode === 200 && JSON.parse(r.body).ok) ok('/publish correct secret → 200');
  else bad(`/publish correct: ${r.statusCode} ${r.body}`);

  // 6. /publish unknown topic — bus.publish is a no-op when no subscribers;
  //    the server returns 200 rather than 400 (matches services/test-ws-bridge.js).
  r = await postJson(`http://localhost:${WS_PORT}/publish`,
    { topic: 'fakeTopic', target: 'x', payload: {} },
    { 'X-WS-Push-Secret': PUSH_SECRET });
  if (r.statusCode === 200) ok('/publish unknown topic → 200 (no-op)');
  else bad(`/publish unknown: ${r.statusCode} ${r.body}`);

  // 7. WebSocket client + handshake + subscribe
  const ws = new WebSocket(`ws://localhost:${WS_PORT}/?token=test-user`, 'graphql-ws');
  const received = [];
  ws.on('message', (data) => {
    try { received.push(JSON.parse(data.toString())); }
    catch { /* ignore */ }
  });
  await new Promise((res, rej) => {
    ws.once('open', res);
    ws.once('error', rej);
    setTimeout(() => rej(new Error('ws open timeout')), 3000);
  });
  ok('WS client connected with graphql-ws subprotocol');

  ws.send(JSON.stringify({ type: 'connection_init' }));
  await waitFor(() => received.some((f) => f.type === 'connection_ack'));
  ok('connection_init → connection_ack');

  ws.send(JSON.stringify({
    id: 'stack-sub-1',
    type: 'start',
    payload: {
      data: JSON.stringify({
        query: 'subscription S { onTaskStatus(runID: "stack-e2e") { runID status } }',
      }),
    },
  }));
  await waitFor(() => received.some((f) => f.type === 'start_ack' && f.id === 'stack-sub-1'));
  ok('start → start_ack');

  // 8. End-to-end: API mutation → WS data frame
  received.length = 0;
  await new Promise((r) => setTimeout(r, 100));
  const apiResp = await postJson(`http://localhost:${API_PORT}/api/graphql`, {
    query: 'mutation { publishTaskStatus(input: {runID: "stack-e2e", success: true, runner: "stack-test"}) { runID } }',
  });
  if (apiResp.statusCode === 200) ok('API mutation → 200');
  else bad(`API mutation: ${apiResp.statusCode} ${apiResp.body}`);

  await waitFor(() => received.some((f) => f.type === 'data' && f.payload?.data?.onTaskStatus?.runID === 'stack-e2e'));
  ok('mutation publish → WS data frame received');

  ws.close();
  apiServer.close();
  wsServer.close();

  console.log(`\n  ${pass} passed, ${fail} failed`);
  process.exit(fail > 0 ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(2); });
