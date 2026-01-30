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
  deleteSkillEditorChatSession
};
