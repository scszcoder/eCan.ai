/**
 * P2.8 — Subscription publish-side resolvers.
 *
 * Each resolver wires a `publish*` mutation from `services/cn-publishers.js`.
 * The mutation delegates to the event-bus; no database side-effect.
 */

const {
  publishPuzzle,
  publishPuzzleResult,
  publishLongLLMTaskComplete,
  publishStoryUpdate,
  publishSceneComplete,
  publishAgentSceneEvent,
} = require('../services/cn-publishers');

module.exports = {
  Mutation: {
    publishPuzzle: (_, { input }, context) => publishPuzzle(context.prisma, context.identity, input),
    publishPuzzleResult: (_, { input }, context) => publishPuzzleResult(context.prisma, context.identity, input),
    publishLongLLMTaskComplete: (_, { input }, context) => publishLongLLMTaskComplete(context.prisma, context.identity, input),
    publishStoryUpdate: (_, { input }, context) => publishStoryUpdate(context.prisma, context.identity, input),
    publishSceneComplete: (_, { input }, context) => publishSceneComplete(context.prisma, context.identity, input),
    publishAgentSceneEvent: (_, { input }, context) => publishAgentSceneEvent(context.prisma, context.identity, input),
  },
};
