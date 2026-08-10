/**
 * P2.8 — Subscription publish-side triggers (CN, SSE 架构).
 *
 * Each mutation here routes the payload through the in-process event-bus
 * to the matching subscription topic. The SSE bridge (services/sse-bridge.js)
 * subscribes to the same bus and pushes events to connected SSE clients.
 *
 * Topic map (kept in sync with `resolvers/subscriptions.js`):
 *   onPuzzleReceived          -> '__global__'    (broadcast)
 *   onPuzzleResultReceived    -> input.pzid
 *   onLongLLMTaskComplete     -> input.id
 *   onStoryUpdate             -> input.acctSiteID
 *   onSceneComplete           -> input.request_id
 *   onAgentSceneEvent         -> input.acctSiteID
 *
 * Cross-instance delivery note:
 *   bus.publish only reaches in-process subscribers. SCF may run multiple
 *   ecan-graphql-api instances; an SSE client connected to instance B will
 *   not receive a publish from instance A. The `services/sse-bridge-push.js`
 *   module attached via `attachSseBridge()` in `index.js` forwards each
 *   publish to the independent `ecan-graphql-sse` function via HTTP POST,
 *   closing the cross-instance gap (mirrors AWS AppSync's
 *   appsync-api → appsync-realtime-api pub/sub).
 */

const bus = require('../event-bus');

function publishPuzzle(_prisma, _identity, input) {
  bus.publish('onPuzzleReceived', '__global__', input);
  return input;
}

function publishPuzzleResult(_prisma, _identity, input) {
  const pzid = String(input.pzid);
  bus.publish('onPuzzleResultReceived', pzid, input);
  return input;
}

function publishLongLLMTaskComplete(_prisma, _identity, input) {
  const id = String(input.id || input.taskID || 'unknown');
  const payload = { ...input, id };
  bus.publish('onLongLLMTaskComplete', id, payload);
  return payload;
}

function publishStoryUpdate(_prisma, _identity, input) {
  if (!input.acctSiteID) throw new Error('publishStoryUpdate: acctSiteID is required');
  bus.publish('onStoryUpdate', String(input.acctSiteID), input);
  return input;
}

function publishSceneComplete(_prisma, _identity, input) {
  const requestId = String(input.request_id || '');
  if (!requestId) throw new Error('publishSceneComplete: request_id is required');
  bus.publish('onSceneComplete', requestId, input);
  return input;
}

function publishAgentSceneEvent(_prisma, _identity, input) {
  if (!input.acctSiteID) throw new Error('publishAgentSceneEvent: acctSiteID is required');
  bus.publish('onAgentSceneEvent', String(input.acctSiteID), input);
  return input;
}

module.exports = {
  publishPuzzle,
  publishPuzzleResult,
  publishLongLLMTaskComplete,
  publishStoryUpdate,
  publishSceneComplete,
  publishAgentSceneEvent,
};