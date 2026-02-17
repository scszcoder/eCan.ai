/**
 * Tool handler: subscribe_skill
 * Subscribe an agent to a skill so it can use it.
 */
import { DynamoDBClient, PutItemCommand } from "@aws-sdk/client-dynamodb";
import { marshall } from "@aws-sdk/util-dynamodb";

const dynamodb = new DynamoDBClient({ region: "us-east-1" });
const SUBSCRIPTIONS_TABLE = process.env.SUBSCRIPTIONS_TABLE || "Agent_Skill_Subscriptions";

export async function subscribe_skill(toolInput) {
  const { agent_id, skill_id, role } = toolInput;
  if (!agent_id || !skill_id) {
    throw new Error("agent_id and skill_id are required");
  }

  const now = new Date().toISOString();
  const item = {
    agent_id,
    skill_id,
    role: role || "executor",
    subscribed_at: now,
  };

  await dynamodb.send(new PutItemCommand({
    TableName: SUBSCRIPTIONS_TABLE,
    Item: marshall(item),
  }));

  return { agent_id, skill_id, role: item.role, status: "subscribed", subscribed_at: now };
}
