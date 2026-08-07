/**
 * P2.8 — Subscription publish-side triggers.
 *
 * Each function here is a thin "publish-only" mutation: it routes the payload
 * through the in-process event-bus to the matching subscription topic, with no
 * database side-effect. They live in their own module so the business domains
 * (cn-jobs / cn-capabilities / cn-scene) stay free of "pure publish" code.
 *
 * Topic map (kept in sync with `resolvers/subscriptions.js`):
 *   onPuzzleReceived          -> '__global__'    (broadcast)
 *   onPuzzleResultReceived    -> input.pzid
 *   onLongLLMTaskComplete     -> input.id
 *   onStoryUpdate             -> input.acctSiteID
 *   onSceneComplete           -> input.request_id
 *   onAgentSceneEvent         -> input.acctSiteID
 *
 * Authorization:
 *   These mutations pass through the GraphQL context identity unchanged; the
 *   subscription resolver in `resolvers/subscriptions.js` carries the identity
 *   forward, and the existing `event-bus.js` publish path is fire-and-forget. A
 *   later ACL layer can add per-topic owner checks before `bus.publish`.
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
