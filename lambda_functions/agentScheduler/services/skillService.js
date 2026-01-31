// Skill service backed by MySQL/Aurora via RDS Data API
const crypto = require("crypto");
const { execute } = require("../db/rdsClient");

const JSON_FIELDS = [
  "config",
  "diagram",
  "tags",
  "examples",
  "inputModes",
  "outputModes",
  "apps",
  "limitations",
  "tool_config",
  "parameters",
  "knowledge_scope",
  "skill_config"
];

function genId(prefix) {
  return `${prefix}_${crypto.randomBytes(8).toString("hex")}`;
}

function toDbParam(name, value) {
  if (value === null || value === undefined) {
    return { name, value: { isNull: true } };
  }
  if (typeof value === "number") {
    return { name, value: { doubleValue: value } };
  }
  if (typeof value === "boolean") {
    return { name, value: { booleanValue: value } };
  }
  return { name, value: { stringValue: String(value) } };
}

function safeJsonStringify(value, fallback = null) {
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
  const cols = result.columnMetadata?.map((c) => c.name) || [];
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

async function addSkill(skill) {
  const requestedId = skill.id;
  const id = requestedId || genId("skill");

  if (requestedId) {
    const existing = await getSkillById(requestedId);
    if (existing) {
      return { success: false, id: requestedId, error: "ID_TAKEN: Skill id already exists" };
    }
  }

  const sql = `
    INSERT INTO agent_skills
    (id, askid, name, owner, description, version, path, source, level,
     config, diagram, tags, examples, inputModes, outputModes, apps, limitations,
     price, price_model, public, rentable)
    VALUES
    (:id, :askid, :name, :owner, :description, :version, :path, :source, :level,
     :config, :diagram, :tags, :examples, :inputModes, :outputModes, :apps, :limitations,
     :price, :price_model, :public, :rentable)
  `;
  const params = [
    toDbParam("id", id),
    toDbParam("askid", skill.askid || 0),
    toDbParam("name", skill.name || ""),
    toDbParam("owner", skill.owner),
    toDbParam("description", skill.description || null),
    toDbParam("version", skill.version || "1.0.0"),
    toDbParam("path", skill.path || null),
    toDbParam("source", skill.source || "ui"),
    toDbParam("level", skill.level || null),
    toDbParam("config", safeJsonStringify(skill.config)),
    toDbParam("diagram", safeJsonStringify(skill.diagram)),
    toDbParam("tags", safeJsonStringify(skill.tags)),
    toDbParam("examples", safeJsonStringify(skill.examples)),
    toDbParam("inputModes", safeJsonStringify(skill.inputModes)),
    toDbParam("outputModes", safeJsonStringify(skill.outputModes)),
    toDbParam("apps", safeJsonStringify(skill.apps)),
    toDbParam("limitations", safeJsonStringify(skill.limitations)),
    toDbParam("price", skill.price || 0),
    toDbParam("price_model", skill.price_model || null),
    toDbParam("public", skill.public || false),
    toDbParam("rentable", skill.rentable || false)
  ];
  try {
    await execute(sql, params);
    return { success: true, id };
  } catch (err) {
    if ((err.message || "").toLowerCase().includes("duplicate")) {
      return { success: false, id, error: "ID_TAKEN: Skill id already exists" };
    }
    throw err;
  }
}

async function updateSkill(id, owner, fields) {
  const current = await getSkillById(id);
  if (!current) {
    return { success: false, id, error: "NOT_FOUND: Skill not found" };
  }
  if (owner && current.owner !== owner) {
    return { success: false, id, error: "FORBIDDEN: Not the owner" };
  }

  const allowed = [
    "askid",
    "name",
    "owner",
    "description",
    "version",
    "path",
    "source",
    "level",
    "config",
    "diagram",
    "tags",
    "examples",
    "inputModes",
    "outputModes",
    "apps",
    "limitations",
    "price",
    "price_model",
    "public",
    "rentable"
  ];
  const setParts = [];
  const params = [toDbParam("id", id)];
  for (const key of allowed) {
    if (key in fields) {
      setParts.push(`${key} = :${key}`);
      const val = JSON_FIELDS.includes(key) ? safeJsonStringify(fields[key]) : fields[key];
      params.push(toDbParam(key, val));
    }
  }
  if (!setParts.length) return { success: false, error: "No valid fields to update" };
  const sql = `UPDATE agent_skills SET ${setParts.join(", ")} WHERE id = :id`;
  await execute(sql, params);
  return { success: true, id };
}

async function deleteSkill(id, ownerEmail, ownerSub) {
  const current = await getSkillById(id);
  if (!current) {
    return { success: false, id, error: "NOT_FOUND: Skill not found" };
  }
  // Check ownership against both email and Cognito sub
  const ownerMatches = !current.owner || 
    (ownerEmail && current.owner === ownerEmail) || 
    (ownerSub && current.owner === ownerSub);
  if (!ownerMatches) {
    return { success: false, id, error: "FORBIDDEN: Not the owner" };
  }

  await execute("DELETE FROM agent_skill_rels WHERE skill_id = :id", [toDbParam("id", id)]);
  await execute("DELETE FROM agent_task_skill_rels WHERE skill_id = :id", [toDbParam("id", id)]);
  await execute("DELETE FROM agent_skill_knowledge_rels WHERE skill_id = :id", [toDbParam("id", id)]);
  await execute("DELETE FROM agent_skill_tool_rels WHERE skill_id = :id", [toDbParam("id", id)]);
  await execute("DELETE FROM agent_skills WHERE id = :id", [toDbParam("id", id)]);
  return { success: true };
}

async function getSkillById(id) {
  const res = await execute("SELECT * FROM agent_skills WHERE id = :id LIMIT 1", [toDbParam("id", id)]);
  const rows = rowsToObjects(res);
  return rows[0] || null;
}

async function getSkillsByOwner(owner) {
  const res = await execute("SELECT * FROM agent_skills WHERE owner = :owner", [toDbParam("owner", owner)]);
  return rowsToObjects(res);
}

/**
 * Get skills by multiple owner identifiers (email and/or Cognito sub)
 * This handles both legacy skills (stored with Cognito sub) and new skills (stored with email)
 */
async function getSkillsByOwners(ownerEmail, ownerSub) {
  const owners = [ownerEmail, ownerSub].filter(o => o && o.trim());
  if (owners.length === 0) {
    return [];
  }
  if (owners.length === 1) {
    return getSkillsByOwner(owners[0]);
  }
  // Query with OR condition for both identifiers
  const res = await execute(
    "SELECT * FROM agent_skills WHERE owner = :ownerEmail OR owner = :ownerSub",
    [toDbParam("ownerEmail", ownerEmail), toDbParam("ownerSub", ownerSub)]
  );
  return rowsToObjects(res);
}

async function querySkills({ id, name, description }) {
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
  const sql = `SELECT * FROM agent_skills${where.length ? " WHERE " + where.join(" AND ") : ""}`;
  const res = await execute(sql, params);
  return rowsToObjects(res);
}

async function addToolToSkill(skillId, toolId, { dependency_type = "required", usage_frequency = "medium", importance = 1, tool_config = {} } = {}) {
  await execute("DELETE FROM agent_skill_tool_rels WHERE skill_id = :skill_id AND tool_id = :tool_id", [
    toDbParam("skill_id", skillId),
    toDbParam("tool_id", toolId)
  ]);
  const sql = `
    INSERT INTO agent_skill_tool_rels
    (id, skill_id, tool_id, dependency_type, usage_frequency, importance, tool_config)
    VALUES (:id, :skill_id, :tool_id, :dependency_type, :usage_frequency, :importance, :tool_config)
  `;
  const params = [
    toDbParam("id", genId("rel_st")),
    toDbParam("skill_id", skillId),
    toDbParam("tool_id", toolId),
    toDbParam("dependency_type", dependency_type),
    toDbParam("usage_frequency", usage_frequency),
    toDbParam("importance", importance),
    toDbParam("tool_config", safeJsonStringify(tool_config, "{}"))
  ];
  await execute(sql, params);
  return { success: true };
}

async function removeToolFromSkill(skillId, toolId) {
  await execute("DELETE FROM agent_skill_tool_rels WHERE skill_id = :skill_id AND tool_id = :tool_id", [
    toDbParam("skill_id", skillId),
    toDbParam("tool_id", toolId)
  ]);
  return { success: true };
}

async function getSkillTools(skillId, dependency_type) {
  const where = ["skill_id = :skill_id"];
  const params = [toDbParam("skill_id", skillId)];
  if (dependency_type) {
    where.push("dependency_type = :dependency_type");
    params.push(toDbParam("dependency_type", dependency_type));
  }
  const sql = `SELECT * FROM agent_skill_tool_rels WHERE ${where.join(" AND ")} ORDER BY importance DESC`;
  const res = await execute(sql, params);
  return rowsToObjects(res);
}

async function addKnowledgeToSkill(skillId, knowledgeId, { dependency_type = "required", access_pattern = "read", knowledge_scope = [] } = {}) {
  await execute("DELETE FROM agent_skill_knowledge_rels WHERE skill_id = :skill_id AND knowledge_id = :knowledge_id", [
    toDbParam("skill_id", skillId),
    toDbParam("knowledge_id", knowledgeId)
  ]);
  const sql = `
    INSERT INTO agent_skill_knowledge_rels
    (id, skill_id, knowledge_id, dependency_type, access_pattern, knowledge_scope)
    VALUES (:id, :skill_id, :knowledge_id, :dependency_type, :access_pattern, :knowledge_scope)
  `;
  const params = [
    toDbParam("id", genId("rel_sk")),
    toDbParam("skill_id", skillId),
    toDbParam("knowledge_id", knowledgeId),
    toDbParam("dependency_type", dependency_type),
    toDbParam("access_pattern", access_pattern),
    toDbParam("knowledge_scope", safeJsonStringify(knowledge_scope || [], "[]"))
  ];
  await execute(sql, params);
  return { success: true };
}

async function removeKnowledgeFromSkill(skillId, knowledgeId) {
  await execute("DELETE FROM agent_skill_knowledge_rels WHERE skill_id = :skill_id AND knowledge_id = :knowledge_id", [
    toDbParam("skill_id", skillId),
    toDbParam("knowledge_id", knowledgeId)
  ]);
  return { success: true };
}

async function getSkillKnowledges(skillId, dependency_type) {
  const where = ["skill_id = :skill_id"];
  const params = [toDbParam("skill_id", skillId)];
  if (dependency_type) {
    where.push("dependency_type = :dependency_type");
    params.push(toDbParam("dependency_type", dependency_type));
  }
  const sql = `SELECT * FROM agent_skill_knowledge_rels WHERE ${where.join(" AND ")} ORDER BY importance DESC`;
  const res = await execute(sql, params);
  return rowsToObjects(res);
}

module.exports = {
  addSkill,
  updateSkill,
  deleteSkill,
  getSkillById,
  getSkillsByOwner,
  getSkillsByOwners,
  querySkills,
  addToolToSkill,
  removeToolFromSkill,
  getSkillTools,
  addKnowledgeToSkill,
  removeKnowledgeFromSkill,
  getSkillKnowledges
};
