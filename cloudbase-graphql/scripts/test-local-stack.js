#!/usr/bin/env node
/**
 * End-to-end local stack test — simulates the deployed topology with two
 * Node processes on different ports:
 *
 *   port 9101 → ecan-graphql-sse function (SSE function)
 *   port 9100 → ecan-graphql-api function (publishes via HTTP POST to 9101)
 *
 * The GraphQL API has its bridge wired to SSE_LOCAL_URL=http://localhost:9101
 * instead of the production TCB host. SSE_PUSH_SECRET is set so the bridge
 * actually fires.
 *
 * Tests:
 *   1. SSE function /healthz returns 200
 *   2. /publish with correct secret returns 200 + delivery count
 *   3. /publish with wrong secret returns 401
 *   4. /api/events?topic=onTaskStatus&runID=abc returns 200 + ReadableStream
 *   5. End-to-end: SSE client connects, then API publishes publishTaskStatus
 *      (via local yoga.fetch), SSE client receives the matching event frame.
 *
 * Run: node scripts/test-local-stack.js
 */
const assert = require('node:assert/strict');
const http = require('node:http');

const SSE_PORT = 9101;
const API_PORT = 9100;
const PUSH_SECRET = 'test-stack-secret';

function startSseFunction() {
  const { main } = require('/Users/liuqiang/WorkSpace/ecan/eCan.ai/cloudbase-graphql/functions/ecan-graphql-sse/index.js');
  const server = http.createServer(async (req, res) => {
    let body = '';
    req.on('data', (c) => { body += c; });
    req.on('end', async () => {
      // SCF HTTP trigger event shape
      const event = {
        httpMethod: req.method,
        path: req.url,
        headers: req.headers,
        body: body || undefined,
        queryStringParameters: Object.fromEntries(new URL(req.url, 'http://x').searchParams),
      };
      const ctx = { callbackWaitsForEmptyEventLoop: false };
      try {
        const r = await main(event, ctx);
        res.statusCode = r.statusCode || 200;
        for (const [k, v] of Object.entries(r.headers || {})) res.setHeader(k, v);
        if (r.body && r.body.getReader) {
          const reader = r.body.getReader();
          const pump = async () => {
            while (true) {
              const { value, done } = await reader.read();
              if (done) { res.end(); return; }
              res.write(Buffer.from(value));
            }
          };
          pump().catch(() => res.end());
        } else {
          res.end(r.body || '');
        }
      } catch (e) {
        res.statusCode = 500;
        res.end(JSON.stringify({ error: e.message }));
      }
    });
  });
  return new Promise((resolve) => {
    server.listen(SSE_PORT, () => resolve(server));
  });
}

function startApiFunction() {
  const apiModule = require('/Users/liuqiang/WorkSpace/ecan/eCan.ai/cloudbase-graphql/index.js');
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
  return new Promise((resolve) => {
    server.listen(API_PORT, () => resolve(server));
  });
}

// `get` for short responses: collects body and resolves on `end`.
function get(url) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, (res) => {
      let chunks = '';
      res.on('data', (c) => { chunks += c; });
      res.on('end', () => resolve({ statusCode: res.statusCode, body: chunks, headers: res.headers }));
      res.on('error', reject);
    });
    req.on('error', reject);
  });
}

// `getStream` for SSE: resolves with the live response object so callers can
// pump frames themselves.
function getStream(url) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, (res) => resolve(res));
    req.on('error', reject);
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

let pass = 0, fail = 0;
const ok = (m) => { pass++; console.log(`  ✓ ${m}`); };
const bad = (m) => { fail++; console.log(`  ✗ ${m}`); };

async function main() {
  // Wire env BEFORE requiring modules so SSE bridge sees SSE_LOCAL_URL.
  process.env.SSE_PUSH_SECRET = PUSH_SECRET;
  process.env.SSE_LOCAL_URL = `http://localhost:${SSE_PORT}`;
  process.env.SSE_HEARTBEAT_MS = '200'; // faster heartbeats for test
  process.env.ALLOW_INSECURE_AUTH = 'true';
  process.env.NODE_ENV = 'development'; // allow insecure auth

  // 1. Start SSE function
  console.log(`\n[stack] starting SSE function on :${SSE_PORT}`);
  const sseServer = await startSseFunction();
  ok('SSE function started');
  console.log('[stack] SSE up, starting API');

  // 2. Start GraphQL API function
  console.log(`[stack] starting API function on :${API_PORT}`);
  const apiServer = await startApiFunction();
  ok('API function started');
  console.log('[stack] API up, calling /healthz');

  // 3. SSE /healthz
  let r = await get(`http://localhost:${SSE_PORT}/healthz`);
  if (r.statusCode === 200 && r.body.includes('ecan-graphql-sse')) ok('SSE /healthz returns 200 + service name');
  else bad(`SSE /healthz: ${r.statusCode} ${r.body}`);

  // 4. /publish wrong secret
  r = await postJson(`http://localhost:${SSE_PORT}/publish`, { topic: 'onTaskStatus', target: 'x', payload: { s: 1 } });
  if (r.statusCode === 401) ok('SSE /publish wrong secret → 401');
  else bad(`SSE /publish wrong secret: ${r.statusCode} ${r.body}`);

  // 5. /publish correct secret
  r = await postJson(`http://localhost:${SSE_PORT}/publish`,
    { topic: 'onTaskStatus', target: 'e2e-test-1', payload: { runID: 'e2e-test-1', status: 'completed' } },
    { 'X-ECAN-Push-Secret': PUSH_SECRET }
  );
  if (r.statusCode === 200 && JSON.parse(r.body).success) ok('SSE /publish OK → 200 + delivery');
  else bad(`SSE /publish OK: ${r.statusCode} ${r.body}`);

  // 6. /publish unknown topic
  r = await postJson(`http://localhost:${SSE_PORT}/publish`,
    { topic: 'fakeTopic', target: 'x', payload: {} },
    { 'X-ECAN-Push-Secret': PUSH_SECRET }
  );
  if (r.statusCode === 400) ok('SSE /publish unknown topic → 400');
  else bad(`SSE /publish unknown topic: ${r.statusCode} ${r.body}`);

  // 7. End-to-end: SSE client + GraphQL publish
  console.log('\n[stack] end-to-end: SSE subscribe + GraphQL publish');
  const sseRes = await getStream(`http://localhost:${SSE_PORT}/api/events?topic=onTaskStatus&runID=e2e-e2e`);
  console.log('[stack] SSE response received:', sseRes.statusCode, sseRes.headers['content-type']);
  if (sseRes.statusCode !== 200 || !sseRes.headers['content-type']?.includes('text/event-stream')) {
    bad(`SSE /api/events: ${sseRes.statusCode} ${sseRes.headers['content-type']}`);
    apiServer.close();
    sseServer.close();
    process.exit(1);
  }
  ok('SSE /api/events returns 200 + text/event-stream');

  // Collect frames in background
  const frames = [];
  const decoder = new TextDecoder();
  let sseEnd = false;
  let onFrameResolve;
  const onFrame = new Promise((resolve) => {
    onFrameResolve = resolve;
    sseRes.on('data', (chunk) => {
      const text = decoder.decode(chunk);
      process.stdout.write(`[sse-frame] ${JSON.stringify(text)}\n`);
      frames.push(text);
      if (text.includes('event: onTaskStatus') && text.includes('e2e-e2e')) {
        resolve();
      }
    });
    sseRes.on('end', () => { sseEnd = true; resolve(); });
    setTimeout(() => { console.log('[sse-frame] timeout 8s'); resolve(); }, 8000);
  });

  // Give stream.start() time to register the subscription
  console.log('[stack] waiting 200ms for subscription');
  await new Promise(r => setTimeout(r, 200));

  // Trigger a publish via GraphQL mutation on the local API
  console.log('[stack] POSTing GraphQL mutation');
  const apiResp = await postJson(`http://localhost:${API_PORT}/api/graphql`, {
    query: 'mutation { publishTaskStatus(input: {runID: "e2e-e2e", success: true, runner: "test"}) { runID } }',
  });
  console.log('[stack] mutation result:', apiResp.statusCode, apiResp.body.slice(0, 300));
  if (apiResp.statusCode === 200) ok(`API mutation → 200`);
  else bad(`API mutation: ${apiResp.statusCode} ${apiResp.body}`);

  await onFrame;
  console.log('[stack] onFrame resolved');

  const allText = frames.join('');
  if (allText.includes(': connected')) ok('SSE frame: :connected comment');
  else bad(`no :connected in: ${allText}`);
  if (allText.includes('event: onTaskStatus') && allText.includes('e2e-e2e')) {
    ok('SSE frame: onTaskStatus event delivered via cross-instance push');
  } else {
    bad(`onTaskStatus frame missing. frames: ${allText}`);
  }

  sseRes.destroy();
  apiServer.close();
  sseServer.close();

  console.log(`\n  ${pass} passed, ${fail} failed`);
  process.exit(fail > 0 ? 1 : 0);
}

main().catch(e => { console.error(e); process.exit(2); });
