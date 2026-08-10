/**
 * In-process Pub/Sub for GraphQL Subscriptions.
 *
 * Why in-process:
 *   - SCF hands each function instance a fresh process. A single GraphQL API
 *     function owns its own connection pool, so most publish/subscribe flows
 *     are intra-instance. The `services/ws-bridge-push.js` module attaches
 *     a cross-instance bridge to this bus; every publish() is forwarded to
 *     the independent `ecan-graphql-ws` function via HTTP POST, which then
 *     distributes to its own in-process WS clients (one per `start` frame).
 *     This mirrors the AWS AppSync appsync-api ↔ appsync-realtime-api topology.
 *
 * Channel naming convention:
 *   "<topic>:<target>" — topic is one of the 14 subscription names; target is
 *   the resolver argument (channelId / runId / sessionId / owner / etc.).
 *   "*" suffix is supported for cross-cutting topics (e.g. "puzzle:*").
 *
 * Backpressure / cancellation:
 *   Subscribers return an async iterator. When the underlying WS closes or
 *   graphql-yoga tears the subscription down, the iterator's `return()` is
 *   invoked; we then remove the listener so the Set does not leak.
 *
 * Failure isolation:
 *   Per-subscriber dispatch is wrapped in try/catch. A bad handler does not
 *   poison the bus or starve other subscribers.
 */

const subscriptions = new Map(); // channel -> Set<{ queue, signal }>

function channelKey(topic, target) {
  return `${topic}:${String(target)}`;
}

function ensureChannel(key) {
  let set = subscriptions.get(key);
  if (!set) { set = new Set(); subscriptions.set(key, set); }
  return set;
}

/**
 * Subscribe to (topic, target). Returns an async iterator that yields events.
 * @param {string} topic       Subscription field name, e.g. "onSkillEditorStreamEvent"
 * @param {string} target      Resolver argument, e.g. sessionId / channelId / owner
 * @param {object} ctx         Resolver context (carries identity for filtering)
 */
function subscribe(topic, target, ctx) {
  const key = channelKey(topic, target);
  const set = ensureChannel(key);
  const handler = { ctx, queue: [], signal: { closed: false }, resolvers: [] };
  set.add(handler);

  const iterator = {
    [Symbol.asyncIterator]() { return this; },
    next() {
      if (handler.signal.closed) return Promise.resolve({ value: undefined, done: true });
      if (handler.queue.length > 0) {
        return Promise.resolve({ value: handler.queue.shift(), done: false });
      }
      return new Promise((resolve) => handler.resolvers.push(resolve));
    },
    return() {
      handler.signal.closed = true;
      const subSet = subscriptions.get(key);
      if (subSet) {
        subSet.delete(handler);
        if (subSet.size === 0) subscriptions.delete(key);
      }
      // Resolve any pending next() so the consumer learns of the close.
      while (handler.resolvers.length) handler.resolvers.shift()({ value: undefined, done: true });
      return Promise.resolve({ value: undefined, done: true });
    },
    throw(err) {
      handler.signal.closed = true;
      const subSet = subscriptions.get(key);
      if (subSet) {
        subSet.delete(handler);
        if (subSet.size === 0) subscriptions.delete(key);
      }
      return Promise.reject(err);
    },
  };
  return iterator;
}

/**
 * Publish an event to all subscribers of (topic, target).
 * @param {string} topic
 * @param {string} target
 * @param {*} payload
 * @returns {number} number of subscribers that received the event
 */
function publish(topic, target, payload) {
  // Forward to the cross-instance bridge first (if attached). The bridge is the only
  // path for cross-instance delivery; in-process subscribers are handled below.
  if (bridge) {
    try { bridge({ topic, target, payload }); } catch { /* swallow */ }
  }

  const key = channelKey(topic, target);
  const set = subscriptions.get(key);
  if (!set || set.size === 0) return 0;
  let delivered = 0;
  for (const handler of Array.from(set)) {
    if (handler.signal.closed) continue;
    try {
      // Drain pending resolvers first — they were waiting for the next event,
      // so resolving them counts as a delivery. If no resolver is waiting,
      // queue the payload so the next iterator.next() picks it up.
      if (handler.resolvers.length > 0) {
        while (handler.resolvers.length) {
          handler.resolvers.shift()({ value: payload, done: false });
        }
      } else {
        handler.queue.push(payload);
      }
      delivered += 1;
    } catch (e) {
      // Swallow; failure of one subscriber must not poison the others.
      // Remove the bad handler so we don't keep failing.
      set.delete(handler);
    }
  }
  if (set.size === 0) subscriptions.delete(key);
  return delivered;
}

/**
 * Optional bridge for cross-instance broadcast. Attached from
 * `services/ws-bridge-push.js` once at startup; receives every
 * `bus.publish(topic, target, payload)` and forwards it to the independent
 * `ecan-graphql-ws` function via HTTP.
 *
 * @param {(payload: {topic: string, target: string, payload: any}) => void} push
 */
let bridge = null;
function attachBridge(push) { bridge = push; }
function detachBridge() { bridge = null; }
function getBridge() { return bridge; }

/**
 * Observability: how many distinct (topic, target) channels currently have listeners.
 */
function metrics() {
  const counts = {};
  for (const key of subscriptions.keys()) {
    counts[key] = subscriptions.get(key).size;
  }
  return { channels: subscriptions.size, counts, bridgeAttached: !!bridge };
}

/**
 * Drop everything. Used in tests.
 */
function reset() {
  for (const set of subscriptions.values()) {
    for (const handler of set) handler.signal.closed = true;
  }
  subscriptions.clear();
  bridge = null;
}

module.exports = {
  subscribe,
  publish,
  attachBridge,
  detachBridge,
  getBridge,
  metrics,
  reset,
  // exported for unit tests
  _channelKey: channelKey,
};