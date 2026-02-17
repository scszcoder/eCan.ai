/**
 * Tool handler: agent_add_tasks
 * Assign one or more tasks to an agent.
 */
import { DynamoDBClient, UpdateItemCommand } from "@aws-sdk/client-dynamodb";

const dynamodb = new DynamoDBClient({ region: "us-east-1" });
const TASKS_TABLE = process.env.TASKS_TABLE || "Tasks";

export async function agent_add_tasks(toolInput) {
  const { agent_id, task_ids } = toolInput;
  if (!agent_id || !task_ids || task_ids.length === 0) {
    throw new Error("agent_id and task_ids (non-empty array) are required");
  }

  const results = [];
  for (const task_id of task_ids) {
    try {
      await dynamodb.send(new UpdateItemCommand({
        TableName: TASKS_TABLE,
        Key: { task_id: { S: task_id } },
        UpdateExpression: "SET agent_id = :aid, updated_at = :now",
        ExpressionAttributeValues: {
          ":aid": { S: agent_id },
          ":now": { S: new Date().toISOString() },
        },
      }));
      results.push({ task_id, status: "assigned" });
    } catch (err) {
      results.push({ task_id, status: "failed", error: err.message });
    }
  }

  return { agent_id, assignments: results, assigned_count: results.filter(r => r.status === "assigned").length };
}
