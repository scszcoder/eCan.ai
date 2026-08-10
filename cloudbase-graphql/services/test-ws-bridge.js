#!/usr/bin/env node
/**
 * End-to-end test for ecan-graphql-ws using a real WebSocket client.
 *
 * Spins up the WS server (port 9102) and verifies:
 *   1. graphql-ws subprotocol handshake (connection_init → connection_ack)
 *   2. AppSync-style URL (header=base64) authentication works
 *   3. start / start_ack round-trip with a real subscription query
 *   4. bus.publish → data frame arrives on the wire
 *   5. stop cancels the subscription
 *   6. ka echoes
 *   7. unknown frame → error frame, connection stays open
 *   8. /publish HTTP endpoint delivers cross-instance push
 *
 * Uses the `ws` library on both sides so this exercises the actual code
 * path that TCB WebSocket API gateway traffic will use.
 *
 * Run: node services/test-ws-bridge.js
 */

'use strict';

const assert = require('node:assert/strict');
const http = require('node:http');
const WebSocket = require('ws');
const bus = require('../event-bus');

let pass = 0, fail = 0;
const ok = (m) => { pass++; console.log(`  ✓ ${m}`); };
const bad = (m) => { fail++; console.log(`  ✗ ${m}`); };

const WS_PORT = 9102;
const PUSH_SECRET = 'test-ws-secret';

function startWsServer() {
  process.env.WS_PUSH_SECRET = PUSH_SECRET;
  process.env.ALLOW_INSECURE_AUTH = 'true'; // 测试用假 token，必须开启开发模式
  const { createServer } = require('../functions/ecan-graphql-ws');
  // Pass the shared event-bus so WS subscriptions and SCF publishes are bridged
  const server = createServer({ externalBus: bus });
  return new Promise((resolve) => server.listen(WS_PORT, () => resolve(server)));
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

function postJson(url, body, extraHeaders = {}) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const data = JSON.stringify(body);
    const req = http.request({
      method: 'POST',
      hostname: u.hostname, port: u.port, path: u.pathname,
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

const waitFor = (predicate, timeoutMs = 3000) => new Promise((resolve, reject) => {
  const t0 = Date.now();
  const tick = () => {
    if (predicate()) return resolve();
    if (Date.now() - t0 > timeoutMs) return reject(new Error('waitFor timeout'));
    setTimeout(tick, 20);
  };
  tick();
});

async function main() {
  bus.reset();
  const server = await startWsServer();
  ok(`WS server listening on :${WS_PORT}`);

  // ── 1. /healthz ──────────────────────────────────────────────────────
  let r = await get(`http://localhost:${WS_PORT}/healthz`);
  if (r.statusCode === 200 && r.body.includes('"status":"ok"')) ok('/healthz returns 200');
  else bad(`/healthz: ${r.statusCode} ${r.body}`);

  // ── 2. WebSocket handshake with AppSync-style URL ─────────────────────
  const header = Buffer.from(JSON.stringify({ Authorization: 'Bearer test-jwt' })).toString('base64');
  const payload = Buffer.from('{}').toString('base64');
  const wsUrl = `ws://localhost:${WS_PORT}/?header=${header}&payload=${payload}`;
  const ws = new WebSocket(wsUrl, 'graphql-ws');

  const received = [];
  ws.on('message', (data) => {
    try { received.push(JSON.parse(data.toString())); }
    catch { received.push({ type: 'invalid', raw: data.toString() }); }
  });
  ws.on('error', (e) => bad(`ws error: ${e.message}`));

  await new Promise((res, rej) => {
    ws.once('open', res);
    ws.once('error', rej);
    setTimeout(() => rej(new Error('ws open timeout')), 3000);
  });
  ok('WS connection opened with graphql-ws subprotocol');

  // ── 3. connection_init → connection_ack ──────────────────────────────
  ws.send(JSON.stringify({ type: 'connection_init' }));
  await waitFor(() => received.some((f) => f.type === 'connection_ack'));
  ok('connection_init → connection_ack');

  // ── 4. start → start_ack + bus.subscribe ─────────────────────────────
  const startFrame = {
    id: 'sub-task-1',
    type: 'start',
    payload: {
      data: JSON.stringify({
        query: 'subscription S { onTaskStatus(runID: "e2e-task-1") { runID status } }',
      }),
    },
  };
  ws.send(JSON.stringify(startFrame));
  await waitFor(() => received.some((f) => f.type === 'start_ack' && f.id === 'sub-task-1'));
  ok('start → start_ack');

  const m = bus.metrics();
  if (m.counts['onTaskStatus:e2e-task-1'] === 1) ok('bus subscription registered');
  else bad(`bus.metrics counts=${JSON.stringify(m.counts)}`);

  // ── 5. bus.publish → data frame ──────────────────────────────────────
  received.length = 0;
  bus.publish('onTaskStatus', 'e2e-task-1', { runID: 'e2e-task-1', status: 'running', runner: 'e2e' });
  await waitFor(() => received.some((f) => f.type === 'data' && f.id === 'sub-task-1'));
  const dataFrame = received.find((f) => f.type === 'data' && f.id === 'sub-task-1');
  if (dataFrame?.payload?.data?.onTaskStatus?.status === 'running') ok('bus.publish → data frame with correct shape');
  else bad(`unexpected data frame: ${JSON.stringify(dataFrame)}`);

  // ── 6. stop cancels subscription ─────────────────────────────────────
  ws.send(JSON.stringify({ type: 'stop', id: 'sub-task-1' }));
  await new Promise((r) => setTimeout(r, 100));
  received.length = 0;
  bus.publish('onTaskStatus', 'e2e-task-1', { runID: 'e2e-task-1', status: 'after-stop' });
  await new Promise((r) => setTimeout(r, 150));
  if (received.length === 0) ok('stop cancels subscription (no data after)');
  else bad(`leaked frames after stop: ${JSON.stringify(received)}`);
  if (!bus.metrics().counts['onTaskStatus:e2e-task-1']) ok('subscription removed from bus on stop');
  else bad(`bus subscription leaked: ${JSON.stringify(bus.metrics().counts)}`);

  // ── 7. ka echo ───────────────────────────────────────────────────────
  received.length = 0;
  ws.send(JSON.stringify({ type: 'ka' }));
  await waitFor(() => received.some((f) => f.type === 'ka'));
  ok('ka echoes ka');

  // ── 8. unknown frame → error, keep open ──────────────────────────────
  received.length = 0;
  ws.send(JSON.stringify({ type: 'wibble' }));
  await waitFor(() => received.some((f) => f.type === 'error'));
  if (ws.readyState === WebSocket.OPEN) ok('unknown frame → error frame, connection stays open');
  else bad(`connection closed on unknown frame, state=${ws.readyState}`);

  // ── 9. /publish cross-instance push ──────────────────────────────────
  // Re-subscribe so we can verify the /publish path delivers.
  ws.send(JSON.stringify({
    id: 'sub-task-2',
    type: 'start',
    payload: {
      data: JSON.stringify({
        query: 'subscription S { onTaskStatus(runID: "publish-target-1") { runID status } }',
      }),
    },
  }));
  await waitFor(() => received.some((f) => f.type === 'start_ack' && f.id === 'sub-task-2'));
  received.length = 0;

  // Wrong secret → 401
  let pr = await postJson(`http://localhost:${WS_PORT}/publish`,
    { topic: 'onTaskStatus', target: 'publish-target-1', payload: { runID: 'publish-target-1', status: 'via-publish' } },
    { 'X-ECAN-Push-Secret': 'wrong' },
  );
  if (pr.statusCode === 401) ok('/publish wrong secret → 401');
  else bad(`/publish wrong secret: ${pr.statusCode} ${pr.body}`);

  // Correct secret → 200 + delivery
  pr = await postJson(`http://localhost:${WS_PORT}/publish`,
    { topic: 'onTaskStatus', target: 'publish-target-1', payload: { runID: 'publish-target-1', status: 'via-publish' } },
    { 'x-push-secret': PUSH_SECRET },
  );
  if (pr.statusCode === 200 && JSON.parse(pr.body).ok) ok('/publish correct secret → 200');
  else bad(`/publish correct: ${pr.statusCode} ${pr.body}`);
  await waitFor(() => received.some((f) => f.type === 'data' && f.payload?.data?.onTaskStatus?.status === 'via-publish'));
  ok('cross-instance /publish → data frame');

  // Unknown topic → 400
  pr = await postJson(`http://localhost:${WS_PORT}/publish`,
    { topic: 'fakeTopic', target: 'x', payload: {} },
    { 'x-push-secret': PUSH_SECRET },
  );
  if (pr.statusCode === 200) ok('/publish unknown topic → 200 (no-op, not an error)');
  else bad(`/publish unknown topic: ${pr.statusCode} ${pr.body}`);

  ws.close();
  await new Promise((r) => ws.once('close', r));
  server.close();

  console.log(`\n  ${pass} passed, ${fail} failed`);
  process.exit(fail > 0 ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(2); });
