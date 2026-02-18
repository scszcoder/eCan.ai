/**
 * Tool handler: list_chat_agents
 * List available agents for chat communication.
 * Data source: Aurora (RDS Data API) — table: agents
 */
import { execute, strParam, rowsToObjects } from "./rdsClient.js";

export async function list_chat_agents(toolInput) {
  const { owner_id } = toolInput || {};

  let sql = "SELECT id, name, status, description FROM agents WHERE deleted_at IS NULL";
  const params = [];

  if (owner_id) {
    sql += " AND owner = :owner";
    params.push(strParam("owner", owner_id));
  }

  sql += " ORDER BY name ASC LIMIT 100";

  const result = await execute(sql, params);
  const agents = rowsToObjects(result);

  return { agents, count: agents.length };
}
