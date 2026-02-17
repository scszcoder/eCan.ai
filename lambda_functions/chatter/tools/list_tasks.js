/**
 * Tool handler: list_tasks
 * List all tasks and their statuses, enriched with live Fargate task state.
 *
 * 1. Queries DynamoDB Tasks table for the owner's tasks.
 * 2. For any task with an ecs_task_arn, calls ECS DescribeTasks to get live status.
 * 3. Optionally queries EventBridge Scheduler to check schedule state.
 */
import {
  ECSClient,
  DescribeTasksCommand,
  ListTasksCommand,
} from "@aws-sdk/client-ecs";
import {
  SchedulerClient,
  ListSchedulesCommand,
} from "@aws-sdk/client-scheduler";
import { DynamoDBClient, QueryCommand } from "@aws-sdk/client-dynamodb";
import { unmarshall } from "@aws-sdk/util-dynamodb";

const ecs       = new ECSClient({ region: "us-east-1" });
const scheduler = new SchedulerClient({ region: "us-east-1" });
const dynamodb  = new DynamoDBClient({ region: "us-east-1" });

const ECS_CLUSTER = process.env.ECS_CLUSTER || "";
const TASKS_TABLE = process.env.TASKS_TABLE || "Tasks";

export async function list_tasks(toolInput) {
  const { owner_id, agent_id, status_filter } = toolInput;
  if (!owner_id) {
    throw new Error("owner_id is required");
  }

  // 1. Query DynamoDB for tasks belonging to this owner
  const queryParams = {
    TableName: TASKS_TABLE,
    KeyConditionExpression: "owner_id = :oid",
    ExpressionAttributeValues: { ":oid": { S: owner_id } },
  };
  if (agent_id) {
    queryParams.FilterExpression = "agent_id = :aid";
    queryParams.ExpressionAttributeValues[":aid"] = { S: agent_id };
  }

  const resp = await dynamodb.send(new QueryCommand(queryParams));
  let tasks = (resp.Items || []).map(item => unmarshall(item));

  // 2. Enrich tasks that have an ecs_task_arn with live ECS status
  const arns = tasks
    .map(t => t.ecs_task_arn)
    .filter(Boolean);

  if (arns.length > 0 && ECS_CLUSTER) {
    try {
      // DescribeTasks accepts up to 100 ARNs
      const batchSize = 100;
      const ecsStatusMap = new Map();
      for (let i = 0; i < arns.length; i += batchSize) {
        const batch = arns.slice(i, i + batchSize);
        const descResp = await ecs.send(new DescribeTasksCommand({
          cluster: ECS_CLUSTER,
          tasks: batch,
        }));
        for (const t of (descResp.tasks || [])) {
          ecsStatusMap.set(t.taskArn, {
            ecs_status: t.lastStatus,          // PROVISIONING, PENDING, RUNNING, DEPROVISIONING, STOPPED
            ecs_desired_status: t.desiredStatus,
            ecs_started_at: t.startedAt?.toISOString() ?? null,
            ecs_stopped_at: t.stoppedAt?.toISOString() ?? null,
            ecs_stop_reason: t.stoppedReason ?? null,
          });
        }
      }
      // Merge ECS info into task records
      for (const task of tasks) {
        if (task.ecs_task_arn && ecsStatusMap.has(task.ecs_task_arn)) {
          Object.assign(task, ecsStatusMap.get(task.ecs_task_arn));
        }
      }
    } catch (err) {
      // Non-fatal — return tasks without live ECS enrichment
      console.warn(`[list_tasks] ECS DescribeTasks failed: ${err.message}`);
    }
  }

  // 3. Enrich with EventBridge Scheduler info for scheduled tasks
  try {
    const schedResp = await scheduler.send(new ListSchedulesCommand({
      NamePrefix: "ecan-task-",
      GroupName: "default",
      MaxResults: 100,
    }));
    const schedMap = new Map();
    for (const s of (schedResp.Schedules || [])) {
      schedMap.set(s.Name, {
        schedule_state: s.State,              // ENABLED / DISABLED
        schedule_expression: s.ScheduleExpression ?? null,
      });
    }
    for (const task of tasks) {
      const sName = task.schedule_name || `ecan-task-${task.task_id}`;
      if (schedMap.has(sName)) {
        Object.assign(task, schedMap.get(sName));
      }
    }
  } catch (err) {
    console.warn(`[list_tasks] EventBridge ListSchedules failed: ${err.message}`);
  }

  // 4. Filter by status if requested
  if (status_filter && status_filter !== "all") {
    tasks = tasks.filter(t => {
      const effectiveStatus = t.ecs_status?.toLowerCase() || t.status;
      return effectiveStatus === status_filter;
    });
  }

  return { tasks, count: tasks.length };
}
