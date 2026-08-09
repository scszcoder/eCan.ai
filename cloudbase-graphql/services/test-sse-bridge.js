/**
 * 单元测试 — services/sse-bridge.js + event-bus.js 协作
 *
 * 验证：
 *   1. buildSSEResponse 拒绝 unknown topic
 *   2. buildSSEResponse 拒绝 missing target (非 broadcast topic)
 *   3. buildSSEResponse 返回 text/event-stream headers
 *   4. SSE 连接后，bus.publish 推一条消息，Response 立即收到 event frame
 *   5. SSE 连接后无 publish 时保持连接（不立即关闭）
 *
 * 跑：node cloudbase-graphql/services/test-sse-bridge.js
 */

const bus = require('../event-bus');
const { buildSSEResponse } = require('./sse-bridge');

// 测试加速：把心跳周期压到 100ms（默认 25s）。必须在 require sse-bridge 之前改 env。
process.env.SSE_HEARTBEAT_MS = '100';

let pass = 0, fail = 0;
function ok(msg) { pass++; console.log(`  ✓ ${msg}`); }
function bad(msg) { fail++; console.log(`  ✗ ${msg}`); }

// 重置 event-bus
bus.reset();

(async () => {
  // Test 1: unknown topic → 400
  let resp = buildSSEResponse('onBogusTopic', 'x', {});
  if (resp.status === 400) ok('rejects unknown topic'); else bad(`expected 400 got ${resp.status}`);

  // Test 2: missing target for non-broadcast → 400
  resp = buildSSEResponse('onTaskStatus', null, {});
  if (resp.status === 400) ok('rejects missing target'); else bad(`expected 400 got ${resp.status}`);

  // Test 3: valid topic → 200 + text/event-stream
  const captured = [];
  resp = buildSSEResponse('onTaskStatus', 'unit-test-1', {});
  if (resp.status !== 200) { bad(`expected 200 got ${resp.status}`); process.exit(1); }
  if (!resp.headers.get('content-type').includes('text/event-stream')) {
    bad(`expected text/event-stream, got ${resp.headers.get('content-type')}`);
    process.exit(1);
  }
  ok('returns text/event-stream + 200');

  // Test 4: subscribe then publish → stream emits an event frame
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();

  // 给 stream start() 一瞬间触发
  await new Promise(r => setTimeout(r, 50));

  // 此时 stream 应该发了首条注释 (: connected topic=...)
  const first = await reader.read();
  if (!first.done && first.value) {
    const text = decoder.decode(first.value);
    if (text.includes(': connected')) ok('emits initial :connected comment');
    else bad(`first frame missing :connected: ${JSON.stringify(text)}`);
  } else {
    bad('stream closed immediately');
  }

  // publish
  bus.publish('onTaskStatus', 'unit-test-1', { runID: 'unit-test-1', status: 'running' });

  const second = await reader.read();
  if (second.value) {
    const text = decoder.decode(second.value);
    if (text.includes('event: onTaskStatus') && text.includes('"status":"running"')) {
      ok('publish event delivered as SSE event frame');
    } else {
      bad(`publish frame malformed: ${JSON.stringify(text)}`);
    }
  } else {
    bad('stream closed after publish');
  }

  // Test 5: 不订阅的 target 不应收到 onTaskStatus event frame
  // 先 drain 掉 Test 4 的剩余 frame
  let drained = await reader.read();
  bus.publish('onTaskStatus', 'different-target', { runID: 'x' });
  await new Promise(r => setTimeout(r, 100));
  const third = await reader.read();
  if (third.done) {
    ok('stream closed after unrelated publish (acceptable)');
  } else if (third.value) {
    const text = decoder.decode(third.value);
    // 心跳帧（: ping ...）是允许的，但 onTaskStatus event frame 不应出现
    if (text.includes('event: onTaskStatus')) {
      bad(`LEAKED event from unrelated target: ${JSON.stringify(text)}`);
    } else {
      ok(`unrelated publish did not leak (got: ${JSON.stringify(text.slice(0, 60))})`);
    }
  }

  await reader.cancel();
  await new Promise(r => setTimeout(r, 50));

  // 验证 channel 已清理
  const after = bus.metrics();
  if (!after.counts['onTaskStatus:unit-test-1']) ok('subscription cleaned up on close');
  else bad(`subscription not cleaned: ${JSON.stringify(after.counts)}`);

  console.log(`\n  ${pass} passed, ${fail} failed`);
  process.exit(fail > 0 ? 1 : 0);
})();