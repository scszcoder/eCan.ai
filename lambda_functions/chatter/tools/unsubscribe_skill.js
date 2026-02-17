/**
 * Tool handler: unsubscribe_skill
 * Unsubscribe an agent from a skill.
 */
import { DynamoDBClient, DeleteItemCommand } from "@aws-sdk/client-dynamodb";

const dynamodb = new DynamoDBClient({ region: "us-east-1" });
const SUBSCRIPTIONS_TABLE = process.env.SUBSCRIPTIONS_TABLE || "Agent_Skill_Subscriptions";

export async function unsubscribe_skill(toolInput) {
  const { agent_id, skill_id } = toolInput;
  if (!agent_id || !skill_id) {
    throw new Error("agent_id and skill_id are required");
  }

  await dynamodb.send(new DeleteItemCommand({
    TableName: SUBSCRIPTIONS_TABLE,
    Key: {
      agent_id: { S: agent_id },
      skill_id: { S: skill_id },
    },
  }));

  return { agent_id, skill_id, status: "unsubscribed" };
}
