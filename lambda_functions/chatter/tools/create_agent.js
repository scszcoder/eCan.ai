/**
 * Tool handler: create_agent
 * Create a new agent.
 */
import { DynamoDBClient, PutItemCommand } from "@aws-sdk/client-dynamodb";
import { marshall } from "@aws-sdk/util-dynamodb";
import { randomUUID } from "node:crypto";

const dynamodb = new DynamoDBClient({ region: "us-east-1" });
const AGENTS_TABLE = process.env.AGENTS_TABLE || "Agents";

export async function create_agent(toolInput) {
  const { owner_id, agent_name, agent_type, description, config } = toolInput;
  if (!owner_id || !agent_name) {
    throw new Error("owner_id and agent_name are required");
  }

  const agentId = randomUUID();
  const now = new Date().toISOString();
  const item = {
    owner_id,
    agent_id: agentId,
    agent_name,
    agent_type: agent_type || "worker",
    description: description || "",
    config: config || {},
    status: "online",
    created_at: now,
    updated_at: now,
  };

  await dynamodb.send(new PutItemCommand({
    TableName: AGENTS_TABLE,
    Item: marshall(item, { removeUndefinedValues: true }),
  }));

  return { agent_id: agentId, agent_name, status: "created", created_at: now };
}
