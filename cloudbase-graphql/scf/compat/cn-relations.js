function parseJson(value, fallback = {}) {
  if (value == null || value === '') return fallback;
  if (typeof value === 'object') return value;
  try { return JSON.parse(value); } catch { return fallback; }
}

function parseIds(value) {
  const parsed = parseJson(value, value);
  if (Array.isArray(parsed)) return parsed.map(String);
  if (parsed && typeof parsed === 'object') return Object.values(parsed).flat().map(String);
  return String(parsed || '').split(',').map((id) => id.trim()).filter(Boolean);
}

const definitions = {
  AgentSkill: {
    model: 'agentSkillRel', ownerPath: 'agent', unique: 'agentId_skillId', keys: ['agentId', 'skillId'],
    input: (v) => ({ agentId: v.agid, skillId: v.skid, status: v.status || 'active', proficiencyLevel: v.proficiency || 0, config: parseJson(v.langgraph, {}) }),
    output: (v) => ({ ...v, agid: v.agentId, skid: v.skillId, proficiency: v.proficiencyLevel, langgraph: v.config }),
  },
  AgentTask: {
    model: 'agentTaskRel', ownerPath: 'agent', unique: 'agentId_taskId', keys: ['agentId', 'taskId'],
    input: (v) => ({ agentId: v.agid, taskId: v.task_id, vehicleId: v.vehicle_id, status: v.status || 'assigned', scheduledStart: v.assigned_at ? new Date(v.assigned_at) : undefined, actualStart: v.started_at ? new Date(v.started_at) : undefined, actualEnd: v.completed_at ? new Date(v.completed_at) : undefined }),
    output: (v) => ({ ...v, agid: v.agentId, task_id: v.taskId, vehicle_id: v.vehicleId }),
  },
  AgentTool: {
    model: 'agentToolRel', ownerPath: 'agent', unique: 'agentId_toolId', keys: ['agentId', 'toolId'],
    input: (v) => ({ agentId: v.agid, toolId: v.tool_id, permission: v.permission, grantedAt: v.granted_at ? new Date(v.granted_at) : undefined }),
    output: (v) => ({ ...v, agid: v.agentId, tool_id: v.toolId, granted_at: v.grantedAt }),
  },
  SkillTool: {
    model: 'agentSkillToolRel', ownerPath: 'skill', unique: 'skillId_toolId', keys: ['skillId', 'toolId'],
    input: (v) => ({ skillId: v.skill_id, toolId: v.tool_id, dependencyType: v.usage_type, status: v.required === false ? 'optional' : 'active' }),
    output: (v) => ({ ...v, skill_id: v.skillId, tool_id: v.toolId, usage_type: v.dependencyType, required: v.status !== 'optional' }),
  },
  SkillKnowledge: {
    model: 'agentSkillKnowledgeRel', ownerPath: 'skill', unique: 'skillId_knowledgeId', keys: ['skillId', 'knowledgeId'],
    input: (v) => ({ skillId: v.skill_id, knowledgeId: v.knowledge_id, dependencyType: v.dependency_type, usageFrequency: Number(v.usage_frequency || 0), importance: v.importance || 0, accessPattern: v.access_pattern, knowledgeScope: parseJson(v.knowledge_scope, {}) }),
    output: (v) => ({ ...v, skill_id: v.skillId, knowledge_id: v.knowledgeId, dependency_type: v.dependencyType, usage_frequency: String(v.usageFrequency), access_pattern: v.accessPattern, knowledge_scope: v.knowledgeScope }),
  },
  TaskSkill: {
    model: 'agentTaskSkillRel', ownerPath: 'task', unique: 'taskId_skillId', keys: ['taskId', 'skillId'],
    input: (v) => ({ taskId: v.task_id, skillId: v.skill_id, isRequired: v.required !== false, qualityThreshold: v.proficiency_required }),
    output: (v) => ({ ...v, task_id: v.taskId, skill_id: v.skillId, required: v.isRequired, proficiency_required: v.qualityThreshold }),
  },
};

function ownershipWhere(definition, owner) { return { [definition.ownerPath]: { owner } }; }

async function queryRelation(prisma, identity, definitionName, { ids, qb }) {
  const definition = definitions[definitionName];
  const query = parseJson(qb, {});
  const idList = parseIds(ids);
  const mapped = definition.input(query);
  const keyFilter = Object.fromEntries(definition.keys.filter((key) => mapped[key]).map((key) => [key, mapped[key]]));
  const rows = await prisma[definition.model].findMany({
    where: { ...ownershipWhere(definition, identity.sub), ...(idList.length ? { id: { in: idList } } : {}), ...keyFilter },
    take: 200,
  });
  return JSON.stringify(rows.map(definition.output));
}

async function upsertRelations(prisma, identity, definitionName, input) {
  const definition = definitions[definitionName];
  const results = [];

  // 解析并验证所有输入
  const validInputs = [];
  for (const raw of input || []) {
    if (raw.owner && raw.owner !== identity.sub) {
      results.push({ success: false, error: 'Cross-owner access is forbidden' });
      continue;
    }
    const data = definition.input(raw);
    if (definition.keys.some((key) => !data[key])) {
      results.push({ success: false, error: `Missing ${definition.keys.join('/')}` });
      continue;
    }
    validInputs.push({ raw, data });
  }

  if (validInputs.length === 0) {
    return JSON.stringify(results);
  }

  // 收集所有需要检查的 owner ID（去重）
  const ownerModel = definition.ownerPath === 'agent' ? 'agent' : definition.ownerPath === 'skill' ? 'agentSkill' : 'agentTask';
  const ownerIds = [...new Set(validInputs.map(({ data }) => data[definition.keys[0]]))];

  // 批量查询已拥有的 owner 记录
  const ownedRecords = await prisma[ownerModel].findMany({
    where: { id: { in: ownerIds }, owner: identity.sub },
    select: { id: true },
  });
  const ownedSet = new Set(ownedRecords.map((r) => r.id));

  // 过滤出有效的输入（owner 已拥有）
  const validForUpsert = [];
  for (const { raw, data } of validInputs) {
    const ownerId = data[definition.keys[0]];
    if (!ownedSet.has(ownerId)) {
      results.push({ success: false, error: 'Owned parent not found' });
      continue;
    }
    validForUpsert.push({ raw, data });
  }

  if (validForUpsert.length === 0) {
    return JSON.stringify(results);
  }

  // 使用事务批量执行 upsert
  const upsertResults = await prisma.$transaction(
    validForUpsert.map(({ data }) => {
      const unique = Object.fromEntries(definition.keys.map((key) => [key, data[key]]));
      return prisma[definition.model].upsert({
        where: { [definition.unique]: unique },
        create: data,
        update: data,
      });
    })
  );

  // 收集结果
  for (const row of upsertResults) {
    results.push({ id: row.id, success: true });
  }

  return JSON.stringify(results);
}

async function removeRelations(prisma, identity, definitionName, input) {
  const definition = definitions[definitionName];
  const results = [];
  for (const raw of input || []) {
    if (raw.owner && raw.owner !== identity.sub) { results.push({ id: raw.oid, success: false, error: 'Cross-owner access is forbidden' }); continue; }
    const changed = await prisma[definition.model].deleteMany({ where: { id: String(raw.oid), ...ownershipWhere(definition, identity.sub) } });
    results.push({ id: raw.oid, success: changed.count === 1, error: changed.count ? null : 'Not found' });
  }
  return JSON.stringify(results);
}

module.exports = { definitions, parseIds, parseJson, queryRelation, removeRelations, upsertRelations };
