function nowIso() {
  return new Date().toISOString();
}

function placeholderId(prefix) {
  return `${prefix}_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
}

function splitPath(filePath = "") {
  const normalized = String(filePath);
  const parts = normalized.split("/");
  const fileName = parts[parts.length - 1] || "";
  return { filePath: normalized, fileName };
}

function buildSkillFileContent(filePath, content = "", skillName = null) {
  const { fileName } = splitPath(filePath);
  return {
    content,
    filePath,
    fileName,
    fileSize: content ? Buffer.byteLength(content, "utf8") : 0,
    skillName: skillName || null
  };
}

function buildSkillFileInfo(filePath, skillName = null) {
  const { fileName } = splitPath(filePath);
  return {
    filePath,
    fileName,
    fileSize: 0,
    skillName: skillName || null,
    updatedAt: nowIso()
  };
}

async function getNodeStateSchema() {
  return { schemaVersion: "v0", schema: {} };
}

async function readSkillFile(filePath) {
  return buildSkillFileContent(filePath, "");
}

async function openSkillFile(filePath, skillName) {
  return buildSkillFileContent(filePath, "", skillName || null);
}

async function listSkillFiles(prefix, limit, nextToken) {
  return [];
}

async function checkSkillExists(name) {
  return { exists: false, name };
}

async function getEditorCache(userId) {
  return { cacheData: {}, recentFiles: [] };
}

async function getSkillRunStatus(runId, since) {
  return [];
}

async function getSkillEditorEvents(sessionId, since) {
  return [];
}

async function getSkillEditorChatSessions(userId) {
  return [];
}

async function getSkillEditorChatHistory(sessionId, limit, offset) {
  return [];
}

async function writeSkillFile(input) {
  return buildSkillFileInfo(input?.filePath || "");
}

async function scaffoldSkill(input) {
  return {
    skillRoot: input?.name ? `/skills/${input.name}` : "/skills/placeholder",
    name: input?.name || "placeholder",
    diagramPath: "/skills/placeholder/diagram.json"
  };
}

async function copySkillTo(input) {
  return {
    skillRoot: input?.targetDir || "/skills",
    name: input?.newName || "copy",
    diagramPath: "/skills/copy/diagram.json"
  };
}

async function saveEditorCache(input) {
  return { renamed: false, newFilePath: null };
}

async function clearEditorCache(userId) {
  return true;
}

async function runSkill(input) {
  return { runId: placeholderId("run"), status: "running", message: "placeholder", data: {} };
}

async function pauseRunSkill(input) {
  return { runId: input?.runId || null, status: "paused", message: "placeholder", data: {} };
}

async function resumeRunSkill(input) {
  return { runId: input?.runId || null, status: "running", message: "placeholder", data: {} };
}

async function stepRunSkill(input) {
  return { runId: input?.runId || null, status: "stepped", message: "placeholder", data: {} };
}

async function cancelRunSkill(input) {
  return { runId: input?.runId || null, status: "canceled", message: "placeholder", data: {} };
}

async function setupSimStep(bundle) {
  return { runId: placeholderId("sim"), status: "ready", message: "placeholder", data: {} };
}

async function stepSim() {
  return { runId: placeholderId("sim"), status: "stepped", message: "placeholder", data: {} };
}

async function testLanggraph2Flowgram() {
  return { runId: placeholderId("sim"), status: "ok", message: "placeholder", data: {} };
}

async function simTimerEvent() {
  return { runId: placeholderId("sim"), status: "ok", message: "placeholder", data: {} };
}

async function simWebsocketEvent() {
  return { runId: placeholderId("sim"), status: "ok", message: "placeholder", data: {} };
}

async function simSseEvent() {
  return { runId: placeholderId("sim"), status: "ok", message: "placeholder", data: {} };
}

async function simWebhookEvent() {
  return { runId: placeholderId("sim"), status: "ok", message: "placeholder", data: {} };
}

async function setSkillBreakpoints(username, node_name) {
  return { success: true, message: "placeholder", data: {} };
}

async function clearSkillBreakpoints(username, node_name) {
  return { success: true, message: "placeholder", data: {} };
}

async function requestSkillState(username, skill) {
  return { success: true, message: "placeholder", data: {} };
}

async function injectSkillState(username, skill) {
  return { success: true, message: "placeholder", data: {} };
}

async function loadSkillSchemas(username, skill) {
  return { success: true, message: "placeholder", data: {} };
}

async function createSkillEditorChatSession(input) {
  return {
    id: placeholderId("session"),
    name: input?.name || null,
    flowgramId: input?.flowgramId || null,
    createdAt: nowIso(),
    updatedAt: nowIso()
  };
}

async function sendSkillEditorChatMessage(input) {
  const message = {
    id: placeholderId("msg"),
    role: "assistant",
    content: "placeholder",
    timestamp: nowIso(),
    attachments: null,
    metadata: null
  };
  return {
    sessionId: input?.sessionId || placeholderId("session"),
    sessionName: input?.name || null,
    state: "queued",
    intent: null,
    message,
    clarification: null,
    plan: null,
    flowgram: null,
    validation: null
  };
}

async function cancelSkillEditorChatGeneration(sessionId) {
  return true;
}

async function deleteSkillEditorChatSession(sessionId) {
  return true;
}

/**
 * Query the cloud task run ID from DynamoDB.
 * Looks up the AGENT_TASKS table by task_id to find the associated runID.
 *
 * @param {string|null} taskId - The task ID to look up
 * @param {object} metaData - Additional metadata for the query (e.g. owner)
 * @returns {TaskStatus} - { id, runID, runner, status, success, error, timestamp }
 */
async function queryCloudTaskRunId(taskId, hostName, metaData) {
  const AWS = require("aws-sdk");
  const dynamodb = new AWS.DynamoDB.DocumentClient();

  const RUNS_TABLE = process.env.CLOUD_TASK_RUNS_TABLE || process.env.AGENT_TASKS_DDB_TABLE || "agent_tasks";
  const HISTORY_TABLE = process.env.CLOUD_TASK_RUNS_HISTORY_TABLE || "agent_tasks_history";

  const ecsTaskIdFromArn = (taskArn) => {
    if (!taskArn || typeof taskArn !== "string") return null;
    const parts = taskArn.split("/");
    const last = parts.length ? parts[parts.length - 1] : "";
    return last || null;
  };

  try {
    // Parse metaData if it's a string (AWSJSON comes as string)
    let meta = metaData;
    if (typeof meta === "string") {
      try { meta = JSON.parse(meta); } catch (_) { meta = {}; }
    }
    meta = meta || {};

    const ownerId = meta.owner_id || meta.ownerId || meta.sub || meta.userSub || meta.cognito_sub || null;
    const owner = meta.owner || meta.username || meta.email || null;
    const requestedRunId = meta.run_id || meta.runID || meta.runId || null;
    console.log(`[queryCloudTaskRunId] taskId=${taskId}, hostName=${hostName}, owner_id=${ownerId}, owner=${owner}, requestedRunId=${requestedRunId}`);

    if (!taskId && !ownerId && !owner) {
      return {
        id: null,
        runID: null,
        runner: null,
        status: JSON.stringify({ state: "error" }),
        success: false,
        error: "task_id or owner_id is required",
        timestamp: nowIso()
      };
    }

    // 1) If caller provided a run_id (short id), search history table under this owner_id.
    if (requestedRunId && ownerId) {
      const q = await dynamodb.query({
        TableName: HISTORY_TABLE,
        KeyConditionExpression: "owner_id = :oid",
        FilterExpression: "contains(run_sk, :rid)",
        ExpressionAttributeValues: {
          ":oid": ownerId,
          ":rid": String(requestedRunId),
        },
        ScanIndexForward: false,
        Limit: 5,
      }).promise();

      const item = (q.Items && q.Items.length) ? q.Items[0] : null;
      if (item) {
        return {
          id: item.task_id || taskId || null,
          runID: item.run_id || String(requestedRunId),
          runner: String(ownerId),
          status: JSON.stringify({ state: "ok", taskArn: item.task_arn || null, run_sk: item.run_sk || null }),
          success: true,
          error: null,
          timestamp: nowIso(),
        };
      }
    }

    // 2) Default path: return the latest pointer from agent_tasks (full taskArn is stored there).
    if (taskId && ownerId) {
      const res = await dynamodb.get({
        TableName: RUNS_TABLE,
        Key: { owner_id: String(ownerId), task_id: String(taskId) },
      }).promise();

      if (res && res.Item) {
        const taskArn = res.Item.run_id || null;
        const shortRunId = ecsTaskIdFromArn(taskArn) || taskArn;
        return {
          id: String(taskId),
          runID: shortRunId,
          runner: String(ownerId),
          status: JSON.stringify({ state: "ok", taskArn, updated_at: res.Item.updated_at || null }),
          success: true,
          error: null,
          timestamp: nowIso(),
        };
      }
    }

    // Try RDS lookup first (AGENT_TASKS table via the existing agentScheduler DB)
    // The task's run_id is typically stored in the task's config or metadata
    const rdsExecute = require("../db/rdsExecute");
    const Secrets = process.env.SECRET_ARN || "";
    const Cluster = process.env.CLUSTER_ARN || "";
    const DB = process.env.DB_NAME || "ecandb";

    let sqlStatement;
    if (taskId) {
      // Query by task mid (numeric ID) or by string ID in config
      sqlStatement = `SELECT mid, owner, config, status FROM AGENT_TASKS WHERE mid = ${parseInt(taskId, 10) || 0} LIMIT 1`;
    } else {
      // Fallback: query latest task for owner
      sqlStatement = `SELECT mid, owner, config, status FROM AGENT_TASKS WHERE owner = '${owner}' ORDER BY mid DESC LIMIT 1`;
    }

    const params = {
      secretArn: Secrets,
      resourceArn: Cluster,
      sql: sqlStatement,
      database: DB
    };

    const result = await rdsExecute(params);
    const records = (result && result.records) || [];

    if (records.length > 0) {
      const row = records[0];
      // RDS Data API returns arrays of field objects
      const mid = row[0] && (row[0].longValue || row[0].stringValue || null);
      const rowOwner = row[1] && (row[1].stringValue || null);
      let config = row[2] && (row[2].stringValue || null);
      const rowStatus = row[3] && (row[3].stringValue || "pending");

      // Parse config to extract run_id
      let runId = null;
      if (config) {
        try {
          const configObj = typeof config === "string" ? JSON.parse(config) : config;
          runId = configObj.run_id || configObj.runID || configObj.runId || null;
        } catch (_) { /* ignore parse errors */ }
      }

      return {
        id: String(mid),
        runID: runId,
        runner: rowOwner,
        status: JSON.stringify({ state: rowStatus }),
        success: true,
        error: null,
        timestamp: nowIso()
      };
    }

    return {
      id: taskId,
      runID: null,
      runner: null,
      status: JSON.stringify({ state: "not_found" }),
      success: false,
      error: "Task not found",
      timestamp: nowIso()
    };

  } catch (err) {
    console.error("[queryCloudTaskRunId] Error:", err);
    return {
      id: taskId,
      runID: null,
      runner: null,
      status: JSON.stringify({ state: "error" }),
      success: false,
      error: String(err.message || err),
      timestamp: nowIso()
    };
  }
}

module.exports = {
  getNodeStateSchema,
  readSkillFile,
  openSkillFile,
  listSkillFiles,
  checkSkillExists,
  getEditorCache,
  getSkillRunStatus,
  getSkillEditorEvents,
  getSkillEditorChatSessions,
  getSkillEditorChatHistory,
  writeSkillFile,
  scaffoldSkill,
  copySkillTo,
  saveEditorCache,
  clearEditorCache,
  runSkill,
  pauseRunSkill,
  resumeRunSkill,
  stepRunSkill,
  cancelRunSkill,
  setupSimStep,
  stepSim,
  testLanggraph2Flowgram,
  simTimerEvent,
  simWebsocketEvent,
  simSseEvent,
  simWebhookEvent,
  setSkillBreakpoints,
  clearSkillBreakpoints,
  requestSkillState,
  injectSkillState,
  loadSkillSchemas,
  createSkillEditorChatSession,
  sendSkillEditorChatMessage,
  cancelSkillEditorChatGeneration,
  deleteSkillEditorChatSession,
  queryCloudTaskRunId
};
