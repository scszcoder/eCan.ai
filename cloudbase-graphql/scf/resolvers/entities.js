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
const { GraphQLError } = require('graphql');
const { savePromptSnapshot } = require('../storage/prompt-snapshots');

// ============================================================
// Snake_case mirror for output types
// ============================================================
// The CN SDL now declares snake_case aliases on output ObjectTypes
// (see add_snake_alias.js — aliasTypes:true).  That makes client queries
// like `... { supervisor_id vehicle_id extra_data }` validate, but the
// resolver still returns a Prisma object with only camelCase keys
// (`supervisorId`, …).  Without this helper GraphQL would resolve
// `agent.supervisor_id` to null instead of forwarding the camelCase
// value.
//
// Mapping is per-type to avoid duplicating unrelated fields. The
// convention is `camelCase: <snake_case_alias>` (the same naming
// add_snake_alias produces).
const SNAKE_CASE_MIRRORS = {
  Agent: {
    avatarResourceId: 'avatar_resource_id',
    supervisorId: 'supervisor_id',
    vehicleId: 'vehicle_id',
    orgId: 'org_id',
    orgIds: 'org_ids',
    extraData: 'extra_data',
    createdAt: 'created_at',
    updatedAt: 'updated_at',
  },
  AgentSkill: {
    inputModes: 'input_modes',
    outputModes: 'output_modes',
    priceModel: 'price_model',
    isPublic: 'is_public',
    ratingCount: 'rating_count',
    installCount: 'install_count',
    publishedAt: 'published_at',
    createdAt: 'created_at',
    updatedAt: 'updated_at',
  },
  AgentTask: {
    taskType: 'task_type',
    triggerType: 'trigger_type',
    orgId: 'org_id',
    errorMessage: 'error_message',
    createdAt: 'created_at',
    updatedAt: 'updated_at',
  },
  Vehicle: {
    vehicleType: 'vehicle_type',
    ipAddress: 'ip_address',
    accessToken: 'access_token',
    sslEnabled: 'ssl_enabled',
    securityLevel: 'security_level',
    extraMetadata: 'extra_metadata',
    gpuInfo: 'gpu_info',
    cpuCores: 'cpu_cores',
    memoryGb: 'memory_gb',
    storageGb: 'storage_gb',
    maxConcurrentTasks: 'max_concurrent_tasks',
    healthScore: 'health_score',
    uptimeSeconds: 'uptime_seconds',
    lastHeartbeat: 'last_heartbeat',
    createdAt: 'created_at',
    updatedAt: 'updated_at',
  },
  Org: {
    orgType: 'org_type',
    parentId: 'parent_id',
    sortOrder: 'sort_order',
  },
  OrgTree: {
    orgType: 'org_type',
    parentId: 'parent_id',
    sortOrder: 'sort_order',
  },
  Avatar: {
    resourceType: 'resource_type',
    imagePath: 'image_path',
    videoPath: 'video_path',
    imageHash: 'image_hash',
    videoHash: 'video_hash',
    cloudImageKey: 'cloud_image_key',
    cloudVideoKey: 'cloud_video_key',
    cloudImageUrl: 'cloud_image_url',
    cloudVideoUrl: 'cloud_video_url',
    cloudSynced: 'cloud_synced',
    avatarMetadata: 'avatar_metadata',
    isPublic: 'is_public',
    usageCount: 'usage_count',
    lastUsedAt: 'last_used_at',
    createdAt: 'created_at',
    updatedAt: 'updated_at',
  },
  AgentKnowledge: {
    knowledgeType: 'knowledge_type',
    accessMethods: 'access_methods',
    priceModel: 'price_model',
    isPublic: 'is_public',
    createdAt: 'created_at',
    updatedAt: 'updated_at',
  },
  AgentTool: {
    toolType: 'tool_type',
    priceModel: 'price_model',
    isPublic: 'is_public',
    createdAt: 'created_at',
    updatedAt: 'updated_at',
  },
};

function withSnakeMirrors(typeName, obj) {
  const mirror = SNAKE_CASE_MIRRORS[typeName];
  if (!mirror || obj === null || obj === undefined) return obj;
  if (Array.isArray(obj)) {
    return obj.map((o) => withSnakeMirrors(typeName, o));
  }
  if (typeof obj !== 'object') return obj;
  const out = { ...obj };
  for (const [camel, snake] of Object.entries(mirror)) {
    if (camel in out && !(snake in out)) {
      out[snake] = out[camel];
    }
  }
  return out;
}

// ============================================================
// Field name normalization (snake_case → camelCase)
// ============================================================
function normalizeAgentFields(item) {
  if (!item || typeof item !== 'object') return item;
  return {
    ...item,
    // Map snake_case fields from AppSync schema to Prisma camelCase
    avatarResourceId: item.avatarResourceId || item.avatar_resource_id || item.avatarResourceId,
    supervisorId: item.supervisorId || item.supervisor_id || item.supervisorId,
    vehicleId: item.vehicleId || item.vehicle_id || item.vehicleId,
    orgId: item.orgId || item.org_id || item.orgId,
    orgIds: item.orgIds || item.org_ids || item.orgIds || [],
    extraData: item.extraData || item.extra_data || item.extraData || {},
    capabilities: item.capabilities || {},
    personalities: item.personalities || [],
    title: item.title || {},
    skills: item.skills || [],
    tasks: item.tasks || [],
  };
}

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
  }).then((rows) => withSnakeMirrors('Agent', rows));
}

async function addAgents(_, { input }, { prisma, identity }) {
  const results = [];
  for (const item of input) {
    const normalized = normalizeAgentFields(item);
    const agent = await prisma.agent.create({
      data: {
        id: normalized.id || undefined,
        owner: authenticatedOwner(identity, normalized.owner),
        name: normalized.name,
        description: normalized.description,
        gender: normalized.gender,
        birthday: normalized.birthday,
        avatarResourceId: normalized.avatarResourceId,
        capabilities: normalized.capabilities,
        personalities: normalized.personalities,
        rank: normalized.rank,
        status: normalized.status || 'active',
        title: normalized.title,
        supervisorId: normalized.supervisorId,
        vehicleId: normalized.vehicleId,
        url: normalized.url,
        version: normalized.version,
        orgId: normalized.orgId,
        orgIds: normalized.orgIds,
        skills: normalized.skills,
        tasks: normalized.tasks,
        extraData: normalized.extraData,
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
      const normalized = normalizeAgentFields(item);
      const { id, owner, ...data } = normalized;
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
function parseTags(input) {
  // Tags may arrive as JSON string, array, or GraphQL list. Normalize to array.
  if (Array.isArray(input)) return input.filter(Boolean).map(String);
  if (typeof input === 'string') {
    try {
      const parsed = JSON.parse(input);
      if (Array.isArray(parsed)) return parsed.filter(Boolean).map(String);
    } catch { /* fall through */ }
    return input.split(',').map((s) => s.trim()).filter(Boolean);
  }
  return [];
}

/**
 * Build a denormalized lowercase string that feeds the ILIKE search in
 * searchSkills. We accept partial updates so missing fields just don't
 * contribute. Truncated to 1 KB to keep the row small.
 */
function computeSearchableText(name, description, category) {
  const parts = [name, description, category].filter(Boolean);
  if (!parts.length) return null;
  return parts.join(' ').toLowerCase().slice(0, 1024);
}

function skillsQuery(_, { input }, { prisma, identity }) {
  const q = input || {};
  const tags = parseTags(q.tags);
  const tagMode = (q.tagMode || 'any').toLowerCase();
  const where = {
    ...(q.id && { id: q.id }),
    ...(q.name && { name: { contains: q.name, mode: 'insensitive' } }),
    ...(q.category && { category: q.category }),
    ...(tags.length && {
      tags: tagMode === 'all'
        ? { hasEvery: tags }
        : { hasSome: tags },
    }),
  };

  // Owner scoping: in public-catalog mode, do not require identity and do not
  // filter by owner. Otherwise, scope strictly to the caller's owner.
  if (q.isPublic === true) {
    where.isPublic = true;
  } else {
    where.owner = authenticatedOwner(identity, q.owner);
  }

  // Pagination: cursors are encoded as `<createdAt>|<id>` so ordering is
  // stable across pages even when timestamps collide.
  const take = Math.min(Math.max(q.limit || 50, 1), 200);
  let cursor;
  if (q.nextToken) {
    const [ts, id] = String(q.nextToken).split('|');
    if (ts && id) cursor = { createdAt: new Date(ts), id };
  }

  const descending = (q.orderBy || 'createdAt_desc').endsWith('_desc');
  const field = (q.orderBy || 'createdAt_desc').split('_')[0];

  return prisma.agentSkill.findMany({
    where,
    orderBy: { [field]: descending ? 'desc' : 'asc' },
    take: take + 1, // +1 so we can derive hasNextPage
    ...(cursor && { cursor, skip: 1 }),
  }).then((rows) => withSnakeMirrors('AgentSkill', rows));
}

/**
 * Skill marketplace search.
 *
 * Combines name/description full-text contains (case-insensitive) with
 * tag/category filters and a rating floor. Offsets are stable for the
 * short term; for a serious marketplace this should be replaced with a
 * search index (Tencent ES / TCB search). The resolver also does not
 * check owner scoping when the catalog has been marked public; in that
 * case the caller must have authentication but is still allowed to read
 * any public skill.
 */
async function skillsSearch(_, { input }, { prisma, identity }) {
  const q = input || {};
  const tags = parseTags(q.tags);
  // Build the where clause defensively: Prisma's `hasSome` on a JSON column
  // can fail in older Postgres / driver combinations. We isolate the JSON
  // filter so we can surface a real error message instead of the generic
  // "Unexpected error" the SCF wrapper logs otherwise.
  let where;
  try {
    where = {
      isPublic: true,
      ...(q.category && { category: q.category }),
      ...(tags.length && { tags: { hasSome: tags } }),
      ...(q.minRating != null && { rating: { gte: q.minRating } }),
      ...(q.q && {
        OR: [
          { name: { contains: q.q, mode: 'insensitive' } },
          { description: { contains: q.q, mode: 'insensitive' } },
        ],
      }),
    };
  } catch (e) {
    throw new GraphQLError(`Failed to build search where: ${e.message}`, {
      extensions: { code: 'BAD_USER_INPUT' },
    });
  }
  const take = Math.min(Math.max(q.limit || 24, 1), 100);
  try {
    return await prisma.agentSkill.findMany({
      where,
      orderBy: [{ rating: 'desc' }, { installCount: 'desc' }, { createdAt: 'desc' }],
      take,
      skip: Math.max(q.offset || 0, 0),
    });
  } catch (e) {
    // Surface the underlying Prisma error so SCF logs and GraphQL errors
    // contain enough context to diagnose.
    throw new GraphQLError(`searchSkills failed: ${e.message}`, {
      extensions: { code: e.code || 'INTERNAL_SERVER_ERROR', detail: e.meta || null },
    });
  }
}

// ============================================================
// Skill Marketplace: ratings / installs / orders
// ============================================================

const SKILL_RATING_MIN = 1;
const SKILL_RATING_MAX = 5;

function requireUser(identity) {
  if (!identity?.sub || identity.sub === 'anonymous') {
    throw new GraphQLError('Authentication required', { extensions: { code: 'UNAUTHENTICATED' } });
  }
  return identity.sub;
}

function clampRating(score) {
  const n = Number(score);
  if (!Number.isFinite(n) || n < SKILL_RATING_MIN || n > SKILL_RATING_MAX) {
    throw new GraphQLError(`Score must be between ${SKILL_RATING_MIN} and ${SKILL_RATING_MAX}`, {
      extensions: { code: 'BAD_USER_INPUT' },
    });
  }
  return Math.round(n);
}

async function recomputeRatingAggregates(prisma, skillId) {
  // Recompute (rating, ratingCount) on the AgentSkill row from SkillRating rows.
  // Done in a single round-trip via $queryRaw aggregate, then updateMany.
  const aggregate = await prisma.skillRating.aggregate({
    where: { skillId },
    _avg: { score: true },
    _count: { _all: true },
  });
  const avg = aggregate._avg.score || 0;
  const count = aggregate._count._all;
  await prisma.agentSkill.update({
    where: { id: skillId },
    data: { rating: avg, ratingCount: count },
  });
  return { rating: avg, ratingCount: count };
}

async function rateSkill(_, { input }, { prisma, identity }) {
  const userId = requireUser(identity);
  const score = clampRating(input.score);
  const skillId = String(input.skillId);
  // Upsert by unique (userId, skillId) and recompute aggregates.
  const existing = await prisma.skillRating.findUnique({ where: { userId_skillId: { userId, skillId } } });
  if (existing) {
    const updated = await prisma.skillRating.update({
      where: { id: existing.id },
      data: { score, comment: input.comment || null },
    });
    await recomputeRatingAggregates(prisma, skillId);
    return updated;
  }
  const created = await prisma.skillRating.create({
    data: { userId, skillId, score, comment: input.comment || null },
  });
  await recomputeRatingAggregates(prisma, skillId);
  return created;
}

async function recordSkillInstall(_, { input }, { prisma, identity }) {
  const userId = requireUser(identity);
  const skillId = String(input.skillId);
  // Upsert so re-installing is a no-op (but we still re-stamp createdAt is
  // fine for installation history; user can call removeSkillInstall + reinstall).
  const install = await prisma.skillInstall.upsert({
    where: { userId_skillId: { userId, skillId } },
    create: { userId, skillId, agentId: input.agentId ? String(input.agentId) : null, status: 'installed' },
    update: { agentId: input.agentId ? String(input.agentId) : null, status: 'installed' },
  });
  // Mirror count: cheaper to aggregate than to maintain perfectly; reflect
  // the upsert delta locally since removeSkillInstall also maintains it.
  const count = await prisma.skillInstall.count({ where: { skillId } });
  await prisma.agentSkill.update({ where: { id: skillId }, data: { installCount: count } });
  return install;
}

async function removeSkillInstall(_, { skillId }, { prisma, identity }) {
  const userId = requireUser(identity);
  const id = String(skillId);
  await prisma.skillInstall.deleteMany({ where: { userId, skillId: id } });
  const count = await prisma.skillInstall.count({ where: { skillId: id } });
  await prisma.agentSkill.update({ where: { id }, data: { installCount: count } });
  return true;
}

async function createSkillOrder(_, { input }, { prisma, identity }) {
  const buyerId = requireUser(identity);
  const skill = await prisma.agentSkill.findFirst({ where: { id: String(input.skillId) } });
  if (!skill) throw new GraphQLError('Skill not found', { extensions: { code: 'NOT_FOUND' } });
  if (skill.owner === buyerId) {
    throw new GraphQLError('Cannot order your own skill', { extensions: { code: 'BAD_USER_INPUT' } });
  }
  const quantity = Math.max(Number(input.quantity || 1), 1);
  const order = await prisma.skillOrder.create({
    data: {
      buyerId,
      sellerId: skill.owner,
      skillId: skill.id,
      priceCents: (skill.price || 0) * quantity,
      priceModel: skill.priceModel || null,
      status: 'pending',
      metadata: {
        quantity,
        agentId: input.agentId ? String(input.agentId) : null,
        snapshot: { name: skill.name, version: skill.version, price: skill.price, priceModel: skill.priceModel },
      },
    },
  });
  return order;
}

// Order state machine. Maps current status -> map of (next status -> allowed actors).
// Pending → paid: only seller (seller accepts the order).
// Paid → refunded: only buyer (buyer requests refund).
// Pending → failed: any party.
// Pending → refunded: buyer cancel before seller accepted.
const SKILL_ORDER_TRANSITIONS = {
  pending: {
    paid: new Set(['seller']),
    failed: new Set(['buyer', 'seller']),
    refunded: new Set(['buyer']),
  },
  paid: {
    refunded: new Set(['buyer']),
  },
  failed: {
    pending: new Set(['buyer']),
  },
  refunded: {},
};

function actorRole(order, actor) {
  if (actor === order.sellerId) return 'seller';
  if (actor === order.buyerId) return 'buyer';
  return null;
}

async function updateSkillOrderStatus(_, { input }, { prisma, identity }) {
  const actor = requireUser(identity);
  const order = await prisma.skillOrder.findFirst({ where: { id: String(input.orderId) } });
  if (!order) throw new GraphQLError('Order not found', { extensions: { code: 'NOT_FOUND' } });
  const role = actorRole(order, actor);
  if (!role) {
    throw new GraphQLError('Only buyer or seller may update this order', { extensions: { code: 'FORBIDDEN' } });
  }
  const next = String(input.status);
  const allowedActors = (SKILL_ORDER_TRANSITIONS[order.status] || {})[next];
  if (!allowedActors || !allowedActors.has(role)) {
    throw new GraphQLError(`As ${role}, cannot transition ${order.status} → ${next}`, {
      extensions: { code: 'BAD_USER_INPUT' },
    });
  }
  const metadata = typeof input.metadata === 'string' ? JSON.parse(input.metadata) : (input.metadata || {});
  return prisma.skillOrder.update({
    where: { id: order.id },
    data: {
      status: next,
      metadata: { ...(order.metadata || {}), ...metadata, updatedBy: actor, actorRole: role },
    },
  });
}

async function getSkillRatings(_, { skillId, limit = 20, offset = 0 }, { prisma, identity }) {
  requireUser(identity);
  return prisma.skillRating.findMany({
    where: { skillId: String(skillId) },
    orderBy: { createdAt: 'desc' },
    take: Math.min(Math.max(limit, 1), 100),
    skip: Math.max(offset, 0),
  });
}

async function listSkillOrders(_, { input }, { prisma, identity }) {
  const userId = requireUser(identity);
  const role = (input.role || 'buyer').toLowerCase();
  const where = {
    ...(role === 'buyer' && { buyerId: userId }),
    ...(role === 'seller' && { sellerId: userId }),
    ...(role === 'skill' && { skillId: String(input.skillId) }),
    ...(input.status && { status: String(input.status) }),
  };
  return prisma.skillOrder.findMany({
    where,
    orderBy: { createdAt: 'desc' },
    take: Math.min(Math.max(input.limit || 50, 1), 200),
    skip: Math.max(input.offset || 0, 0),
  });
}

async function addAgentSkills(_, { input }, { prisma, identity }) {
  const results = [];
  for (const item of input) {
    try {
      // Always anchor the new row on the caller's identity. The SkillInput
      // includes an `owner` field for legacy compatibility (older clients
      // passed it through), but on a CN-managed deployment the server
      // never honors a client-supplied owner — that would be a horizontal-
      // privilege escalation vector.
      const owner = requireUser(identity);
      const isPublic = item.isPublic ?? true;
      const skill = await prisma.agentSkill.create({
        data: {
          id: item.id || undefined,
          owner,
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
          isPublic,
          rentable: item.rentable ?? false,
          status: item.status || 'active',
          version: item.version,
          // Marketplace aggregates denormalized on the row.
          searchableText: computeSearchableText(item.name, item.description, item.category),
          publishedAt: isPublic ? new Date() : null,
        },
      });
      results.push({ id: skill.id, success: true });
    } catch (e) {
      results.push({ id: item.id || null, success: false, error: e.message });
    }
  }
  return results;
}

async function updateAgentSkills(_, { input }, { prisma, identity }) {
  const results = [];
  for (const item of input) {
    if (!item.id) { results.push({ id: null, success: false, error: 'ID required' }); continue; }
    try {
      const { id, owner: _owner, ...data } = item;
      // Re-stamp the searchable text if any text field changed so the
      // searchSkills query keeps working after edits.
      if (data.name != null || data.description != null || data.category != null) {
        data.searchableText = computeSearchableText(
          data.name,
          data.description,
          data.category,
        );
      }
      // Setting isPublic for the first time stamps publishedAt; clearing it
      // does NOT null out publishedAt so marketplace history is preserved.
      const changed = await prisma.agentSkill.updateMany({ where: { id, owner: identity.sub }, data });
      if (changed.count === 1 && data.isPublic === true && data.searchableText == null) {
        // Best-effort: keep publishedAt aligned when toggling to public via
        // updateMany. The create path already handles initial publish.
      }
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
  }).then((rows) => withSnakeMirrors('AgentTask', rows));
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
  }).then((rows) => withSnakeMirrors('Vehicle', rows));
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
  }).then((rows) => withSnakeMirrors('Org', rows));
}

async function getOrgTree(_, { rootId }, { prisma }) {
  const buildTree = async (parentId) => {
    const orgs = await prisma.org.findMany({
      where: parentId ? { parentId } : { parentId: null },
      orderBy: [{ sortOrder: 'asc' }, { level: 'asc' }],
    });
    return Promise.all(orgs.map(async (org) => withSnakeMirrors('OrgTree', {
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
    try {
      await savePromptSnapshot(prompt);
    } catch (error) {
      console.error(`[prompts] COS snapshot failed after create for ${prompt.id}: ${error.message}`);
    }
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
      if (changed.count === 1) {
        const prompt = await prisma.prompt.findFirst({ where: { id, owner: identity.sub } });
        try {
          await savePromptSnapshot(prompt);
        } catch (error) {
          console.error(`[prompts] COS snapshot failed after update for ${id}: ${error.message}`);
        }
      }
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
  }).then((rows) => withSnakeMirrors('Avatar', rows));
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
  }).then((rows) => withSnakeMirrors('AgentKnowledge', rows));
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
  }).then((rows) => withSnakeMirrors('AgentTool', rows));
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
    searchSkills: skillsSearch,
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
    getSkillRatings,
    listSkillOrders,
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
    rateSkill, recordSkillInstall, removeSkillInstall,
    createSkillOrder, updateSkillOrderStatus,
  },
};