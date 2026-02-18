/**
 * Tool handler: create_agent
 * Create a new agent.
 * Data source: Aurora (RDS Data API) — table: agents
 */
import { execute, strParam } from "./rdsClient.js";
import { randomUUID } from "node:crypto";

export async function create_agent(toolInput) {
  const { owner_id, agent_name, description, config } = toolInput;
  if (!owner_id || !agent_name) {
    throw new Error("owner_id and agent_name are required");
  }

  const agentId = `agent_${randomUUID().replace(/-/g, "").slice(0, 16)}`;
  const now = new Date().toISOString().slice(0, 23);  // MySQL datetime(6)

  const sql = `INSERT INTO agents (id, name, owner, description, status, capabilities, extra_data, created_at, updated_at)
               VALUES (:id, :name, :owner, :desc, 'active', :config, '{}', :now, :now)`;

  await execute(sql, [
    strParam("id", agentId),
    strParam("name", agent_name),
    strParam("owner", owner_id),
    strParam("desc", description || ""),
    strParam("config", typeof config === "object" ? JSON.stringify(config) : (config || "{}")),
    strParam("now", now),
  ]);

  return { agent_id: agentId, agent_name, status: "created", created_at: now };
}
