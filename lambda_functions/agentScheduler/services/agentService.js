// MySQL/Aurora agent service backed by the RDS Data API.
// Mirrors the Python-side agent model/service semantics where possible.
const crypto = require("crypto");
const { execute } = require("../db/rdsClient");
const { checkAvatarExists } = require("./avatarService");

const JSON_FIELDS = ["personalities", "capabilities", "title", "extra_data", "permissions", "execution_context", "result"];

function genId() {
  return `agent_${crypto.randomBytes(8).toString("hex")}`;
}

function toDbParam(name, value) {
  if (value === null || value === undefined) {
    return { name, value: { isNull: true } };
  }
  if (typeof value === "number") {
    return { name, value: { doubleValue: value } };
  }
  return { name, value: { stringValue: String(value) } };
}

function safeJsonStringify(value, fallback = "[]") {
  try {
    if (value === null || value === undefined) return fallback;
    return JSON.stringify(value);
  } catch (e) {
    return fallback;
  }
}

function parseFieldValue(field) {
  if (!field) return null;
  if (field.stringValue !== undefined) return field.stringValue;
  if (field.longValue !== undefined) return field.longValue;
  if (field.doubleValue !== undefined) return field.doubleValue;
  if (field.booleanValue !== undefined) return field.booleanValue;
  return null;
}

function rowsToObjects(result) {
  // Normalize column names to lower-case so GraphQL field resolvers match even if
  // the RDS column metadata comes back in upper-case.
  const cols = result.columnMetadata?.map((c) => (c.name || "").toLowerCase()) || [];
  return (result.records || []).map((row) => {
    const obj = {};
    cols.forEach((col, idx) => {
      obj[col] = parseFieldValue(row[idx]);
      if (JSON_FIELDS.includes(col) && typeof obj[col] === "string") {
        try {
          obj[col] = JSON.parse(obj[col]);
        } catch (e) {
          // leave as string if parsing fails
        }
      }
    });
    return obj;
  });
}

/**
 * Convert MySQL datetime string to ISO 8601 format for GraphQL serialization
 */
function toISODateTime(val) {
  if (!val) return null;
  if (typeof val !== 'string') return val;
  // Check if already ISO format
  if (val.includes('T')) return val;
  // Convert MySQL format "YYYY-MM-DD HH:MM:SS.ffffff" to ISO "YYYY-MM-DDTHH:MM:SS.ffffffZ"
  return val.replace(' ', 'T') + 'Z';
}

/**
 * Normalize datetime fields in an agent object for GraphQL serialization
 */
function normalizeAgentDatetimes(agent) {
  if (!agent) return agent;
  if (agent.created_at) agent.created_at = toISODateTime(agent.created_at);
  if (agent.updated_at) agent.updated_at = toISODateTime(agent.updated_at);
  return agent;
}

async function addAgent(agent) {
  const requestedId = agent.id;
  const id = requestedId || genId();

  const owner = agent.owner;
  if (!owner || String(owner).trim().length === 0) {
    return { success: false, id, error: "MISSING_OWNER: owner is required" };
  }

  if (agent.supervisor_id) {
    if (String(agent.supervisor_id) === String(id)) {
      return { success: false, id, error: "INVALID_SUPERVISOR: supervisor_id cannot be self" };
    }
    const supervisor = await getAgentById(agent.supervisor_id);
    if (!supervisor) {
      return { success: false, id, error: "SUPERVISOR_NOT_FOUND: supervisor_id does not exist" };
    }
  }

  if (agent.avatar_resource_id) {
    const avatarExists = await checkAvatarExists(agent.avatar_resource_id);
    if (!avatarExists) {
      return { success: false, id, error: "AVATAR_NOT_FOUND: avatar_resource_id does not exist" };
    }
  }

  // Guardrail: if the client supplies an id, ensure it is not already taken
  if (requestedId) {
    const existing = await getAgentById(requestedId);
    if (existing) {
      return { success: false, id: requestedId, error: "ID_TAKEN: Agent id already exists" };
    }
  }

  const sql = `
    INSERT INTO agents
    (
      \`id\`, \`name\`, \`description\`, \`owner\`, \`gender\`, \`title\`, \`rank\`, \`birthday\`, \`supervisor_id\`,
      \`personalities\`, \`capabilities\`, \`status\`, \`version\`, \`url\`, \`vehicle_id\`, \`avatar_resource_id\`, \`extra_data\`
    )
    VALUES
    (
      :id, :name, :description, :owner, :gender, :title, :rank, :birthday, :supervisor_id,
      :personalities, :capabilities, :status, :version, :url, :vehicle_id, :avatar_resource_id, :extra_data
    )
  `;
  const params = [
    toDbParam("id", id),
    toDbParam("name", agent.name || ""),
    toDbParam("description", agent.description || null),
    toDbParam("owner", owner),
    toDbParam("gender", agent.gender || "male"),
    toDbParam("title", safeJsonStringify(agent.title || [])),
    toDbParam("rank", agent.rank || null),
    toDbParam("birthday", agent.birthday || null),
    toDbParam("supervisor_id", agent.supervisor_id || null),
    toDbParam("personalities", safeJsonStringify(agent.personalities || [])),
    toDbParam("capabilities", safeJsonStringify(agent.capabilities || [])),
    toDbParam("status", agent.status || "active"),
    toDbParam("version", agent.version || null),
    toDbParam("url", agent.url || null),
    toDbParam("vehicle_id", agent.vehicle_id || null),
    toDbParam("avatar_resource_id", agent.avatar_resource_id || null),
    toDbParam("extra_data", safeJsonStringify(agent.extra_data || {}))
  ];
  try {
    await execute(sql, params);
    return { success: true, id };
  } catch (err) {
    // Fallback for races or DB-level uniqueness errors
    if ((err.message || "").toLowerCase().includes("duplicate")) {
      return { success: false, id, error: "ID_TAKEN: Agent id already exists" };
    }
    throw err;
  }
}

async function updateAgent(id, owner, fields) {
  // Guardrail: ensure the agent exists before updating
  const current = await getAgentById(id);
  if (!current) {
    return { success: false, id, error: "NOT_FOUND: Agent not found" };
  }
  // owner can be a string or an array of acceptable owner identifiers
  if (owner) {
    const acceptableOwners = Array.isArray(owner) ? owner.filter(Boolean) : [owner];
    if (!acceptableOwners.includes(current.owner)) {
      return { success: false, id, error: "FORBIDDEN: Not the owner" };
    }
  }

  const allowed = [
    "name",
    "description",
    "gender",
    "title",
    "rank",
    "birthday",
    "supervisor_id",
    "personalities",
    "capabilities",
    "status",
    "version",
    "url",
    "vehicle_id",
    "avatar_resource_id",
    "extra_data"
  ];
  const setParts = [];
  const params = [toDbParam("id", id)];
  for (const key of allowed) {
    if (key in fields) {
      setParts.push(`\`${key}\` = :${key}`);
      const val = JSON_FIELDS.includes(key) ? safeJsonStringify(fields[key], key === "extra_data" ? "{}" : "[]") : fields[key];
      params.push(toDbParam(key, val));
    }
  }
  if (!setParts.length) {
    return { success: false, error: "No valid fields to update" };
  }
  const sql = `UPDATE agents SET ${setParts.join(", ")} WHERE id = :id`;
  await execute(sql, params);
  return { success: true, id };
}

async function deleteAgent(id, owner) {
  const current = await getAgentById(id);
  if (!current) {
    return { success: false, id, error: "NOT_FOUND: Agent not found" };
  }
  // owner can be a string or an array of acceptable owner identifiers
  if (owner) {
    const acceptableOwners = Array.isArray(owner) ? owner.filter(Boolean) : [owner];
    if (!acceptableOwners.includes(current.owner)) {
      return { success: false, id, error: "FORBIDDEN: Not the owner" };
    }
  }
  // Delete associations first to avoid FK issues
  await execute("DELETE FROM agent_org_rels WHERE agent_id = :id", [toDbParam("id", id)]);
  await execute("DELETE FROM agent_skill_rels WHERE agent_id = :id", [toDbParam("id", id)]);
  await execute("DELETE FROM agent_task_rels WHERE agent_id = :id", [toDbParam("id", id)]);
  await execute("DELETE FROM agents WHERE id = :id", [toDbParam("id", id)]);
  return { success: true, id };
}

async function getAgentById(id) {
  const res = await execute("SELECT * FROM agents WHERE id = :id LIMIT 1", [toDbParam("id", id)]);
  const rows = rowsToObjects(res);
  const agent = rows[0] || null;
  if (agent) {
    normalizeAgentDatetimes(agent);
    await enrichAgentWithRelations(agent);
  }
  return agent;
}

/**
 * Enrich an agent object with org_ids, skills, tasks from relationship tables.
 * This merges the relationship data into the agent's extra_data field.
 */
async function enrichAgentWithRelations(agent) {
  const agentId = agent.id;
  
  // Get org relationships
  const orgRes = await execute(
    "SELECT org_id FROM agent_org_rels WHERE agent_id = :agent_id AND status = 'active'",
    [toDbParam("agent_id", agentId)]
  );
  const orgRows = rowsToObjects(orgRes);
  const orgIds = orgRows.map(r => r.org_id).filter(Boolean);
  
  // Get skill relationships
  const skillRes = await execute(
    "SELECT skill_id FROM agent_skill_rels WHERE agent_id = :agent_id AND status = 'active'",
    [toDbParam("agent_id", agentId)]
  );
  const skillRows = rowsToObjects(skillRes);
  const skillIds = skillRows.map(r => r.skill_id).filter(Boolean);
  
  // Get task relationships
  const taskRes = await execute(
    "SELECT task_id FROM agent_task_rels WHERE agent_id = :agent_id",
    [toDbParam("agent_id", agentId)]
  );
  const taskRows = rowsToObjects(taskRes);
  const taskIds = taskRows.map(r => r.task_id).filter(Boolean);
  
  // Add to agent object directly (for frontend compatibility)
  agent.skills = skillIds;
  agent.tasks = taskIds;
  agent.org_ids = orgIds;
  agent.org_id = orgIds[0] || null;  // Frontend expects singular org_id
  
  // Also merge into extra_data for persistence
  let extraData = agent.extra_data || {};
  if (typeof extraData === 'string') {
    try { extraData = JSON.parse(extraData); } catch (e) { extraData = {}; }
  }
  extraData.org_ids = orgIds;
  extraData.skills = skillIds;
  extraData.tasks = taskIds;
  agent.extra_data = extraData;
  
  return agent;
}

async function getAgentsByOwner(owner) {
  const res = await execute("SELECT * FROM agents WHERE owner = :owner", [toDbParam("owner", owner)]);
  const agents = rowsToObjects(res);
  // Normalize datetimes and enrich each agent with relationship data
  agents.forEach(normalizeAgentDatetimes);
  await Promise.all(agents.map(agent => enrichAgentWithRelations(agent)));
  return agents;
}

/**
 * Get agents by multiple owner identifiers (username, email, Cognito sub)
 * This handles the case where agents might be stored with different owner formats
 */
async function getAgentsByOwners(owner, ownerEmail, ownerSub) {
  // Build list of unique owner identifiers to query
  const owners = new Set();
  if (owner) owners.add(owner);  // sanitized username from frontend
  if (ownerEmail) owners.add(ownerEmail);  // actual email
  if (ownerSub) owners.add(ownerSub);  // Cognito sub ID
  // Also add sanitized email (underscore format) if email is provided
  if (ownerEmail) owners.add(ownerEmail.replace(/[@.]/g, "_"));
  
  if (owners.size === 0) return [];
  
  // Build OR query for all possible owner values
  const ownerList = Array.from(owners);
  const placeholders = ownerList.map((_, i) => `:owner${i}`).join(", ");
  const params = ownerList.map((o, i) => toDbParam(`owner${i}`, o));
  
  console.log(`[agentService] getAgentsByOwners querying with owners: ${JSON.stringify(ownerList)}`);
  const sql = `SELECT * FROM agents WHERE owner IN (${placeholders})`;
  const res = await execute(sql, params);
  const agents = rowsToObjects(res);
  console.log(`[agentService] getAgentsByOwners found ${agents.length} agents`);
  // Normalize datetimes and enrich each agent with relationship data
  agents.forEach(normalizeAgentDatetimes);
  await Promise.all(agents.map(agent => enrichAgentWithRelations(agent)));
  return agents;
}

async function queryAgents({ id, name, description }) {
  const where = [];
  const params = [];
  if (id) {
    where.push("id = :id");
    params.push(toDbParam("id", id));
  }
  if (name) {
    where.push("name LIKE :name");
    params.push(toDbParam("name", `%${name}%`));
  }
  if (description) {
    where.push("description LIKE :description");
    params.push(toDbParam("description", `%${description}%`));
  }
  const sql = `SELECT * FROM agents${where.length ? " WHERE " + where.join(" AND ") : ""}`;
  const res = await execute(sql, params);
  const agents = rowsToObjects(res);
  // Normalize datetimes and enrich each agent with relationship data
  agents.forEach(normalizeAgentDatetimes);
  await Promise.all(agents.map(agent => enrichAgentWithRelations(agent)));
  return agents;
}

async function assignAgentToOrg(agentId, orgId, { role = "member", permissions = [], access_level = "read", status = "active" } = {}) {
  // Replace existing association for (agent, org)
  await execute("DELETE FROM agent_org_rels WHERE agent_id = :agent_id AND org_id = :org_id", [
    toDbParam("agent_id", agentId),
    toDbParam("org_id", orgId)
  ]);
  const sql = `
    INSERT INTO agent_org_rels (agent_id, org_id, role, permissions, access_level, status)
    VALUES (:agent_id, :org_id, :role, :permissions, :access_level, :status)
  `;
  const params = [
    toDbParam("agent_id", agentId),
    toDbParam("org_id", orgId),
    toDbParam("role", role),
    toDbParam("permissions", safeJsonStringify(permissions || [])),
    toDbParam("access_level", access_level),
    toDbParam("status", status)
  ];
  await execute(sql, params);
  return { success: true };
}

async function assignSkillToAgent(agentId, skillId, { proficiency_level = "beginner", priority = 0, status = "active" } = {}) {
  await execute("DELETE FROM agent_skill_rels WHERE agent_id = :agent_id AND skill_id = :skill_id", [
    toDbParam("agent_id", agentId),
    toDbParam("skill_id", skillId)
  ]);
  const sql = `
    INSERT INTO agent_skill_rels (agent_id, skill_id, proficiency_level, priority, status)
    VALUES (:agent_id, :skill_id, :proficiency_level, :priority, :status)
  `;
  const params = [
    toDbParam("agent_id", agentId),
    toDbParam("skill_id", skillId),
    toDbParam("proficiency_level", proficiency_level),
    toDbParam("priority", priority),
    toDbParam("status", status)
  ];
  await execute(sql, params);
  return { success: true };
}

async function assignTaskToAgent(agentId, taskId, vehicleId, { priority = "medium", status = "pending", execution_context = {} } = {}) {
  await execute("DELETE FROM agent_task_rels WHERE agent_id = :agent_id AND task_id = :task_id AND vehicle_id = :vehicle_id", [
    toDbParam("agent_id", agentId),
    toDbParam("task_id", taskId),
    toDbParam("vehicle_id", vehicleId)
  ]);
  const sql = `
    INSERT INTO agent_task_rels (agent_id, task_id, vehicle_id, priority, status, execution_context)
    VALUES (:agent_id, :task_id, :vehicle_id, :priority, :status, :execution_context)
  `;
  const params = [
    toDbParam("agent_id", agentId),
    toDbParam("task_id", taskId),
    toDbParam("vehicle_id", vehicleId),
    toDbParam("priority", priority),
    toDbParam("status", status),
    toDbParam("execution_context", safeJsonStringify(execution_context || {}))
  ];
  await execute(sql, params);
  return { success: true };
}

async function getAgentStatistics(agentId) {
  const stats = { agent_id: agentId };
  const [orgRes, skillRes, taskRes, runningRes, completedRes] = await Promise.all([
    execute("SELECT COUNT(*) AS count FROM agent_org_rels WHERE agent_id = :agent_id AND status = 'active'", [toDbParam("agent_id", agentId)]),
    execute("SELECT COUNT(*) AS count FROM agent_skill_rels WHERE agent_id = :agent_id AND status = 'active'", [toDbParam("agent_id", agentId)]),
    execute("SELECT COUNT(*) AS count FROM agent_task_rels WHERE agent_id = :agent_id", [toDbParam("agent_id", agentId)]),
    execute("SELECT COUNT(*) AS count FROM agent_task_rels WHERE agent_id = :agent_id AND status = 'running'", [toDbParam("agent_id", agentId)]),
    execute("SELECT COUNT(*) AS count FROM agent_task_rels WHERE agent_id = :agent_id AND status = 'completed'", [toDbParam("agent_id", agentId)])
  ]);
  const orgCount = rowsToObjects(orgRes)[0]?.count || 0;
  const skillCount = rowsToObjects(skillRes)[0]?.count || 0;
  const taskTotal = rowsToObjects(taskRes)[0]?.count || 0;
  const running = rowsToObjects(runningRes)[0]?.count || 0;
  const completed = rowsToObjects(completedRes)[0]?.count || 0;
  return {
    success: true,
    data: {
      organizations: orgCount,
      skills: skillCount,
      tasks: { total: taskTotal, running, completed }
    }
  };
}

module.exports = {
  addAgent,
  updateAgent,
  deleteAgent,
  getAgentById,
  getAgentsByOwner,
  getAgentsByOwners,
  queryAgents,
  assignAgentToOrg,
  assignSkillToAgent,
  assignTaskToAgent,
  getAgentStatistics,
  enrichAgentWithRelations
};
