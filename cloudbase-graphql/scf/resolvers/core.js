/**
 * Skill editor events, getAllMine, and cloud task launch.
 */

const { GraphQLError } = require('graphql');

function getSkillEditorEvents(_, { sessionId, since }, { prisma, identity }) {
  return prisma.skillEditorEvent.findMany({
    where: {
      owner: identity.sub,
      ...(sessionId && { sessionId }),
      ...(since && { timestamp: { gt: new Date(since) } }),
    },
    orderBy: { timestamp: 'desc' },
    take: 100,
  });
}

async function getAllMine(_, { owner }, { prisma, identity }) {
  const userId = require('../auth').authenticatedOwner(identity, owner);
  const [agents, skills, tasks, vehicles, orgs, prompts, avatars, knowledges, tools, settings, accountData] = await Promise.all([
      prisma.agent.findMany({ where: { owner: userId }, orderBy: { createdAt: 'desc' }, take: 50 }),
      prisma.agentSkill.findMany({ where: { owner: userId }, orderBy: { createdAt: 'desc' }, take: 50 }),
      prisma.agentTask.findMany({ where: { owner: userId }, orderBy: { createdAt: 'desc' }, take: 50 }),
      prisma.vehicle.findMany({ where: { owner: userId }, orderBy: { createdAt: 'desc' }, take: 50 }),
      prisma.org.findMany({ orderBy: { sortOrder: 'asc' }, take: 50 }),
      prisma.prompt.findMany({ where: { owner: userId }, orderBy: { createdAt: 'desc' }, take: 50 }),
      prisma.avatar.findMany({ where: { owner: userId }, orderBy: { createdAt: 'desc' }, take: 50 }),
      prisma.agentKnowledge.findMany({ where: { owner: userId }, orderBy: { createdAt: 'desc' }, take: 50 }),
      prisma.agentTool.findMany({ where: { owner: userId }, orderBy: { createdAt: 'desc' }, take: 50 }),
      prisma.setting.findMany({ where: { owner: { in: [userId, '__global__'] } } }),
      require('../compat/cn-accounts').queryMine(prisma, identity),
    ]);
    return { agents, skills, tasks, vehicles, orgs, prompts, avatars, knowledges, tools, settings, ...accountData };
}

async function addSkillEditorEvent(_, { input }, { prisma, identity }) {
  const event = await prisma.skillEditorEvent.create({
    data: {
      owner: require('../auth').authenticatedOwner(identity, input.owner),
      sessionId: input.sessionId,
      flowgramId: input.flowgramId,
      eventType: input.eventType,
      payload: input.payload || {},
      timestamp: input.timestamp ? new Date(input.timestamp) : new Date(),
    },
  });
  // The Prisma model uses `eventId` (not `id`) as the primary key, so spread
  // it back so the GraphQL SkillEditorEvent eventId field resolves.
  return { eventId: event.eventId, owner: event.owner, sessionId: event.sessionId, flowgramId: event.flowgramId, eventType: event.eventType, payload: event.payload, timestamp: event.timestamp.toISOString() };
}

async function runCloudTasks(_, { input }, { prisma, identity, getScheduler }) {
  if (!Array.isArray(input) || input.length < 1 || input.length > 20) {
    throw new GraphQLError('runCloudTasks accepts 1-20 tasks');
  }
  const items = []; const runIds = {};
    for (const item of input) {
      try {
        const suppliedTaskId = item?.task_id ? String(item.task_id) : null;
        const task = await prisma.agentTask.findFirst({
          where: suppliedTaskId
            ? { id: suppliedTaskId, owner: identity.sub }
            : { name: String(item?.task_name || ''), owner: identity.sub },
        });
        if (!task) throw new Error('Task not found');
        const options = typeof item.options === 'string' ? JSON.parse(item.options) : (item.options || {});
        const runId = await getScheduler().launch({ owner: identity.sub, taskId: task.id, options });
        items.push({ task_id: task.id, run_id: runId, success: true }); runIds[task.id] = runId;
      } catch (error) {
        items.push({ task_id: item?.task_id || null, run_id: null, success: false, error: error.message });
      }
    }
    return JSON.stringify({ items, run_ids: runIds });
}

module.exports = {
  Query: { getSkillEditorEvents, getAllMine },
  Mutation: { addSkillEditorEvent, runCloudTasks },
};