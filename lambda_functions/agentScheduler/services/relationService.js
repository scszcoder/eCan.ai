const crypto = require("crypto");
const { execute } = require("../db/rdsClient");

const TABLES = {
  agent_org_rels: {
    idPrefix: "aor",
    required: ["agent_id", "org_id"],
    json: ["permissions"],
    columns: [
      "id",
      "agent_id",
      "org_id",
      "role",
      "status",
      "join_date",
      "leave_date",
      "permissions",
      "access_level",
      "created_at",
      "updated_at",
    ],
    queryable: ["id", "agent_id", "org_id", "role", "status", "access_level"],
  },
  agent_skill_rels: {
    idPrefix: "asr",
    required: ["agent_id", "skill_id"],
    json: [],
    columns: [
      "id",
      "agent_id",
      "skill_id",
      "proficiency_level",
      "experience_points",
      "certification_level",
      "usage_count",
      "success_rate",
      "last_used",
      "status",
      "is_favorite",
      "priority",
      "created_at",
      "updated_at",
    ],
    queryable: ["id", "agent_id", "skill_id", "status", "proficiency_level", "is_favorite"],
  },
  agent_skill_tool_rels: {
    idPrefix: "ast",
    required: ["skill_id", "tool_id"],
    json: ["tool_config", "parameters"],
    columns: [
      "id",
      "skill_id",
      "tool_id",
      "dependency_type",
      "usage_frequency",
      "importance",
      "tool_config",
      "parameters",
      "usage_count",
      "success_rate",
      "last_used",
      "status",
      "created_at",
      "updated_at",
    ],
    queryable: ["id", "skill_id", "tool_id", "dependency_type", "status"],
  },
  agent_skill_knowledge_rels: {
    idPrefix: "ask",
    required: ["skill_id", "knowledge_id"],
    json: ["knowledge_scope"],
    columns: [
      "id",
      "skill_id",
      "knowledge_id",
      "dependency_type",
      "usage_frequency",
      "importance",
      "access_pattern",
      "knowledge_scope",
      "access_count",
      "last_accessed",
      "average_query_time",
      "status",
      "created_at",
      "updated_at",
    ],
    queryable: ["id", "skill_id", "knowledge_id", "dependency_type", "status"],
  },
  agent_task_rels: {
    idPrefix: "atr",
    required: ["agent_id", "task_id"],
    json: ["result", "execution_context"],
    columns: [
      "id",
      "agent_id",
      "task_id",
      "vehicle_id",
      "status",
      "priority",
      "progress",
      "scheduled_start",
      "actual_start",
      "estimated_end",
      "actual_end",
      "result",
      "error_message",
      "logs",
      "cpu_usage",
      "memory_usage",
      "execution_time",
      "execution_context",
      "retry_count",
      "max_retries",
      "created_at",
      "updated_at",
    ],
    queryable: ["id", "agent_id", "task_id", "vehicle_id", "status", "priority"],
  },
  agent_task_skill_rels: {
    idPrefix: "ats",
    required: ["task_id", "skill_id"],
    json: [
      "skill_config",
      "parameters",
      "constraints_json",
      "resource_requirements",
      "success_criteria",
    ],
    columns: [
      "id",
      "task_id",
      "skill_id",
      "role",
      "execution_order",
      "is_required",
      "skill_config",
      "parameters",
      "constraints_json",
      "estimated_duration",
      "estimated_cost",
      "resource_requirements",
      "success_criteria",
      "quality_threshold",
      "status",
      "actual_duration",
      "actual_cost",
      "quality_score",
      "created_at",
      "updated_at",
    ],
    queryable: ["id", "task_id", "skill_id", "role", "status", "is_required"],
  },
};

function genId(prefix) {
  return `${prefix}_${crypto.randomBytes(10).toString("hex")}`;
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

function safeJsonStringify(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === "string") {
    // Allow raw JSON strings to pass through.
    return value;
  }
  try {
    return JSON.stringify(value);
  } catch {
    return null;
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

function rowsToObjects(result, jsonFields) {
  const cols = result.columnMetadata?.map((c) => c.name) || [];
  return (result.records || []).map((row) => {
    const obj = {};
    cols.forEach((col, idx) => {
      obj[col] = parseFieldValue(row[idx]);
      if (jsonFields.includes(col) && typeof obj[col] === "string") {
        try {
          obj[col] = JSON.parse(obj[col]);
        } catch {
          // leave as string
        }
      }
    });
    return obj;
  });
}

function normalizeInputArray(input) {
  if (!input) return [];
  return Array.isArray(input) ? input : [input];
}

async function addRels(tableKey, input) {
  const table = TABLES[tableKey];
  if (!table) throw new Error(`Unknown rel table: ${tableKey}`);
  const items = normalizeInputArray(input);
  const results = [];

  for (const item of items) {
    const id = String(item?.id || genId(table.idPrefix));

    const missing = table.required.filter((k) => !item?.[k]);
    if (missing.length) {
      results.push({ id, success: false, error: `Missing required fields: ${missing.join(",")}` });
      continue;
    }

    const cols = ["id", ...table.required];
    const params = [toDbParam("id", id), ...table.required.map((k) => toDbParam(k, item[k]))];

    for (const col of table.columns) {
      if (col === "id") continue;
      if (table.required.includes(col)) continue;
      if (!(col in (item || {}))) continue;

      cols.push(col);
      const val = table.json.includes(col) ? safeJsonStringify(item[col]) : item[col];
      params.push(toDbParam(col, val));
    }

    const placeholders = cols.map((c) => `:${c}`).join(", ");
    const sql = `INSERT INTO ${tableKey} (${cols.join(", ")}) VALUES (${placeholders})`;
    try {
      await execute(sql, params);
      results.push({ id, success: true, error: null });
    } catch (e) {
      results.push({ id, success: false, error: e?.message || String(e) });
    }
  }

  return results;
}

async function updateRels(tableKey, input) {
  const table = TABLES[tableKey];
  if (!table) throw new Error(`Unknown rel table: ${tableKey}`);
  const items = normalizeInputArray(input);
  const results = [];

  for (const item of items) {
    const id = item?.id;
    if (!id) {
      results.push({ id: null, success: false, error: "Missing id" });
      continue;
    }
    const setParts = [];
    const params = [toDbParam("id", id)];

    for (const col of table.columns) {
      if (col === "id") continue;
      if (!(col in (item || {}))) continue;
      setParts.push(`${col} = :${col}`);
      const val = table.json.includes(col) ? safeJsonStringify(item[col]) : item[col];
      params.push(toDbParam(col, val));
    }

    if (!setParts.length) {
      results.push({ id, success: false, error: "No fields to update" });
      continue;
    }
    const sql = `UPDATE ${tableKey} SET ${setParts.join(", ")} WHERE id = :id`;
    try {
      await execute(sql, params);
      results.push({ id: String(id), success: true, error: null });
    } catch (e) {
      results.push({ id: String(id), success: false, error: e?.message || String(e) });
    }
  }

  return results;
}

async function removeRels(tableKey, ids) {
  const table = TABLES[tableKey];
  if (!table) throw new Error(`Unknown rel table: ${tableKey}`);
  const items = normalizeInputArray(ids);
  const results = [];
  for (const rawId of items) {
    const id = typeof rawId === "string" ? rawId : rawId?.id;
    if (!id) {
      results.push({ id: null, success: false, error: "Missing id" });
      continue;
    }
    try {
      await execute(`DELETE FROM ${tableKey} WHERE id = :id`, [toDbParam("id", id)]);
      results.push({ id: String(id), success: true, error: null });
    } catch (e) {
      results.push({ id: String(id), success: false, error: e?.message || String(e) });
    }
  }
  return results;
}

async function queryRels(tableKey, input) {
  const table = TABLES[tableKey];
  if (!table) throw new Error(`Unknown rel table: ${tableKey}`);
  const q = (input && typeof input === "object") ? input : {};

  const where = [];
  const params = [];
  for (const key of table.queryable) {
    if (q[key] === undefined || q[key] === null || q[key] === "") continue;
    where.push(`${key} = :${key}`);
    params.push(toDbParam(key, q[key]));
  }

  const limit = Math.min(Math.max(Number(q.limit || 100) || 100, 1), 500);
  const offset = Math.max(Number(q.offset || 0) || 0, 0);
  const sql = `SELECT * FROM ${tableKey}${where.length ? " WHERE " + where.join(" AND ") : ""} ORDER BY updated_at DESC LIMIT ${limit} OFFSET ${offset}`;
  const res = await execute(sql, params);
  return rowsToObjects(res, table.json);
}

module.exports = {
  addRels,
  updateRels,
  removeRels,
  queryRels,
};
