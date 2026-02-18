/**
 * Tool handler: stop_task
 * Stop a running task (Fargate instance) and optionally delete its EventBridge schedule.
 * Data source: Aurora (RDS Data API) — table: agent_tasks
 *
 * Looks up the task in Aurora to find:
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
import { execute, strParam, rowsToObjects } from "./rdsClient.js";

const ecs       = new ECSClient({ region: "us-east-1" });
const scheduler = new SchedulerClient({ region: "us-east-1" });

const ECS_CLUSTER = process.env.ECS_CLUSTER || "";

export async function stop_task(toolInput) {
  const { task_id } = toolInput;
  if (!task_id) {
    throw new Error("task_id is required");
  }

  // 1. Look up task record in Aurora
  const res = await execute(
    "SELECT id, name, status, metadata FROM agent_tasks WHERE id = :id",
    [strParam("id", task_id)]
  );
  const rows = rowsToObjects(res);
  const taskRecord = rows.length > 0 ? rows[0] : null;

  // Parse metadata JSON to get ecs_task_arn and schedule_name
  let meta = {};
  try { meta = taskRecord?.metadata ? JSON.parse(taskRecord.metadata) : {}; } catch (_) {}

  const results = { task_id, actions: [] };

  // 2. Stop the running Fargate task if we have an ARN
  const ecsTaskArn = meta.ecs_task_arn;
  if (ecsTaskArn && ECS_CLUSTER) {
    try {
      await ecs.send(new StopTaskCommand({
        cluster: ECS_CLUSTER,
        task: ecsTaskArn,
        reason: `Stopped by chatter tool (task_id=${task_id})`,
      }));
      results.actions.push({ action: "ecs_stop_task", status: "success", ecs_task_arn: ecsTaskArn });
    } catch (err) {
      results.actions.push({ action: "ecs_stop_task", status: "failed", error: err.message });
    }
  }

  // 3. Delete the EventBridge schedule if one exists
  const scheduleName = meta.schedule_name || `ecan-task-${task_id}`;
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
  }

  // 4. Update Aurora status
  await execute(
    "UPDATE agent_tasks SET status = :status, updated_at = :now WHERE id = :id",
    [
      strParam("status", "stopped"),
      strParam("now", new Date().toISOString().slice(0, 23)),
      strParam("id", task_id),
    ]
  );

  results.status = "stopped";
  return results;
}
