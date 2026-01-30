// Agent knowledge service backed by MySQL/Aurora via RDS Data API
const crypto = require("crypto");
const { execute } = require("../db/rdsClient");

const JSON_FIELDS = [
  "content",
  "tags",
  "categories",
  "config",
  "access_methods",
  "limitations",
  "settings"
];

function genId() {
  return `knowledge_${crypto.randomBytes(8).toString("hex")}`;
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

async function addKnowledge(knowledge) {
  const requestedId = knowledge.id;
  const id = requestedId || genId();

  if (requestedId) {
    const existing = await getKnowledgeById(requestedId);
    if (existing) {
      return { success: false, id: requestedId, error: "ID_TAKEN: Knowledge id already exists" };
    }
  }

  const sql = `
    INSERT INTO agent_knowledges
    (id, name, description, owner, knowledge_type, version, path, level,
     content, tags, categories, config, access_methods, limitations,
     public, rentable, price, price_model, status, settings)
    VALUES
    (:id, :name, :description, :owner, :knowledge_type, :version, :path, :level,
     :content, :tags, :categories, :config, :access_methods, :limitations,
     :public, :rentable, :price, :price_model, :status, :settings)
  `;
  const params = [
    toDbParam("id", id),
    toDbParam("name", knowledge.name || ""),
    toDbParam("description", knowledge.description || null),
    toDbParam("owner", knowledge.owner),
    toDbParam("knowledge_type", knowledge.knowledge_type || null),
    toDbParam("version", knowledge.version || null),
    toDbParam("path", knowledge.path || null),
    toDbParam("level", knowledge.level || null),
    toDbParam("content", knowledge.content || null),
    toDbParam("tags", safeJsonStringify(knowledge.tags)),
    toDbParam("categories", safeJsonStringify(knowledge.categories)),
    toDbParam("config", safeJsonStringify(knowledge.config)),
    toDbParam("access_methods", safeJsonStringify(knowledge.access_methods)),
    toDbParam("limitations", safeJsonStringify(knowledge.limitations)),
    toDbParam("public", knowledge.public || false),
    toDbParam("rentable", knowledge.rentable || false),
    toDbParam("price", knowledge.price || 0),
    toDbParam("price_model", knowledge.price_model || null),
    toDbParam("status", knowledge.status || "active"),
    toDbParam("settings", safeJsonStringify(knowledge.settings))
  ];
  try {
    await execute(sql, params);
    return { success: true, id };
  } catch (err) {
    if ((err.message || "").toLowerCase().includes("duplicate")) {
      return { success: false, id, error: "ID_TAKEN: Knowledge id already exists" };
    }
    throw err;
  }
}

async function updateKnowledge(id, owner, fields) {
  const current = await getKnowledgeById(id);
  if (!current) {
    return { success: false, id, error: "NOT_FOUND: Knowledge not found" };
  }
  if (owner && current.owner !== owner) {
    return { success: false, id, error: "FORBIDDEN: Not the owner" };
  }

  const allowed = [
    "name",
    "description",
    "knowledge_type",
    "version",
    "path",
    "level",
    "content",
    "tags",
    "categories",
    "config",
    "access_methods",
    "limitations",
    "public",
    "rentable",
    "price",
    "price_model",
    "status",
    "settings"
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
  const sql = `UPDATE agent_knowledges SET ${setParts.join(", ")} WHERE id = :id`;
  await execute(sql, params);
  return { success: true, id };
}

async function getKnowledgeById(id) {
  const res = await execute("SELECT * FROM agent_knowledges WHERE id = :id LIMIT 1", [toDbParam("id", id)]);
  const rows = rowsToObjects(res);
  return rows[0] || null;
}

async function deleteKnowledge(id, owner) {
  const current = await getKnowledgeById(id);
  if (!current) {
    return { success: false, id, error: "NOT_FOUND: Knowledge not found" };
  }
  if (owner && current.owner !== owner) {
    return { success: false, id, error: "FORBIDDEN: Not the owner" };
  }

  await execute("DELETE FROM agent_knowledges WHERE id = :id", [toDbParam("id", id)]);
  return { success: true };
}

async function getKnowledgesByOwner(owner) {
  const res = await execute("SELECT * FROM agent_knowledges WHERE owner = :owner", [toDbParam("owner", owner)]);
  return rowsToObjects(res);
}

async function queryKnowledges({ id, name, description }) {
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
  const sql = `SELECT * FROM agent_knowledges${where.length ? " WHERE " + where.join(" AND ") : ""}`;
  const res = await execute(sql, params);
  return rowsToObjects(res);
}

module.exports = {
  addKnowledge,
  updateKnowledge,
  getKnowledgeById,
  deleteKnowledge,
  getKnowledgesByOwner,
  queryKnowledges
};
