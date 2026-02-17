/**
 * Tool handler: schedule_task
 * Schedule a task to run at a specific time or interval, or run it immediately.
 *
 * A "task" is a Fargate instance launch.
 *
 * Schedule modes:
 *   - "now" / "immediate"  → directly calls ECS RunTask (no scheduler)
 *   - ISO datetime          → one-time via EventBridge Scheduler at()
 *   - cron expression       → recurring via EventBridge Scheduler cron()
 *   - rate expression       → recurring via EventBridge Scheduler rate()
 *
 * Required env vars (shared with skill_editor_lambda / agentScheduler):
 *   ECS_CLUSTER, ECS_TASK_DEFINITION, ECS_SUBNETS (comma-separated),
 *   ECS_SECURITY_GROUPS (comma-separated, optional),
 *   SCHEDULER_ROLE_ARN  — IAM role that EventBridge Scheduler assumes
 *                         to call ecs:RunTask (not needed for "now" mode).
 */
import { ECSClient, RunTaskCommand } from "@aws-sdk/client-ecs";
import {
  SchedulerClient,
  CreateScheduleCommand,
  UpdateScheduleCommand,
} from "@aws-sdk/client-scheduler";
import { DynamoDBClient, PutItemCommand } from "@aws-sdk/client-dynamodb";
import { marshall } from "@aws-sdk/util-dynamodb";

const ecsClient = new ECSClient({ region: "us-east-1" });
const scheduler = new SchedulerClient({ region: "us-east-1" });
const dynamodb  = new DynamoDBClient({ region: "us-east-1" });

const ECS_CLUSTER          = process.env.ECS_CLUSTER          || "";
const ECS_TASK_DEFINITION  = process.env.ECS_TASK_DEFINITION  || "";
const ECS_SUBNETS          = (process.env.ECS_SUBNETS          || "").split(",").filter(Boolean);
const ECS_SECURITY_GROUPS  = (process.env.ECS_SECURITY_GROUPS  || "").split(",").filter(Boolean);
const ECS_CONTAINER_NAME   = process.env.ECS_CONTAINER_NAME   || "ecan-cloud-worker";
const SCHEDULER_ROLE_ARN   = process.env.SCHEDULER_ROLE_ARN   || "";
const TASKS_TABLE          = process.env.TASKS_TABLE           || "Tasks";
const AWS_ACCOUNT_ID       = process.env.AWS_ACCOUNT_ID        || "667118410653";

/** Check if the schedule means "run right now". */
function isRunNow(schedule) {
  const s = schedule.trim().toLowerCase();
  return s === "now" || s === "immediate" || s === "immediately" || s === "run_now";
}

/**
 * Convert user-friendly schedule string to EventBridge expression.
 */
function toScheduleExpression(schedule) {
  if (schedule.startsWith("cron(") || schedule.startsWith("at(") || schedule.startsWith("rate(")) {
    return schedule;
  }
  if (/^\d{4}-\d{2}-\d{2}T/.test(schedule)) {
    return `at(${schedule.replace(/Z$/, "")})`;
  }
  const fields = schedule.trim().split(/\s+/);
  const expr = fields.length === 5 ? `${schedule} *` : schedule;
  return `cron(${expr})`;
}

/** Build the common container env vars. */
function buildContainerEnv(task_id, parameters) {
  return [
    { name: "ECAN_TASK_ID",     value: task_id },
    { name: "ECAN_WORKER_MODE", value: "scheduled" },
    ...(parameters
      ? [{ name: "ECAN_TASK_PARAMS", value: JSON.stringify(parameters) }]
      : []),
  ];
}

export async function schedule_task(toolInput) {
  const { task_id, schedule, timezone, repeat, parameters } = toolInput;
  if (!task_id || !schedule) {
    throw new Error("task_id and schedule are required");
  }
  if (!ECS_CLUSTER || !ECS_TASK_DEFINITION) {
    throw new Error("ECS_CLUSTER and ECS_TASK_DEFINITION env vars must be set");
  }

  const now = new Date().toISOString();
  const containerEnv = buildContainerEnv(task_id, parameters);

  // Build network config (shared by both paths)
  const networkConfig = {
    awsvpcConfiguration: {
      subnets: ECS_SUBNETS,
      assignPublicIp: "ENABLED",
    },
  };
  if (ECS_SECURITY_GROUPS.length > 0) {
    networkConfig.awsvpcConfiguration.securityGroups = ECS_SECURITY_GROUPS;
  }

  // ── "Run now" path — directly call ECS RunTask ───────────────────────
  if (isRunNow(schedule)) {
    const resp = await ecsClient.send(new RunTaskCommand({
      cluster: ECS_CLUSTER,
      taskDefinition: ECS_TASK_DEFINITION,
      launchType: "FARGATE",
      networkConfiguration: networkConfig,
      overrides: {
        containerOverrides: [{
          name: ECS_CONTAINER_NAME,
          environment: containerEnv,
        }],
      },
      tags: [
        { key: "task_id", value: task_id },
        { key: "mode",    value: "run_now" },
      ],
    }));

    const tasks = resp.tasks || [];
    const ecsTaskArn = tasks.length > 0 ? tasks[0].taskArn : null;

    if (!ecsTaskArn) {
      const failures = resp.failures || [];
      const reason = failures.length > 0 ? failures[0].reason : "Unknown";
      throw new Error(`Failed to start Fargate task: ${reason}`);
    }

    // Persist to DynamoDB
    await dynamodb.send(new PutItemCommand({
      TableName: TASKS_TABLE,
      Item: marshall({
        task_id,
        ecs_task_arn: ecsTaskArn,
        schedule_expression: "now",
        status: "running",
        parameters: parameters || {},
        created_at: now,
        updated_at: now,
      }, { removeUndefinedValues: true }),
    }));

    return {
      task_id,
      ecs_task_arn: ecsTaskArn,
      mode: "run_now",
      status: "running",
    };
  }

  // ── Scheduled path — use EventBridge Scheduler ───────────────────────
  if (!SCHEDULER_ROLE_ARN) {
    throw new Error("SCHEDULER_ROLE_ARN env var must be set for EventBridge Scheduler");
  }

  const scheduleExpression = toScheduleExpression(schedule);
  const tz = timezone || "UTC";
  const scheduleName = `ecan-task-${task_id}`;
  const isOneTime = scheduleExpression.startsWith("at(");

  // EventBridge EcsParameters use PascalCase
  const ebNetworkConfig = {
    awsvpcConfiguration: {
      Subnets: ECS_SUBNETS,
      AssignPublicIp: "ENABLED",
    },
  };
  if (ECS_SECURITY_GROUPS.length > 0) {
    ebNetworkConfig.awsvpcConfiguration.SecurityGroups = ECS_SECURITY_GROUPS;
  }

  const scheduleInput = {
    Name: scheduleName,
    GroupName: "default",
    ScheduleExpression: scheduleExpression,
    ScheduleExpressionTimezone: tz,
    FlexibleTimeWindow: { Mode: "OFF" },
    Target: {
      Arn: `arn:aws:ecs:us-east-1:${AWS_ACCOUNT_ID}:cluster/${ECS_CLUSTER}`,
      RoleArn: SCHEDULER_ROLE_ARN,
      EcsParameters: {
        TaskDefinitionArn: ECS_TASK_DEFINITION,
        TaskCount: 1,
        LaunchType: "FARGATE",
        NetworkConfiguration: ebNetworkConfig,
        Overrides: {
          ContainerOverrides: [{
            Name: ECS_CONTAINER_NAME,
            Environment: containerEnv.map(e => ({ Name: e.name, Value: e.value })),
          }],
        },
      },
    },
    State: "ENABLED",
    ...(isOneTime ? { ActionAfterCompletion: "DELETE" } : {}),
  };

  try {
    await scheduler.send(new CreateScheduleCommand(scheduleInput));
  } catch (err) {
    if (err.name === "ConflictException") {
      await scheduler.send(new UpdateScheduleCommand(scheduleInput));
    } else {
      throw err;
    }
  }

  // Persist schedule metadata in DynamoDB
  await dynamodb.send(new PutItemCommand({
    TableName: TASKS_TABLE,
    Item: marshall({
      task_id,
      schedule_name: scheduleName,
      schedule_expression: scheduleExpression,
      timezone: tz,
      repeat: isOneTime ? false : (repeat !== false),
      parameters: parameters || {},
      status: "scheduled",
      created_at: now,
      updated_at: now,
    }, { removeUndefinedValues: true }),
  }));

  return {
    task_id,
    schedule_name: scheduleName,
    schedule_expression: scheduleExpression,
    timezone: tz,
    mode: isOneTime ? "one_time" : "recurring",
    status: "scheduled",
  };
}
