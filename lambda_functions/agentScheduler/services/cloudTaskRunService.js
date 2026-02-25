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
  UpdateItemCommand,
  QueryCommand,
} = require("@aws-sdk/client-dynamodb");
const { marshall, unmarshall } = require("@aws-sdk/util-dynamodb");

const REGION = process.env.AWS_REGION || "us-east-1";
const CLOUD_TASK_RUNS_TABLE = process.env.CLOUD_TASK_RUNS_TABLE || process.env.AGENT_TASKS_DDB_TABLE || "agent_tasks";
const CLOUD_TASK_RUNS_HISTORY_TABLE = process.env.CLOUD_TASK_RUNS_HISTORY_TABLE || "agent_tasks_history";

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

function _ecsTaskIdFromArn(taskArn) {
  if (!taskArn || typeof taskArn !== "string") return "";
  const parts = taskArn.split("/");
  return parts.length > 0 ? (parts[parts.length - 1] || "") : "";
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
  // Use UpdateItem (instead of PutItem) so we do not clobber auxiliary attributes
  // such as throttling/lease fields.
  const updateParts = [
    "run_id = :rid",
    "schedule = :sch",
    "updated_at = :now",
  ];
  const values = {
    ":rid": run_id || "",
    ":sch": safeStringify(schedule),
    ":now": now,
  };
  if (host_name) {
    updateParts.push("host_name = :hn");
    values[":hn"] = String(host_name);
  }
  if (meta_data !== undefined) {
    updateParts.push("meta_data = :md");
    values[":md"] = safeStringify(meta_data);
  }

  const res = await dynamodb.send(new UpdateItemCommand({
    TableName: CLOUD_TASK_RUNS_TABLE,
    Key: marshall({ owner_id, task_id }),
    UpdateExpression: `SET ${updateParts.join(", ")}`,
    ExpressionAttributeValues: marshall(values, { removeUndefinedValues: true }),
    ReturnValues: "ALL_NEW",
  }));

  return res.Attributes ? unmarshall(res.Attributes) : {
    owner_id,
    task_id,
    run_id: run_id || "",
    schedule: safeStringify(schedule),
    updated_at: now,
    ...(host_name ? { host_name: String(host_name) } : {}),
    ...(meta_data !== undefined ? { meta_data: safeStringify(meta_data) } : {}),
  };
}

/**
 * Acquire a short-lived launch lease for a (owner_id, task_id) pair.
 * This prevents runaway clients from launching many tasks concurrently.
 */
async function acquireLaunchLease({ owner_id, task_id, lease_seconds = 20, reason = "runCloudTasks" }) {
  if (!owner_id || !task_id) {
    throw new Error("owner_id and task_id are required");
  }

  const seconds = Number(lease_seconds);
  if (!Number.isFinite(seconds) || seconds <= 0) {
    return { ok: true, skipped: true };
  }

  const nowSec = Math.floor(Date.now() / 1000);
  const untilSec = nowSec + Math.floor(seconds);

  try {
    const res = await dynamodb.send(new UpdateItemCommand({
      TableName: CLOUD_TASK_RUNS_TABLE,
      Key: marshall({ owner_id, task_id }),
      UpdateExpression: "SET launch_lease_until = :until, launch_lease_set_at = :now, launch_lease_reason = :reason",
      ConditionExpression: "attribute_not_exists(launch_lease_until) OR launch_lease_until < :now",
      ExpressionAttributeValues: marshall({
        ":until": untilSec,
        ":now": nowSec,
        ":reason": String(reason || ""),
      }, { removeUndefinedValues: true }),
      ReturnValues: "ALL_NEW",
    }));

    return { ok: true, nowSec, untilSec, item: res.Attributes ? unmarshall(res.Attributes) : null };
  } catch (e) {
    if (e && (e.name === "ConditionalCheckFailedException" || e.Code === "ConditionalCheckFailedException")) {
      return { ok: false, nowSec, untilSec: null, throttled: true };
    }
    throw e;
  }
}

async function clearLaunchLease({ owner_id, task_id }) {
  if (!owner_id || !task_id) {
    throw new Error("owner_id and task_id are required");
  }
  try {
    await dynamodb.send(new UpdateItemCommand({
      TableName: CLOUD_TASK_RUNS_TABLE,
      Key: marshall({ owner_id, task_id }),
      UpdateExpression: "REMOVE launch_lease_until, launch_lease_set_at, launch_lease_reason",
    }));
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e?.message || String(e) };
  }
}

/**
 * Append-only history record of task runs.
 *
 * Expected table shape:
 *   PK: owner_id (String)
 *   SK: run_sk  (String)  // `${run_started_at}#${run_id}`
 */
async function appendTaskRunHistory({ owner_id, task_id, task_arn, run_started_at, schedule, host_name, meta_data }) {
  if (!owner_id || !task_id) {
    throw new Error("owner_id and task_id are required");
  }
  const startedAt = (run_started_at ? String(run_started_at) : new Date().toISOString());
  const runId = _ecsTaskIdFromArn(task_arn) || "";
  const runSk = `${startedAt}#${runId || "unknown"}`;

  const item = {
    owner_id,
    run_sk: runSk,
    task_id,
    run_id: runId,
    task_arn: task_arn || "",
    run_started_at: startedAt,
    schedule: safeStringify(schedule),
    created_at: new Date().toISOString(),
  };
  if (host_name) item.host_name = String(host_name);
  if (meta_data !== undefined) item.meta_data = safeStringify(meta_data);

  await dynamodb.send(new PutItemCommand({
    TableName: CLOUD_TASK_RUNS_HISTORY_TABLE,
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
  CLOUD_TASK_RUNS_HISTORY_TABLE,
  getTaskRun,
  upsertTaskRun,
  appendTaskRunHistory,
  findTaskRunByHostName,
  acquireLaunchLease,
  clearLaunchLease,
};
