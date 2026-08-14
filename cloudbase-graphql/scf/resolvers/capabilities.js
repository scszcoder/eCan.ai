/**
 * Capability resolvers (Query + Mutation):
 *   AgentEndpoint, A2AMessage, RagDocument, LongLlmTask, SkillEditorChat.
 */

const {
  createChatSession, deleteAgentEndpoint, endLongLlmTask, getChatHistory, getChatSessions,
  publishSkillEditorEvent, queryAgentEndpoints, registerRagDocuments,
  sendA2AMessage, sendChatMessage, setChatState, startLongLlmTask, upsertAgentEndpoint,
} = require('../services/cn-capabilities');
const { getLongLlmTask } = require('../services/cn-capabilities');

module.exports = {
  Query: {
    queryAgentEndpoints: (_, { org, limit, offset }, context) =>
      queryAgentEndpoints(context.prisma, context.identity, org, { limit, offset }),
    getLongLLMTask: (_, { id }, context) => getLongLlmTask(context.prisma, context.identity, id),
    getSkillEditorChatSessions: (_, { userId }, context) => getChatSessions(context.prisma, context.identity, userId),
    getSkillEditorChatHistory: (_, { sessionId, limit, offset }, context) =>
      getChatHistory(context.prisma, context.identity, sessionId, limit, offset),
  },
  Mutation: {
    upsertAgentEndpoint: (_, { input }, context) => upsertAgentEndpoint(context.prisma, context.identity, input),
    deleteAgentEndpoint: (_, { id }, context) => deleteAgentEndpoint(context.prisma, context.identity, id),
    sendA2AMessage: (_, { input }, context) => sendA2AMessage(context.prisma, context.identity, input),
    reqRAGStore: (_, { input }, context) => registerRagDocuments(context.prisma, context.identity, input),
    startLongLLMTask: (_, { task_input }, context) => startLongLlmTask(context.prisma, context.identity, task_input),
    endLongLLMTask: (_, { input }, context) => endLongLlmTask(context.prisma, context.identity, input),
    createSkillEditorChatSession: (_, { input }, context) => createChatSession(context.prisma, context.identity, input),
    sendSkillEditorChatMessage: (_, { input }, context) => sendChatMessage(context.prisma, context.identity, input),
    cancelSkillEditorChatGeneration: (_, { sessionId }, context) =>
      setChatState(context.prisma, context.identity, sessionId, 'cancelled'),
    deleteSkillEditorChatSession: (_, { sessionId }, context) =>
      setChatState(context.prisma, context.identity, sessionId, 'deleted', true),
    publishSkillEditorStreamEvent: (_, { input }, context) =>
      publishSkillEditorEvent(context.prisma, context.identity, input),
  },
};