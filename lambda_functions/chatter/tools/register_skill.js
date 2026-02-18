/**
 * Tool handler: register_skill
 * Register a new skill in the skill registry.
 * Data source: Aurora (RDS Data API) — table: agent_skills
 */
import { execute, strParam } from "./rdsClient.js";
import { randomUUID } from "node:crypto";

export async function register_skill(toolInput) {
  const { owner_id, name, category, description, input_schema, output_schema } = toolInput;
  if (!owner_id || !name) {
    throw new Error("owner_id and name are required");
  }

  const skillId = `skill_${randomUUID().replace(/-/g, "").slice(0, 16)}`;
  const now = new Date().toISOString().slice(0, 23);

  const sql = `INSERT INTO agent_skills (id, name, owner, description, tags, config, created_at, updated_at)
               VALUES (:id, :name, :owner, :desc, :tags, :config, :now, :now)`;

  await execute(sql, [
    strParam("id", skillId),
    strParam("name", name),
    strParam("owner", owner_id),
    strParam("desc", description || ""),
    strParam("tags", category ? JSON.stringify([category]) : "[]"),
    strParam("config", input_schema ? JSON.stringify({ input_schema, output_schema }) : "{}"),
    strParam("now", now),
  ]);

  return { skill_id: skillId, name, category, status: "registered", created_at: now };
}
