/**
 * Tool handler: list_skills
 * List all available skills and their statuses.
 * Data source: Aurora (RDS Data API) — table: agent_skills
 */
import { execute, strParam, rowsToObjects } from "./rdsClient.js";

export async function list_skills(toolInput) {
  const { owner_id, category, status_filter } = toolInput;
  if (!owner_id) {
    throw new Error("owner_id is required");
  }

  let sql = "SELECT * FROM agent_skills WHERE owner = :owner";
  const params = [strParam("owner", owner_id)];

  if (category) {
    sql += " AND JSON_CONTAINS(tags, :cat, '$')";
    params.push(strParam("cat", JSON.stringify(category)));
  }

  sql += " ORDER BY updated_at DESC";

  const result = await execute(sql, params);
  const skills = rowsToObjects(result);

  return { skills, count: skills.length };
}
