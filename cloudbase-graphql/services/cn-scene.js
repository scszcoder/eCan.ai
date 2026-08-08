/**
 * CN Scene & Story Operations
 *
 * Operations for video scene generation, story management, and scene templates.
 */

const { parseIds, parseJson } = require('../compat/cn-relations');

function parseInput(input) {
  if (typeof input === 'string') {
    try { return JSON.parse(input); } catch { return {}; }
  }
  return input || {};
}

async function queryScenes(prisma, identity, input) {
  const selector = parseInput(input);
  const rows = await prisma.legacyRecord.findMany({
    where: { owner: identity.sub, kind: 'scene', ...(selector.label ? { externalId: { contains: selector.label } } : {}) },
    orderBy: { createdAt: 'desc' },
    take: Math.min(selector.limit || 50, 200),
  });
  return JSON.stringify(rows.map(r => ({ ...r.data, id: r.externalId })));
}

async function saveScene(prisma, identity, input) {
  const selector = parseInput(input);
  const externalId = String(selector.scene_id || selector.id || '');
  if (!externalId) return JSON.stringify({ success: false, error: 'Missing scene_id' });
  const existing = await prisma.legacyRecord.findFirst({ where: { owner: identity.sub, kind: 'scene', externalId } });
  const sceneData = {
    scene_id: externalId,
    acctSiteID: selector.acctSiteID,
    label: selector.label,
    description: selector.description,
    clip: selector.clip,
    images: selector.images,
    video: selector.video,
    thumbnails: selector.thumbnails,
    captions: selector.captions,
    agent_ids: selector.agent_ids,
    status: selector.status,
    duration_ms: selector.duration_ms,
    actions: selector.actions,
    dialogs: selector.dialogs,
    priority: selector.priority,
    n_repeat: selector.n_repeat,
    trigger_events: selector.trigger_events,
    emotion: selector.emotion,
    style: selector.style,
  };
  const row = existing
    ? await prisma.legacyRecord.update({ where: { id: existing.id }, data: { data: sceneData, updatedAt: new Date() } })
    : await prisma.legacyRecord.create({ data: { owner: identity.sub, kind: 'scene', externalId, data: sceneData } });
  return JSON.stringify({ ...sceneData, id: row.externalId });
}

async function deleteScene(prisma, identity, input) {
  const selector = parseInput(input);
  const externalId = String(selector.id || '');
  if (!externalId) return 'false';
  const result = await prisma.legacyRecord.deleteMany({ where: { owner: identity.sub, kind: 'scene', externalId } });
  return String(result.count > 0);
}

async function querySceneTemplates(prisma, identity, emotion, style) {
  // Predefined scene templates
  const templates = [
    { id: 'tmpl_serious_001', label: 'Professional Talk', emotion: 'serious', description: 'Formal business presentation style' },
    { id: 'tmpl_friendly_001', label: 'Friendly Chat', emotion: 'friendly', description: 'Warm and approachable conversation' },
    { id: 'tmpl_excited_001', label: 'Excited Demo', emotion: 'excited', description: 'High-energy product demonstration' },
    { id: 'tmpl_calm_001', label: 'Calm Tutorial', emotion: 'calm', description: 'Relaxed step-by-step guide' },
  ];
  let filtered = templates;
  if (emotion) filtered = filtered.filter(t => t.emotion === emotion);
  if (style) filtered = filtered.filter(t => t.style === style);
  return JSON.stringify(filtered);
}

async function queryStories(prisma, identity, acctSiteID, limit = 20, nextToken) {
  const rows = await prisma.legacyRecord.findMany({
    where: { owner: identity.sub, kind: 'story', ...(acctSiteID ? { externalId: { contains: acctSiteID } } : {}) },
    orderBy: { createdAt: 'desc' },
    take: Math.min(limit, 200),
    skip: nextToken ? 1 : 0,
    ...(nextToken ? { cursor: { id: nextToken } } : {}),
  });
  const items = rows.map(r => ({ ...r.data, id: r.externalId }));
  const lastId = rows.length > 0 ? rows[rows.length - 1].id : null;
  return JSON.stringify({ items, nextToken: lastId });
}

async function saveStory(prisma, identity, input) {
  const selector = parseInput(input);
  const externalId = String(selector.id || '');
  if (!externalId) return JSON.stringify({ success: false, error: 'Missing story id' });
  const existing = await prisma.legacyRecord.findFirst({ where: { owner: identity.sub, kind: 'story', externalId } });
  const storyData = {
    id: externalId,
    acctSiteID: selector.acctSiteID,
    title: selector.title,
    description: selector.description,
    status: selector.status,
    agent_ids: selector.agent_ids,
    scenes: selector.scenes,
    current_scene_index: selector.current_scene_index,
  };
  const row = existing
    ? await prisma.legacyRecord.update({ where: { id: existing.id }, data: { data: storyData, updatedAt: new Date() } })
    : await prisma.legacyRecord.create({ data: { owner: identity.sub, kind: 'story', externalId, data: storyData } });
  return JSON.stringify({ ...storyData });
}

async function initReqScene(prisma, identity, input) {
  const selector = parseInput(input);
  const requestId = `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  const requestData = {
    request_id: requestId,
    acctSiteID: selector.acctSiteID,
    agent_id: selector.agent_id,
    emotion: selector.emotion,
    style: selector.style,
    status: 'pending',
    estimated_time_ms: selector.duration_hint_ms || 30000,
  };
  await prisma.legacyRecord.create({ data: { owner: identity.sub, kind: 'scene_request', externalId: requestId, data: requestData } });
  return JSON.stringify({ ...requestData, message: 'Scene request initiated' });
}

async function readyReqScene(prisma, identity, input) {
  const selector = parseInput(input);
  const requestId = String(selector.request_id || '');
  const existing = await prisma.legacyRecord.findFirst({ where: { owner: identity.sub, kind: 'scene_request', externalId: requestId } });
  if (existing) {
    await prisma.legacyRecord.update({ where: { id: existing.id }, data: { data: { ...existing.data, status: selector.status || 'ready' }, updatedAt: new Date() } });
  }
  return JSON.stringify({ request_id: requestId, status: selector.status || 'ready', message: 'Scene ready' });
}

async function getSceneRequestStatus(prisma, identity, requestId) {
  const existing = await prisma.legacyRecord.findFirst({ where: { owner: identity.sub, kind: 'scene_request', externalId: String(requestId) } });
  return JSON.stringify(existing ? existing.data : { request_id: requestId, status: 'not_found' });
}

async function publishSceneResult(prisma, identity, input) {
  const selector = parseInput(input);
  const requestId = String(selector.request_id || '');
  await prisma.legacyRecord.create({ data: { owner: identity.sub, kind: 'scene_result', externalId: requestId, data: selector } });
  const bus = require('../event-bus');
  // Both onSceneComplete (by request_id) and onAgentSceneEvent (by acctSiteID) match.
  bus.publish('onSceneComplete', requestId, selector);
  if (selector.acctSiteID) bus.publish('onAgentSceneEvent', selector.acctSiteID, selector);
  pushToWebSocketBridge('onSceneComplete', requestId, selector).catch((e) => {
    console.warn('[publishSceneResult] WebSocket bridge push failed:', e.message);
  });
  if (selector.acctSiteID) {
    pushToWebSocketBridge('onAgentSceneEvent', String(selector.acctSiteID), selector).catch((e) => {
      console.warn('[publishSceneResult] WebSocket bridge push failed:', e.message);
    });
  }
  return JSON.stringify(selector);
}

async function queryExtBotSkillRun(prisma, identity, configs) {
  const results = (configs || []).map(cfg => ({ run_id: cfg.run_id, skid: cfg.skid, status: 'pending', message: 'Skill run queued' }));
  return JSON.stringify(results);
}

async function queryCloudTaskRunId(prisma, identity, input) {
  const selector = parseInput(input);
  return JSON.stringify({ runID: selector.task_id || `task_${Date.now()}`, status: JSON.stringify(selector.meta_data || {}), success: true });
}

async function publishTaskStatus(prisma, identity, input) {
  const selector = parseInput(input);
  const runID = String(selector.runID || `run_${Date.now()}`);
  await prisma.legacyRecord.create({ data: { owner: identity.sub, kind: 'task_status', externalId: runID, data: selector } });
  const bus = require('../event-bus');
  const payload = { runID, status: selector.status || null, success: !!selector.success, error: selector.error || null, runner: selector.runner || null };
  bus.publish('onTaskStatus', runID, payload);
  pushToWebSocketBridge('onTaskStatus', runID, payload).catch((e) => {
    console.warn('[publishTaskStatus] WebSocket bridge push failed:', e.message);
  });
  return JSON.stringify({ runID, success: true });
}

async function pushToWebSocketBridge(topic, target, data) {
  const secret = process.env.WEBSOCKET_PUSH_SECRET;
  const host = process.env.GRAPHQL_ENDPOINT_HOST;
  if (!secret || !host || !target) return;
  const url = `https://${host}/ws/push`;
  const body = JSON.stringify({ topic, target, payload: data });
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-ECAN-Push-Secret': secret,
      },
      body,
    });
    if (!res.ok) {
      console.warn(`[pushToWebSocketBridge] non-2xx: ${res.status}`);
    }
  } catch (e) {
    console.warn(`[pushToWebSocketBridge] fetch failed: ${e.message}`);
  }
}

module.exports = {
  queryScenes, saveScene, deleteScene, querySceneTemplates,
  queryStories, saveStory,
  initReqScene, readyReqScene, getSceneRequestStatus, publishSceneResult,
  queryExtBotSkillRun, queryCloudTaskRunId, publishTaskStatus,
};
