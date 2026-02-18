/**
 * Tool handler: subscribe_skill
 * Subscribe an agent to a skill (create agent_skill_rels record).
 * Data source: Aurora (RDS Data API) — table: agent_skill_rels
 */
import { execute, strParam } from "./rdsClient.js";
import { randomUUID } from "node:crypto";

export async function subscribe_skill(toolInput) {
  const { agent_id, skill_id, proficiency_level } = toolInput;
  if (!agent_id || !skill_id) {
    throw new Error("agent_id and skill_id are required");
  }

  const relId = `asr_${randomUUID().replace(/-/g, "").slice(0, 16)}`;
  const now = new Date().toISOString().slice(0, 23);

  const sql = `INSERT INTO agent_skill_rels (id, agent_id, skill_id, proficiency_level, status, created_at, updated_at)
               VALUES (:id, :agent_id, :skill_id, :level, 'active', :now, :now)
               ON DUPLICATE KEY UPDATE status = 'active', updated_at = :now`;

  await execute(sql, [
    strParam("id", relId),
    strParam("agent_id", agent_id),
    strParam("skill_id", skill_id),
    strParam("level", proficiency_level || "beginner"),
    strParam("now", now),
  ]);

  return { agent_id, skill_id, status: "subscribed", subscribed_at: now };
}
