/**
 * Type-level GraphQL resolvers.
 *
 * The bigint / camelCase mappings below exist because Prisma stores some columns
 * as BigInt and the GraphQL schema exposes them as Int; a few legacy columns
 * are stored under snake_case names but surfaced as camelCase.
 */

module.exports = {
  AgentEndpoint: { lastSeen: (value) => Number(value.lastSeen) },
  Vehicle: { uptimeSeconds: (value) => value.uptimeSeconds == null ? null : Number(value.uptimeSeconds) },
  WanChatMessage: {
    chatID: (value) => value.chatId,
    timestamp: (value) => value.timestamp?.toISOString?.() || String(value.timestamp || ''),
  },
  LongLLMTaskResult: {
    acctSiteID: (value) => value.acctSiteId,
    agentID: (value) => value.agentId,
    workType: (value) => value.workType,
    taskID: (value) => value.taskId,
    timestamp: (value) => value.updatedAt?.toISOString?.() || String(value.updatedAt || ''),
  },
};