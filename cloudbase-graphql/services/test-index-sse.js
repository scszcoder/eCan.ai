/**
 * 本地端到端验证：模拟 SCF HTTP 触发器调用 index.js handler，
 * 验证 /api/events SSE 路由。
 *
 * 跑：node cloudbase-graphql/services/test-index-sse.js
 *
 * 测试：
 *   1. GET /api/events?topic=onTaskStatus&runID=abc → 200 + streaming body
 *   2. stream 立即发 :connected 注释
 *   3. 另起 mutation /api/graphql publish* 触发后，stream 收到 event frame
 *   4. 取消 reader 后 cleanup
 */

// 加速心跳
process.env.SSE_HEARTBEAT_MS = '200';

// 隔离 event-bus
const bus = require('../event-bus');
bus.reset();

const { main: handler } = require('../index.js');

(async () => {
  let pass = 0, fail = 0;
  const ok = m => { pass++; console.log(`  ✓ ${m}`); };
  const bad = m => { fail++; console.log(`  ✗ ${m}`); };

  console.log('Test 1: SSE GET /api/events?topic=onTaskStatus&runID=local-1');
  // 启动 SSE 连接 + 200ms 后 publish + 100ms 后第二 publish
  const ssePromise = handler({
    httpMethod: 'GET',
    headers: { host: 'localhost' },
    path: '/api/events?topic=onTaskStatus&runID=local-1',
  });

  // 给 start() 一段时间注册订阅
  await new Promise(r => setTimeout(r, 50));

  // 现在 publish
  bus.publish('onTaskStatus', 'local-1', { runID: 'local-1', status: 'completed' });
  bus.publish('onTaskStatus', 'local-1', { runID: 'local-1', status: 'failed' });

  const sseResp = await ssePromise;
  if (sseResp.statusCode !== 200) bad(`statusCode ${sseResp.statusCode}`);
  else ok('statusCode 200');
  // SCF headers are lowercased
  const ct = sseResp.headers['content-type'] || sseResp.headers['Content-Type'];
  if (ct?.includes('text/event-stream')) ok('Content-Type: text/event-stream');
  else bad(`content-type ${ct}`);

  // 读 stream — collect all frames for 800ms
  const reader = sseResp.body.getReader();
  const decoder = new TextDecoder();
  const frames = [];
  const deadline = Date.now() + 800;
  while (Date.now() < deadline) {
    const r = await reader.read();
    if (r.done) break;
    frames.push(decoder.decode(r.value));
  }
  const allText = frames.join('');
  if (allText.includes(': connected')) ok('first frame is :connected');
  else bad(`no :connected in: ${allText}`);
  if (allText.includes('event: onTaskStatus') && allText.includes('"status":"completed"')) {
    ok('publish event frame received (status=completed)');
  } else bad(`no completed: ${allText}`);
  if (allText.includes('event: onTaskStatus') && allText.includes('"status":"failed"')) {
    ok('publish event frame received (status=failed)');
  } else bad(`no failed: ${allText}`);

  // cancel & verify cleanup
  await reader.cancel();
  await new Promise(r => setTimeout(r, 200));
  const after = bus.metrics();
  if (!after.counts['onTaskStatus:local-1']) ok('subscription cleaned up');
  else bad(`not cleaned: ${JSON.stringify(after.counts)}`);

  console.log(`\n  ${pass} passed, ${fail} failed`);
  process.exit(fail > 0 ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });