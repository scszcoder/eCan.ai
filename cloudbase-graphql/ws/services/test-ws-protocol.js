#!/usr/bin/env node
/**
 * Unit tests for services/ws-protocol.js — pure protocol logic, no network.
 *
 * Tests:
 *   1. parseFrame: rejects malformed inputs
 *   2. extractSubscriptionField: extracts the first `on<Field>` token
 *   3. extractFirstArgValue: extracts a string scalar argument
 *   4. resolveStartTarget: maps (query, variables) → (topic, target)
 *   5. handleClientMessage:
 *      - connection_init before init → connection_error + close
 *      - connection_init → connection_ack
 *      - duplicate connection_init → close
 *      - start before init → close
 *      - start with valid query → start_ack + bus.subscribe invoked
 *      - start triggers a 'data' frame when bus.publish fires
 *      - stop cancels the subscription (no more data frames)
 *      - ka echoes
 *      - unknown frame type → error frame
 *      - subscription limit enforced
 *      - close cleans up
 *
 * Run: node services/test-ws-protocol.js
 */

'use strict';

const assert = require('node:assert/strict');
const protocol = require('./ws-protocol');
const bus = require('../event-bus');

process.env.SSE_HEARTBEAT_MS = '100';

let pass = 0, fail = 0;
function ok(m) { pass++; console.log(`  ✓ ${m}`); }
function bad(m) { fail++; console.log(`  ✗ ${m}`); }

// In-memory transport. We record every frame `send` is asked to emit.
function makeSink() {
  const frames = [];
  return {
    frames,
    send(frame) { frames.push(frame); },
  };
}

// Helper: flush the event loop enough microtasks for the pump to advance.
const tick = () => new Promise((r) => setImmediate(r));
async function settle(n = 5) { for (let i = 0; i < n; i++) await tick(); }

// =================================================================
// 1. parseFrame
// =================================================================
console.log('\n[1] parseFrame');
{
  const r1 = protocol.parseFrame('not json');
  if (r1.error) ok('rejects non-JSON'); else bad(`expected error, got ${JSON.stringify(r1)}`);

  const r2 = protocol.parseFrame('null');
  if (r2.error) ok('rejects null'); else bad(`expected error, got ${JSON.stringify(r2)}`);

  const r3 = protocol.parseFrame('[]');
  if (r3.error) ok('rejects array'); else bad(`expected error, got ${JSON.stringify(r3)}`);

  const r4 = protocol.parseFrame('{"type":"ka"}');
  if (r4.frame?.type === 'ka') ok('accepts valid object');
  else bad(`unexpected: ${JSON.stringify(r4)}`);

  const r5 = protocol.parseFrame('x'.repeat(70 * 1024));
  if (r5.error?.includes('exceeds')) ok('rejects oversized frame');
  else bad(`expected size error, got ${JSON.stringify(r5)}`);
}

// =================================================================
// 2. extractSubscriptionField
// =================================================================
console.log('\n[2] extractSubscriptionField');
{
  const cases = [
    ['subscription S { onMessageReceived(chatID: "x") { id } }', 'onMessageReceived'],
    ['{ onTaskStatus(runID: "r") { status } }', 'onTaskStatus'],
    ['query Q { getTask(id: "x") { id } }', null], // Query, not subscription
    ['', null],
    [null, null],
  ];
  for (const [input, expected] of cases) {
    const got = protocol.extractSubscriptionField(input);
    if (got === expected) ok(`"${String(input).slice(0, 40)}" → ${expected}`);
    else bad(`"${String(input).slice(0, 40)}" expected ${expected}, got ${got}`);
  }
}

// =================================================================
// 3. extractFirstArgValue
// =================================================================
console.log('\n[3] extractFirstArgValue');
{
  const a = protocol.extractFirstArgValue(
    'subscription S { onMessageReceived(chatID: "abc-123") { id } }',
    'onMessageReceived', 'chatID'
  );
  if (a === 'abc-123') ok('extracts quoted string arg');
  else bad(`expected "abc-123", got ${a}`);

  const b = protocol.extractFirstArgValue(
    'subscription S { onTaskStatus(runID: "r-7") { status } }',
    'onTaskStatus', 'runID'
  );
  if (b === 'r-7') ok('extracts second field arg');
  else bad(`expected "r-7", got ${b}`);

  const c = protocol.extractFirstArgValue(
    'subscription S { onTaskStatus(runID: $id) { status } }',
    'onTaskStatus', 'runID'
  );
  if (c === undefined) ok('returns undefined for variable arg');
  else bad(`expected undefined, got ${c}`);
}

// =================================================================
// 4. resolveStartTarget
// =================================================================
console.log('\n[4] resolveStartTarget');
{
  const identity = { sub: 'u1' };
  const r1 = protocol.resolveStartTarget({
    data: JSON.stringify({
      query: 'subscription S { onMessageReceived(chatID: "room1") { id } }',
    }),
  }, identity);
  if (r1.topic === 'onMessageReceived' && r1.target === 'room1') ok('maps simple subscription');
  else bad(`unexpected: ${JSON.stringify(r1)}`);

  const r2 = protocol.resolveStartTarget({
    data: JSON.stringify({
      query: 'subscription S { onTaskStatus(runID: $runID) { status } }',
      variables: { runID: 'run-42' },
    }),
  }, identity);
  if (r2.topic === 'onTaskStatus' && r2.target === 'run-42') ok('falls back to variables');
  else bad(`unexpected: ${JSON.stringify(r2)}`);

  const r3 = protocol.resolveStartTarget({
    data: JSON.stringify({
      query: 'subscription S { onPuzzleReceived { pzid } }',
    }),
  }, identity);
  if (r3.topic === 'onPuzzleReceived' && r3.target === '__global__') ok('broadcast topic resolves to global target');
  else bad(`unexpected: ${JSON.stringify(r3)}`);

  const r4 = protocol.resolveStartTarget({
    data: JSON.stringify({
      query: 'subscription S { onMessageReceived { id } }',
    }),
  }, identity);
  if (r4.error?.includes('requires argument')) ok('missing arg → error');
  else bad(`expected error, got ${JSON.stringify(r4)}`);

  const r5 = protocol.resolveStartTarget({
    data: JSON.stringify({
      query: 'subscription S { onBogusTopic(x: "1") { id } }',
    }),
  }, identity);
  if (r5.error?.includes('unknown subscription field')) ok('unknown field → error');
  else bad(`expected error, got ${JSON.stringify(r5)}`);

  const r6 = protocol.resolveStartTarget({
    data: JSON.stringify({
      query: 'subscription S { onAccountNotification(owner: "u1") { id } }',
    }),
  }, identity);
  if (r6.topic === 'onAccountNotification' && r6.target === 'u1') ok('account notification allows its owner');
  else bad(`unexpected: ${JSON.stringify(r6)}`);

  const r7 = protocol.resolveStartTarget({
    data: JSON.stringify({
      query: 'subscription S { onAccountNotification(owner: "another-user") { id } }',
    }),
  }, identity);
  if (r7.error?.includes('authenticated owner')) ok('account notification rejects a different owner');
  else bad(`expected authorization error, got ${JSON.stringify(r7)}`);
}

// =================================================================
// 5. handleClientMessage state machine
// =================================================================
console.log('\n[5] handleClientMessage state machine');

(async () => {
  bus.reset();

  // 5.1 start before connection_init
  {
    const sink = makeSink();
    const state = protocol.createConnectionState({
      connectionId: 'c1', send: sink.send, identity: { sub: 'u1' },
    });
    const r = protocol.handleClientMessage(state, JSON.stringify({ type: 'start', id: 's1', payload: { data: '{"query":"subscription S { onTaskStatus(runID: \"r1\") { status } }"}' } }));
    if (r.close && sink.frames.some((f) => f.type === 'connection_error')) ok('start before init → close + error');
    else bad(`expected close + error, frames=${JSON.stringify(sink.frames)}`);
  }

  // 5.2 valid handshake
  {
    const sink = makeSink();
    const state = protocol.createConnectionState({
      connectionId: 'c2', send: sink.send, identity: { sub: 'u2' },
    });
    const r = protocol.handleClientMessage(state, JSON.stringify({ type: 'connection_init' }));
    if (!r.close && sink.frames.some((f) => f.type === 'connection_ack')) ok('connection_init → connection_ack');
    else bad(`unexpected: ${JSON.stringify(sink.frames)}`);

    // duplicate
    sink.frames.length = 0;
    const r2 = protocol.handleClientMessage(state, JSON.stringify({ type: 'connection_init' }));
    if (r2.close && sink.frames.some((f) => f.type === 'connection_error')) ok('duplicate connection_init → close');
    else bad(`unexpected: ${JSON.stringify(sink.frames)}`);
  }

  // 5.3 start → start_ack + bus.subscribe wired
  {
    const sink = makeSink();
    const state = protocol.createConnectionState({
      connectionId: 'c3', send: sink.send, identity: { sub: 'u3' },
    });
    protocol.handleClientMessage(state, JSON.stringify({ type: 'connection_init' }));
    sink.frames.length = 0;

    protocol.handleClientMessage(state, JSON.stringify({
      type: 'start', id: 'subA',
      payload: { data: JSON.stringify({ query: 'subscription S { onTaskStatus(runID: "runA") { status } }' }) },
    }));
    await settle();
    const m = bus.metrics();
    if (m.counts['onTaskStatus:runA'] === 1 && sink.frames.some((f) => f.type === 'start_ack')) {
      ok('start → start_ack + bus.subscribe');
    } else {
      bad(`metrics=${JSON.stringify(m.counts)} frames=${JSON.stringify(sink.frames)}`);
    }
  }

  // 5.4 bus.publish → data frame
  {
    bus.reset();
    const sink = makeSink();
    const state = protocol.createConnectionState({
      connectionId: 'c4', send: sink.send, identity: { sub: 'u4' },
    });
    protocol.handleClientMessage(state, JSON.stringify({ type: 'connection_init' }));
    protocol.handleClientMessage(state, JSON.stringify({
      type: 'start', id: 'subB',
      payload: { data: JSON.stringify({ query: 'subscription S { onTaskStatus(runID: "runB") { status } }' }) },
    }));
    await settle();
    sink.frames.length = 0;

    bus.publish('onTaskStatus', 'runB', { runID: 'runB', status: 'running' });
    await settle();

    const data = sink.frames.find((f) => f.type === 'data');
    if (data
        && data.id === 'subB'
        && data.payload?.data?.onTaskStatus?.status === 'running') {
      ok('bus.publish → data frame with correct payload shape');
    } else {
      bad(`unexpected data frame: ${JSON.stringify(sink.frames)}`);
    }

    // 5.5 stop → no more frames
    protocol.handleClientMessage(state, JSON.stringify({ type: 'stop', id: 'subB' }));
    sink.frames.length = 0;
    bus.publish('onTaskStatus', 'runB', { runID: 'runB', status: 'after-stop' });
    await settle();
    if (sink.frames.length === 0) ok('stop cancels subscription (no further data)');
    else bad(`leaked frames after stop: ${JSON.stringify(sink.frames)}`);

    protocol.closeConnection(state);
  }

  // 5.6 ka echoes
  {
    bus.reset();
    const sink = makeSink();
    const state = protocol.createConnectionState({
      connectionId: 'c6', send: sink.send, identity: { sub: 'u6' },
    });
    protocol.handleClientMessage(state, JSON.stringify({ type: 'connection_init' }));
    protocol.handleClientMessage(state, JSON.stringify({ type: 'ka' }));
    if (sink.frames.some((f) => f.type === 'ka')) ok('ka echoes ka');
    else bad(`no ka echoed: ${JSON.stringify(sink.frames)}`);
    protocol.closeConnection(state);
  }

  // 5.7 unknown frame → error frame, no close
  {
    bus.reset();
    const sink = makeSink();
    const state = protocol.createConnectionState({
      connectionId: 'c7', send: sink.send, identity: { sub: 'u7' },
    });
    protocol.handleClientMessage(state, JSON.stringify({ type: 'connection_init' }));
    sink.frames.length = 0;
    const r = protocol.handleClientMessage(state, JSON.stringify({ type: 'wibble' }));
    if (!r.close && sink.frames.some((f) => f.type === 'error')) ok('unknown frame → error frame, keep open');
    else bad(`unexpected: ${JSON.stringify(sink.frames)}`);
    protocol.closeConnection(state);
  }

  // 5.8 subscription limit
  {
    bus.reset();
    const sink = makeSink();
    const state = protocol.createConnectionState({
      connectionId: 'c8', send: sink.send, identity: { sub: 'u8' },
    });
    protocol.handleClientMessage(state, JSON.stringify({ type: 'connection_init' }));
    // open MAX_SUBSCRIPTIONS_PER_CONN subscriptions against distinct targets
    for (let i = 0; i < protocol.MAX_SUBSCRIPTIONS_PER_CONN; i++) {
      protocol.handleClientMessage(state, JSON.stringify({
        type: 'start', id: `s${i}`,
        payload: { data: JSON.stringify({ query: `subscription S { onTaskStatus(runID: "limit-${i}") { status } }` }) },
      }));
    }
    sink.frames.length = 0;
    protocol.handleClientMessage(state, JSON.stringify({
      type: 'start', id: 'overflow',
      payload: { data: JSON.stringify({ query: 'subscription S { onTaskStatus(runID: "overflow") { status } }' }) },
    }));
    const err = sink.frames.find((f) => f.type === 'error');
    if (err && err.payload?.[0]?.message?.includes('too many subscriptions')) ok('subscription limit enforced');
    else bad(`expected limit error, got ${JSON.stringify(sink.frames)}`);
    protocol.closeConnection(state);
  }

  // 5.9 close cleans up
  {
    bus.reset();
    const sink = makeSink();
    const state = protocol.createConnectionState({
      connectionId: 'c9', send: sink.send, identity: { sub: 'u9' },
    });
    protocol.handleClientMessage(state, JSON.stringify({ type: 'connection_init' }));
    protocol.handleClientMessage(state, JSON.stringify({
      type: 'start', id: 'sX',
      payload: { data: JSON.stringify({ query: 'subscription S { onTaskStatus(runID: "runX") { status } }' }) },
    }));
    await settle();
    if (bus.metrics().counts['onTaskStatus:runX'] !== 1) {
      bad(`pre-close metric missing: ${JSON.stringify(bus.metrics().counts)}`);
      return finish();
    }
    protocol.closeConnection(state);
    if (!bus.metrics().counts['onTaskStatus:runX']) ok('close → bus subscription removed');
    else bad(`subscription leaked: ${JSON.stringify(bus.metrics().counts)}`);
  }

  finish();
})();

function finish() {
  console.log(`\n  ${pass} passed, ${fail} failed`);
  process.exit(fail > 0 ? 1 : 0);
}
