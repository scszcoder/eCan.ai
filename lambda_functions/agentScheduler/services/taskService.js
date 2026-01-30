// Task service backed by MySQL/Aurora via RDS Data API
const crypto = require("crypto");
const { execute } = require("../db/rdsClient");

const JSON_FIELDS = [
  "objectives",
  "schedule",
  "result",
  "metadata",
  "skill_config",
  "parameters",
  "constraints_json",
  "resource_requirements",
  "success_criteria",
  "execution_context"
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

async function addTask(task) {
  const requestedId = task.id;
  const id = requestedId || genId("task");

  if (requestedId) {
    const existing = await getTaskById(requestedId);
    if (existing) {
      return { success: false, id: requestedId, error: "ID_TAKEN: Task id already exists" };
    }
  }

  const sql = `
    INSERT INTO agent_tasks
    (id, name, description, owner, source, org_id, priority, status, task_type,
     objectives, schedule, trigger_type, progress, result, error_message, metadata)
    VALUES
    (:id, :name, :description, :owner, :source, :org_id, :priority, :status, :task_type,
     :objectives, :schedule, :trigger_type, :progress, :result, :error_message, :metadata)
  `;
  const params = [
    toDbParam("id", id),
    toDbParam("name", task.name || ""),
    toDbParam("description", task.description || null),
    toDbParam("owner", task.owner),
    toDbParam("source", task.source || "ui"),
    toDbParam("org_id", task.org_id || null),
    toDbParam("priority", task.priority || "medium"),
    toDbParam("status", task.status || "pending"),
    toDbParam("task_type", task.task_type || null),
    toDbParam("objectives", safeJsonStringify(task.objectives)),
    toDbParam("schedule", safeJsonStringify(task.schedule)),
    toDbParam("trigger_type", task.trigger_type || null),
    toDbParam("progress", task.progress || 0.0),
    toDbParam("result", safeJsonStringify(task.result)),
    toDbParam("error_message", task.error_message || null),
    toDbParam("metadata", safeJsonStringify(task.metadata))
  ];
  try {
    await execute(sql, params);
    return { success: true, id };
  } catch (err) {
    if ((err.message || "").toLowerCase().includes("duplicate")) {
      return { success: false, id, error: "ID_TAKEN: Task id already exists" };
    }
    throw err;
  }
}

async function updateTask(id, owner, fields) {
  const current = await getTaskById(id);
  if (!current) {
    return { success: false, id, error: "NOT_FOUND: Task not found" };
  }
  if (owner && current.owner !== owner) {
    return { success: false, id, error: "FORBIDDEN: Not the owner" };
  }

  const allowed = [
    "name",
    "description",
    "owner",
    "source",
    "org_id",
    "priority",
    "status",
    "task_type",
    "objectives",
    "schedule",
    "trigger_type",
    "progress",
    "result",
    "error_message",
    "metadata"
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
  const sql = `UPDATE agent_tasks SET ${setParts.join(", ")} WHERE id = :id`;
  await execute(sql, params);
  return { success: true, id };
}

async function deleteTask(id, owner) {
  const current = await getTaskById(id);
  if (!current) {
    return { success: false, id, error: "NOT_FOUND: Task not found" };
  }
  if (owner && current.owner !== owner) {
    return { success: false, id, error: "FORBIDDEN: Not the owner" };
  }

  await execute("DELETE FROM agent_task_rels WHERE task_id = :id", [toDbParam("id", id)]);
  await execute("DELETE FROM agent_task_skill_rels WHERE task_id = :id", [toDbParam("id", id)]);
  await execute("DELETE FROM agent_tasks WHERE id = :id", [toDbParam("id", id)]);
  return { success: true };
}

async function getTaskById(id) {
  const res = await execute("SELECT * FROM agent_tasks WHERE id = :id LIMIT 1", [toDbParam("id", id)]);
  const rows = rowsToObjects(res);
  return rows[0] || null;
}

async function queryTasks({ id, name, description }) {
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
  const sql = `SELECT * FROM agent_tasks${where.length ? " WHERE " + where.join(" AND ") : ""}`;
  const res = await execute(sql, params);
  return rowsToObjects(res);
}

async function addSkillToTask(taskId, skillId, { role = "primary", execution_order = 0, is_required = true, skill_config = {} } = {}) {
  // Upsert by delete+insert to satisfy unique constraint
  await execute("DELETE FROM agent_task_skill_rels WHERE task_id = :task_id AND skill_id = :skill_id", [
    toDbParam("task_id", taskId),
    toDbParam("skill_id", skillId)
  ]);
  const sql = `
    INSERT INTO agent_task_skill_rels
    (id, task_id, skill_id, role, execution_order, is_required, skill_config)
    VALUES (:id, :task_id, :skill_id, :role, :execution_order, :is_required, :skill_config)
  `;
  const params = [
    toDbParam("id", genId("rel_ts")),
    toDbParam("task_id", taskId),
    toDbParam("skill_id", skillId),
    toDbParam("role", role),
    toDbParam("execution_order", execution_order),
    toDbParam("is_required", is_required),
    toDbParam("skill_config", safeJsonStringify(skill_config, "{}"))
  ];
  await execute(sql, params);
  return { success: true };
}

async function removeSkillFromTask(taskId, skillId) {
  await execute("DELETE FROM agent_task_skill_rels WHERE task_id = :task_id AND skill_id = :skill_id", [
    toDbParam("task_id", taskId),
    toDbParam("skill_id", skillId)
  ]);
  return { success: true };
}

async function getTaskSkills(taskId, role) {
  const where = ["task_id = :task_id"];
  const params = [toDbParam("task_id", taskId)];
  if (role) {
    where.push("role = :role");
    params.push(toDbParam("role", role));
  }
  const sql = `SELECT * FROM agent_task_skill_rels WHERE ${where.join(" AND ")} ORDER BY execution_order`;
  const res = await execute(sql, params);
  return rowsToObjects(res);
}

async function getTaskExecutions(taskId, status) {
  const where = ["task_id = :task_id"];
  const params = [toDbParam("task_id", taskId)];
  if (status) {
    where.push("status = :status");
    params.push(toDbParam("status", status));
  }
  const sql = `SELECT * FROM agent_task_rels WHERE ${where.join(" AND ")} ORDER BY created_at DESC`;
  const res = await execute(sql, params);
  return rowsToObjects(res);
}

async function getTaskStatistics(taskId) {
  const baseParams = [toDbParam("task_id", taskId)];
  const [
    totalExec,
    completedExec,
    failedExec,
    runningExec,
    skillCount,
    requiredSkillCount,
    avgExecTime
  ] = await Promise.all([
    execute("SELECT COUNT(*) AS count FROM agent_task_rels WHERE task_id = :task_id", baseParams),
    execute("SELECT COUNT(*) AS count FROM agent_task_rels WHERE task_id = :task_id AND status = 'completed'", baseParams),
    execute("SELECT COUNT(*) AS count FROM agent_task_rels WHERE task_id = :task_id AND status = 'failed'", baseParams),
    execute("SELECT COUNT(*) AS count FROM agent_task_rels WHERE task_id = :task_id AND status = 'running'", baseParams),
    execute("SELECT COUNT(*) AS count FROM agent_task_skill_rels WHERE task_id = :task_id", baseParams),
    execute("SELECT COUNT(*) AS count FROM agent_task_skill_rels WHERE task_id = :task_id AND is_required = 1", baseParams),
    execute("SELECT AVG(execution_time) AS avgTime FROM agent_task_rels WHERE task_id = :task_id AND status = 'completed' AND execution_time IS NOT NULL", baseParams)
  ]);

  const total = rowsToObjects(totalExec)[0]?.count || 0;
  const completed = rowsToObjects(completedExec)[0]?.count || 0;
  const failed = rowsToObjects(failedExec)[0]?.count || 0;
  const running = rowsToObjects(runningExec)[0]?.count || 0;
  const skills = rowsToObjects(skillCount)[0]?.count || 0;
  const required = rowsToObjects(requiredSkillCount)[0]?.count || 0;
  const avgTime = rowsToObjects(avgExecTime)[0]?.avgTime || 0.0;

  const successRate = completed + failed > 0 ? completed / (completed + failed) : 0.0;

  return {
    success: true,
    data: {
      executions: { total, completed, failed, running, success_rate: successRate },
      skills: { total: skills, required },
      performance: { avg_execution_time: avgTime }
    }
  };
}

module.exports = {
  addTask,
  updateTask,
  deleteTask,
  getTaskById,
  queryTasks,
  addSkillToTask,
  removeSkillFromTask,
  getTaskSkills,
  getTaskExecutions,
  getTaskStatistics
};
