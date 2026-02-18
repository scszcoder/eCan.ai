/**
 * Tool handler: agent_add_tasks
 * Assign one or more tasks to an agent via agent_task_rels.
 * Data source: Aurora (RDS Data API) — table: agent_task_rels
 */
import { execute, strParam } from "./rdsClient.js";
import { randomUUID } from "node:crypto";

export async function agent_add_tasks(toolInput) {
  const { agent_id, task_ids } = toolInput;
  if (!agent_id || !task_ids || task_ids.length === 0) {
    throw new Error("agent_id and task_ids (non-empty array) are required");
  }

  const results = [];
  const now = new Date().toISOString().slice(0, 23);

  for (const task_id of task_ids) {
    try {
      const relId = `atr_${randomUUID().replace(/-/g, "").slice(0, 16)}`;
      const sql = `INSERT INTO agent_task_rels (id, agent_id, task_id, created_at, updated_at)
                   VALUES (:id, :agent_id, :task_id, :now, :now)
                   ON DUPLICATE KEY UPDATE updated_at = :now`;
      await execute(sql, [
        strParam("id", relId),
        strParam("agent_id", agent_id),
        strParam("task_id", task_id),
        strParam("now", now),
      ]);
      results.push({ task_id, status: "assigned" });
    } catch (err) {
      results.push({ task_id, status: "failed", error: err.message });
    }
  }

  return { agent_id, assignments: results, assigned_count: results.filter(r => r.status === "assigned").length };
}
