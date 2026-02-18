/**
 * Tool handler: create_task_with_skill
 * Create a new task linked to a skill.
 * Data source: Aurora (RDS Data API) — tables: agent_tasks, agent_task_skill_rels
 */
import { execute, strParam } from "./rdsClient.js";
import { randomUUID } from "node:crypto";

export async function create_task_with_skill(toolInput) {
  const { owner_id, task_name, skill_name, description, parameters, schedule } = toolInput;
  if (!owner_id || !task_name || !skill_name) {
    throw new Error("owner_id, task_name, and skill_name are required");
  }

  const taskId = `task_${randomUUID().replace(/-/g, "").slice(0, 16)}`;
  const now = new Date().toISOString().slice(0, 23);
  const status = schedule ? "scheduled" : "created";

  const sql = `INSERT INTO agent_tasks (id, name, owner, description, status, schedule, metadata, created_at, updated_at)
               VALUES (:id, :name, :owner, :desc, :status, :schedule, :meta, :now, :now)`;

  await execute(sql, [
    strParam("id", taskId),
    strParam("name", task_name),
    strParam("owner", owner_id),
    strParam("desc", description || ""),
    strParam("status", status),
    strParam("schedule", schedule ? JSON.stringify(schedule) : null),
    strParam("meta", parameters ? JSON.stringify(parameters) : "{}"),
    strParam("now", now),
  ]);

  return { task_id: taskId, task_name, skill_name, status, created_at: now };
}
