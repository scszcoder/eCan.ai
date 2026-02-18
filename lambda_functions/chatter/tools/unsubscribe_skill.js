/**
 * Tool handler: unsubscribe_skill
 * Unsubscribe an agent from a skill (soft-delete agent_skill_rels record).
 * Data source: Aurora (RDS Data API) — table: agent_skill_rels
 */
import { execute, strParam } from "./rdsClient.js";

export async function unsubscribe_skill(toolInput) {
  const { agent_id, skill_id } = toolInput;
  if (!agent_id || !skill_id) {
    throw new Error("agent_id and skill_id are required");
  }

  const now = new Date().toISOString().slice(0, 23);
  const sql = `UPDATE agent_skill_rels SET status = 'inactive', updated_at = :now
               WHERE agent_id = :agent_id AND skill_id = :skill_id`;

  await execute(sql, [
    strParam("now", now),
    strParam("agent_id", agent_id),
    strParam("skill_id", skill_id),
  ]);

  return { agent_id, skill_id, status: "unsubscribed" };
}
