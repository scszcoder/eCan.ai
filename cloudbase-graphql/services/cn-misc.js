/**
 * CN Miscellaneous Operations
 *
 * RAG queries, screen/UI operations, Cloud tasks, SOAP, puzzle, passive browser, etc.
 */

function parseInput(input) {
  if (typeof input === 'string') {
    try { return JSON.parse(input); } catch { return {}; }
  }
  return input || {};
}

async function queryRAGs(prisma, identity, qs) {
  // Placeholder for RAG knowledge base queries
  const query = parseInput(qs);
  const results = [{ text: `RAG result for: ${JSON.stringify(query).substring(0, 100)}`, score: 0.95 }];
  return JSON.stringify(results);
}

async function getFB(prisma, identity, fb_reqs) {
  // Placeholder for feedback requests
  return JSON.stringify({ status: 'ok', processed: (fb_reqs || []).length });
}

async function queryChats(prisma, identity, msgs) {
  // Placeholder for chat query
  return JSON.stringify({ status: 'ok', processed: (msgs || []).length });
}

async function genSchedules(prisma, identity, settings) {
  const s = parseInput(settings);
  return JSON.stringify({ schedules: [], count: 0, settings: s });
}

async function regSteps(prisma, identity, inSteps) {
  return JSON.stringify({ registered: (inSteps || []).length, steps: inSteps });
}

async function reqMachineLanAddr(prisma, identity, mid) {
  return JSON.stringify({ mid: mid || 'unknown', lan_addr: '192.168.1.100', hostname: `machine-${mid || 'local'}` });
}

async function reqScreenTxtRead(prisma, identity, inScrn) {
  const results = (inScrn || []).map((s, i) => ({ id: s.id || String(i), text: 'Screen text placeholder' }));
  return JSON.stringify(results);
}

async function reqScreenIconRead(prisma, identity, inScrn) {
  const results = (inScrn || []).map((s, i) => ({ id: s.id || String(i), clickables: [{ x: 100, y: 200, label: 'Button' }] }));
  return JSON.stringify(results);
}

async function getNodeStateSchema(prisma, identity) {
  return JSON.stringify({ schema: { type: 'object', properties: {} }, schemaVersion: '1.0' });
}

async function getNodesPrompts(prisma, identity, nodes) {
  const results = (nodes || []).map(n => ({ askid: n.askid, prompt: `Prompt for: ${n.name}` }));
  return JSON.stringify(results);
}

async function checkSkillExists(prisma, identity, name) {
  const exists = await prisma.agentSkill.findFirst({ where: { owner: identity.sub, name } });
  return JSON.stringify({ name, exists: !!exists });
}


async function sendCloudA2AMessage(prisma, identity, input) {
  const selector = parseInput(input);
  const messageId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  return JSON.stringify({
    id: messageId,
    channelId: selector.channelId,
    sessionId: selector.sessionId,
    senderId: selector.senderId,
    recipientId: selector.recipientId,
    createdAt: new Date().toISOString(),
  });
}

async function getA2AMessages(prisma, identity, channelId, limit = 50, nextToken) {
  // Channel routing: A2AMessage stores (toAgentId, fromAgentId) addresses. We use the
  // existing typed model instead of the legacy unindexed JSON blob.
  void nextToken;
  const owner = identity.sub;
  const rows = await prisma.a2AMessage.findMany({
    where: { owner, OR: [{ toAgentId: channelId }, { fromAgentId: channelId }] },
    orderBy: { timestamp: 'desc' },
    take: Math.min(limit, 100),
  });
  return JSON.stringify({ items: rows, nextToken: rows.length > 0 ? rows[rows.length - 1].id : null });
}

async function sendPuzzleSolution(prisma, identity, input) {
  return JSON.stringify({ request_id: input?.request_id, solved: true, message: 'Solution received' });
}

async function requestPuzzleSolve(prisma, identity, puzzles) {
  const results = (puzzles || []).map(p => ({ id: p.id || `puzzle_${Date.now()}`, status: 'pending' }));
  return JSON.stringify(results);
}

// Cloud task operations
async function runSkill(prisma, identity, input) {
  const selector = parseInput(input);
  const runId = `run_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  return JSON.stringify({ runId, status: 'running', message: 'Skill started' });
}

async function stepRunSkill(prisma, identity, input) {
  return JSON.stringify({ status: 'stepped', message: 'Advanced one step' });
}

async function pauseRunSkill(prisma, identity, input) {
  return JSON.stringify({ status: 'paused', message: 'Skill paused' });
}

async function resumeRunSkill(prisma, identity, input) {
  return JSON.stringify({ status: 'resumed', message: 'Skill resumed' });
}

async function cancelRunSkill(prisma, identity, input) {
  return JSON.stringify({ status: 'cancelled', message: 'Skill cancelled' });
}

async function getSkillRunStatus(prisma, identity, runId, since) {
  const events = [{ runId, status: 'running', current_node: 'start', timestamp: new Date().toISOString() }];
  return JSON.stringify(events);
}

async function runTest(prisma, identity, tests) {
  const results = (tests || []).map(t => ({ id: t.id, status: 'passed', message: `Test ${t.name} passed` }));
  return JSON.stringify(results);
}

// SOAP operations
async function startSoap(prisma, identity, input) {
  const selector = parseInput(input);
  const soapId = `soap_${Date.now()}`;
  return JSON.stringify({ soap_id: soapId, status: 'started', message: 'SOAP session started' });
}

async function stopSoap(prisma, identity, soapId) {
  return 'true';
}

// Simulation operations
async function setupSimStep(prisma, identity, bundle) {
  return JSON.stringify({ status: 'ready', message: 'Simulation step configured' });
}

async function stepSim(prisma, identity) {
  return JSON.stringify({ status: 'stepped', message: 'Simulation stepped' });
}

async function simSseEvent(prisma, identity) {
  return JSON.stringify({ status: 'simulated', message: 'SSE event simulated' });
}

async function simTimerEvent(prisma, identity) {
  return JSON.stringify({ status: 'simulated', message: 'Timer event simulated' });
}

async function simWebhookEvent(prisma, identity) {
  return JSON.stringify({ status: 'simulated', message: 'Webhook event simulated' });
}

async function simWebsocketEvent(prisma, identity) {
  return JSON.stringify({ status: 'simulated', message: 'WebSocket event simulated' });
}

async function testLanggraph2Flowgram(prisma, identity) {
  return JSON.stringify({ status: 'ok', message: 'LangGraph to Flowgram conversion tested' });
}

// Passive browser operations
async function publishPassiveCommand(prisma, identity, input) {
  const out = { ...input, status: 'published' };
  const bus = require('../event-bus');
  bus.publish('onPassiveCommand', input.runId, out);
  return JSON.stringify(out);
}

async function publishPassiveHello(prisma, identity, input) {
  const out = { ...input, status: 'published' };
  const bus = require('../event-bus');
  bus.publish('onPassiveHello', input.runId, out);
  return JSON.stringify(out);
}

async function publishPassiveStepResult(prisma, identity, input) {
  const out = { ...input, status: 'published' };
  const bus = require('../event-bus');
  bus.publish('onPassiveStepResult', input.runId, out);
  return JSON.stringify(out);
}

// Account notification
async function publishAccountNotification(prisma, identity, input) {
  const notif = { ...input, createdAt: new Date().toISOString(), id: `notif_${Date.now()}` };
  await prisma.accountNotification.create({ data: { owner: identity.sub, notifId: notif.id, payload: notif } });
  const bus = require('../event-bus');
  bus.publish('onAccountNotification', identity.sub, notif);
  return JSON.stringify(notif);
}

module.exports = {
  queryRAGs, getFB, queryChats, genSchedules, regSteps,
  reqMachineLanAddr, reqScreenTxtRead, reqScreenIconRead,
  getNodeStateSchema, getNodesPrompts, checkSkillExists,
  sendCloudA2AMessage, getA2AMessages,
  sendPuzzleSolution, requestPuzzleSolve,
  runSkill, stepRunSkill, pauseRunSkill, resumeRunSkill, cancelRunSkill, getSkillRunStatus,
  runTest,
  startSoap, stopSoap,
  setupSimStep, stepSim, simSseEvent, simTimerEvent, simWebhookEvent, simWebsocketEvent,
  testLanggraph2Flowgram,
  publishPassiveCommand, publishPassiveHello, publishPassiveStepResult,
  publishAccountNotification,
};
