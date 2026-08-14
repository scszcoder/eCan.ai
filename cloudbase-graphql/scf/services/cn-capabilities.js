const crypto = require('node:crypto');

function parseJson(value, fallback = {}) { if (value == null) return fallback; if (typeof value === 'object') return value; try { return JSON.parse(value); } catch { return fallback; } }
function assertUser(identity, requested) { if (requested && requested !== identity.sub) throw new Error('Cross-owner access is forbidden'); return identity.sub; }

async function upsertAgentEndpoint(prisma, identity, input) {
  const ownedAgent = await prisma.agent.findFirst({ where: { id: input.id, owner: identity.sub }, select: { id: true } });
  if (!ownedAgent) throw new Error('Owned agent not found');
  return prisma.agentEndpoint.upsert({
    where: { id: input.id },
    create: { ...input, owner: identity.sub, lastSeen: BigInt(Math.floor(Date.now() / 1000)), ttl: input.ttl || 180 },
    update: { ...input, owner: identity.sub, lastSeen: BigInt(Math.floor(Date.now() / 1000)), ttl: input.ttl || 180 },
  });
}

async function queryAgentEndpoints(prisma, identity, org, { limit = 200, offset = 0 } = {}) {
  const membership = await prisma.agentEndpoint.findFirst({ where: { owner: identity.sub, org }, select: { id: true } });
  if (!membership) return [];
  const now = Math.floor(Date.now() / 1000);
  const rows = await prisma.agentEndpoint.findMany({
    where: { org },
    orderBy: { lastSeen: 'desc' },
    take: Math.min(Math.max(1, limit), 500),  // 限制 1-500
    skip: Math.max(0, offset),
  });
  return rows.filter((row) => Number(row.lastSeen) + row.ttl >= now);
}

async function deleteAgentEndpoint(prisma, identity, id) {
  const row = await prisma.agentEndpoint.findFirst({ where: { id, owner: identity.sub } });
  if (!row) throw new Error('Agent endpoint not found');
  await prisma.agentEndpoint.delete({ where: { id } });
  return row;
}

async function sendA2AMessage(prisma, identity, input) {
  const sender = await prisma.agentEndpoint.findFirst({ where: { id: input.fromAgentId, owner: identity.sub, org: input.org } });
  const receiver = await prisma.agentEndpoint.findFirst({ where: { id: input.toAgentId, org: input.org } });
  if (!sender || !receiver) throw new Error('A2A endpoint not found in organization');
  const row = await prisma.a2AMessage.create({ data: { owner: identity.sub, toAgentId: input.toAgentId, fromAgentId: input.fromAgentId, org: input.org, payload: parseJson(input.payload, {}) } });
  // Mirror Intl AppSync semantics: sendA2AMessage triggers onA2AMessageReceived
  // subscribers. Publish to in-process event-bus; cross-instance delivery via
  // ws-bridge-push.js → TCS WS service.
  const bus = require('../event-bus');
  bus.publish('onA2AMessageReceived', input.toAgentId, row);
  bus.publish('onMessageReceived', input.toAgentId, row);
  return row;
}

async function registerRagDocuments(prisma, identity, input) {
  const rows = [];
  for (const item of input || []) {
    const safeFile = String(item.file).replace(/[^A-Za-z0-9._-]/g, '_');
    const objectKey = `users/${encodeURIComponent(identity.sub)}/rag/${encodeURIComponent(item.pid)}/${safeFile}`;
    const row = await prisma.ragDocument.upsert({
      where: { owner_pid_fid: { owner: identity.sub, pid: String(item.pid), fid: String(item.fid) } },
      create: { owner: identity.sub, fid: String(item.fid), pid: String(item.pid), file: safeFile, type: item.type, format: item.format, options: parseJson(item.options, {}), version: item.version, objectKey },
      update: { file: safeFile, type: item.type, format: item.format, options: parseJson(item.options, {}), version: item.version, objectKey },
    });
    rows.push({ id: row.id, fid: row.fid, pid: row.pid, object_key: row.objectKey });
  }
  return JSON.stringify({ success: true, count: rows.length, documents: rows });
}

async function startLongLlmTask(prisma, identity, taskInput) {
  const input = parseJson(taskInput, {});
  const row = await prisma.longLlmTask.create({ data: { owner: identity.sub, acctSiteId: input.acctSiteID, agentId: input.agentID, workType: input.workType, taskId: input.taskID, input, status: 'pending' } });
  return JSON.stringify({ id: row.id, status: row.status });
}

async function endLongLlmTask(prisma, identity, input) {
  const taskRef = input.id || input.taskID;
  const current = await prisma.longLlmTask.findFirst({ where: { owner: identity.sub, OR: [{ id: taskRef }, { taskId: taskRef }] } });
  if (!current) throw new Error('Long LLM task not found');
  return prisma.longLlmTask.update({ where: { id: current.id }, data: { acctSiteId: input.acctSiteID, agentId: input.agentID, workType: input.workType, taskId: input.taskID, status: input.status || 'complete', results: input.results } });
}

async function getLongLlmTask(prisma, identity, id) {
  const row = await prisma.longLlmTask.findFirst({ where: { id, owner: identity.sub } });
  if (!row) throw new Error('Long LLM task not found');
  return JSON.stringify({ ...row, acctSiteID: row.acctSiteId, agentID: row.agentId, taskID: row.taskId, timestamp: row.updatedAt });
}

async function createChatSession(prisma, identity, input) {
  assertUser(identity, input.userId);
  return prisma.skillEditorChatSession.create({ data: { owner: identity.sub, name: input.name || 'New chat', flowgramId: input.flowgramId } });
}

async function getChatSessions(prisma, identity, userId) { assertUser(identity, userId); return prisma.skillEditorChatSession.findMany({ where: { owner: identity.sub }, orderBy: { updatedAt: 'desc' }, take: 100 }); }

async function getChatHistory(prisma, identity, sessionId, limit = 100, offset = 0) {
  const session = await prisma.skillEditorChatSession.findFirst({ where: { id: sessionId, owner: identity.sub }, select: { id: true } });
  if (!session) throw new Error('Chat session not found');
  return prisma.skillEditorChatMessage.findMany({ where: { sessionId, owner: identity.sub }, orderBy: { timestamp: 'asc' }, take: Math.min(limit || 100, 200), skip: Math.max(offset || 0, 0) });
}

async function sendChatMessage(prisma, identity, input) {
  assertUser(identity, input.userId);
  const session = await prisma.skillEditorChatSession.findFirst({ where: { id: input.sessionId, owner: identity.sub } });
  if (!session || session.state === 'cancelled') throw new Error('Chat session is unavailable');
  const message = await prisma.skillEditorChatMessage.create({ data: { owner: identity.sub, sessionId: session.id, role: 'user', content: input.content, attachments: parseJson(input.attachments, []), metadata: { canvasContext: parseJson(input.canvasContext, {}), clarificationResponses: parseJson(input.clarificationResponses, {}), flowgramId: input.flowgramId } } });
  await prisma.skillEditorChatSession.update({ where: { id: session.id }, data: { flowgramId: input.flowgramId || session.flowgramId } });
  return { sessionId: session.id, sessionName: session.name, state: 'accepted', intent: null, message, clarification: null, plan: null, flowgram: null, validation: null };
}

async function setChatState(prisma, identity, sessionId, state, remove = false) {
  const session = await prisma.skillEditorChatSession.findFirst({ where: { id: sessionId, owner: identity.sub }, select: { id: true } });
  if (!session) return false;
  if (remove) await prisma.skillEditorChatSession.delete({ where: { id: sessionId } }); else await prisma.skillEditorChatSession.update({ where: { id: sessionId }, data: { state } });
  return true;
}

async function publishSkillEditorEvent(prisma, identity, input) {
  assertUser(identity, input.owner);
  const row = await prisma.skillEditorEvent.create({ data: { owner: identity.sub, sessionId: input.sessionId, flowgramId: input.flowgramId, eventType: input.eventType, payload: parseJson(input.payload, {}) } });
  // Mirror Intl AppSync semantics: publishSkillEditorEvent triggers
  // onSkillEditorStreamEvent(sessionId) subscribers via in-process event-bus.
  // Cross-instance delivery via ws-bridge-push.js → TCS WS service.
  const bus = require('../event-bus');
  bus.publish('onSkillEditorStreamEvent', input.sessionId, row);
  return { eventId: row.eventId, owner: row.owner, sessionId: row.sessionId, flowgramId: row.flowgramId, eventType: row.eventType, payload: row.payload, timestamp: (row.timestamp instanceof Date ? row.timestamp.toISOString() : row.timestamp) };
}

function newApiKey() { return `ecan_cn_${crypto.randomBytes(24).toString('base64url')}`; }

module.exports = { createChatSession, deleteAgentEndpoint, endLongLlmTask, getChatHistory, getChatSessions, getLongLlmTask, newApiKey, publishSkillEditorEvent, queryAgentEndpoints, registerRagDocuments, sendA2AMessage, sendChatMessage, setChatState, startLongLlmTask, upsertAgentEndpoint };
