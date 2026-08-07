/**
 * Relation resolvers (Query + Mutation): agent↔skill, agent↔task, agent↔org,
 * and the intl-compatible relations layer (compat/cn-relations).
 *
 * The typed AgentSkillRel/AgentTaskRel/AgentOrgRel tables own ownership data;
 * the intl compat layer is a parallel API for legacy clients.
 */

const { assertOwnedAgent } = require('../context-helpers');
const { queryRelation, removeRelations, upsertRelations } = require('../compat/cn-relations');

function queryAgentSkillRels(_, { input }, { prisma, identity }) {
  return prisma.agentSkillRel.findMany({
    where: {
      ...(input?.agentId && { agentId: input.agentId }),
      ...(input?.skillId && { skillId: input.skillId }),
      agent: { owner: identity.sub },
    },
  });
}

function queryAgentTaskRels(_, { input }, { prisma, identity }) {
  return prisma.agentTaskRel.findMany({
    where: {
      ...(input?.agentId && { agentId: input.agentId }),
      ...(input?.taskId && { taskId: input.taskId }),
      agent: { owner: identity.sub },
    },
  });
}

function queryAgentOrgRels(_, { input }, { prisma, identity }) {
  return prisma.agentOrgRel.findMany({
    where: {
      ...(input?.agentId && { agentId: input.agentId }),
      ...(input?.orgId && { orgId: input.orgId }),
      agent: { owner: identity.sub },
    },
  });
}

async function addAgentSkillRels(_, { input }, { prisma, identity }) {
  for (const item of input) {
    await assertOwnedAgent(prisma, identity, item.agentId);
    await prisma.agentSkillRel.upsert({
      where: { agentId_skillId: { agentId: item.agentId, skillId: item.skillId } },
      create: {
        agentId: item.agentId, skillId: item.skillId,
        proficiencyLevel: item.proficiencyLevel || 0,
        experiencePoints: item.experiencePoints || 0,
        certificationLevel: item.certificationLevel || 0,
        usageCount: item.usageCount || 0,
        successRate: item.successRate || 0,
        lastUsed: item.lastUsed ? new Date(item.lastUsed) : null,
        status: item.status || 'active',
        isFavorite: item.isFavorite ?? false,
        priority: item.priority || 0,
        config: item.config || {},
      },
      update: {
        proficiencyLevel: item.proficiencyLevel,
        experiencePoints: item.experiencePoints,
        certificationLevel: item.certificationLevel,
        usageCount: item.usageCount,
        successRate: item.successRate,
        lastUsed: item.lastUsed ? new Date(item.lastUsed) : null,
        status: item.status,
        isFavorite: item.isFavorite,
        priority: item.priority,
        config: item.config,
      },
    });
  }
  return { success: true };
}

async function removeAgentSkillRels(_, { input }, { prisma, identity }) {
  for (const item of input) {
    if (item.agentId) await assertOwnedAgent(prisma, identity, item.agentId);
    if (item.id) {
      await prisma.agentSkillRel.deleteMany({ where: { id: item.id, agent: { owner: identity.sub } } });
    } else if (item.agentId && item.skillId) {
      await prisma.agentSkillRel.delete({ where: { agentId_skillId: { agentId: item.agentId, skillId: item.skillId } } });
    }
  }
  return { success: true };
}

async function addAgentTaskRels(_, { input }, { prisma, identity }) {
  for (const item of input) {
    await assertOwnedAgent(prisma, identity, item.agentId);
    await prisma.agentTaskRel.upsert({
      where: { agentId_taskId: { agentId: item.agentId, taskId: item.taskId } },
      create: {
        agentId: item.agentId, taskId: item.taskId,
        vehicleId: item.vehicleId,
        status: item.status || 'assigned',
        priority: item.priority || 0, progress: item.progress || 0,
        scheduledStart: item.scheduledStart ? new Date(item.scheduledStart) : null,
        actualStart: item.actualStart ? new Date(item.actualStart) : null,
        estimatedEnd: item.estimatedEnd ? new Date(item.estimatedEnd) : null,
        actualEnd: item.actualEnd ? new Date(item.actualEnd) : null,
        result: item.result || {}, errorMessage: item.errorMessage, logs: item.logs,
        cpuUsage: item.cpuUsage, memoryUsage: item.memoryUsage,
        executionTime: item.executionTime,
        executionContext: item.executionContext || {},
        retryCount: item.retryCount || 0, maxRetries: item.maxRetries || 3,
      },
      update: {
        vehicleId: item.vehicleId,
        status: item.status, priority: item.priority, progress: item.progress,
        scheduledStart: item.scheduledStart ? new Date(item.scheduledStart) : undefined,
        actualStart: item.actualStart ? new Date(item.actualStart) : undefined,
        estimatedEnd: item.estimatedEnd ? new Date(item.estimatedEnd) : undefined,
        actualEnd: item.actualEnd ? new Date(item.actualEnd) : undefined,
        result: item.result, errorMessage: item.errorMessage, logs: item.logs,
        cpuUsage: item.cpuUsage, memoryUsage: item.memoryUsage,
        executionTime: item.executionTime, executionContext: item.executionContext,
        retryCount: item.retryCount, maxRetries: item.maxRetries,
      },
    });
  }
  return { success: true };
}

async function removeAgentTaskRels(_, { input }, { prisma, identity }) {
  for (const item of input) {
    if (item.agentId) await assertOwnedAgent(prisma, identity, item.agentId);
    if (item.id) {
      await prisma.agentTaskRel.deleteMany({ where: { id: item.id, agent: { owner: identity.sub } } });
    } else if (item.agentId && item.taskId) {
      await prisma.agentTaskRel.delete({ where: { agentId_taskId: { agentId: item.agentId, taskId: item.taskId } } });
    }
  }
  return { success: true };
}

async function addAgentOrgRels(_, { input }, { prisma, identity }) {
  for (const item of input) {
    await assertOwnedAgent(prisma, identity, item.agentId);
    await prisma.agentOrgRel.upsert({
      where: { agentId_orgId: { agentId: item.agentId, orgId: item.orgId } },
      create: {
        agentId: item.agentId, orgId: item.orgId, role: item.role,
        accessLevel: item.accessLevel || 'member',
        status: item.status || 'active', permissions: item.permissions || [],
        joinDate: item.joinDate ? new Date(item.joinDate) : null,
        leaveDate: item.leaveDate ? new Date(item.leaveDate) : null,
      },
      update: {
        role: item.role, accessLevel: item.accessLevel,
        status: item.status, permissions: item.permissions,
        joinDate: item.joinDate ? new Date(item.joinDate) : undefined,
        leaveDate: item.leaveDate ? new Date(item.leaveDate) : undefined,
      },
    });
  }
  return { success: true };
}

async function removeAgentOrgRels(_, { input }, { prisma, identity }) {
  for (const item of input) {
    if (item.agentId) await assertOwnedAgent(prisma, identity, item.agentId);
    if (item.id) {
      await prisma.agentOrgRel.deleteMany({ where: { id: item.id, agent: { owner: identity.sub } } });
    } else if (item.agentId && item.orgId) {
      await prisma.agentOrgRel.delete({ where: { agentId_orgId: { agentId: item.agentId, orgId: item.orgId } } });
    }
  }
  return { success: true };
}

const UPDATE_DELEGATES = {
  updateAgentSkillRels: addAgentSkillRels,
  updateAgentTaskRels: addAgentTaskRels,
  updateAgentOrgRels: addAgentOrgRels,
};

module.exports = {
  Query: {
    queryAgentSkillRels, queryAgentTaskRels, queryAgentOrgRels,
    queryAgentSkillRelations: (_, args, context) => queryRelation(context.prisma, context.identity, 'AgentSkill', args),
    getAgentSkillRelations: (_, args, context) => queryRelation(context.prisma, context.identity, 'AgentSkill', args),
    queryAgentTaskRelations: (_, args, context) => queryRelation(context.prisma, context.identity, 'AgentTask', args),
    getAgentTaskRelations: (_, args, context) => queryRelation(context.prisma, context.identity, 'AgentTask', args),
    queryAgentToolRelations: (_, args, context) => queryRelation(context.prisma, context.identity, 'AgentTool', args),
    getAgentToolRelations: (_, args, context) => queryRelation(context.prisma, context.identity, 'AgentTool', args),
    querySkillToolRelations: (_, args, context) => queryRelation(context.prisma, context.identity, 'SkillTool', args),
    getSkillToolRelations: (_, args, context) => queryRelation(context.prisma, context.identity, 'SkillTool', args),
    querySkillKnowledgeRelations: (_, args, context) => queryRelation(context.prisma, context.identity, 'SkillKnowledge', args),
    getSkillKnowledgeRelations: (_, args, context) => queryRelation(context.prisma, context.identity, 'SkillKnowledge', args),
    queryTaskSkillRelations: (_, args, context) => queryRelation(context.prisma, context.identity, 'TaskSkill', args),
    getTaskSkillRelations: (_, args, context) => queryRelation(context.prisma, context.identity, 'TaskSkill', args),
  },
  Mutation: {
    addAgentSkillRels,
    removeAgentSkillRels,
    ...Object.fromEntries(Object.entries(UPDATE_DELEGATES).map(([k, fn]) => [k, (_, args, ctx) => fn(_, args, ctx)])),
    addAgentTaskRels,
    removeAgentTaskRels,
    addAgentOrgRels,
    removeAgentOrgRels,

    addAgentSkillRelations: (_, { input }, context) => upsertRelations(context.prisma, context.identity, 'AgentSkill', input),
    updateAgentSkillRelations: (_, { input }, context) => upsertRelations(context.prisma, context.identity, 'AgentSkill', input),
    removeAgentSkillRelations: (_, { input }, context) => removeRelations(context.prisma, context.identity, 'AgentSkill', input),
    addAgentTaskRelations: (_, { input }, context) => upsertRelations(context.prisma, context.identity, 'AgentTask', input),
    updateAgentTaskRelations: (_, { input }, context) => upsertRelations(context.prisma, context.identity, 'AgentTask', input),
    removeAgentTaskRelations: (_, { input }, context) => removeRelations(context.prisma, context.identity, 'AgentTask', input),
    addAgentToolRelations: (_, { input }, context) => upsertRelations(context.prisma, context.identity, 'AgentTool', input),
    updateAgentToolRelations: (_, { input }, context) => upsertRelations(context.prisma, context.identity, 'AgentTool', input),
    removeAgentToolRelations: (_, { input }, context) => removeRelations(context.prisma, context.identity, 'AgentTool', input),
    addSkillToolRelations: (_, { input }, context) => upsertRelations(context.prisma, context.identity, 'SkillTool', input),
    updateSkillToolRelations: (_, { input }, context) => upsertRelations(context.prisma, context.identity, 'SkillTool', input),
    removeSkillToolRelations: (_, { input }, context) => removeRelations(context.prisma, context.identity, 'SkillTool', input),
    addSkillKnowledgeRelations: (_, { input }, context) => upsertRelations(context.prisma, context.identity, 'SkillKnowledge', input),
    updateSkillKnowledgeRelations: (_, { input }, context) => upsertRelations(context.prisma, context.identity, 'SkillKnowledge', input),
    removeSkillKnowledgeRelations: (_, { input }, context) => removeRelations(context.prisma, context.identity, 'SkillKnowledge', input),
    addTaskSkillRelations: (_, { input }, context) => upsertRelations(context.prisma, context.identity, 'TaskSkill', input),
    updateTaskSkillRelations: (_, { input }, context) => upsertRelations(context.prisma, context.identity, 'TaskSkill', input),
    removeTaskSkillRelations: (_, { input }, context) => removeRelations(context.prisma, context.identity, 'TaskSkill', input),
  },
};