/**
 * Tool handler: list_agents
 * List all available agents and their statuses.
 */
import { DynamoDBClient, QueryCommand } from "@aws-sdk/client-dynamodb";
import { unmarshall } from "@aws-sdk/util-dynamodb";

const dynamodb = new DynamoDBClient({ region: "us-east-1" });
const AGENTS_TABLE = process.env.AGENTS_TABLE || "Agents";

export async function list_agents(toolInput) {
  const { owner_id, status_filter } = toolInput;
  if (!owner_id) {
    throw new Error("owner_id is required");
  }

  const resp = await dynamodb.send(new QueryCommand({
    TableName: AGENTS_TABLE,
    KeyConditionExpression: "owner_id = :oid",
    ExpressionAttributeValues: { ":oid": { S: owner_id } },
  }));

  let agents = (resp.Items || []).map(item => unmarshall(item));

  if (status_filter && status_filter !== "all") {
    agents = agents.filter(a => a.status === status_filter);
  }

  return { agents, count: agents.length };
}
