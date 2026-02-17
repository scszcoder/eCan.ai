/**
 * Tool handler: list_chat_agents
 * List available agents for chat communication.
 */
import { DynamoDBClient, ScanCommand } from "@aws-sdk/client-dynamodb";
import { unmarshall } from "@aws-sdk/util-dynamodb";

const dynamodb = new DynamoDBClient({ region: "us-east-1" });
const AGENTS_TABLE = process.env.AGENTS_TABLE || "Agents";

export async function list_chat_agents(_toolInput) {
  const resp = await dynamodb.send(new ScanCommand({
    TableName: AGENTS_TABLE,
    ProjectionExpression: "agent_id, agent_name, #s, agent_type",
    ExpressionAttributeNames: { "#s": "status" },
    Limit: 100,
  }));

  const agents = (resp.Items || []).map(item => unmarshall(item));
  return { agents, count: agents.length };
}
