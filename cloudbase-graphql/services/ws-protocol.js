/**
 * graphql-ws protocol layer — AppSync-compatible WebSocket server core.
 *
 * Goal: a Node.js-side implementation of the graphql-ws / AWS AppSync realtime
 * protocol that lets any "standard" graphql-ws client (browser `new WebSocket(url,
 * 'graphql-ws')` or Python `websockets.connect(url, subprotocols=['graphql-ws'])`)
 * connect with **zero protocol changes**.
 *
 * Reference frames (AppSync Realtime, graphql-ws subprotocol):
 *
 *   Client → Server                                  Server → Client
 *   ──────────────                                   ───────────────
 *   {type: 'connection_init'}                        {type: 'connection_ack'}
 *   {type: 'start', id, payload:{data, extensions}}  {type: 'start_ack', id}
 *                                                   {type: 'data', id, payload:{data:{<field>: ...}}}
 *                                                   {type: 'error', id, payload:[...errors...]}
 *   {type: 'stop', id}                               (no response; resource cleanup)
 *   {type: 'ka'}                                     {type: 'ka'}
 *
 * No `connection_terminate` is sent by AWS AppSync — we follow the same convention.
 *
 * Layered design:
 *   - This module is **pure** protocol logic. It does NOT touch the network.
 *   - The TCB WS function in `functions/ecan-graphql-ws/index.js` instantiates a
 *     `ws` server, calls `handleClientMessage(...)` for each incoming frame, and
 *     uses `sendFrame(...)` to write back.
 *   - It does NOT touch GraphQL — the resolver mapping from subscription query to
 *     `(topic, target)` lives in `resolvers/subscriptions.js` and is shared with
 *     the SSE bridge. Both transports therefore publish to the **same**
 *     event-bus and read the **same** topic map.
 *
 * Why this layer:
 *   - Testable without a network. `scripts/test-ws-protocol.js` runs each branch
 *     of the state machine against an in-memory sink.
 *   - Reusable: if we later want to serve the same protocol from a different
 *     transport (e.g. a sidecar Node process behind SCF), only the framing layer
 *     changes.
 */

'use strict';

const bus = require('../event-bus');

// Allow transports to inject an external bus (e.g. the WS server's own pubsub).
// When opts.externalBus is provided, it takes precedence over the module-level bus.
// This enables clean testing without module-level mocks.
function getBus(opts) {
  return opts && opts.externalBus ? opts.externalBus : bus;
}
// Topic → argument-name map. Kept in sync with resolvers/subscriptions.js.
// When you add a new subscription, update BOTH resolvers/subscriptions.js AND this map.
// The WS bridge (services/ws-bridge-push.js) fans out to TCS WS service.
const TOPIC_TARGET_KEY = {
  onMessageReceived:        'chatID',
  onA2AMessageReceived:     'channelId',
  onAccountNotification:    'owner',
  onSkillEditorStreamEvent: 'sessionId',
  onPassiveCommand:         'runId',
  onPassiveHello:           'runId',
  onPassiveStepResult:      'runId',
  onPuzzleReceived:         null, // broadcast
  onPuzzleResultReceived:   'pzid',
  onLongLLMTaskComplete:    'id',
  onSceneComplete:          'request_id',
  onAgentSceneEvent:        'acctSiteID',
  onStoryUpdate:            'acctSiteID',
  onTaskStatus:             'runID',
};

const GLOBAL_TOPIC = '__global__';

// Limits to keep a malicious or buggy client from monopolizing an instance.
const MAX_SUBSCRIPTIONS_PER_CONN = 50;
const MAX_FRAME_BYTES = 64 * 1024;

/**
 * Connection state. One instance per WS connection.
 *
 * Lifecycle:
 *   created → init → ready → closed
 *
 * The `send` function is injected by the transport layer so this module stays
 * transport-agnostic. For real WS it wraps `ws.send(JSON.stringify(frame))`;
 * for tests it's a recording array.
 */
function createConnectionState({ connectionId, send, log = () => {}, onStart, onStop }) {
  const state = {
    connectionId,
    _send: send,              // (frame) => void — default transport
    _sendOverride: null,      // optional per-frame override (set by handleClientMessage)
    get send() { return this._sendOverride || this._send; },
    log,
    onStart,                  // (topic, subId, target) => void
    onStop,                   // (topic) => void
    initialized: false,        // true after connection_ack
    closed: false,
    subscriptions: new Map(),  // subId → { topic, target, ctx, iterator, pump: Promise<void> }
  };
  return state;
}

function sendFrame(state, frame) {
  try {
    state.send(frame);
  } catch (e) {
    state.log(`[ws:${state.connectionId}] send failed: ${e.message}`);
    // The transport will likely detect the failure and close the socket; we
    // don't try to recover here.
  }
}

/**
 * Validate a frame shape. Returns the parsed object on success, or
 * { error: string } so the caller can emit a connection-level error.
 *
 * AppSync will accept frames with extra fields; we follow the same policy
 * (lenient on read, strict on emit).
 */
function parseFrame(raw, maxBytes = MAX_FRAME_BYTES) {
  if (typeof raw !== 'string') return { error: 'frame must be a string' };
  if (raw.length > maxBytes) return { error: `frame exceeds ${maxBytes} bytes` };
  let obj;
  try { obj = JSON.parse(raw); }
  catch { return { error: 'invalid JSON' }; }
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) {
    return { error: 'frame must be a JSON object' };
  }
  if (typeof obj.type !== 'string') return { error: 'frame missing "type"' };
  return { frame: obj };
}

/**
 * Extract the GraphQL subscription field name from a subscription document.
 *
 * We do **not** parse the GraphQL — the GraphQL-yoga schema is already validated
 * upstream and the client always sends a single root field. We regex out the
 * first `on[A-Z]\w*` token from the query body.
 *
 * Examples:
 *   'subscription S { onMessageReceived(chatID: "x") { ... } }' → 'onMessageReceived'
 */
function extractSubscriptionField(query) {
  if (typeof query !== 'string') return null;
  const m = query.match(/\bon([A-Z][A-Za-z0-9]+)\b/);
  return m ? `on${m[1]}` : null;
}

/**
 * Extract the value of a named argument from the first root field call.
 *
 * Handles only string literal arguments (e.g. `chatID: "abc"`). Variable
 * references like `chatID: $id` return `undefined` so the caller can fall back
 * to `variables[argName]`. Numeric / boolean / enum literals are not supported
 * here because every CN subscription's routing arg is a string.
 *
 *   onMessageReceived(chatID: "abc")      → 'abc'
 *   onMessageReceived(chatID: $id)        → undefined (need variables)
 *   onMessageReceived(chatID: "abc", x: 1) → 'abc'
 */
function extractFirstArgValue(query, fieldName, argName) {
  if (typeof query !== 'string') return undefined;
  // Match: <fieldName>...<argName>: "<value>" ... and capture the value.
  // We require the value to start with a double-quote (string literal) and
  // explicitly forbid a leading "$" (variable reference).
  const re = new RegExp(`\\b${fieldName}\\b[\\s\\S]*?\\b${argName}\\s*:\\s*"([^"]*)"`, 'i');
  const m = query.match(re);
  return m ? m[1] : undefined;
}

/**
 * Convert a parsed `start` frame's payload into the bus (topic, target) pair.
 *
 * AppSync convention: `payload.data` is a JSON-encoded string
 *   { query, variables } | '{ "query": "...", "variables": {...} }'
 *
 * @returns {{topic: string, target: string, identity: object} | {error: string}}
 */
function resolveStartTarget(payload, identity) {
  if (!payload || typeof payload !== 'object') return { error: 'missing payload' };

  // payload.data may be either an object or a stringified JSON.
  let data = payload.data;
  if (typeof data === 'string') {
    try { data = JSON.parse(data); }
    catch { return { error: 'payload.data is not valid JSON' }; }
  }
  if (!data || typeof data !== 'object') return { error: 'payload.data must be an object' };

  const query = data.query;
  const variables = data.variables || {};
  if (typeof query !== 'string') return { error: 'payload.data.query is required' };

  const fieldName = extractSubscriptionField(query);
  if (!fieldName) return { error: 'no subscription field found in query' };
  if (!TOPIC_TARGET_KEY.hasOwnProperty(fieldName)) {
    return { error: `unknown subscription field: ${fieldName}` };
  }

  const argName = TOPIC_TARGET_KEY[fieldName];
  let target;
  if (argName === null) {
    // broadcast
    target = GLOBAL_TOPIC;
  } else {
    // 1. Try the inline literal in the query.
    target = extractFirstArgValue(query, fieldName, argName);
    // 2. Fall back to variables[argName].
    if (target == null && variables && variables[argName] != null) {
      target = String(variables[argName]);
    }
    if (target == null || target === '') {
      return { error: `subscription "${fieldName}" requires argument "${argName}"` };
    }
  }

  return { topic: fieldName, target: String(target), identity };
}

/**
 * Handle one client frame.
 *
 * Returns a list of side effects the transport should perform, e.g. { close: true }
 * or { close: false }. This keeps the protocol module synchronous and testable.
 *
 * State transitions:
 *   - Before connection_init: any frame → send connection_error and close.
 *   - connection_init → ack (only once)
 *   - start: validates, subscribes, pumps events into send()
 *   - stop: cancels the matching subscription
 *   - ka: echo back
 *   - any other: send error frame, keep connection open
 */
function handleClientMessage(state, raw, opts = {}) {
  if (state.closed) return { close: true };

  // Allow transports that wire `send` later (e.g. TCB WS trigger) to inject
  // it per-frame. The state-bound send still wins for the HTTP-server path.
  if (opts.send && state._send !== opts.send) {
    state._sendOverride = opts.send;
  }
  const parsed = parseFrame(raw);
  if (parsed.error) {
    sendFrame(state, { type: 'connection_error', payload: { message: parsed.error } });
    return { close: true };
  }
  const frame = parsed.frame;

  switch (frame.type) {
    case 'connection_init': {
      if (state.initialized) {
        sendFrame(state, { type: 'connection_error', payload: { message: 'duplicate connection_init' } });
        return { close: true };
      }
      state.initialized = true;
      sendFrame(state, { type: 'connection_ack' });
      return { close: false };
    }

    case 'start': {
      if (!state.initialized) {
        sendFrame(state, { type: 'connection_error', payload: { message: 'start before connection_ack' } });
        return { close: true };
      }
      const id = frame.id;
      if (!id || typeof id !== 'string') {
        sendFrame(state, { type: 'error', id, payload: [{ message: 'start requires id' }] });
        return { close: false };
      }
      if (state.subscriptions.has(id)) {
        sendFrame(state, { type: 'error', id, payload: [{ message: `duplicate subscription id: ${id}` }] });
        return { close: false };
      }
      if (state.subscriptions.size >= MAX_SUBSCRIPTIONS_PER_CONN) {
        sendFrame(state, { type: 'error', id, payload: [{ message: `too many subscriptions (limit ${MAX_SUBSCRIPTIONS_PER_CONN})` }] });
        return { close: false };
      }

      const r = resolveStartTarget(frame.payload, state.identity);
      if (r.error) {
        sendFrame(state, { type: 'error', id, payload: [{ message: r.error }] });
        return { close: false };
      }

      const sub = { topic: r.topic, target: r.target, identity: r.identity, id };
      state.subscriptions.set(id, sub);
      sendFrame(state, { type: 'start_ack', id });

      // Notify external bridge (e.g. WS server) of new subscription.
      // When state.onStart is provided, the WS server takes over bus subscription
      // via for-await-of so events flow through the same pub/sub pipeline.
      // When state.onStart is absent (standalone test), we subscribe here.
      if (state.onStart) {
        state.onStart(r.topic, id, r.target);
      } else {
        const ctx = { identity: r.identity };
        let iterator;
        try { iterator = getBus(opts).subscribe(r.topic, r.target, ctx); }
        catch (e) {
          sendFrame(state, { type: 'error', id, payload: [{ message: `subscribe failed: ${e.message}` }] });
          state.subscriptions.delete(id);
          return { close: false };
        }
        sub.iterator = iterator;
        sub.pump = pumpSubscription(state, sub).catch((e) => {
          state.log(`[ws:${state.connectionId}] pump crashed: ${e.message}`);
        });
      }
      return { close: false };
    }

    case 'stop': {
      const id = frame.id;
      const sub = state.subscriptions.get(id);
      if (sub) {
        const topic = sub.topic;
        state.subscriptions.delete(id);
        Promise.resolve(sub.iterator?.return?.()).catch(() => {});
        state.onStop?.(topic);
      }
      // AppSync emits no `complete` frame for stop — silent cleanup.
      return { close: false };
    }

    case 'ka': {
      sendFrame(state, { type: 'ka' });
      return { close: false };
    }

    case 'connection_terminate': {
      // Signal all active pumps to stop
      for (const [id, sub] of state.subscriptions) {
        state.onStop?.(sub.topic);
        Promise.resolve(sub.iterator?.return?.()).catch(() => {});
      }
      state.subscriptions.clear();
      // AppSync sends no acknowledgement — close transport immediately
      return { close: true };
    }

    default: {
      sendFrame(state, { type: 'error', id: frame.id, payload: [{ message: `unknown frame type: ${frame.type}` }] });
      return { close: false };
    }
  }
}

/**
 * Background pump: drain bus events for one subscription and emit `data` frames.
 *
 * Mirrors the AppSync wire shape exactly:
 *   { type: 'data', id: <subId>, payload: { data: { <field>: <payload> } } }
 *
 * Cancellation:
 *   - When `iterator.return()` is called (stop frame or connection close), the
 *     pump's `next()` resolves with { done: true }, and we exit cleanly.
 *   - If send fails, the transport will close the connection and clean us up.
 */
async function pumpSubscription(state, sub) {
  try {
    while (!state.closed) {
      const { value, done } = await sub.iterator.next();
      if (done) return;
      // AppSync wraps the inner value: { payload: { data: { <field>: <value> } } }
      sendFrame(state, {
        type: 'data',
        id: sub.id,
        payload: { data: { [sub.topic]: value } },
      });
    }
  } catch (e) {
    sendFrame(state, {
      type: 'error',
      id: sub.id,
      payload: [{ message: e.message }],
    });
  }
}

/**
 * Tear down all subscriptions on a connection.
 *
 * Idempotent. Safe to call from the transport `close` handler.
 */
function closeConnection(state) {
  if (state.closed) return;
  state.closed = true;
  for (const [id, sub] of state.subscriptions) {
    try { Promise.resolve(sub.iterator?.return?.()); } catch { /* ignore */ }
    state.subscriptions.delete(id);
  }
}

module.exports = {
  // state factory + lifecycle
  createConnectionState,
  handleClientMessage,
  closeConnection,
  // exported for tests
  parseFrame,
  extractSubscriptionField,
  extractFirstArgValue,
  resolveStartTarget,
  // shared with SSE bridge (kept here for symmetry; re-exported from ws-bridge-push.js too)
  TOPIC_TARGET_KEY,
  GLOBAL_TOPIC,
  MAX_SUBSCRIPTIONS_PER_CONN,
  MAX_FRAME_BYTES,
};
