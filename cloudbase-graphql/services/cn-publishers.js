/**
 * P2.8 — Subscription publish-side triggers (CN, graphql-ws topology).
 *
 * Each mutation here routes the payload through the in-process event-bus
 * to the matching subscription topic. The WS bridge (services/ws-bridge-push.js)
 * forwards every publish to the independent `ecan-graphql-ws` cloud function
 * via HTTP POST, which then delivers to all WS clients that subscribed to the
 * matching (topic, target) via the graphql-ws `start` frame.
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
 *   ecan-graphql-api instances; a WS client connected to instance B will
 *   not receive a publish from instance A. The `services/ws-bridge-push.js`
 *   module attached via `attachWsBridge()` in `index.js` forwards each
 *   publish to the independent `ecan-graphql-ws` function via HTTP POST,
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
  const siteID = String(input.acctSiteID || '');
  if (!siteID) throw new Error('publishLongLLMTaskComplete: acctSiteID is required');
  const payload = { ...input, id, acctSiteID: siteID };
  bus.publish('onLongLLMTaskComplete', siteID, payload);
  return payload;
}

function publishStoryUpdate(_prisma, _identity, input) {
  if (!input.acctSiteID) throw new Error('publishStoryUpdate: acctSiteID is required');
  bus.publish('onStoryUpdate', String(input.acctSiteID), input);
  return input;
}

function publishSceneComplete(_prisma, _identity, input) {
  const requestId = String(input.request_id || '');
  const siteID = String(input.acctSiteID || '');
  if (!siteID) throw new Error('publishSceneComplete: acctSiteID is required');
  if (!requestId) throw new Error('publishSceneComplete: request_id is required');
  bus.publish('onSceneComplete', siteID, input);
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