/**
 * Tool handler: create_task_with_skill
 * Create a new task linked to a skill.
 */
import { DynamoDBClient, PutItemCommand } from "@aws-sdk/client-dynamodb";
import { marshall } from "@aws-sdk/util-dynamodb";
import { randomUUID } from "node:crypto";

const dynamodb = new DynamoDBClient({ region: "us-east-1" });
const TASKS_TABLE = process.env.TASKS_TABLE || "Tasks";

export async function create_task_with_skill(toolInput) {
  const { owner_id, task_name, skill_name, description, parameters, schedule } = toolInput;
  if (!owner_id || !task_name || !skill_name) {
    throw new Error("owner_id, task_name, and skill_name are required");
  }

  const taskId = randomUUID();
  const now = new Date().toISOString();
  const item = {
    owner_id,
    task_id: taskId,
    task_name,
    skill_name,
    description: description || "",
    parameters: parameters || {},
    schedule: schedule || null,
    status: schedule ? "scheduled" : "created",
    created_at: now,
    updated_at: now,
  };

  await dynamodb.send(new PutItemCommand({
    TableName: TASKS_TABLE,
    Item: marshall(item, { removeUndefinedValues: true }),
  }));

  return { task_id: taskId, task_name, skill_name, status: item.status, created_at: now };
}
