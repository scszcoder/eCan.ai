/**
 * Tool handler: stop_task
 * Stop a running task (Fargate instance) and optionally delete its EventBridge schedule.
 *
 * Looks up the task in DynamoDB to find:
 *   - ecs_task_arn   → calls ECS StopTask to kill the running container
 *   - schedule_name  → calls EventBridge Scheduler DeleteSchedule to remove recurring trigger
 *
 * Required env vars: ECS_CLUSTER
 */
import { ECSClient, StopTaskCommand } from "@aws-sdk/client-ecs";
import {
  SchedulerClient,
  DeleteScheduleCommand,
} from "@aws-sdk/client-scheduler";
import {
  DynamoDBClient,
  GetItemCommand,
  UpdateItemCommand,
} from "@aws-sdk/client-dynamodb";
import { unmarshall } from "@aws-sdk/util-dynamodb";

const ecs       = new ECSClient({ region: "us-east-1" });
const scheduler = new SchedulerClient({ region: "us-east-1" });
const dynamodb  = new DynamoDBClient({ region: "us-east-1" });

const ECS_CLUSTER = process.env.ECS_CLUSTER || "";
const TASKS_TABLE = process.env.TASKS_TABLE || "Tasks";

export async function stop_task(toolInput) {
  const { task_id } = toolInput;
  if (!task_id) {
    throw new Error("task_id is required");
  }

  // 1. Look up task record in DynamoDB
  const getResp = await dynamodb.send(new GetItemCommand({
    TableName: TASKS_TABLE,
    Key: { task_id: { S: task_id } },
  }));
  const taskRecord = getResp.Item ? unmarshall(getResp.Item) : null;

  const results = { task_id, actions: [] };

  // 2. Stop the running Fargate task if we have an ARN
  const ecsTaskArn = taskRecord?.ecs_task_arn;
  if (ecsTaskArn && ECS_CLUSTER) {
    try {
      await ecs.send(new StopTaskCommand({
        cluster: ECS_CLUSTER,
        task: ecsTaskArn,
        reason: `Stopped by chatter tool (task_id=${task_id})`,
      }));
      results.actions.push({ action: "ecs_stop_task", status: "success", ecs_task_arn: ecsTaskArn });
    } catch (err) {
      // Task may already be stopped — treat InvalidParameterException as non-fatal
      results.actions.push({ action: "ecs_stop_task", status: "failed", error: err.message });
    }
  }

  // 3. Delete the EventBridge schedule if one exists
  const scheduleName = taskRecord?.schedule_name || `ecan-task-${task_id}`;
  try {
    await scheduler.send(new DeleteScheduleCommand({
      Name: scheduleName,
      GroupName: "default",
    }));
    results.actions.push({ action: "delete_schedule", status: "success", schedule_name: scheduleName });
  } catch (err) {
    if (err.name !== "ResourceNotFoundException") {
      results.actions.push({ action: "delete_schedule", status: "failed", error: err.message });
    }
    // ResourceNotFoundException is fine — no schedule to delete
  }

  // 4. Update DynamoDB status
  await dynamodb.send(new UpdateItemCommand({
    TableName: TASKS_TABLE,
    Key: { task_id: { S: task_id } },
    UpdateExpression: "SET #status = :status, updated_at = :now",
    ExpressionAttributeNames: { "#status": "status" },
    ExpressionAttributeValues: {
      ":status": { S: "stopped" },
      ":now": { S: new Date().toISOString() },
    },
  }));

  results.status = "stopped";
  return results;
}
