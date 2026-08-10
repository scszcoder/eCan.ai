#!/usr/bin/env node
/**
 * End-to-end local stack test — simulates the deployed topology with two
 * Node processes on different ports:
 *
 *   port 9101 → ecan-graphql-ws function (self-built graphql-ws bridge)
 *   port 9100 → ecan-graphql-api function (publishes via HTTP POST to 9101)
 *
 * The GraphQL API has its bridge wired to WS_LOCAL_URL=http://localhost:9101
 * instead of the production TCB host. WS_PUSH_SECRET is set so the bridge
 * actually fires.
 *
 * Tests:
 *   1. WS function /healthz returns 200
 *   2. /publish with correct secret returns 200 + delivery count
 *   3. /publish with wrong secret returns 401
 *   4. WebSocket client connects with graphql-ws subprotocol
 *   5. End-to-end: WS client connects, then API publishes publishTaskStatus,
 *      WS client receives the matching data frame.
 *
 * Run: node scripts/test-local-stack.js
 */
const assert = require('node:assert/strict');
const http = require('node:http');
const WebSocket = require('ws');
const bus = require('../event-bus');

const WS_PORT = 9101;
const API_PORT = 9100;
const PUSH_SECRET = 'test-stack-secret';

function startWsFunction() {
  process.env.WS_PUSH_SECRET = PUSH_SECRET;
  const { createServer } = require('../functions/ecan-graphql-ws');
  const server = http.createServer();
  const wss = new WebSocket.Server({ server });
  // Reuse the WS function's HTTP server by attaching its request handler too.
  // Simpler: spin up the WS function fully.
  const fnServer = require('../functions/ecan-graphql-ws').createServer();
  return new Promise((resolve) => {
    fnServer.listen(WS_PORT, () => resolve(fnServer));
  });
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
      hostname: u.hostname,
      port: u.port,
      path: u.pathname,
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

let pass = 0, fail = 0;
const ok = (m) => { pass++; console.log(`  ✓ ${m}`); };
const bad = (m) => { fail++; console.log(`  ✗ ${m}`); };

async function main() {
  // Wire env BEFORE requiring modules so the bridge sees WS_LOCAL_URL.
  process.env.WS_PUSH_SECRET = PUSH_SECRET;
  process.env.WS_LOCAL_URL = `http://localhost:${WS_PORT}`;
  process.env.ALLOW_INSECURE_AUTH = 'true';
  process.env.NODE_ENV = 'development';

  // 1. Start WS function
  bus.reset();
  console.log(`\n[stack] starting WS function on :${WS_PORT}`);
  const wsServer = await startWsFunction();
  ok('WS function started');

  // 2. Start GraphQL API function
  console.log(`[stack] starting API function on :${API_PORT}`);
  const apiServer = await startApiFunction();
  ok('API function started');

  // 3. WS /healthz
  let r = await get(`http://localhost:${WS_PORT}/healthz`);
  if (r.statusCode === 200 && r.body.includes('ecan-graphql-ws')) ok('WS /healthz returns 200 + service name');
  else bad(`WS /healthz: ${r.statusCode} ${r.body}`);

  // 4. /publish wrong secret
  r = await postJson(`http://localhost:${WS_PORT}/publish`, { topic: 'onTaskStatus', target: 'x', payload: { s: 1 } });
  if (r.statusCode === 401) ok('WS /publish wrong secret → 401');
  else bad(`WS /publish wrong secret: ${r.statusCode} ${r.body}`);

  // 5. /publish correct secret
  r = await postJson(`http://localhost:${WS_PORT}/publish`,
    { topic: 'onTaskStatus', target: 'e2e-test-1', payload: { runID: 'e2e-test-1', status: 'completed' } },
    { 'X-ECAN-Push-Secret': PUSH_SECRET }
  );
  if (r.statusCode === 200 && JSON.parse(r.body).success) ok('WS /publish OK → 200 + delivery');
  else bad(`WS /publish OK: ${r.statusCode} ${r.body}`);

  // 6. /publish unknown topic
  r = await postJson(`http://localhost:${WS_PORT}/publish`,
    { topic: 'fakeTopic', target: 'x', payload: {} },
    { 'X-ECAN-Push-Secret': PUSH_SECRET }
  );
  if (r.statusCode === 400) ok('WS /publish unknown topic → 400');
  else bad(`WS /publish unknown topic: ${r.statusCode} ${r.body}`);

  // 7. End-to-end: WS client + GraphQL publish
  console.log('\n[stack] end-to-end: WS subscribe + GraphQL publish');
  const ws = new WebSocket(`ws://localhost:${WS_PORT}/?token=test-user`, 'graphql-ws');
  const received = [];
  ws.on('message', (data) => {
    try {
      const text = data.toString();
      received.push(text);
      process.stdout.write(`[ws-frame] ${JSON.stringify(text)}\n`);
    } catch { /* ignore */ }
  });
  ws.on('error', (e) => bad(`ws error: ${e.message}`));
  await new Promise((res, rej) => {
    ws.once('open', res);
    ws.once('error', rej);
    setTimeout(() => rej(new Error('ws open timeout')), 3000);
  });
  ok('WS client connected');

  // Handshake
  ws.send(JSON.stringify({ type: 'connection_init' }));
  await waitFor(() => received.some((s) => s.includes('connection_ack')));
  ok('connection_init → connection_ack');

  // Subscribe
  ws.send(JSON.stringify({
    id: 'stack-sub-1',
    type: 'start',
    payload: {
      data: JSON.stringify({
        query: 'subscription S { onTaskStatus(runID: "e2e-e2e") { runID status } }',
      }),
    },
  }));
  await waitFor(() => received.some((s) => s.includes('start_ack')));
  ok('start → start_ack');

  await new Promise((r) => setTimeout(r, 200));

  // Trigger a publish via GraphQL mutation on the local API
  console.log('[stack] POSTing GraphQL mutation');
  const apiResp = await postJson(`http://localhost:${API_PORT}/api/graphql`, {
    query: 'mutation { publishTaskStatus(input: {runID: "e2e-e2e", success: true, runner: "test"}) { runID } }',
  });
  console.log('[stack] mutation result:', apiResp.statusCode, apiResp.body.slice(0, 300));
  if (apiResp.statusCode === 200) ok(`API mutation → 200`);
  else bad(`API mutation: ${apiResp.statusCode} ${apiResp.body}`);

  await waitFor(() => received.some((s) => s.includes('e2e-e2e') && s.includes('onTaskStatus')));

  const allText = received.join('');
  if (allText.includes('connection_ack')) ok('WS frame: connection_ack');
  else bad(`no connection_ack in: ${allText}`);
  if (allText.includes('start_ack')) ok('WS frame: start_ack');
  else bad(`no start_ack in: ${allText}`);
  if (allText.includes('e2e-e2e') && allText.includes('onTaskStatus')) {
    ok('WS frame: onTaskStatus event delivered via cross-instance push');
  } else {
    bad(`onTaskStatus frame missing. frames: ${allText}`);
  }

  ws.close();
  apiServer.close();
  wsServer.close();

  console.log(`\n  ${pass} passed, ${fail} failed`);
  process.exit(fail > 0 ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(2); });
