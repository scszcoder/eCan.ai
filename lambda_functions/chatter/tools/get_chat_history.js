/**
 * Tool handler: get_chat_history
 * Get chat history with a specific agent.
 */
import { DynamoDBClient, QueryCommand } from "@aws-sdk/client-dynamodb";
import { unmarshall } from "@aws-sdk/util-dynamodb";

const dynamodb = new DynamoDBClient({ region: "us-east-1" });
const A2A_MESSAGES_TABLE = process.env.A2A_MESSAGES_TABLE || "A2A_Messages";

export async function get_chat_history(toolInput) {
  const { agent_id, limit } = toolInput;
  if (!agent_id) {
    throw new Error("agent_id is required");
  }

  const resp = await dynamodb.send(new QueryCommand({
    TableName: A2A_MESSAGES_TABLE,
    KeyConditionExpression: "channel_id = :cid",
    ExpressionAttributeValues: { ":cid": { S: agent_id } },
    ScanIndexForward: false, // newest first
    Limit: limit || 50,
  }));

  const messages = (resp.Items || []).map(item => unmarshall(item));
  return { messages, count: messages.length };
}
