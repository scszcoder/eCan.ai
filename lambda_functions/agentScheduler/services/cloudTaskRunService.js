/**
 * DynamoDB-based Cloud Task Run Service
 *
 * Stores latest ECS/Fargate run id per task.
 *
 * Expected table shape (recommended):
 *   PK: owner_id (String)
 *   SK: task_id  (String)
 *
 * Attributes:
 *   run_id   (String)  - ECS taskArn or other run identifier
 *   schedule (String)  - JSON string (or schedule expression)
 *   host_name (String) - optional
 *   meta_data (String) - optional JSON string
 *   updated_at (String) - ISO timestamp
 */

const {
  DynamoDBClient,
  GetItemCommand,
  PutItemCommand,
  QueryCommand,
} = require("@aws-sdk/client-dynamodb");
const { marshall, unmarshall } = require("@aws-sdk/util-dynamodb");

const REGION = process.env.AWS_REGION || "us-east-1";
const CLOUD_TASK_RUNS_TABLE = process.env.CLOUD_TASK_RUNS_TABLE || process.env.AGENT_TASKS_DDB_TABLE || "agent_tasks";

const dynamodb = new DynamoDBClient({ region: REGION });

function safeStringify(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

async function getTaskRun({ owner_id, task_id }) {
  if (!owner_id || !task_id) return null;
  const res = await dynamodb.send(new GetItemCommand({
    TableName: CLOUD_TASK_RUNS_TABLE,
    Key: marshall({ owner_id, task_id }),
  }));
  if (!res.Item) return null;
  return unmarshall(res.Item);
}

async function upsertTaskRun({ owner_id, task_id, run_id, schedule, host_name, meta_data }) {
  if (!owner_id || !task_id) {
    throw new Error("owner_id and task_id are required");
  }
  const now = new Date().toISOString();
  const item = {
    owner_id,
    task_id,
    run_id: run_id || "",
    schedule: safeStringify(schedule),
    updated_at: now,
  };
  if (host_name) item.host_name = String(host_name);
  if (meta_data !== undefined) item.meta_data = safeStringify(meta_data);

  await dynamodb.send(new PutItemCommand({
    TableName: CLOUD_TASK_RUNS_TABLE,
    Item: marshall(item, { removeUndefinedValues: true }),
  }));

  return item;
}

async function findTaskRunByHostName({ owner_id, host_name, limit = 25 }) {
  if (!owner_id || !host_name) return null;

  // Query by owner_id then filter in memory (no assumptions about GSIs)
  const res = await dynamodb.send(new QueryCommand({
    TableName: CLOUD_TASK_RUNS_TABLE,
    KeyConditionExpression: "owner_id = :oid",
    ExpressionAttributeValues: marshall({ ":oid": owner_id }),
    Limit: limit,
  }));

  const items = (res.Items || []).map((it) => unmarshall(it));
  const filtered = items.filter((it) => String(it.host_name || "") === String(host_name));
  if (filtered.length === 0) return null;

  // Prefer newest by updated_at
  filtered.sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")));
  return filtered[0];
}

module.exports = {
  CLOUD_TASK_RUNS_TABLE,
  getTaskRun,
  upsertTaskRun,
  findTaskRunByHostName,
};
