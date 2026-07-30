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
const { PrismaClient } = require('@prisma/client');
const cloudbase = require('@cloudbase/node-sdk');

// TCB 环境初始化（仅在云端生效）
let tcbApp = null;
if (process.env.TCB_REGION) {
  tcbApp = cloudbase.init({
    env: cloudbase.SyunWing,
  });
}

// Prisma Client 单例
let prisma;

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
  Query: {
    // Agents
    getAgents: (_, { input }, { prisma, identity }) => {
      return prisma.agent.findMany({
        where: {
          owner: input?.owner || identity.sub,
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
          owner: input?.owner || identity.sub,
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
          owner: input?.owner || identity.sub,
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
          owner: input?.owner || identity.sub,
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
        where: { owner: owner || identity.sub },
        orderBy: { createdAt: 'desc' },
      });
    },
    queryPrompts: (_, { input }, { prisma, identity }) => {
      return prisma.prompt.findMany({
        where: {
          owner: input?.owner || identity.sub,
        },
        orderBy: { createdAt: 'desc' },
      });
    },

    // Avatars
    getAvatars: (_, args, { prisma, identity }) => {
      return prisma.avatar.findMany({
        where: {
          ...(args?.owner && { owner: args.owner }),
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
          owner: args?.owner || identity.sub,
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
          owner: args?.owner || identity.sub,
          ...(args?.name && { name: { contains: args.name, mode: 'insensitive' } }),
        },
        orderBy: { createdAt: 'desc' },
      });
    },
    queryAgentTools: (_, { input }, { prisma, identity }) => resolvers.Query.getAgentTools(_, input, { prisma, identity }),

    // Settings
    getSettings: (_, { ids, username }, { prisma, identity }) => {
      const owner = username || identity.sub;
      return prisma.setting.findMany({
        where: ids?.length 
          ? { id: { in: ids } }
          : { OR: [{ owner }, { owner: null }] },
      });
    },

    // Skill Editor Events
    getSkillEditorEvents: (_, { sessionId, since }, { prisma, identity }) => {
      return prisma.skillEditorEvent.findMany({
        where: {
          ...(sessionId ? { sessionId } : { owner: identity.sub }),
          ...(since && { timestamp: { gt: new Date(since) } }),
        },
        orderBy: { timestamp: 'desc' },
        take: 100,
      });
    },

    // getAllMine - 批量获取当前用户数据
    getAllMine: async (_, { owner }, { prisma, identity }) => {
      const userId = owner || identity.sub;
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
        prisma.setting.findMany({ where: { OR: [{ owner: userId }, { owner: null }] } }),
      ]);
      return { agents, skills, tasks, vehicles, orgs, prompts, avatars, knowledges, tools, settings };
    },

    // Relations
    queryAgentSkillRels: (_, { input }, { prisma }) => {
      return prisma.agentSkillRel.findMany({
        where: {
          ...(input?.agentId && { agentId: input.agentId }),
          ...(input?.skillId && { skillId: input.skillId }),
        },
      });
    },
    queryAgentTaskRels: (_, { input }, { prisma }) => {
      return prisma.agentTaskRel.findMany({
        where: {
          ...(input?.agentId && { agentId: input.agentId }),
          ...(input?.taskId && { taskId: input.taskId }),
        },
      });
    },
    queryAgentOrgRels: (_, { input }, { prisma }) => {
      return prisma.agentOrgRel.findMany({
        where: {
          ...(input?.agentId && { agentId: input.agentId }),
          ...(input?.orgId && { orgId: input.orgId }),
        },
      });
    },
  },

  Mutation: {
    // ============ Agents ============
    addAgents: async (_, { input }, { prisma, identity }) => {
      const results = [];
      for (const item of input) {
        const agent = await prisma.agent.create({
          data: {
            id: item.id || undefined,
            owner: item.owner || identity.sub,
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

    updateAgents: async (_, { input }, { prisma }) => {
      const results = [];
      for (const item of input) {
        if (!item.id) {
          results.push({ id: null, success: false, error: 'ID required' });
          continue;
        }
        try {
          const { id, ...data } = item;
          await prisma.agent.update({ where: { id }, data });
          results.push({ id, success: true });
        } catch (e) {
          results.push({ id: item.id, success: false, error: e.message });
        }
      }
      return results;
    },

    removeAgents: async (_, { ids }, { prisma }) => {
      const results = [];
      for (const id of ids) {
        try {
          await prisma.agent.delete({ where: { id } });
          results.push({ id, success: true });
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
            owner: item.owner || identity.sub,
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

    updateAgentSkills: async (_, { input }, { prisma }) => {
      const results = [];
      for (const item of input) {
        if (!item.id) {
          results.push({ id: null, success: false, error: 'ID required' });
          continue;
        }
        try {
          const { id, ...data } = item;
          await prisma.agentSkill.update({ where: { id }, data });
          results.push({ id, success: true });
        } catch (e) {
          results.push({ id: item.id, success: false, error: e.message });
        }
      }
      return results;
    },

    removeAgentSkills: async (_, { ids }, { prisma }) => {
      const results = [];
      for (const id of ids) {
        try {
          await prisma.agentSkill.delete({ where: { id } });
          results.push({ id, success: true });
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
        const task = await prisma.agentTask.create({
          data: {
            id: item.id || undefined,
            owner: item.owner || identity.sub,
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
        results.push({ id: task.id, success: true });
      }
      return results;
    },

    updateAgentTasks: async (_, { input }, { prisma }) => {
      const results = [];
      for (const item of input) {
        if (!item.id) {
          results.push({ id: null, success: false, error: 'ID required' });
          continue;
        }
        try {
          const { id, ...data } = item;
          await prisma.agentTask.update({ where: { id }, data });
          results.push({ id, success: true });
        } catch (e) {
          results.push({ id: item.id, success: false, error: e.message });
        }
      }
      return results;
    },

    removeAgentTasks: async (_, { ids }, { prisma }) => {
      const results = [];
      for (const id of ids) {
        try {
          await prisma.agentTask.delete({ where: { id } });
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
            owner: item.owner || identity.sub,
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

    updateVehicles: async (_, { input }, { prisma }) => {
      const results = [];
      for (const item of input) {
        if (!item.id) {
          results.push({ id: null, success: false, error: 'ID required' });
          continue;
        }
        try {
          const { id, ...data } = item;
          await prisma.vehicle.update({ where: { id }, data });
          results.push({ id, success: true });
        } catch (e) {
          results.push({ id: item.id, success: false, error: e.message });
        }
      }
      return results;
    },

    removeVehicles: async (_, { ids }, { prisma }) => {
      const results = [];
      for (const id of ids) {
        try {
          await prisma.vehicle.delete({ where: { id } });
          results.push({ id, success: true });
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
            owner: item.owner || identity.sub,
            prompt: item.prompt,
            version: item.version,
          },
        });
        results.push({ id: prompt.id, success: true });
      }
      return results;
    },

    updatePrompts: async (_, { input }, { prisma }) => {
      const results = [];
      for (const item of input) {
        if (!item.id) {
          results.push({ id: null, success: false, error: 'ID required' });
          continue;
        }
        try {
          const { id, ...data } = item;
          await prisma.prompt.update({ where: { id }, data });
          results.push({ id, success: true });
        } catch (e) {
          results.push({ id: item.id, success: false, error: e.message });
        }
      }
      return results;
    },

    removePrompts: async (_, { ids }, { prisma }) => {
      const results = [];
      for (const id of ids) {
        try {
          await prisma.prompt.delete({ where: { id } });
          results.push({ id, success: true });
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
            owner: item.owner || identity.sub,
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

    updateAvatars: async (_, { input }, { prisma }) => {
      const results = [];
      for (const item of input) {
        if (!item.id) {
          results.push({ id: null, success: false, error: 'ID required' });
          continue;
        }
        try {
          const { id, ...data } = item;
          await prisma.avatar.update({ where: { id }, data });
          results.push({ id, success: true });
        } catch (e) {
          results.push({ id: item.id, success: false, error: e.message });
        }
      }
      return results;
    },

    removeAvatars: async (_, { ids }, { prisma }) => {
      const results = [];
      for (const id of ids) {
        try {
          await prisma.avatar.delete({ where: { id } });
          results.push({ id, success: true });
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
            owner: item.owner || identity.sub,
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

    updateAgentKnowledges: async (_, { input }, { prisma }) => {
      const results = [];
      for (const item of input) {
        if (!item.id) {
          results.push({ id: null, success: false, error: 'ID required' });
          continue;
        }
        try {
          const { id, ...data } = item;
          await prisma.agentKnowledge.update({ where: { id }, data });
          results.push({ id, success: true });
        } catch (e) {
          results.push({ id: item.id, success: false, error: e.message });
        }
      }
      return results;
    },

    removeAgentKnowledges: async (_, { ids }, { prisma }) => {
      const results = [];
      for (const id of ids) {
        try {
          await prisma.agentKnowledge.delete({ where: { id } });
          results.push({ id, success: true });
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
            owner: item.owner || identity.sub,
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

    updateAgentTools: async (_, { input }, { prisma }) => {
      const results = [];
      for (const item of input) {
        if (!item.id) {
          results.push({ id: null, success: false, error: 'ID required' });
          continue;
        }
        try {
          const { id, ...data } = item;
          await prisma.agentTool.update({ where: { id }, data });
          results.push({ id, success: true });
        } catch (e) {
          results.push({ id: item.id, success: false, error: e.message });
        }
      }
      return results;
    },

    removeAgentTools: async (_, { ids }, { prisma }) => {
      const results = [];
      for (const id of ids) {
        try {
          await prisma.agentTool.delete({ where: { id } });
          results.push({ id, success: true });
        } catch (e) {
          results.push({ id, success: false, error: e.message });
        }
      }
      return results;
    },

    // ============ Settings ============
    updateSettings: async (_, { input }, { prisma }) => {
      for (const item of input) {
        const key = typeof item === 'string' ? item : item.key;
        const value = typeof item === 'string' ? {} : item.value || {};
        await prisma.setting.upsert({
          where: { key },
          create: { key, value },
          update: { value },
        });
      }
      return 'OK';
    },

    // ============ Skill Editor Events ============
    addSkillEditorEvent: async (_, { input }, { prisma, identity }) => {
      return prisma.skillEditorEvent.create({
        data: {
          owner: input.owner || identity.sub,
          sessionId: input.sessionId,
          flowgramId: input.flowgramId,
          eventType: input.eventType,
          payload: input.payload || {},
          timestamp: input.timestamp ? new Date(input.timestamp) : new Date(),
        },
      });
    },

    // ============ Relations ============
    addAgentSkillRels: async (_, { input }, { prisma }) => {
      for (const item of input) {
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

    updateAgentSkillRels: async (_, { input }, { prisma }) => {
      return resolvers.Mutation.addAgentSkillRels(_, { input }, { prisma });
    },

    removeAgentSkillRels: async (_, { input }, { prisma }) => {
      for (const item of input) {
        if (item.id) {
          await prisma.agentSkillRel.delete({ where: { id: item.id } });
        } else if (item.agentId && item.skillId) {
          await prisma.agentSkillRel.delete({
            where: { agentId_skillId: { agentId: item.agentId, skillId: item.skillId } },
          });
        }
      }
      return { success: true };
    },

    addAgentTaskRels: async (_, { input }, { prisma }) => {
      for (const item of input) {
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

    updateAgentTaskRels: async (_, { input }, { prisma }) => {
      return resolvers.Mutation.addAgentTaskRels(_, { input }, { prisma });
    },

    removeAgentTaskRels: async (_, { input }, { prisma }) => {
      for (const item of input) {
        if (item.id) {
          await prisma.agentTaskRel.delete({ where: { id: item.id } });
        } else if (item.agentId && item.taskId) {
          await prisma.agentTaskRel.delete({
            where: { agentId_taskId: { agentId: item.agentId, taskId: item.taskId } },
          });
        }
      }
      return { success: true };
    },

    addAgentOrgRels: async (_, { input }, { prisma }) => {
      for (const item of input) {
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

    updateAgentOrgRels: async (_, { input }, { prisma }) => {
      return resolvers.Mutation.addAgentOrgRels(_, { input }, { prisma });
    },

    removeAgentOrgRels: async (_, { input }, { prisma }) => {
      for (const item of input) {
        if (item.id) {
          await prisma.agentOrgRel.delete({ where: { id: item.id } });
        } else if (item.agentId && item.orgId) {
          await prisma.agentOrgRel.delete({
            where: { agentId_orgId: { agentId: item.agentId, orgId: item.orgId } },
          });
        }
      }
      return { success: true };
    },
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
  
  # Relations
  queryAgentSkillRels(input: JSON): [AgentSkillRel!]!
  queryAgentTaskRels(input: JSON): [AgentTaskRel!]!
  queryAgentOrgRels(input: JSON): [AgentOrgRel!]!
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
  uptimeSeconds: BigInt
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
    // 从 TCB 获取用户身份
    let identity = { sub: 'anonymous' };
    
    try {
      if (tcbApp) {
        const auth = tcbApp.auth();
        if (auth) {
          const userInfo = await auth.getUserInfo();
          if (userInfo && userInfo.uid) {
            identity = { sub: userInfo.uid };
          }
        }
      }
    } catch (e) {
      // TCB auth 不可用，使用 anonymous
    }
    
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
      body: event.body ? JSON.parse(event.body) : undefined,
    });
    
    const response = await yoga.fetch(request);
    const body = await response.text();
    
    return {
      statusCode: response.status,
      headers: Object.fromEntries(response.headers.entries()),
      body,
    };
  }
  
  // 事件触发
  return { message: 'TCB GraphQL API Ready' };
};
