/**
 * Entity resolvers (Query + Mutation): Agents / Skills / Tasks / Vehicles /
 * Orgs / Prompts / Avatars / Knowledges / Tools / Settings.
 *
 * Each entity follows the same pattern:
 *   Query  : get<Plural>  — paginated list with optional input filter
 *            query<Plural> — alias used by intl clients
 *   Mutation: add<Plural> / update<Plural> / remove<Plural>
 */

const { authenticatedOwner } = require('../auth');

// ============================================================
// Agents
// ============================================================
function agentsQuery(_, { input }, { prisma, identity }) {
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
}

async function addAgents(_, { input }, { prisma, identity }) {
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
}

async function updateAgents(_, { input }, { prisma, identity }) {
  const results = [];
  for (const item of input) {
    if (!item.id) { results.push({ id: null, success: false, error: 'ID required' }); continue; }
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
}

async function removeAgents(_, { ids }, { prisma, identity }) {
  const results = [];
  for (const id of ids) {
    try {
      const changed = await prisma.agent.deleteMany({ where: { id, owner: identity.sub } });
      results.push({ id, success: changed.count === 1, error: changed.count ? null : 'Not found' });
    } catch (e) { results.push({ id, success: false, error: e.message }); }
  }
  return results;
}

// ============================================================
// Skills
// ============================================================
function skillsQuery(_, { input }, { prisma, identity }) {
  return prisma.agentSkill.findMany({
    where: {
      owner: authenticatedOwner(identity, input?.owner),
      ...(input?.id && { id: input.id }),
      ...(input?.name && { name: { contains: input.name, mode: 'insensitive' } }),
    },
    orderBy: { createdAt: 'desc' },
    take: 50,
  });
}

async function addAgentSkills(_, { input }, { prisma, identity }) {
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
}

async function updateAgentSkills(_, { input }, { prisma, identity }) {
  const results = [];
  for (const item of input) {
    if (!item.id) { results.push({ id: null, success: false, error: 'ID required' }); continue; }
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
}

async function removeAgentSkills(_, { ids }, { prisma, identity }) {
  const results = [];
  for (const id of ids) {
    try {
      const changed = await prisma.agentSkill.deleteMany({ where: { id, owner: identity.sub } });
      results.push({ id, success: changed.count === 1, error: changed.count ? null : 'Not found' });
    } catch (e) { results.push({ id, success: false, error: e.message }); }
  }
  return results;
}

// ============================================================
// Tasks
// ============================================================
function tasksQuery(_, { input }, { prisma, identity }) {
  return prisma.agentTask.findMany({
    where: {
      owner: authenticatedOwner(identity, input?.owner),
      ...(input?.id && { id: input.id }),
      ...(input?.status && { status: input.status }),
    },
    orderBy: { createdAt: 'desc' },
    take: 50,
  });
}

async function addAgentTasks(_, { input }, { prisma, identity, getScheduler }) {
  const results = [];
  for (const item of input) {
    try {
      const owner = authenticatedOwner(identity, item.owner);
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
}

async function updateAgentTasks(_, { input }, { prisma, identity, getScheduler }) {
  const results = [];
  for (const item of input) {
    if (!item.id) { results.push({ id: null, success: false, error: 'ID required' }); continue; }
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
}

async function removeAgentTasks(_, { ids }, { prisma, identity, getScheduler }) {
  const results = [];
  for (const id of ids) {
    try {
      const task = await prisma.agentTask.findFirst({ where: { id, owner: identity.sub }, select: { id: true } });
      if (!task) { results.push({ id, success: false, error: 'Not found' }); continue; }
      try {
        await getScheduler().deleteTask(id);
      } catch (syncErr) {
        console.warn(`Scheduler delete failed for task ${id}:`, syncErr.message);
      }
      await prisma.agentTask.delete({ where: { id, owner: identity.sub } });
      results.push({ id, success: true });
    } catch (e) { results.push({ id, success: false, error: e.message }); }
  }
  return results;
}

// ============================================================
// Vehicles
// ============================================================
function vehiclesQuery(_, { input }, { prisma, identity }) {
  return prisma.vehicle.findMany({
    where: {
      owner: authenticatedOwner(identity, input?.owner),
      ...(input?.id && { id: input.id }),
    },
    orderBy: { createdAt: 'desc' },
    take: 50,
  });
}

async function addVehicles(_, { input }, { prisma, identity }) {
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
}

async function updateVehicles(_, { input }, { prisma, identity }) {
  const results = [];
  for (const item of input) {
    if (!item.id) { results.push({ id: null, success: false, error: 'ID required' }); continue; }
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
}

async function removeVehicles(_, { ids }, { prisma, identity }) {
  const results = [];
  for (const id of ids) {
    try {
      const changed = await prisma.vehicle.deleteMany({ where: { id, owner: identity.sub } });
      results.push({ id, success: changed.count === 1, error: changed.count ? null : 'Not found' });
    } catch (e) { results.push({ id, success: false, error: e.message }); }
  }
  return results;
}

// ============================================================
// Orgs
// ============================================================
function orgsQuery(_, { input }, { prisma }) {
  return prisma.org.findMany({
    where: {
      ...(input?.id && { id: input.id }),
      ...(input?.name && { name: { contains: input.name, mode: 'insensitive' } }),
      ...(input?.orgType && { orgType: input.orgType }),
      ...(input?.status && { status: input.status }),
    },
    orderBy: [{ sortOrder: 'asc' }, { level: 'asc' }],
  });
}

async function getOrgTree(_, { rootId }, { prisma }) {
  const buildTree = async (parentId) => {
    const orgs = await prisma.org.findMany({
      where: parentId ? { parentId } : { parentId: null },
      orderBy: [{ sortOrder: 'asc' }, { level: 'asc' }],
    });
    return Promise.all(orgs.map(async (org) => ({
      id: org.id, name: org.name, description: org.description, orgType: org.orgType,
      level: org.level, parentId: org.parentId, sortOrder: org.sortOrder, status: org.status,
      settings: org.settings, children: await buildTree(org.id), agents: [],
    })));
  };
  const tree = await buildTree(rootId || null);
  return tree[0] || null;
}

async function getOrgAgentTree(_, { rootId }, { prisma }) {
  const [orgs, agents] = await Promise.all([
    prisma.org.findMany({ orderBy: [{ sortOrder: 'asc' }, { level: 'asc' }] }),
    prisma.agent.findMany({ orderBy: { createdAt: 'desc' } }),
  ]);
  const buildTree = (parentId) => orgs
    .filter((o) => o.parentId === parentId)
    .map((org) => ({
      id: org.id, name: org.name, description: org.description, orgType: org.orgType,
      level: org.level, parentId: org.parentId, sortOrder: org.sortOrder, status: org.status,
      settings: org.settings, children: buildTree(org.id), agents: agents.filter((a) => a.orgId === org.id),
    }));
  const tree = buildTree(rootId || null);
  return tree[0] || null;
}

async function addOrgs(_, { input }, { prisma }) {
  const results = [];
  for (const item of input) {
    const org = await prisma.org.create({
      data: {
        id: item.id || undefined,
        name: item.name, description: item.description, orgType: item.orgType,
        parentId: item.parentId, level: item.level || 0, sortOrder: item.sortOrder || 0,
        status: item.status || 'active', settings: item.settings || {},
      },
    });
    results.push({ id: org.id, success: true });
  }
  return results;
}

async function updateOrgs(_, { input }, { prisma }) {
  const results = [];
  for (const item of input) {
    if (!item.id) { results.push({ id: null, success: false, error: 'ID required' }); continue; }
    try {
      const { id, ...data } = item;
      await prisma.org.update({ where: { id }, data });
      results.push({ id, success: true });
    } catch (e) {
      results.push({ id: item.id, success: false, error: e.message });
    }
  }
  return results;
}

async function removeOrgs(_, { ids }, { prisma }) {
  const results = [];
  for (const id of ids) {
    try {
      await prisma.org.delete({ where: { id } });
      results.push({ id, success: true });
    } catch (e) { results.push({ id, success: false, error: e.message }); }
  }
  return results;
}

// ============================================================
// Prompts
// ============================================================
function getPrompts(_, { owner }, { prisma, identity }) {
  return prisma.prompt.findMany({
    where: { owner: authenticatedOwner(identity, owner) },
    orderBy: { createdAt: 'desc' },
  });
}
function queryPrompts(_, { input }, { prisma, identity }) {
  return prisma.prompt.findMany({
    where: { owner: authenticatedOwner(identity, input?.owner) },
    orderBy: { createdAt: 'desc' },
  });
}

async function addPrompts(_, { input }, { prisma, identity }) {
  const results = [];
  for (const item of input) {
    const prompt = await prisma.prompt.create({
      data: { id: item.id || undefined, owner: authenticatedOwner(identity, item.owner), prompt: item.prompt, version: item.version },
    });
    results.push({ id: prompt.id, success: true });
  }
  return results;
}

async function updatePrompts(_, { input }, { prisma, identity }) {
  const results = [];
  for (const item of input) {
    if (!item.id) { results.push({ id: null, success: false, error: 'ID required' }); continue; }
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
}

async function removePrompts(_, { ids }, { prisma, identity }) {
  const results = [];
  for (const id of ids) {
    try {
      const changed = await prisma.prompt.deleteMany({ where: { id, owner: identity.sub } });
      results.push({ id, success: changed.count === 1, error: changed.count ? null : 'Not found' });
    } catch (e) { results.push({ id, success: false, error: e.message }); }
  }
  return results;
}

// ============================================================
// Avatars
// ============================================================
function avatarsQuery(_, args, { prisma, identity }) {
  return prisma.avatar.findMany({
    where: {
      owner: authenticatedOwner(identity, args?.owner),
      ...(args?.resourceType && { resourceType: args.resourceType }),
    },
    orderBy: { createdAt: 'desc' },
  });
}

async function addAvatars(_, { input }, { prisma, identity }) {
  const results = [];
  for (const item of input) {
    const avatar = await prisma.avatar.create({
      data: {
        id: item.id || undefined,
        owner: authenticatedOwner(identity, item.owner),
        name: item.name, description: item.description,
        resourceType: item.resourceType || 'image',
        imagePath: item.imagePath, videoPath: item.videoPath,
        imageHash: item.imageHash, videoHash: item.videoHash,
        cloudImageKey: item.cloudImageKey, cloudVideoKey: item.cloudVideoKey,
        cloudImageUrl: item.cloudImageUrl, cloudVideoUrl: item.cloudVideoUrl,
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
}

async function updateAvatars(_, { input }, { prisma, identity }) {
  const results = [];
  for (const item of input) {
    if (!item.id) { results.push({ id: null, success: false, error: 'ID required' }); continue; }
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
}

async function removeAvatars(_, { ids }, { prisma, identity }) {
  const results = [];
  for (const id of ids) {
    try {
      const changed = await prisma.avatar.deleteMany({ where: { id, owner: identity.sub } });
      results.push({ id, success: changed.count === 1, error: changed.count ? null : 'Not found' });
    } catch (e) { results.push({ id, success: false, error: e.message }); }
  }
  return results;
}

// ============================================================
// Knowledges
// ============================================================
function knowledgesQuery(_, args, { prisma, identity }) {
  return prisma.agentKnowledge.findMany({
    where: {
      owner: authenticatedOwner(identity, args?.owner),
      ...(args?.name && { name: { contains: args.name, mode: 'insensitive' } }),
    },
    orderBy: { createdAt: 'desc' },
  });
}

async function addAgentKnowledges(_, { input }, { prisma, identity }) {
  const results = [];
  for (const item of input) {
    const knowledge = await prisma.agentKnowledge.create({
      data: {
        id: item.id || undefined,
        owner: authenticatedOwner(identity, item.owner),
        name: item.name, description: item.description, content: item.content,
        knowledgeType: item.knowledgeType, categories: item.categories || [],
        tags: item.tags || [], accessMethods: item.accessMethods || [],
        limitations: item.limitations || [],
        level: item.level, price: item.price || 0, priceModel: item.priceModel,
        path: item.path,
        isPublic: item.isPublic ?? false, rentable: item.rentable ?? false,
        status: item.status || 'active',
        settings: item.settings || {}, config: item.config || {}, version: item.version,
      },
    });
    results.push({ id: knowledge.id, success: true });
  }
  return results;
}

async function updateAgentKnowledges(_, { input }, { prisma, identity }) {
  const results = [];
  for (const item of input) {
    if (!item.id) { results.push({ id: null, success: false, error: 'ID required' }); continue; }
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
}

async function removeAgentKnowledges(_, { ids }, { prisma, identity }) {
  const results = [];
  for (const id of ids) {
    try {
      const changed = await prisma.agentKnowledge.deleteMany({ where: { id, owner: identity.sub } });
      results.push({ id, success: changed.count === 1, error: changed.count ? null : 'Not found' });
    } catch (e) { results.push({ id, success: false, error: e.message }); }
  }
  return results;
}

// ============================================================
// Tools
// ============================================================
function toolsQuery(_, args, { prisma, identity }) {
  return prisma.agentTool.findMany({
    where: {
      owner: authenticatedOwner(identity, args?.owner),
      ...(args?.name && { name: { contains: args.name, mode: 'insensitive' } }),
    },
    orderBy: { createdAt: 'desc' },
  });
}

async function addAgentTools(_, { input }, { prisma, identity }) {
  const results = [];
  for (const item of input) {
    const tool = await prisma.agentTool.create({
      data: {
        id: item.id || undefined,
        owner: authenticatedOwner(identity, item.owner),
        name: item.name, description: item.description,
        toolType: item.toolType,
        capabilities: item.capabilities || [], limitations: item.limitations || [],
        dependencies: item.dependencies || [],
        settings: item.settings || {}, config: item.config || {},
        level: item.level, price: item.price || 0, priceModel: item.priceModel,
        path: item.path,
        isPublic: item.isPublic ?? false, rentable: item.rentable ?? false,
        status: item.status || 'active', version: item.version,
      },
    });
    results.push({ id: tool.id, success: true });
  }
  return results;
}

async function updateAgentTools(_, { input }, { prisma, identity }) {
  const results = [];
  for (const item of input) {
    if (!item.id) { results.push({ id: null, success: false, error: 'ID required' }); continue; }
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
}

async function removeAgentTools(_, { ids }, { prisma, identity }) {
  const results = [];
  for (const id of ids) {
    try {
      const changed = await prisma.agentTool.deleteMany({ where: { id, owner: identity.sub } });
      results.push({ id, success: changed.count === 1, error: changed.count ? null : 'Not found' });
    } catch (e) { results.push({ id, success: false, error: e.message }); }
  }
  return results;
}

// ============================================================
// Settings
// ============================================================
function getSettings(_, { ids, username }, { prisma, identity }) {
  const owner = authenticatedOwner(identity, username);
  return prisma.setting.findMany({
    where: ids?.length
      ? { id: { in: ids }, owner: { in: [owner, '__global__'] } }
      : { owner: { in: [owner, '__global__'] } },
  });
}

async function updateSettings(_, { input }, { prisma, identity }) {
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
}

module.exports = {
  Query: {
    getAgents: agentsQuery,
    queryAgents: agentsQuery,
    getAgentSkills: skillsQuery,
    queryAgentSkills: skillsQuery,
    getAgentTasks: tasksQuery,
    queryAgentTasks: tasksQuery,
    getVehicles: vehiclesQuery,
    queryVehicles: vehiclesQuery,
    getOrgs: orgsQuery,
    queryOrgs: orgsQuery,
    getOrgTree,
    getOrgAgentTree,
    getPrompts,
    queryPrompts,
    getAvatars: avatarsQuery,
    queryAvatars: avatarsQuery,
    getAgentKnowledges: knowledgesQuery,
    queryAgentKnowledges: knowledgesQuery,
    getAgentTools: toolsQuery,
    queryAgentTools: toolsQuery,
    getSettings,
  },
  Mutation: {
    addAgents, updateAgents, removeAgents,
    addAgentSkills, updateAgentSkills, removeAgentSkills,
    addAgentTasks, updateAgentTasks, removeAgentTasks,
    addVehicles, updateVehicles, removeVehicles,
    addOrgs, updateOrgs, removeOrgs,
    addPrompts, updatePrompts, removePrompts,
    addAvatars, updateAvatars, removeAvatars,
    addAgentKnowledges, updateAgentKnowledges, removeAgentKnowledges,
    addAgentTools, updateAgentTools, removeAgentTools,
    updateSettings,
  },
};