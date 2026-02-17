/**
 * Tool handler: remove_task
 * Remove a task — stops any running Fargate instance, deletes the
 * EventBridge schedule, and deletes the DynamoDB record.
 */
import { ECSClient, StopTaskCommand } from "@aws-sdk/client-ecs";
import {
  SchedulerClient,
  DeleteScheduleCommand,
} from "@aws-sdk/client-scheduler";
import {
  DynamoDBClient,
  GetItemCommand,
  DeleteItemCommand,
} from "@aws-sdk/client-dynamodb";
import { unmarshall } from "@aws-sdk/util-dynamodb";

const ecs       = new ECSClient({ region: "us-east-1" });
const scheduler = new SchedulerClient({ region: "us-east-1" });
const dynamodb  = new DynamoDBClient({ region: "us-east-1" });

const ECS_CLUSTER = process.env.ECS_CLUSTER || "";
const TASKS_TABLE = process.env.TASKS_TABLE || "Tasks";

export async function remove_task(toolInput) {
  const { task_id } = toolInput;
  if (!task_id) {
    throw new Error("task_id is required");
  }

  // 1. Load task record to get ARN / schedule name
  const getResp = await dynamodb.send(new GetItemCommand({
    TableName: TASKS_TABLE,
    Key: { task_id: { S: task_id } },
  }));
  const taskRecord = getResp.Item ? unmarshall(getResp.Item) : null;

  const actions = [];

  // 2. Stop Fargate task if running
  const ecsTaskArn = taskRecord?.ecs_task_arn;
  if (ecsTaskArn && ECS_CLUSTER) {
    try {
      await ecs.send(new StopTaskCommand({
        cluster: ECS_CLUSTER,
        task: ecsTaskArn,
        reason: `Removed by chatter tool (task_id=${task_id})`,
      }));
      actions.push({ action: "ecs_stop_task", status: "success" });
    } catch (err) {
      actions.push({ action: "ecs_stop_task", status: "skipped", error: err.message });
    }
  }

  // 3. Delete EventBridge schedule
  const scheduleName = taskRecord?.schedule_name || `ecan-task-${task_id}`;
  try {
    await scheduler.send(new DeleteScheduleCommand({
      Name: scheduleName,
      GroupName: "default",
    }));
    actions.push({ action: "delete_schedule", status: "success" });
  } catch (err) {
    if (err.name !== "ResourceNotFoundException") {
      actions.push({ action: "delete_schedule", status: "skipped", error: err.message });
    }
  }

  // 4. Delete DynamoDB record
  await dynamodb.send(new DeleteItemCommand({
    TableName: TASKS_TABLE,
    Key: { task_id: { S: task_id } },
  }));
  actions.push({ action: "delete_db_record", status: "success" });

  return { task_id, status: "removed", actions };
}
