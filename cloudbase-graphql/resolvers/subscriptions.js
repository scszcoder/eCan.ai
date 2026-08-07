/**
 * GraphQL Subscription resolvers.
 *
 * Each field delegates to the in-process event-bus. The resolver argument
 * (channelId / runId / sessionId / owner / pzid / id / request_id / acctSiteID / runID)
 * is the topic "target" — events are routed by `(topic, target)`.
 *
 * Authorization:
 *   The `identity` from the GraphQL context is attached to the subscription. The
 *   publish path can later reject cross-owner delivery by comparing `payload.owner`
 *   to `handler.ctx.identity.sub`.
 */

const bus = require('../event-bus');

const TOPIC = {
  onMessageReceived: 'onMessageReceived',
  onA2AMessageReceived: 'onA2AMessageReceived',
  onAccountNotification: 'onAccountNotification',
  onSkillEditorStreamEvent: 'onSkillEditorStreamEvent',
  onPassiveCommand: 'onPassiveCommand',
  onPassiveHello: 'onPassiveHello',
  onPassiveStepResult: 'onPassiveStepResult',
  onPuzzleReceived: 'onPuzzleReceived',
  onPuzzleResultReceived: 'onPuzzleResultReceived',
  onLongLLMTaskComplete: 'onLongLLMTaskComplete',
  onSceneComplete: 'onSceneComplete',
  onAgentSceneEvent: 'onAgentSceneEvent',
  onStoryUpdate: 'onStoryUpdate',
  onTaskStatus: 'onTaskStatus',
};

/**
 * Build a resolver whose subscription iterates the event-bus for (topic, target).
 * The target extractor is called with resolver args (channelId, runId, …).
 */
function stream(topic, extractTarget) {
  return {
    subscribe: (_, args, ctx) => bus.subscribe(topic, extractTarget(args), ctx),
    // The "resolve" callback maps a published payload to the GraphQL field type.
    // We return the payload directly; field-level coercion in graphql-yoga maps
    // each field's payload to the matching GraphQL field shape.
    resolve: (payload) => payload,
  };
}

module.exports = {
  Subscription: {
    onMessageReceived: stream(TOPIC.onMessageReceived, (a) => a.channelId),
    onA2AMessageReceived: stream(TOPIC.onA2AMessageReceived, (a) => a.channelId),
    onAccountNotification: stream(TOPIC.onAccountNotification, (a) => a.owner),
    onSkillEditorStreamEvent: stream(TOPIC.onSkillEditorStreamEvent, (a) => a.sessionId),
    onPassiveCommand: stream(TOPIC.onPassiveCommand, (a) => a.runId),
    onPassiveHello: stream(TOPIC.onPassiveHello, (a) => a.runId),
    onPassiveStepResult: stream(TOPIC.onPassiveStepResult, (a) => a.runId),
    onPuzzleReceived: stream(TOPIC.onPuzzleReceived, () => '__global__'),
    onPuzzleResultReceived: stream(TOPIC.onPuzzleResultReceived, (a) => a.pzid),
    onLongLLMTaskComplete: stream(TOPIC.onLongLLMTaskComplete, (a) => a.id),
    onSceneComplete: stream(TOPIC.onSceneComplete, (a) => a.request_id),
    onAgentSceneEvent: stream(TOPIC.onAgentSceneEvent, (a) => a.acctSiteID),
    onStoryUpdate: stream(TOPIC.onStoryUpdate, (a) => a.acctSiteID),
    onTaskStatus: stream(TOPIC.onTaskStatus, (a) => a.runID),
  },
  // Re-export the topic map so publishers can `require` a single source of truth.
  TOPIC,
};