/**
 * eCan.ai CN 版本后端
 * GraphQL Yoga + Prisma + PostgreSQL (JSONB)
 *
 * 部署到腾讯云 SCF (Serverless Cloud Function)
 *
 * 架构：
 *   App/前端 → HTTP → 云函数 → PostgreSQL (JSONB)
 *
 * 本地开发：
 *   - 本地不需要直连数据库
 *   - 直接调用已部署的云函数 API
 *   - 或使用 curl/Postman 测试 API
 */

const { createYoga, createSchema } = require('graphql-yoga');
const { GraphQLError } = require('graphql');
const { PrismaClient } = require('@prisma/client');
const cloudbase = require('@cloudbase/node-sdk');
const { executeFileOps } = require('./storage/cos-file-ops');
const { TencentScheduler } = require('./scheduler/tencent-scheduler');
const { queryRelation, removeRelations, upsertRelations } = require('./compat/cn-relations');
const { queryEntity, queryOrganizations, removeEntities, saveEntities } = require('./compat/cn-entities');
const {
  createChatSession, deleteAgentEndpoint, endLongLlmTask, getChatHistory, getChatSessions,
  getLongLlmTask, publishSkillEditorEvent, queryAgentEndpoints, registerRagDocuments,
  sendA2AMessage, sendChatMessage, setChatState, startLongLlmTask, upsertAgentEndpoint,
} = require('./services/cn-capabilities');
const { getWanMessages, mutateApiKeys, queryApiKeys, queryLegacy, removeLegacy, saveLegacy, sendWanMessage } = require('./compat/cn-legacy');
const { confirmPuzzle, dequeueTasks, reportExternalSkill, reportVehicles, requestExternalSkill, requestPuzzle, requestTraining } = require('./services/cn-jobs');

// TCB 环境初始化（仅在云端生效）
let tcbApp = null;
if (process.env.TCB_REGION) {
  tcbApp = cloudbase.init({
    env: cloudbase.SYMBOL_CURRENT_ENV,
  });
}

// Prisma Client 单例
let prisma;
let scheduler;

function getScheduler() {
  if (!scheduler) scheduler = new TencentScheduler();
  return scheduler;
}

// 不安全认证仅在非生产环境启用（生产环境强制要求 Bearer token）
const ALLOW_INSECURE_AUTH = process.env.ALLOW_INSECURE_AUTH === 'true' && process.env.NODE_ENV !== 'production';

function authenticatedOwner(identity, requestedOwner) {
  if (!identity?.sub || identity.sub === 'anonymous') {
    throw new GraphQLError('Authentication required', {
      extensions: { code: 'UNAUTHENTICATED' },
    });
  }
  if (requestedOwner && requestedOwner !== identity.sub) {
    throw new GraphQLError('Cross-owner access is forbidden', {
      extensions: { code: 'FORBIDDEN' },
    });
  }
  return identity.sub;
}

async function resolveIdentity(request) {
  const authorization = request.headers.get('authorization') || '';
  const token = authorization.replace(/^Bearer\s+/i, '').trim();

  if (tcbApp && token) {
    try {
      const verified = await tcbApp.auth().verifyJwt(token);
      const sub = verified?.uid || verified?.openid || verified?.sub;
      if (sub) return { sub };
    } catch (error) {
      throw new GraphQLError('Invalid or expired access token', {
        extensions: { code: 'UNAUTHENTICATED' },
      });
    }
  }

  if (ALLOW_INSECURE_AUTH) {
    return { sub: request.headers.get('x-ecan-test-user') || 'local-development-user' };
  }

  throw new GraphQLError('Bearer token required', {
    extensions: { code: 'UNAUTHENTICATED' },
  });
}

async function assertOwnedAgent(prismaClient, identity, agentId) {
  const agent = await prismaClient.agent.findFirst({
    where: { id: agentId, owner: identity.sub },
    select: { id: true },
  });
  if (!agent) {
    throw new GraphQLError('Agent not found', { extensions: { code: 'FORBIDDEN' } });
  }
}

function getPrisma() {
  if (!prisma) {
    // 从环境变量读取 PostgreSQL 连接信息
    // 格式: postgresql://user:password@host:5432/database
    const connectionString = process.env.DATABASE_URL;

    if (!connectionString) {
      throw new Error('Missing DATABASE_URL environment variable');
    }

    prisma = new PrismaClient({
      log: process.env.NODE_ENV === 'development' ? ['query', 'error', 'warn'] : ['error'],
    });
  }
  return prisma;
}

// ============ GraphQL Resolvers ============

const resolvers = {
  AgentEndpoint: { lastSeen: (value) => Number(value.lastSeen) },
  Vehicle: { uptimeSeconds: (value) => value.uptimeSeconds == null ? null : Number(value.uptimeSeconds) },
  WanChatMessage: { chatID: (value) => value.chatId, timestamp: (value) => value.timestamp?.toISOString?.() || String(value.timestamp || '') },
  LongLLMTaskResult: {
    acctSiteID: (value) => value.acctSiteId,
    agentID: (value) => value.agentId,
    workType: (value) => value.workType,
    taskID: (value) => value.taskId,
    timestamp: (value) => value.updatedAt?.toISOString?.() || String(value.updatedAt || ''),
  },
  Query: {
    // Agents
    getAgents: (_, { input }, { prisma, identity }) => {
      return prisma.agent.findMany({
        where: {
          owner: authenticatedOwner(identity, input?.owner),
          ...(input?.id && { id: input.id }),
          ...(input?.name && { name: { contains: input.name, mode: 'insensitive' } }),
          ...(input?.status && { status: input.status }),
        },
        orderBy: { createdAt: 'desc' },
        take: 50,
      });
    },
    queryAgents: (_, { input }, { prisma, identity }) => resolvers.Query.getAgents(_, { input }, { prisma, identity }),

    // Skills
    getAgentSkills: (_, { input }, { prisma, identity }) => {
      return prisma.agentSkill.findMany({
        where: {
          owner: authenticatedOwner(identity, input?.owner),
          ...(input?.id && { id: input.id }),
          ...(input?.name && { name: { contains: input.name, mode: 'insensitive' } }),
        },
        orderBy: { createdAt: 'desc' },
        take: 50,
      });
    },
    queryAgentSkills: (_, { input }, { prisma, identity }) => resolvers.Query.getAgentSkills(_, { input }, { prisma, identity }),

    // Tasks
    getAgentTasks: (_, { input }, { prisma, identity }) => {
      return prisma.agentTask.findMany({
        where: {
          owner: authenticatedOwner(identity, input?.owner),
          ...(input?.id && { id: input.id }),
          ...(input?.status && { status: input.status }),
        },
        orderBy: { createdAt: 'desc' },
        take: 50,
      });
    },
    queryAgentTasks: (_, { input }, { prisma, identity }) => resolvers.Query.getAgentTasks(_, { input }, { prisma, identity }),

    // Vehicles
    getVehicles: (_, { input }, { prisma, identity }) => {
      return prisma.vehicle.findMany({
        where: {
          owner: authenticatedOwner(identity, input?.owner),
          ...(input?.id && { id: input.id }),
        },
        orderBy: { createdAt: 'desc' },
        take: 50,
      });
    },
    queryVehicles: (_, { input }, { prisma, identity }) => resolvers.Query.getVehicles(_, { input }, { prisma, identity }),

    // Orgs
    getOrgs: (_, { input }, { prisma }) => {
      return prisma.org.findMany({
        where: {
          ...(input?.id && { id: input.id }),
          ...(input?.name && { name: { contains: input.name, mode: 'insensitive' } }),
          ...(input?.orgType && { orgType: input.orgType }),
          ...(input?.status && { status: input.status }),
        },
        orderBy: [{ sortOrder: 'asc' }, { level: 'asc' }],
      });
    },
    queryOrgs: (_, { input }, { prisma }) => resolvers.Query.getOrgs(_, { input }, { prisma }),
    
    getOrgTree: async (_, { rootId }, { prisma }) => {
      const buildTree = async (parentId) => {
        const orgs = await prisma.org.findMany({
          where: parentId ? { parentId } : { parentId: null },
          orderBy: [{ sortOrder: 'asc' }, { level: 'asc' }],
        });
        return Promise.all(orgs.map(async (org) => ({
          id: org.id,
          name: org.name,
          description: org.description,
          orgType: org.orgType,
          level: org.level,
          parentId: org.parentId,
          sortOrder: org.sortOrder,
          status: org.status,
          settings: org.settings,
          children: await buildTree(org.id),
          agents: [],
        })));
      };
      const tree = await buildTree(rootId || null);
      return tree[0] || null;
    },

    getOrgAgentTree: async (_, { rootId }, { prisma }) => {
      const [orgs, agents] = await Promise.all([
        prisma.org.findMany({ orderBy: [{ sortOrder: 'asc' }, { level: 'asc' }] }),
        prisma.agent.findMany({ orderBy: { createdAt: 'desc' } }),
      ]);
      
      const buildTree = (parentId) => {
        return orgs
          .filter(o => o.parentId === parentId)
          .map(org => ({
            id: org.id,
            name: org.name,
            description: org.description,
            orgType: org.orgType,
            level: org.level,
            parentId: org.parentId,
            sortOrder: org.sortOrder,
            status: org.status,
            settings: org.settings,
            children: buildTree(org.id),
            agents: agents.filter(a => a.orgId === org.id),
          }));
      };
      
      const tree = buildTree(rootId || null);
      return tree[0] || null;
    },

    // Prompts
    getPrompts: (_, { owner }, { prisma, identity }) => {
      return prisma.prompt.findMany({
        where: { owner: authenticatedOwner(identity, owner) },
        orderBy: { createdAt: 'desc' },
      });
    },
    queryPrompts: (_, { input }, { prisma, identity }) => {
      return prisma.prompt.findMany({
        where: {
          owner: authenticatedOwner(identity, input?.owner),
        },
        orderBy: { createdAt: 'desc' },
      });
    },

    // Avatars
    getAvatars: (_, args, { prisma, identity }) => {
      return prisma.avatar.findMany({
        where: {
          owner: authenticatedOwner(identity, args?.owner),
          ...(args?.resourceType && { resourceType: args.resourceType }),
        },
        orderBy: { createdAt: 'desc' },
      });
    },
    queryAvatars: (_, { input }, { prisma, identity }) => resolvers.Query.getAvatars(_, { ...input }, { prisma, identity }),

    // Knowledges
    getAgentKnowledges: (_, args, { prisma, identity }) => {
      return prisma.agentKnowledge.findMany({
        where: {
          owner: authenticatedOwner(identity, args?.owner),
          ...(args?.name && { name: { contains: args.name, mode: 'insensitive' } }),
        },
        orderBy: { createdAt: 'desc' },
      });
    },
    queryAgentKnowledges: (_, { input }, { prisma, identity }) => resolvers.Query.getAgentKnowledges(_, input, { prisma, identity }),

    // Tools
    getAgentTools: (_, args, { prisma, identity }) => {
      return prisma.agentTool.findMany({
        where: {
          owner: authenticatedOwner(identity, args?.owner),
          ...(args?.name && { name: { contains: args.name, mode: 'insensitive' } }),
        },
        orderBy: { createdAt: 'desc' },
      });
    },
    queryAgentTools: (_, { input }, { prisma, identity }) => resolvers.Query.getAgentTools(_, input, { prisma, identity }),

    // Settings
    getSettings: (_, { ids, username }, { prisma, identity }) => {
      const owner = authenticatedOwner(identity, username);
      return prisma.setting.findMany({
        where: ids?.length 
          ? { id: { in: ids }, owner: { in: [owner, '__global__'] } }
          : { owner: { in: [owner, '__global__'] } },
      });
    },

    // Skill Editor Events
    getSkillEditorEvents: (_, { sessionId, since }, { prisma, identity }) => {
      return prisma.skillEditorEvent.findMany({
        where: {
          owner: identity.sub,
          ...(sessionId && { sessionId }),
          ...(since && { timestamp: { gt: new Date(since) } }),
        },
        orderBy: { timestamp: 'desc' },
        take: 100,
      });
    },

    // getAllMine - 批量获取当前用户数据
    getAllMine: async (_, { owner }, { prisma, identity }) => {
      const userId = authenticatedOwner(identity, owner);
      const [agents, skills, tasks, vehicles, orgs, prompts, avatars, knowledges, tools, settings] = await Promise.all([
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
      ]);
      return { agents, skills, tasks, vehicles, orgs, prompts, avatars, knowledges, tools, settings };
    },

    // COS file operations (AppSync-compatible entry point)
    reqFileOp: async (_, { fo }, { identity }) => {
      const result = await executeFileOps({ owner: identity.sub, operations: fo });
      // AWSJSON is serialized as a JSON string by AppSync; retain that contract.
      return JSON.stringify(result);
    },

    // Relations
    queryAgentSkillRels: (_, { input }, { prisma, identity }) => {
      return prisma.agentSkillRel.findMany({
        where: {
          ...(input?.agentId && { agentId: input.agentId }),
          ...(input?.skillId && { skillId: input.skillId }),
          agent: { owner: identity.sub },
        },
      });
    },
    queryAgentTaskRels: (_, { input }, { prisma, identity }) => {
      return prisma.agentTaskRel.findMany({
        where: {
          ...(input?.agentId && { agentId: input.agentId }),
          ...(input?.taskId && { taskId: input.taskId }),
          agent: { owner: identity.sub },
        },
      });
    },
    queryAgentOrgRels: (_, { input }, { prisma, identity }) => {
      return prisma.agentOrgRel.findMany({
        where: {
          ...(input?.agentId && { agentId: input.agentId }),
          ...(input?.orgId && { orgId: input.orgId }),
          agent: { owner: identity.sub },
        },
      });
    },

    // Intl-compatible relationship entry points. Data is stored only in CN PostgreSQL.
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
    queryKnowledges: (_, args, context) => queryEntity(context.prisma, context.identity, 'Knowledge', args),
    getKnowledges: (_, args, context) => queryEntity(context.prisma, context.identity, 'Knowledge', args),
    queryAvatarResources: (_, args, context) => queryEntity(context.prisma, context.identity, 'AvatarResource', args),
    getAvatarResources: (_, args, context) => queryEntity(context.prisma, context.identity, 'AvatarResource', args),
    querySkills: (_, args, context) => queryEntity(context.prisma, context.identity, 'Skill', args),
    queryOrganizations: (_, args, context) => queryOrganizations(context.prisma, context.identity, args),
    getOrganizations: (_, args, context) => queryOrganizations(context.prisma, context.identity, args),
    queryAgentEndpoints: (_, { org, limit, offset }, context) => queryAgentEndpoints(context.prisma, context.identity, org, { limit, offset }),
    getLongLLMTask: (_, { id }, context) => getLongLlmTask(context.prisma, context.identity, id),
    getSkillEditorChatSessions: (_, { userId }, context) => getChatSessions(context.prisma, context.identity, userId),
    getSkillEditorChatHistory: (_, { sessionId, limit, offset }, context) => getChatHistory(context.prisma, context.identity, sessionId, limit, offset),
    getBots: (_, { ids }, context) => queryLegacy(context.prisma, context.identity, 'bot', {}, ids),
    queryBots: (_, { qb }, context) => queryLegacy(context.prisma, context.identity, 'bot', qb),
    getManagerMissions: (_, { qm }, context) => queryLegacy(context.prisma, context.identity, 'mission', qm),
    queryMissions: (_, { qm }, context) => queryLegacy(context.prisma, context.identity, 'mission', qm?.[0] || {}),
    reqAccountInfo: (_, { ops }, context) => queryLegacy(context.prisma, context.identity, 'account', ops?.[0] || {}),
    reqOrderInfo: (_, { ops }, context) => queryLegacy(context.prisma, context.identity, 'order', ops?.[0] || {}),
    getWanMessage: (_, { ids }, context) => getWanMessages(context.prisma, context.identity, ids),
    queryAPIKeys: (_, { keys }, context) => queryApiKeys(context.prisma, context.identity, keys),
  },

  Mutation: {
    // ============ Agents ============
    addAgents: async (_, { input }, { prisma, identity }) => {
      const results = [];
      for (const item of input) {
        const agent = await prisma.agent.create({
          data: {
            id: item.id || undefined,
            owner: authenticatedOwner(identity, item.owner),
            name: item.name,
            description: item.description,
            gender: item.gender,
            birthday: item.birthday,
            avatarResourceId: item.avatarResourceId,
            capabilities: item.capabilities || {},
            personalities: item.personalities || [],
            rank: item.rank,
            status: item.status || 'active',
            title: item.title || {},
            supervisorId: item.supervisorId,
            vehicleId: item.vehicleId,
            url: item.url,
            version: item.version,
            orgId: item.orgId,
            orgIds: item.orgIds || [],
            skills: item.skills || [],
            tasks: item.tasks || [],
            extraData: item.extraData || {},
          },
        });
        results.push({ id: agent.id, success: true });
      }
      return results;
    },

    updateAgents: async (_, { input }, { prisma, identity }) => {
      const results = [];
      for (const item of input) {
        if (!item.id) {
          results.push({ id: null, success: false, error: 'ID required' });
          continue;
        }
        try {
          const { id, ...data } = item;
          delete data.owner;
          const changed = await prisma.agent.updateMany({ where: { id, owner: identity.sub }, data });
          results.push({ id, success: changed.count === 1, error: changed.count ? null : 'Not found' });
        } catch (e) {
          results.push({ id: item.id, success: false, error: e.message });
        }
      }
      return results;
    },

    removeAgents: async (_, { ids }, { prisma, identity }) => {
      const results = [];
      for (const id of ids) {
        try {
          const changed = await prisma.agent.deleteMany({ where: { id, owner: identity.sub } });
          results.push({ id, success: changed.count === 1, error: changed.count ? null : 'Not found' });
        } catch (e) {
          results.push({ id, success: false, error: e.message });
        }
      }
      return results;
    },

    // ============ Skills ============
    addAgentSkills: async (_, { input }, { prisma, identity }) => {
      const results = [];
      for (const item of input) {
        const skill = await prisma.agentSkill.create({
          data: {
            id: item.id || undefined,
            owner: authenticatedOwner(identity, item.owner),
            name: item.name,
            description: item.description,
            category: item.category,
            tags: item.tags || [],
            config: item.config || {},
            capabilities: item.capabilities || [],
            limitations: item.limitations || [],
            examples: item.examples || [],
            diagram: item.diagram || {},
            inputModes: item.inputModes || ['text'],
            outputModes: item.outputModes || ['text'],
            askid: item.askid,
            apps: item.apps || [],
            level: item.level,
            price: item.price || 0,
            priceModel: item.priceModel,
            source: item.source,
            path: item.path,
            isPublic: item.isPublic ?? true,
            rentable: item.rentable ?? false,
            status: item.status || 'active',
            version: item.version,
          },
        });
        results.push({ id: skill.id, success: true });
      }
      return results;
    },

    updateAgentSkills: async (_, { input }, { prisma, identity }) => {
      const results = [];
      for (const item of input) {
        if (!item.id) {
          results.push({ id: null, success: false, error: 'ID required' });
          continue;
        }
        try {
          const { id, ...data } = item;
          delete data.owner;
          const changed = await prisma.agentSkill.updateMany({ where: { id, owner: identity.sub }, data });
          results.push({ id, success: changed.count === 1, error: changed.count ? null : 'Not found' });
        } catch (e) {
          results.push({ id: item.id, success: false, error: e.message });
        }
      }
      return results;
    },

    removeAgentSkills: async (_, { ids }, { prisma, identity }) => {
      const results = [];
      for (const id of ids) {
        try {
          const changed = await prisma.agentSkill.deleteMany({ where: { id, owner: identity.sub } });
          results.push({ id, success: changed.count === 1, error: changed.count ? null : 'Not found' });
        } catch (e) {
          results.push({ id, success: false, error: e.message });
        }
      }
      return results;
    },

    // ============ Tasks ============
    addAgentTasks: async (_, { input }, { prisma, identity }) => {
      const results = [];
      for (const item of input) {
        try {
          const owner = authenticatedOwner(identity, item.owner);
          // 先创建数据库记录，再同步 scheduler
          const task = await prisma.agentTask.create({
            data: {
              id: item.id || undefined,
              owner,
              name: item.name,
              description: item.description,
              status: item.status || 'pending',
              priority: item.priority || 'normal',
              taskType: item.taskType,
              triggerType: item.triggerType,
              action: item.action,
              duration: item.duration,
              orgId: item.orgId,
              objectives: item.objectives || [],
              result: item.result || {},
              schedule: item.schedule || {},
              errorMessage: item.errorMessage,
              metadata: item.metadata || {},
            },
          });
          // 同步失败则回滚（删除已创建的记录）
          try {
            await getScheduler().syncTask({ taskId: task.id, owner: task.owner, taskType: task.taskType, triggerType: task.triggerType, schedule: task.schedule, parameters: task.metadata });
          } catch (syncErr) {
            await prisma.agentTask.delete({ where: { id: task.id } });
            throw syncErr;
          }
          results.push({ id: task.id, success: true });
        } catch (e) {
          results.push({ id: item.id || null, success: false, error: e.message });
        }
      }
      return results;
    },

    updateAgentTasks: async (_, { input }, { prisma, identity }) => {
      const results = [];
      for (const item of input) {
        if (!item.id) {
          results.push({ id: null, success: false, error: 'ID required' });
          continue;
        }
        try {
          const { id, ...data } = item;
          delete data.owner;
          const changed = await prisma.agentTask.updateMany({ where: { id, owner: identity.sub }, data });
          if (changed.count === 1) {
            const task = await prisma.agentTask.findFirst({ where: { id, owner: identity.sub } });
            await getScheduler().syncTask({ taskId: task.id, owner: task.owner, taskType: task.taskType, triggerType: task.triggerType, schedule: task.schedule, parameters: task.metadata });
          }
          results.push({ id, success: changed.count === 1, error: changed.count ? null : 'Not found' });
        } catch (e) {
          results.push({ id: item.id, success: false, error: e.message });
        }
      }
      return results;
    },

    removeAgentTasks: async (_, { ids }, { prisma, identity }) => {
      const results = [];
      for (const id of ids) {
        try {
          // 先获取任务信息用于删除 scheduler
          const task = await prisma.agentTask.findFirst({ where: { id, owner: identity.sub }, select: { id: true } });
          if (!task) {
            results.push({ id, success: false, error: 'Not found' });
            continue;
          }
          // 优先删除 scheduler，再删除数据库记录
          try {
            await getScheduler().deleteTask(id);
          } catch (syncErr) {
            // scheduler 删除失败不影响数据库操作
            console.warn(`Scheduler delete failed for task ${id}:`, syncErr.message);
          }
          await prisma.agentTask.delete({ where: { id, owner: identity.sub } });
          results.push({ id, success: true });
        } catch (e) {
          results.push({ id, success: false, error: e.message });
        }
      }
      return results;
    },

    // ============ Vehicles ============
    addVehicles: async (_, { input }, { prisma, identity }) => {
      const results = [];
      for (const item of input) {
        const vehicle = await prisma.vehicle.create({
          data: {
            id: item.id || undefined,
            owner: authenticatedOwner(identity, item.owner),
            name: item.name,
            description: item.description,
            vehicleType: item.vehicleType,
            platform: item.platform,
            architecture: item.architecture,
            environment: item.environment,
            status: item.status || 'offline',
            url: item.url,
            hostname: item.hostname,
            ipAddress: item.ipAddress,
            port: item.port,
            accessToken: item.accessToken,
            sslEnabled: item.sslEnabled ?? false,
            securityLevel: item.securityLevel,
            location: item.location,
            timezone: item.timezone,
            capabilities: item.capabilities || {},
            limitations: item.limitations || {},
            settings: item.settings || {},
            extraMetadata: item.extraMetadata || {},
            gpuInfo: item.gpuInfo || {},
            cpuCores: item.cpuCores,
            memoryGb: item.memoryGb,
            storageGb: item.storageGb,
            maxConcurrentTasks: item.maxConcurrentTasks,
            healthScore: item.healthScore,
          },
        });
        results.push({ id: vehicle.id, success: true });
      }
      return results;
    },

    updateVehicles: async (_, { input }, { prisma, identity }) => {
      const results = [];
      for (const item of input) {
        if (!item.id) {
          results.push({ id: null, success: false, error: 'ID required' });
          continue;
        }
        try {
          const { id, ...data } = item;
          delete data.owner;
          const changed = await prisma.vehicle.updateMany({ where: { id, owner: identity.sub }, data });
          results.push({ id, success: changed.count === 1, error: changed.count ? null : 'Not found' });
        } catch (e) {
          results.push({ id: item.id, success: false, error: e.message });
        }
      }
      return results;
    },

    removeVehicles: async (_, { ids }, { prisma, identity }) => {
      const results = [];
      for (const id of ids) {
        try {
          const changed = await prisma.vehicle.deleteMany({ where: { id, owner: identity.sub } });
          results.push({ id, success: changed.count === 1, error: changed.count ? null : 'Not found' });
        } catch (e) {
          results.push({ id, success: false, error: e.message });
        }
      }
      return results;
    },

    // ============ Orgs ============
    addOrgs: async (_, { input }, { prisma }) => {
      const results = [];
      for (const item of input) {
        const org = await prisma.org.create({
          data: {
            id: item.id || undefined,
            name: item.name,
            description: item.description,
            orgType: item.orgType,
            parentId: item.parentId,
            level: item.level || 0,
            sortOrder: item.sortOrder || 0,
            status: item.status || 'active',
            settings: item.settings || {},
          },
        });
        results.push({ id: org.id, success: true });
      }
      return results;
    },

    updateOrgs: async (_, { input }, { prisma }) => {
      const results = [];
      for (const item of input) {
        if (!item.id) {
          results.push({ id: null, success: false, error: 'ID required' });
          continue;
        }
        try {
          const { id, ...data } = item;
          await prisma.org.update({ where: { id }, data });
          results.push({ id, success: true });
        } catch (e) {
          results.push({ id: item.id, success: false, error: e.message });
        }
      }
      return results;
    },

    removeOrgs: async (_, { ids }, { prisma }) => {
      const results = [];
      for (const id of ids) {
        try {
          await prisma.org.delete({ where: { id } });
          results.push({ id, success: true });
        } catch (e) {
          results.push({ id, success: false, error: e.message });
        }
      }
      return results;
    },

    // ============ Prompts ============
    addPrompts: async (_, { input }, { prisma, identity }) => {
      const results = [];
      for (const item of input) {
        const prompt = await prisma.prompt.create({
          data: {
            id: item.id || undefined,
            owner: authenticatedOwner(identity, item.owner),
            prompt: item.prompt,
            version: item.version,
          },
        });
        results.push({ id: prompt.id, success: true });
      }
      return results;
    },

    updatePrompts: async (_, { input }, { prisma, identity }) => {
      const results = [];
      for (const item of input) {
        if (!item.id) {
          results.push({ id: null, success: false, error: 'ID required' });
          continue;
        }
        try {
          const { id, ...data } = item;
          delete data.owner;
          const changed = await prisma.prompt.updateMany({ where: { id, owner: identity.sub }, data });
          results.push({ id, success: changed.count === 1, error: changed.count ? null : 'Not found' });
        } catch (e) {
          results.push({ id: item.id, success: false, error: e.message });
        }
      }
      return results;
    },

    removePrompts: async (_, { ids }, { prisma, identity }) => {
      const results = [];
      for (const id of ids) {
        try {
          const changed = await prisma.prompt.deleteMany({ where: { id, owner: identity.sub } });
          results.push({ id, success: changed.count === 1, error: changed.count ? null : 'Not found' });
        } catch (e) {
          results.push({ id, success: false, error: e.message });
        }
      }
      return results;
    },

    // ============ Avatars ============
    addAvatars: async (_, { input }, { prisma, identity }) => {
      const results = [];
      for (const item of input) {
        const avatar = await prisma.avatar.create({
          data: {
            id: item.id || undefined,
            owner: authenticatedOwner(identity, item.owner),
            name: item.name,
            description: item.description,
            resourceType: item.resourceType || 'image',
            imagePath: item.imagePath,
            videoPath: item.videoPath,
            imageHash: item.imageHash,
            videoHash: item.videoHash,
            cloudImageKey: item.cloudImageKey,
            cloudVideoKey: item.cloudVideoKey,
            cloudImageUrl: item.cloudImageUrl,
            cloudVideoUrl: item.cloudVideoUrl,
            cloudSynced: item.cloudSynced ?? false,
            avatarMetadata: item.avatarMetadata || {},
            isPublic: item.isPublic ?? false,
            usageCount: item.usageCount || 0,
            lastUsedAt: item.lastUsedAt,
          },
        });
        results.push({ id: avatar.id, success: true });
      }
      return results;
    },

    updateAvatars: async (_, { input }, { prisma, identity }) => {
      const results = [];
      for (const item of input) {
        if (!item.id) {
          results.push({ id: null, success: false, error: 'ID required' });
          continue;
        }
        try {
          const { id, ...data } = item;
          delete data.owner;
          const changed = await prisma.avatar.updateMany({ where: { id, owner: identity.sub }, data });
          results.push({ id, success: changed.count === 1, error: changed.count ? null : 'Not found' });
        } catch (e) {
          results.push({ id: item.id, success: false, error: e.message });
        }
      }
      return results;
    },

    removeAvatars: async (_, { ids }, { prisma, identity }) => {
      const results = [];
      for (const id of ids) {
        try {
          const changed = await prisma.avatar.deleteMany({ where: { id, owner: identity.sub } });
          results.push({ id, success: changed.count === 1, error: changed.count ? null : 'Not found' });
        } catch (e) {
          results.push({ id, success: false, error: e.message });
        }
      }
      return results;
    },

    // ============ Knowledges ============
    addAgentKnowledges: async (_, { input }, { prisma, identity }) => {
      const results = [];
      for (const item of input) {
        const knowledge = await prisma.agentKnowledge.create({
          data: {
            id: item.id || undefined,
            owner: authenticatedOwner(identity, item.owner),
            name: item.name,
            description: item.description,
            content: item.content,
            knowledgeType: item.knowledgeType,
            categories: item.categories || [],
            tags: item.tags || [],
            accessMethods: item.accessMethods || [],
            limitations: item.limitations || [],
            level: item.level,
            price: item.price || 0,
            priceModel: item.priceModel,
            path: item.path,
            isPublic: item.isPublic ?? false,
            rentable: item.rentable ?? false,
            status: item.status || 'active',
            settings: item.settings || {},
            config: item.config || {},
            version: item.version,
          },
        });
        results.push({ id: knowledge.id, success: true });
      }
      return results;
    },

    updateAgentKnowledges: async (_, { input }, { prisma, identity }) => {
      const results = [];
      for (const item of input) {
        if (!item.id) {
          results.push({ id: null, success: false, error: 'ID required' });
          continue;
        }
        try {
          const { id, ...data } = item;
          delete data.owner;
          const changed = await prisma.agentKnowledge.updateMany({ where: { id, owner: identity.sub }, data });
          results.push({ id, success: changed.count === 1, error: changed.count ? null : 'Not found' });
        } catch (e) {
          results.push({ id: item.id, success: false, error: e.message });
        }
      }
      return results;
    },

    removeAgentKnowledges: async (_, { ids }, { prisma, identity }) => {
      const results = [];
      for (const id of ids) {
        try {
          const changed = await prisma.agentKnowledge.deleteMany({ where: { id, owner: identity.sub } });
          results.push({ id, success: changed.count === 1, error: changed.count ? null : 'Not found' });
        } catch (e) {
          results.push({ id, success: false, error: e.message });
        }
      }
      return results;
    },

    // ============ Tools ============
    addAgentTools: async (_, { input }, { prisma, identity }) => {
      const results = [];
      for (const item of input) {
        const tool = await prisma.agentTool.create({
          data: {
            id: item.id || undefined,
            owner: authenticatedOwner(identity, item.owner),
            name: item.name,
            description: item.description,
            toolType: item.toolType,
            capabilities: item.capabilities || [],
            limitations: item.limitations || [],
            dependencies: item.dependencies || [],
            settings: item.settings || {},
            config: item.config || {},
            level: item.level,
            price: item.price || 0,
            priceModel: item.priceModel,
            path: item.path,
            isPublic: item.isPublic ?? false,
            rentable: item.rentable ?? false,
            status: item.status || 'active',
            version: item.version,
          },
        });
        results.push({ id: tool.id, success: true });
      }
      return results;
    },

    updateAgentTools: async (_, { input }, { prisma, identity }) => {
      const results = [];
      for (const item of input) {
        if (!item.id) {
          results.push({ id: null, success: false, error: 'ID required' });
          continue;
        }
        try {
          const { id, ...data } = item;
          delete data.owner;
          const changed = await prisma.agentTool.updateMany({ where: { id, owner: identity.sub }, data });
          results.push({ id, success: changed.count === 1, error: changed.count ? null : 'Not found' });
        } catch (e) {
          results.push({ id: item.id, success: false, error: e.message });
        }
      }
      return results;
    },

    removeAgentTools: async (_, { ids }, { prisma, identity }) => {
      const results = [];
      for (const id of ids) {
        try {
          const changed = await prisma.agentTool.deleteMany({ where: { id, owner: identity.sub } });
          results.push({ id, success: changed.count === 1, error: changed.count ? null : 'Not found' });
        } catch (e) {
          results.push({ id, success: false, error: e.message });
        }
      }
      return results;
    },

    // ============ Settings ============
    updateSettings: async (_, { input }, { prisma, identity }) => {
      // 使用事务确保原子性
      await prisma.$transaction(
        input.map((item) => {
          const key = typeof item === 'string' ? item : item.key;
          const value = typeof item === 'string' ? {} : item.value || {};
          return prisma.setting.upsert({
            where: { owner_key: { owner: identity.sub, key } },
            create: { key, value, owner: identity.sub },
            update: { value },
          });
        })
      );
      return 'OK';
    },

    // ============ Skill Editor Events ============
    addSkillEditorEvent: async (_, { input }, { prisma, identity }) => {
      return prisma.skillEditorEvent.create({
        data: {
          owner: authenticatedOwner(identity, input.owner),
          sessionId: input.sessionId,
          flowgramId: input.flowgramId,
          eventType: input.eventType,
          payload: input.payload || {},
          timestamp: input.timestamp ? new Date(input.timestamp) : new Date(),
        },
      });
    },

    runCloudTasks: async (_, { input }, { prisma, identity }) => {
      if (!Array.isArray(input) || input.length < 1 || input.length > 20) throw new GraphQLError('runCloudTasks accepts 1-20 tasks');
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
        } catch (error) { items.push({ task_id: item?.task_id || null, run_id: null, success: false, error: error.message }); }
      }
      return JSON.stringify({ items, run_ids: runIds });
    },

    // ============ Relations ============
    addAgentSkillRels: async (_, { input }, { prisma, identity }) => {
      for (const item of input) {
        await assertOwnedAgent(prisma, identity, item.agentId);
        await prisma.agentSkillRel.upsert({
          where: { agentId_skillId: { agentId: item.agentId, skillId: item.skillId } },
          create: {
            agentId: item.agentId,
            skillId: item.skillId,
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
    },

    updateAgentSkillRels: async (_, { input }, { prisma, identity }) => {
      return resolvers.Mutation.addAgentSkillRels(_, { input }, { prisma, identity });
    },

    removeAgentSkillRels: async (_, { input }, { prisma, identity }) => {
      for (const item of input) {
        if (item.agentId) await assertOwnedAgent(prisma, identity, item.agentId);
        if (item.id) {
          await prisma.agentSkillRel.deleteMany({ where: { id: item.id, agent: { owner: identity.sub } } });
        } else if (item.agentId && item.skillId) {
          await prisma.agentSkillRel.delete({
            where: { agentId_skillId: { agentId: item.agentId, skillId: item.skillId } },
          });
        }
      }
      return { success: true };
    },

    addAgentTaskRels: async (_, { input }, { prisma, identity }) => {
      for (const item of input) {
        await assertOwnedAgent(prisma, identity, item.agentId);
        await prisma.agentTaskRel.upsert({
          where: { agentId_taskId: { agentId: item.agentId, taskId: item.taskId } },
          create: {
            agentId: item.agentId,
            taskId: item.taskId,
            vehicleId: item.vehicleId,
            status: item.status || 'assigned',
            priority: item.priority || 0,
            progress: item.progress || 0,
            scheduledStart: item.scheduledStart ? new Date(item.scheduledStart) : null,
            actualStart: item.actualStart ? new Date(item.actualStart) : null,
            estimatedEnd: item.estimatedEnd ? new Date(item.estimatedEnd) : null,
            actualEnd: item.actualEnd ? new Date(item.actualEnd) : null,
            result: item.result || {},
            errorMessage: item.errorMessage,
            logs: item.logs,
            cpuUsage: item.cpuUsage,
            memoryUsage: item.memoryUsage,
            executionTime: item.executionTime,
            executionContext: item.executionContext || {},
            retryCount: item.retryCount || 0,
            maxRetries: item.maxRetries || 3,
          },
          update: {
            vehicleId: item.vehicleId,
            status: item.status,
            priority: item.priority,
            progress: item.progress,
            scheduledStart: item.scheduledStart ? new Date(item.scheduledStart) : undefined,
            actualStart: item.actualStart ? new Date(item.actualStart) : undefined,
            estimatedEnd: item.estimatedEnd ? new Date(item.estimatedEnd) : undefined,
            actualEnd: item.actualEnd ? new Date(item.actualEnd) : undefined,
            result: item.result,
            errorMessage: item.errorMessage,
            logs: item.logs,
            cpuUsage: item.cpuUsage,
            memoryUsage: item.memoryUsage,
            executionTime: item.executionTime,
            executionContext: item.executionContext,
            retryCount: item.retryCount,
            maxRetries: item.maxRetries,
          },
        });
      }
      return { success: true };
    },

    updateAgentTaskRels: async (_, { input }, { prisma, identity }) => {
      return resolvers.Mutation.addAgentTaskRels(_, { input }, { prisma, identity });
    },

    removeAgentTaskRels: async (_, { input }, { prisma, identity }) => {
      for (const item of input) {
        if (item.agentId) await assertOwnedAgent(prisma, identity, item.agentId);
        if (item.id) {
          await prisma.agentTaskRel.deleteMany({ where: { id: item.id, agent: { owner: identity.sub } } });
        } else if (item.agentId && item.taskId) {
          await prisma.agentTaskRel.delete({
            where: { agentId_taskId: { agentId: item.agentId, taskId: item.taskId } },
          });
        }
      }
      return { success: true };
    },

    addAgentOrgRels: async (_, { input }, { prisma, identity }) => {
      for (const item of input) {
        await assertOwnedAgent(prisma, identity, item.agentId);
        await prisma.agentOrgRel.upsert({
          where: { agentId_orgId: { agentId: item.agentId, orgId: item.orgId } },
          create: {
            agentId: item.agentId,
            orgId: item.orgId,
            role: item.role,
            accessLevel: item.accessLevel || 'member',
            status: item.status || 'active',
            permissions: item.permissions || [],
            joinDate: item.joinDate ? new Date(item.joinDate) : null,
            leaveDate: item.leaveDate ? new Date(item.leaveDate) : null,
          },
          update: {
            role: item.role,
            accessLevel: item.accessLevel,
            status: item.status,
            permissions: item.permissions,
            joinDate: item.joinDate ? new Date(item.joinDate) : undefined,
            leaveDate: item.leaveDate ? new Date(item.leaveDate) : undefined,
          },
        });
      }
      return { success: true };
    },

    updateAgentOrgRels: async (_, { input }, { prisma, identity }) => {
      return resolvers.Mutation.addAgentOrgRels(_, { input }, { prisma, identity });
    },

    removeAgentOrgRels: async (_, { input }, { prisma, identity }) => {
      for (const item of input) {
        if (item.agentId) await assertOwnedAgent(prisma, identity, item.agentId);
        if (item.id) {
          await prisma.agentOrgRel.deleteMany({ where: { id: item.id, agent: { owner: identity.sub } } });
        } else if (item.agentId && item.orgId) {
          await prisma.agentOrgRel.delete({
            where: { agentId_orgId: { agentId: item.agentId, orgId: item.orgId } },
          });
        }
      }
      return { success: true };
    },

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
    addKnowledges: (_, { input }, context) => saveEntities(context.prisma, context.identity, 'Knowledge', input),
    updateKnowledges: (_, { input }, context) => saveEntities(context.prisma, context.identity, 'Knowledge', input, true),
    removeKnowledges: (_, { input }, context) => removeEntities(context.prisma, context.identity, 'Knowledge', input),
    addAvatarResources: (_, { input }, context) => saveEntities(context.prisma, context.identity, 'AvatarResource', input),
    updateAvatarResources: (_, { input }, context) => saveEntities(context.prisma, context.identity, 'AvatarResource', input, true),
    removeAvatarResources: (_, { input }, context) => removeEntities(context.prisma, context.identity, 'AvatarResource', input),
    addSkills: (_, { input }, context) => saveEntities(context.prisma, context.identity, 'Skill', input),
    updateSkills: (_, { input }, context) => saveEntities(context.prisma, context.identity, 'Skill', input, true),
    removeSkills: (_, { input }, context) => removeEntities(context.prisma, context.identity, 'Skill', input),
    upsertAgentEndpoint: (_, { input }, context) => upsertAgentEndpoint(context.prisma, context.identity, input),
    deleteAgentEndpoint: (_, { id }, context) => deleteAgentEndpoint(context.prisma, context.identity, id),
    sendA2AMessage: (_, { input }, context) => sendA2AMessage(context.prisma, context.identity, input),
    reqRAGStore: (_, { input }, context) => registerRagDocuments(context.prisma, context.identity, input),
    startLongLLMTask: (_, { task_input }, context) => startLongLlmTask(context.prisma, context.identity, task_input),
    endLongLLMTask: (_, { input }, context) => endLongLlmTask(context.prisma, context.identity, input),
    createSkillEditorChatSession: (_, { input }, context) => createChatSession(context.prisma, context.identity, input),
    sendSkillEditorChatMessage: (_, { input }, context) => sendChatMessage(context.prisma, context.identity, input),
    cancelSkillEditorChatGeneration: (_, { sessionId }, context) => setChatState(context.prisma, context.identity, sessionId, 'cancelled'),
    deleteSkillEditorChatSession: (_, { sessionId }, context) => setChatState(context.prisma, context.identity, sessionId, 'deleted', true),
    publishSkillEditorStreamEvent: (_, { input }, context) => publishSkillEditorEvent(context.prisma, context.identity, input),
    addAccts: (_, { input }, context) => saveLegacy(context.prisma, context.identity, 'account', input),
    updateAccts: (_, { input }, context) => saveLegacy(context.prisma, context.identity, 'account', input),
    removeAccts: (_, { input }, context) => removeLegacy(context.prisma, context.identity, 'account', input),
    addBots: (_, { input }, context) => saveLegacy(context.prisma, context.identity, 'bot', input),
    updateBots: (_, { input }, context) => saveLegacy(context.prisma, context.identity, 'bot', input),
    removeBots: (_, { input }, context) => removeLegacy(context.prisma, context.identity, 'bot', input),
    addMissions: (_, { input }, context) => saveLegacy(context.prisma, context.identity, 'mission', input),
    updateMissions: (_, { input }, context) => saveLegacy(context.prisma, context.identity, 'mission', input),
    removeMissions: (_, { input }, context) => removeLegacy(context.prisma, context.identity, 'mission', input),
    updateMissionsExStatus: (_, { input }, context) => saveLegacy(context.prisma, context.identity, 'mission', input),
    reportStatus: (_, { input }, context) => saveLegacy(context.prisma, context.identity, 'mission', input),
    makeOrder: (_, { input }, context) => saveLegacy(context.prisma, context.identity, 'order', input),
    makeBusinessOrders: (_, { input }, context) => saveLegacy(context.prisma, context.identity, 'order', input),
    updateBusinessOrders: (_, { input }, context) => saveLegacy(context.prisma, context.identity, 'order', input),
    removeBusinessOrders: (_, { input }, context) => removeLegacy(context.prisma, context.identity, 'order', input),
    sendWanMessage: (_, { input }, context) => sendWanMessage(context.prisma, context.identity, input),
    reqApiKey: (_, { ops }, context) => mutateApiKeys(context.prisma, context.identity, ops),
    dequeueTasks: (_, { input }, context) => dequeueTasks(context.prisma, context.identity, input),
    reportVehicles: (_, { input }, context) => reportVehicles(context.prisma, context.identity, input),
    requestRunExtSkill: (_, { input }, context) => requestExternalSkill(context.prisma, context.identity, input),
    reportRunExtSkillStatus: (_, { input }, context) => reportExternalSkill(context.prisma, context.identity, input),
    reqTrain: (_, { input }, context) => requestTraining(context.prisma, context.identity, input),
    reqPuzzleSolver: (_, { input }, context) => requestPuzzle(context.prisma, context.identity, input),
    confirmPuzzleSolver: (_, { input }, context) => confirmPuzzle(context.prisma, context.identity, input),
  },
};

// ============ GraphQL Schema (TypeScript-like SDL) ============

const typeDefs = `
scalar JSON

type Query {
  # Agents
  getAgents(input: AgentQueryInput): [Agent!]!
  queryAgents(input: AgentQueryInput): [Agent!]!
  
  # Skills
  getAgentSkills(input: SkillQueryInput): [AgentSkill!]!
  queryAgentSkills(input: SkillQueryInput): [AgentSkill!]!
  
  # Tasks
  getAgentTasks(input: TaskQueryInput): [AgentTask!]!
  queryAgentTasks(input: TaskQueryInput): [AgentTask!]!
  
  # Vehicles
  getVehicles(input: VehicleQueryInput): [Vehicle!]!
  queryVehicles(input: VehicleQueryInput): [Vehicle!]!
  
  # Orgs
  getOrgs(input: OrgQueryInput): [Org!]!
  queryOrgs(input: OrgQueryInput): [Org!]!
  getOrgTree(rootId: ID): OrgTree
  getOrgAgentTree(rootId: ID): OrgTree
  
  # Prompts
  getPrompts(owner: String): [Prompt!]!
  queryPrompts(input: PromptQueryInput): [Prompt!]!
  
  # Avatars
  getAvatars(owner: String, resourceType: String): [Avatar!]!
  queryAvatars(input: AvatarQueryInput): [Avatar!]!
  
  # Knowledges
  getAgentKnowledges(owner: String, name: String): [AgentKnowledge!]!
  queryAgentKnowledges(input: KnowledgeQueryInput): [AgentKnowledge!]!
  
  # Tools
  getAgentTools(owner: String, name: String): [AgentTool!]!
  queryAgentTools(input: ToolQueryInput): [AgentTool!]!
  
  # Settings
  getSettings(ids: [ID!], username: String): [Setting!]!
  
  # Skill Editor Events
  getSkillEditorEvents(sessionId: String, since: String): [SkillEditorEvent!]!
  
  # getAllMine
  getAllMine(owner: String): GetAllMineResponse!

  # COS file operations (AppSync compatibility)
  reqFileOp(fo: [FileOp!]): JSON!
  
  # Relations
  queryAgentSkillRels(input: JSON): [AgentSkillRel!]!
  queryAgentTaskRels(input: JSON): [AgentTaskRel!]!
  queryAgentOrgRels(input: JSON): [AgentOrgRel!]!
  queryAgentSkillRelations(qb: String): JSON
  getAgentSkillRelations(ids: String): JSON
  queryAgentTaskRelations(qb: String): JSON
  getAgentTaskRelations(ids: String): JSON
  queryAgentToolRelations(qb: String): JSON
  getAgentToolRelations(ids: String): JSON
  querySkillToolRelations(qb: String): JSON
  getSkillToolRelations(ids: String): JSON
  querySkillKnowledgeRelations(qb: String): JSON
  getSkillKnowledgeRelations(ids: String): JSON
  queryTaskSkillRelations(qb: String): JSON
  getTaskSkillRelations(ids: String): JSON
  queryKnowledges(qb: String): JSON
  getKnowledges(ids: String): JSON
  queryAvatarResources(qb: String): JSON
  getAvatarResources(ids: String): JSON
  queryOrganizations(qb: String): JSON
  getOrganizations(ids: String): JSON
  querySkills(qs: JSON!): JSON!
  queryAgentEndpoints(org: String!, limit: Int, offset: Int): [AgentEndpoint]!
  getLongLLMTask(id: ID!): JSON!
  getSkillEditorChatSessions(userId: ID!): [SkillEditorChatSession]
  getSkillEditorChatHistory(sessionId: ID!, limit: Int, offset: Int): [SkillEditorChatMessage]
  getBots(ids: [ID!]): JSON!
  queryBots(qb: JSON!): JSON!
  getManagerMissions(qm: JSON!): JSON!
  queryMissions(qm: [MissionIdentifiers]!): JSON!
  reqAccountInfo(ops: [AcctOp!]): JSON!
  reqOrderInfo(ops: [OrderOp!]): JSON!
  getWanMessage(ids: [ID!]): [WanChatMessage]!
  queryAPIKeys(keys: [KeyInfo]!): JSON
}

type Mutation {
  # Agents
  addAgents(input: [AgentInput!]!): [AgentMutationResult!]!
  updateAgents(input: [AgentUpdateInput!]!): [AgentMutationResult!]!
  removeAgents(ids: [ID!]!): [AgentMutationResult!]!
  
  # Skills
  addAgentSkills(input: [SkillInput!]!): [SkillMutationResult!]!
  updateAgentSkills(input: [SkillUpdateInput!]!): [SkillMutationResult!]!
  removeAgentSkills(ids: [ID!]!): [SkillMutationResult!]!
  
  # Tasks
  addAgentTasks(input: [TaskInput!]!): [TaskMutationResult!]!
  updateAgentTasks(input: [TaskUpdateInput!]!): [TaskMutationResult!]!
  removeAgentTasks(ids: [ID!]!): [TaskMutationResult!]!
  
  # Vehicles
  addVehicles(input: [VehicleInput!]!): [VehicleMutationResult!]!
  updateVehicles(input: [VehicleUpdateInput!]!): [VehicleMutationResult!]!
  removeVehicles(ids: [ID!]!): [VehicleMutationResult!]!
  
  # Orgs
  addOrgs(input: [OrgInput!]!): [OrgMutationResult!]!
  updateOrgs(input: [OrgUpdateInput!]!): [OrgMutationResult!]!
  removeOrgs(ids: [ID!]!): [OrgMutationResult!]!
  
  # Prompts
  addPrompts(input: [PromptInput!]!): [PromptMutationResult!]!
  updatePrompts(input: [PromptUpdateInput!]!): [PromptMutationResult!]!
  removePrompts(ids: [ID!]!): [PromptMutationResult!]!
  
  # Avatars
  addAvatars(input: [AvatarInput!]!): [AvatarMutationResult!]!
  updateAvatars(input: [AvatarUpdateInput!]!): [AvatarMutationResult!]!
  removeAvatars(ids: [ID!]!): [AvatarMutationResult!]!
  
  # Knowledges
  addAgentKnowledges(input: [KnowledgeInput!]!): [KnowledgeMutationResult!]!
  updateAgentKnowledges(input: [KnowledgeUpdateInput!]!): [KnowledgeMutationResult!]!
  removeAgentKnowledges(ids: [ID!]!): [KnowledgeMutationResult!]!
  
  # Tools
  addAgentTools(input: [ToolInput!]!): [ToolMutationResult!]!
  updateAgentTools(input: [ToolUpdateInput!]!): [ToolMutationResult!]!
  removeAgentTools(ids: [ID!]!): [ToolMutationResult!]!
  
  # Settings
  updateSettings(input: [JSON!]!): String!
  
  # Skill Editor Events
  addSkillEditorEvent(input: SkillEditorEventInput!): SkillEditorEvent!
  runCloudTasks(input: [CloudTaskInput!]!): JSON!
  
  # Relations
  addAgentSkillRels(input: [JSON!]!): JSON!
  updateAgentSkillRels(input: [JSON!]!): JSON!
  removeAgentSkillRels(input: [JSON!]!): JSON!
  
  addAgentTaskRels(input: [JSON!]!): JSON!
  updateAgentTaskRels(input: [JSON!]!): JSON!
  removeAgentTaskRels(input: [JSON!]!): JSON!
  
  addAgentOrgRels(input: [JSON!]!): JSON!
  updateAgentOrgRels(input: [JSON!]!): JSON!
  removeAgentOrgRels(input: [JSON!]!): JSON!

  addAgentSkillRelations(input: [AgentSkillRelation]!): JSON
  updateAgentSkillRelations(input: [AgentSkillRelation]!): JSON
  removeAgentSkillRelations(input: [RemoveOrder]!): JSON
  addAgentTaskRelations(input: [AgentTaskRelation]!): JSON
  updateAgentTaskRelations(input: [AgentTaskRelation]!): JSON
  removeAgentTaskRelations(input: [RemoveOrder]!): JSON
  addAgentToolRelations(input: [AgentToolRelation]!): JSON
  updateAgentToolRelations(input: [AgentToolRelation]!): JSON
  removeAgentToolRelations(input: [RemoveOrder]!): JSON
  addSkillToolRelations(input: [SkillToolRelation]!): JSON
  updateSkillToolRelations(input: [SkillToolRelation]!): JSON
  removeSkillToolRelations(input: [RemoveOrder]!): JSON
  addSkillKnowledgeRelations(input: [SkillKnowledgeRelation]!): JSON
  updateSkillKnowledgeRelations(input: [SkillKnowledgeRelation]!): JSON
  removeSkillKnowledgeRelations(input: [RemoveOrder]!): JSON
  addTaskSkillRelations(input: [TaskSkillRelation]!): JSON
  updateTaskSkillRelations(input: [TaskSkillRelation]!): JSON
  removeTaskSkillRelations(input: [RemoveOrder]!): JSON
  addKnowledges(input: [Knowledge]!): JSON
  updateKnowledges(input: [Knowledge]!): JSON
  removeKnowledges(input: [RemoveOrder]!): JSON
  addAvatarResources(input: [AvatarResource]!): JSON
  updateAvatarResources(input: [AvatarResource]!): JSON
  removeAvatarResources(input: [RemoveOrder]!): JSON
  addSkills(input: [Skill]!): JSON!
  updateSkills(input: [Skill]!): JSON!
  removeSkills(input: [RemoveOrder]!): JSON!
  upsertAgentEndpoint(input: AgentEndpointInput!): AgentEndpoint
  deleteAgentEndpoint(id: ID!): AgentEndpoint
  sendA2AMessage(input: A2AMessageInput!): A2AMessage
  reqRAGStore(input: [RAGIN]!): JSON!
  startLongLLMTask(task_input: JSON!): JSON!
  endLongLLMTask(input: LongLLMTaskResultInput!): LongLLMTaskResult!
  createSkillEditorChatSession(input: SkillEditorChatSessionInput!): SkillEditorChatSession
  sendSkillEditorChatMessage(input: SkillEditorChatMessageInput!): SkillEditorChatMessageResponse
  cancelSkillEditorChatGeneration(sessionId: ID!): Boolean
  deleteSkillEditorChatSession(sessionId: ID!): Boolean
  publishSkillEditorStreamEvent(input: SkillEditorStreamEventInput!): SkillEditorEvent
  addAccts(input: [Account]!): JSON!
  updateAccts(input: [Account]!): JSON!
  removeAccts(input: [RemoveOrder]!): JSON!
  addBots(input: [Bot]!): JSON!
  updateBots(input: [Bot]!): JSON!
  removeBots(input: [RemoveOrder]!): JSON!
  addMissions(input: [Mission]!, settings: JSON!): JSON!
  updateMissions(input: [Mission]!): JSON!
  removeMissions(input: [RemoveOrder]!): JSON!
  updateMissionsExStatus(input: [SimpleMissionStatus]!): JSON!
  reportStatus(input: [MissionStatus]!): JSON!
  makeOrder(input: [Order]!): JSON!
  makeBusinessOrders(input: [Order]!): JSON!
  updateBusinessOrders(input: [Order]!): JSON!
  removeBusinessOrders(input: [RemoveBusinessOrder]!): JSON!
  sendWanMessage(input: WanChatMessageInput): WanChatMessage
  reqApiKey(ops: [KeyOp]!): JSON!
  dequeueTasks(input: [TaskOrder]!): JSON!
  reportVehicles(input: [VehicleInfo]!): JSON
  requestRunExtSkill(input: [SkillRun]): JSON!
  reportRunExtSkillStatus(input: [SkillRunStatus]): JSON!
  reqTrain(input: [Skill]!): JSON!
  reqPuzzleSolver(input: [PuzzleInput]!): Puzzle!
  confirmPuzzleSolver(input: [PuzzleResultInput]!): PuzzleResult!
}

# ============ Types ============

type Agent {
  id: ID!
  owner: String!
  name: String!
  description: String
  gender: String
  birthday: String
  avatarResourceId: String
  capabilities: JSON
  personalities: JSON
  rank: String
  status: String
  title: JSON
  supervisorId: String
  vehicleId: String
  url: String
  version: String
  orgId: String
  orgIds: JSON
  skills: JSON
  tasks: JSON
  extraData: JSON
  createdAt: String
  updatedAt: String
}

type AgentSkill {
  id: ID!
  owner: String!
  name: String!
  description: String
  category: String
  tags: JSON
  config: JSON
  capabilities: JSON
  limitations: JSON
  examples: JSON
  diagram: JSON
  inputModes: JSON
  outputModes: JSON
  askid: Int
  apps: JSON
  level: String
  price: Int
  priceModel: String
  source: String
  path: String
  isPublic: Boolean
  rentable: Boolean
  status: String
  version: String
  createdAt: String
  updatedAt: String
}

type AgentTask {
  id: ID!
  owner: String!
  name: String!
  description: String
  status: String
  priority: String
  taskType: String
  triggerType: String
  action: String
  duration: Int
  orgId: String
  objectives: JSON
  result: JSON
  schedule: JSON
  errorMessage: String
  metadata: JSON
  createdAt: String
  updatedAt: String
}

type Vehicle {
  id: ID!
  owner: String!
  name: String!
  description: String
  vehicleType: String
  platform: String
  architecture: String
  environment: String
  status: String
  url: String
  hostname: String
  ipAddress: String
  port: Int
  accessToken: String
  sslEnabled: Boolean
  securityLevel: String
  location: String
  timezone: String
  capabilities: JSON
  limitations: JSON
  settings: JSON
  extraMetadata: JSON
  gpuInfo: JSON
  cpuCores: Int
  memoryGb: Float
  storageGb: Float
  maxConcurrentTasks: Int
  healthScore: Float
  uptimeSeconds: Float
  lastHeartbeat: String
  createdAt: String
  updatedAt: String
}

type Org {
  id: ID!
  name: String!
  description: String
  orgType: String
  parentId: String
  level: Int
  sortOrder: Int
  status: String
  settings: JSON
}

type OrgTree {
  id: ID!
  name: String!
  description: String
  orgType: String
  level: Int
  parentId: String
  sortOrder: Int
  status: String
  settings: JSON
  children: [OrgTree!]
  agents: [Agent!]
}

type Prompt {
  id: ID!
  owner: String!
  prompt: JSON!
  version: String
  createdAt: String
  updatedAt: String
}

type Avatar {
  id: ID!
  owner: String
  name: String
  description: String
  resourceType: String!
  imagePath: String
  videoPath: String
  imageHash: String
  videoHash: String
  cloudImageKey: String
  cloudVideoKey: String
  cloudImageUrl: String
  cloudVideoUrl: String
  cloudSynced: Boolean
  avatarMetadata: JSON
  isPublic: Boolean
  usageCount: Int
  lastUsedAt: String
  createdAt: String
  updatedAt: String
}

type AgentKnowledge {
  id: ID!
  owner: String!
  name: String!
  description: String
  content: String
  knowledgeType: String
  categories: JSON
  tags: JSON
  accessMethods: JSON
  limitations: JSON
  level: Int
  price: Float
  priceModel: String
  path: String
  isPublic: Boolean
  rentable: Boolean
  status: String
  settings: JSON
  config: JSON
  version: String
  createdAt: String
  updatedAt: String
}

type AgentTool {
  id: ID!
  owner: String!
  name: String!
  description: String
  toolType: String
  capabilities: JSON
  limitations: JSON
  dependencies: JSON
  settings: JSON
  config: JSON
  level: Int
  price: Float
  priceModel: String
  path: String
  isPublic: Boolean
  rentable: Boolean
  status: String
  version: String
  createdAt: String
  updatedAt: String
}

type Setting {
  id: ID!
  key: String!
  value: JSON!
  owner: String
}

type SkillEditorEvent {
  eventId: ID!
  owner: String!
  sessionId: String!
  flowgramId: String
  eventType: String!
  payload: JSON!
  timestamp: String!
}

type AgentEndpoint {
  id: ID!
  machineId: String!
  org: String!
  name: String
  role: String
  skills: String
  skillsHash: String
  a2aRelayChannel: String!
  lanHint: String
  ecanVer: String
  os: String
  lastSeen: BigInt
  ttl: Int
}

type A2AMessage {
  id: ID!
  toAgentId: String!
  fromAgentId: String!
  org: String!
  payload: JSON!
  timestamp: String!
}

type LongLLMTaskResult {
  id: ID!
  acctSiteID: String
  agentID: String
  workType: String
  taskID: String
  status: String
  results: String
  timestamp: String
}

type SkillEditorChatSession {
  id: ID!
  name: String!
  flowgramId: ID
  createdAt: String!
  updatedAt: String!
}

type SkillEditorChatMessage {
  id: ID!
  role: String!
  content: String!
  timestamp: String!
  attachments: JSON
  metadata: JSON
}

type SkillEditorChatMessageResponse {
  sessionId: ID!
  sessionName: String!
  state: String!
  intent: String
  message: SkillEditorChatMessage!
  clarification: JSON
  plan: JSON
  flowgram: JSON
  validation: JSON
}

type WanChatMessage {
  id: ID
  chatID: String
  sender: String
  receiver: String
  type: String
  contents: String
  parameters: String
  msg: String
  options: JSON
  background: String
  timestamp: String
}

type Puzzle { pzid: ID!, request_id: String, type: String, puzzle_file: String, question: String, url: String, url_key: String, prize: Int, time_limit: Int, module: String, options: String }
type PuzzleResult { pzid: ID!, request_id: String, type: String, solver: String, result: String }

# Relations
type AgentSkillRel {
  id: ID!
  agentId: String!
  skillId: String!
  proficiencyLevel: Int
  experiencePoints: Int
  certificationLevel: Int
  usageCount: Int
  successRate: Float
  lastUsed: String
  status: String
  isFavorite: Boolean
  priority: Int
  config: JSON
}

type AgentTaskRel {
  id: ID!
  agentId: String!
  taskId: String!
  vehicleId: String
  status: String
  priority: Int
  progress: Float
  scheduledStart: String
  actualStart: String
  estimatedEnd: String
  actualEnd: String
  result: JSON
  errorMessage: String
  logs: String
  cpuUsage: Float
  memoryUsage: Float
  executionTime: Float
  executionContext: JSON
  retryCount: Int
  maxRetries: Int
}

type AgentOrgRel {
  id: ID!
  agentId: String!
  orgId: String!
  role: String
  accessLevel: String
  status: String
  permissions: JSON
  joinDate: String
  leaveDate: String
}

# Responses
type AgentMutationResult {
  id: ID
  success: Boolean!
  error: String
}

type SkillMutationResult {
  id: ID
  success: Boolean!
  error: String
}

type TaskMutationResult {
  id: ID
  success: Boolean!
  error: String
}

type VehicleMutationResult {
  id: ID
  success: Boolean!
  error: String
}

type OrgMutationResult {
  id: ID
  success: Boolean!
  error: String
}

type PromptMutationResult {
  id: ID
  success: Boolean!
  error: String
}

type AvatarMutationResult {
  id: ID
  success: Boolean!
  error: String
}

type KnowledgeMutationResult {
  id: ID
  success: Boolean!
  error: String
}

type ToolMutationResult {
  id: ID
  success: Boolean!
  error: String
}

type GetAllMineResponse {
  agents: [Agent!]!
  skills: [AgentSkill!]!
  tasks: [AgentTask!]!
  vehicles: [Vehicle!]!
  orgs: [Org!]!
  prompts: [Prompt!]!
  avatars: [Avatar!]!
  knowledges: [AgentKnowledge!]!
  tools: [AgentTool!]!
  settings: JSON
}

# Inputs
input AgentQueryInput {
  id: ID
  owner: String
  name: String
  status: String
}

input AgentInput {
  id: ID
  owner: String
  name: String!
  description: String
  gender: String
  birthday: String
  avatarResourceId: String
  capabilities: JSON
  personalities: JSON
  rank: String
  status: String
  title: JSON
  supervisorId: String
  vehicleId: String
  url: String
  version: String
  orgId: String
  orgIds: JSON
  skills: JSON
  tasks: JSON
  extraData: JSON
}

input AgentUpdateInput {
  id: ID!
  name: String
  description: String
  gender: String
  birthday: String
  avatarResourceId: String
  capabilities: JSON
  personalities: JSON
  rank: String
  status: String
  title: JSON
  supervisorId: String
  vehicleId: String
  url: String
  version: String
  orgId: String
  orgIds: JSON
  skills: JSON
  tasks: JSON
  extraData: JSON
}

input SkillQueryInput {
  id: ID
  owner: String
  name: String
  category: String
}

input SkillInput {
  id: ID
  owner: String
  name: String!
  description: String
  category: String
  tags: JSON
  config: JSON
  capabilities: JSON
  limitations: JSON
  examples: JSON
  diagram: JSON
  inputModes: JSON
  outputModes: JSON
  askid: Int
  apps: JSON
  level: String
  price: Int
  priceModel: String
  source: String
  path: String
  isPublic: Boolean
  rentable: Boolean
  status: String
  version: String
}

input SkillUpdateInput {
  id: ID!
  name: String
  description: String
  category: String
  tags: JSON
  config: JSON
  capabilities: JSON
  limitations: JSON
  examples: JSON
  diagram: JSON
  inputModes: JSON
  outputModes: JSON
  askid: Int
  apps: JSON
  level: String
  price: Int
  priceModel: String
  source: String
  path: String
  isPublic: Boolean
  rentable: Boolean
  status: String
  version: String
}

input TaskQueryInput {
  id: ID
  owner: String
  status: String
}

input TaskInput {
  id: ID
  owner: String
  name: String!
  description: String
  status: String
  priority: String
  taskType: String
  triggerType: String
  action: String
  duration: Int
  orgId: String
  objectives: JSON
  result: JSON
  schedule: JSON
  errorMessage: String
  metadata: JSON
}

input TaskUpdateInput {
  id: ID!
  name: String
  description: String
  status: String
  priority: String
  taskType: String
  triggerType: String
  action: String
  duration: Int
  orgId: String
  objectives: JSON
  result: JSON
  schedule: JSON
  errorMessage: String
  metadata: JSON
}

input VehicleQueryInput {
  id: ID
  owner: String
}

input VehicleInput {
  id: ID
  owner: String
  name: String!
  description: String
  vehicleType: String
  platform: String
  architecture: String
  environment: String
  status: String
  url: String
  hostname: String
  ipAddress: String
  port: Int
  accessToken: String
  sslEnabled: Boolean
  securityLevel: String
  location: String
  timezone: String
  capabilities: JSON
  limitations: JSON
  settings: JSON
  extraMetadata: JSON
  gpuInfo: JSON
  cpuCores: Int
  memoryGb: Float
  storageGb: Float
  maxConcurrentTasks: Int
  healthScore: Float
}

input VehicleUpdateInput {
  id: ID!
  name: String
  description: String
  vehicleType: String
  platform: String
  architecture: String
  environment: String
  status: String
  url: String
  hostname: String
  ipAddress: String
  port: Int
  accessToken: String
  sslEnabled: Boolean
  securityLevel: String
  location: String
  timezone: String
  capabilities: JSON
  limitations: JSON
  settings: JSON
  extraMetadata: JSON
  gpuInfo: JSON
  cpuCores: Int
  memoryGb: Float
  storageGb: Float
  maxConcurrentTasks: Int
  healthScore: Float
}

input OrgQueryInput {
  id: ID
  name: String
  orgType: String
  status: String
}

input OrgInput {
  id: ID
  name: String!
  description: String
  orgType: String
  parentId: String
  level: Int
  sortOrder: Int
  status: String
  settings: JSON
}

input OrgUpdateInput {
  id: ID!
  name: String
  description: String
  orgType: String
  parentId: String
  level: Int
  sortOrder: Int
  status: String
  settings: JSON
}

input PromptQueryInput {
  id: ID
  owner: String
  search: String
  version: String
}

input PromptInput {
  id: ID
  owner: String
  prompt: JSON!
  version: String
}

input PromptUpdateInput {
  id: ID!
  prompt: JSON
  version: String
}

input AvatarQueryInput {
  owner: String
  resourceType: String
}

input AvatarInput {
  id: ID
  owner: String
  name: String
  description: String
  resourceType: String
  imagePath: String
  videoPath: String
  imageHash: String
  videoHash: String
  cloudImageKey: String
  cloudVideoKey: String
  cloudImageUrl: String
  cloudVideoUrl: String
  cloudSynced: Boolean
  avatarMetadata: JSON
  isPublic: Boolean
  usageCount: Int
  lastUsedAt: String
}

input AvatarUpdateInput {
  id: ID!
  name: String
  description: String
  resourceType: String
  imagePath: String
  videoPath: String
  imageHash: String
  videoHash: String
  cloudImageKey: String
  cloudVideoKey: String
  cloudImageUrl: String
  cloudVideoUrl: String
  cloudSynced: Boolean
  avatarMetadata: JSON
  isPublic: Boolean
  usageCount: Int
  lastUsedAt: String
}

input KnowledgeQueryInput {
  id: ID
  owner: String
  name: String
}

input KnowledgeInput {
  id: ID
  owner: String
  name: String!
  description: String
  content: String
  knowledgeType: String
  categories: JSON
  tags: JSON
  accessMethods: JSON
  limitations: JSON
  level: Int
  price: Float
  priceModel: String
  path: String
  isPublic: Boolean
  rentable: Boolean
  status: String
  settings: JSON
  config: JSON
  version: String
}

input KnowledgeUpdateInput {
  id: ID!
  name: String
  description: String
  content: String
  knowledgeType: String
  categories: JSON
  tags: JSON
  accessMethods: JSON
  limitations: JSON
  level: Int
  price: Float
  priceModel: String
  path: String
  isPublic: Boolean
  rentable: Boolean
  status: String
  settings: JSON
  config: JSON
  version: String
}

input ToolQueryInput {
  id: ID
  owner: String
  name: String
}

input ToolInput {
  id: ID
  owner: String
  name: String!
  description: String
  toolType: String
  capabilities: JSON
  limitations: JSON
  dependencies: JSON
  settings: JSON
  config: JSON
  level: Int
  price: Float
  priceModel: String
  path: String
  isPublic: Boolean
  rentable: Boolean
  status: String
  version: String
}

input ToolUpdateInput {
  id: ID!
  name: String
  description: String
  toolType: String
  capabilities: JSON
  limitations: JSON
  dependencies: JSON
  settings: JSON
  config: JSON
  level: Int
  price: Float
  priceModel: String
  path: String
  isPublic: Boolean
  rentable: Boolean
  status: String
  version: String
}

input SkillEditorEventInput {
  owner: String
  sessionId: String!
  flowgramId: String
  eventType: String!
  payload: JSON
  timestamp: String
}

input FileOp {
  op: String!
  names: String!
  options: String
  expiresIn: Int
  contentType: String
}

input RemoveOrder {
  oid: ID!
  owner: String!
  reason: String!
}

input Knowledge {
  knid: ID!
  name: String
  owner: String
  description: String
  path: String
  status: String
  rag: String
  metadata: JSON
}

input AvatarResource {
  id: ID!
  owner: String
  resource_type: String
  name: String
  description: String
  image_path: String
  video_path: String
  image_hash: String
  video_hash: String
  cloud_image_url: String
  cloud_video_url: String
  cloud_image_key: String
  cloud_video_key: String
  cloud_synced: Boolean
  avatar_metadata: JSON
  usage_count: Int
  last_used_at: String
  is_public: Boolean
  created_at: String
  updated_at: String
}

input Skill {
  skid: ID!
  owner: String
  createdOn: String!
  platform: String
  app: String
  site: String
  site_name: String
  page: String
  name: String
  path: String
  main: String
  description: String!
  runtime: Int!
  price_model: String!
  price: Int!
  privacy: String
}

input AgentEndpointInput {
  id: ID!
  machineId: String!
  org: String!
  name: String
  role: String
  skills: String
  skillsHash: String
  a2aRelayChannel: String!
  lanHint: String
  ecanVer: String
  os: String
  ttl: Int
}

input A2AMessageInput {
  toAgentId: String!
  fromAgentId: String!
  org: String!
  payload: JSON!
}

input RAGIN {
  fid: ID!
  pid: ID!
  file: String!
  type: String!
  format: String!
  options: JSON!
  version: String!
}

input LongLLMTaskResultInput {
  acctSiteID: String
  agentID: String
  workType: String
  taskID: String
  status: String
  results: String
}

input SkillEditorChatSessionInput {
  name: String
  flowgramId: ID
  userId: ID!
}

input SkillEditorChatMessageInput {
  sessionId: ID!
  content: String!
  attachments: JSON
  canvasContext: JSON
  clarificationResponses: JSON
  userId: ID!
  flowgramId: ID
}

input SkillEditorStreamEventInput {
  owner: ID!
  sessionId: ID!
  flowgramId: ID
  eventType: String!
  payload: JSON
}

input Account {
  actid: ID!
  user_name: String
  subid: String
  dob: String
  email: String
  phone: String
  addr: String
  ssn4: String
  sign_on_date: String
  pay_method1: String
  pay1_details: String
  pay_method2: String
  pay2_details: String
  pay_method3: String
  pay3_details: String
  subs: String
  fund: Int
  quota: Int
  states: String
}

input AcctOp { actid: ID!, op: String!, options: String! }
input OrderOp { oid: ID!, op: String, options: String }
input KeyInfo { aws_api_key: String, option: String }
input KeyOp { op: String, keys: String, options: String }

input Bot {
  bid: ID!
  owner: String
  roles: String
  org: String
  birthday: String
  gender: String
  interests: String
  status: String
  levels: String
  vehicle: String
  location: String!
}

input Mission {
  mid: ID!
  ticket: ID!
  owner: String
  botid: ID!
  cuspas: String
  search_kw: String
  search_cat: String
  status: String!
  trepeat: ID!
  store: String!
  asin: String!
  brand: String!
  mtype: String!
  esd: String!
  as_server: Int!
  skills: String!
  config: String!
}

input MissionIdentifiers {
  byowneruser: Boolean
  mid: ID
  ticket: ID
  botid: ID
  owner: String
  requester: String
  type: String
  config: String
  phrase: String
  pseudo_store: String
  skills: String
  esd_range: String
  status: String
  created_date_range: String
  test_mode: Boolean
}

input MissionStatus { mid: ID!, bid: ID, status: String, starttime: String, usage: String, endtime: String, nthretry: Int }
input SimpleMissionStatus { mid: ID!, status: String }

input Order {
  oid: ID!
  actid: ID!
  orderID: String
  products: [String]!
  description: String
  yek: String
  number: Int
  discount: Int
  discountType: String
  dealType: String
  unitPrice: Int
  total: Int
  payMethod: String
  beginDate: String
  endDate: String
  status: String
  transactions: String
}

input RemoveBusinessOrder { oid: ID!, owner: String!, reason: String!, products: [String]!, productTypes: [String]! }
input WanChatMessageInput { chatID: String, sender: String, receiver: String, type: String, contents: String, parameters: String }
input TaskOrder { vehicles: String! }
input VehicleInfo { vid: ID, vname: String!, owner: String, status: String, lastseen: String, functions: String, bids: String, hardware: String, software: String, ip: String, created_at: String }
input SkillRun { skid: ID!, requester_mid: ID!, owner: String, name: String, start: String, in_data: String, verbose: Boolean }
input SkillRunStatus { run_id: ID!, skid: ID!, runner_mid: ID!, runner_bid: ID!, requester: String, request_method: String, status: String, start_time: String, end_time: String, result_data: String! }
input PuzzleInput { pzid: ID!, request_id: String, type: String, puzzle_file: String, question: String, url: String, url_key: String, prize: Int, time_limit: Int, module: String, options: String }
input PuzzleResultInput { pzid: ID!, request_id: String, type: String, solver: String, result: String }

input AgentSkillRelation {
  agid: ID!
  skid: ID!
  owner: String!
  status: String
  langgraph: JSON
  proficiency: Int
  acquired_at: String
  created_at: String
  updated_at: String
}

input AgentTaskRelation {
  agid: ID!
  task_id: ID!
  owner: String!
  status: String
  vehicle_id: String
  assigned_at: String
  started_at: String
  completed_at: String
  created_at: String
  updated_at: String
}

input AgentToolRelation {
  agid: ID!
  tool_id: ID!
  owner: String!
  permission: String
  granted_at: String
  created_at: String
  updated_at: String
}

input SkillToolRelation {
  skill_id: ID!
  tool_id: ID!
  owner: String!
  usage_type: String
  required: Boolean
  created_at: String
  updated_at: String
}

input SkillKnowledgeRelation {
  skill_id: ID!
  knowledge_id: ID!
  owner: String!
  dependency_type: String
  usage_frequency: String
  importance: Int
  access_pattern: String
  knowledge_scope: JSON
  created_at: String
  updated_at: String
}

input TaskSkillRelation {
  task_id: ID!
  skill_id: ID!
  owner: String!
  required: Boolean
  proficiency_required: Int
  created_at: String
  updated_at: String
}

input CloudTaskInput {
  options: JSON!
  task_id: String
  task_name: String
}
`;

// ============ Create Yoga Server ============

const yoga = createYoga({
  schema: createSchema({ typeDefs, resolvers }),
  graphqlEndpoint: '/api/graphql',
  landingPage: true,
  cors: {
    origin: '*',
    methods: ['GET', 'POST', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization'],
  },
  context: async ({ request }) => {
    const identity = await resolveIdentity(request);
    return {
      prisma: getPrisma(),
      identity,
    };
  },
  fetchAPI: { Response },
});

// ============ SCF Handler ============

exports.main = async (event, context) => {
  // 适配 SCF 格式
  const isHttpEvent = event.httpMethod || event.method;
  
  if (isHttpEvent) {
    // HTTP 触发
    const url = new URL(event.path || '/api/graphql', `https://${event.headers?.host || 'localhost'}`);
    const request = new Request(url.toString(), {
      method: event.httpMethod || event.method,
      headers: new Headers(event.headers || {}),
      body: event.body || undefined,
    });
    
    const response = await yoga.fetch(request);
    const body = await response.text();
    
    return {
      statusCode: response.status,
      headers: Object.fromEntries(response.headers.entries()),
      body,
    };
  }

  if (event?.Type === 'Timer' && event.Message) {
    const payload = typeof event.Message === 'string' ? JSON.parse(event.Message) : event.Message;
    if (payload.action !== 'run_cloud_task' || !payload.owner_id || !payload.task_id) {
      throw new Error('Invalid CN scheduler timer payload');
    }
    const runId = await getScheduler().launch({ owner: String(payload.owner_id), taskId: String(payload.task_id), options: payload.options || {} });
    return { success: true, run_id: runId, task_id: String(payload.task_id) };
  }
  
  // 事件触发
  return { message: 'TCB GraphQL API Ready' };
};
