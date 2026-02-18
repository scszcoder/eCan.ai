/**
 * Tool handler: list_agents
 * List all available agents and their statuses.
 * Data source: Aurora (RDS Data API) — table: agents
 */
import { execute, strParam, rowsToObjects } from "./rdsClient.js";

export async function list_agents(toolInput) {
  const { owner_id, status_filter } = toolInput;
  if (!owner_id) {
    throw new Error("owner_id is required");
  }

  let sql = "SELECT * FROM agents WHERE owner = :owner AND deleted_at IS NULL";
  const params = [strParam("owner", owner_id)];

  if (status_filter && status_filter !== "all") {
    sql += " AND status = :status";
    params.push(strParam("status", status_filter));
  }

  sql += " ORDER BY updated_at DESC";

  const result = await execute(sql, params);
  const agents = rowsToObjects(result);

  return { agents, count: agents.length };
}
