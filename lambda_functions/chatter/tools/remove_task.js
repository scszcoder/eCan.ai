/**
 * Tool handler: remove_task
 * Remove a task — stops any running Fargate instance, deletes the
 * EventBridge schedule, and soft-deletes the Aurora record.
 * Data source: Aurora (RDS Data API) — table: agent_tasks
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

export async function remove_task(toolInput) {
  const { task_id } = toolInput;
  if (!task_id) {
    throw new Error("task_id is required");
  }

  // 1. Load task record from Aurora to get ARN / schedule name
  const res = await execute(
    "SELECT id, name, status, metadata FROM agent_tasks WHERE id = :id",
    [strParam("id", task_id)]
  );
  const rows = rowsToObjects(res);
  const taskRecord = rows.length > 0 ? rows[0] : null;

  let meta = {};
  try { meta = taskRecord?.metadata ? JSON.parse(taskRecord.metadata) : {}; } catch (_) {}

  const actions = [];

  // 2. Stop Fargate task if running
  const ecsTaskArn = meta.ecs_task_arn;
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
  const scheduleName = meta.schedule_name || `ecan-task-${task_id}`;
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

  // 4. Soft-delete Aurora record
  await execute(
    "UPDATE agent_tasks SET status = :status, deleted_at = :now, updated_at = :now WHERE id = :id",
    [
      strParam("status", "removed"),
      strParam("now", new Date().toISOString().slice(0, 23)),
      strParam("id", task_id),
    ]
  );
  actions.push({ action: "delete_db_record", status: "success" });

  return { task_id, status: "removed", actions };
}
