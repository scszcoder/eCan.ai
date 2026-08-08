const crypto = require('node:crypto');

function parse(value, fallback = {}) { if (value == null) return fallback; if (typeof value === 'object') return value; try { return JSON.parse(value); } catch { return fallback; } }
function owner(identity, requested) { if (requested && requested !== identity.sub) throw new Error('Cross-owner access is forbidden'); return identity.sub; }
function identifier(kind, item) { const fields = { account: 'actid', bot: 'bid', mission: 'mid', order: 'oid' }; return String(item?.[fields[kind]] || item?.id || ''); }

async function saveLegacy(prisma, identity, kind, input) {
  const results = [];
  for (const item of input || []) {
    try { const user = owner(identity, item.owner); const externalId = identifier(kind, item); if (!externalId) throw new Error(`Missing ${kind} id`); const row = await prisma.legacyRecord.upsert({ where: { owner_kind_externalId: { owner: user, kind, externalId } }, create: { owner: user, kind, externalId, data: item }, update: { data: item } }); results.push({ id: row.externalId, success: true }); }
    catch (error) { results.push({ id: identifier(kind, item) || null, success: false, error: error.message }); }
  }
  return JSON.stringify(results);
}

async function removeLegacy(prisma, identity, kind, input) {
  const results = [];
  for (const item of input || []) { try { owner(identity, item.owner); const changed = await prisma.legacyRecord.deleteMany({ where: { owner: identity.sub, kind, externalId: String(item.oid) } }); results.push({ id: item.oid, success: changed.count === 1, error: changed.count ? null : 'Not found' }); } catch (error) { results.push({ id: item?.oid || null, success: false, error: error.message }); } }
  return JSON.stringify(results);
}

async function queryLegacy(prisma, identity, kind, selector, ids) {
  const query = parse(selector, Array.isArray(selector) ? selector[0] : {}); owner(identity, query?.owner);
  const idList = (ids || []).map(String); const externalId = identifier(kind, query);
  const rows = await prisma.legacyRecord.findMany({ where: { owner: identity.sub, kind, ...(idList.length ? { externalId: { in: idList } } : {}), ...(externalId ? { externalId } : {}) }, orderBy: { updatedAt: 'desc' }, take: 200 });
  return JSON.stringify(rows.map((row) => row.data));
}

async function sendWanMessage(prisma, identity, input) {
  if (!input) throw new Error('Message input required');
  if (input.sender && input.sender !== identity.sub) { const agent = await prisma.agent.findFirst({ where: { id: input.sender, owner: identity.sub }, select: { id: true } }); if (!agent) throw new Error('Sender is not owned by authenticated user'); }
  const row = await prisma.wanMessage.create({ data: { owner: identity.sub, chatId: input.chatID, sender: input.sender, receiver: input.receiver, type: input.type, contents: input.contents, parameters: input.parameters } });
  // Mirror Intl AppSync semantics: sendWanMessage must trigger onMessageReceived(chatID)
  // subscribers. The CN WebSocket SCF speaks graphql-ws (same as Intl AppSync),
  // so we publish to the in-process event-bus AND push to the WebSocket SCF
  // for cross-instance delivery.
  const payload = {
    id: row.id,
    chatID: row.chatId,
    sender: row.sender,
    receiver: row.receiver,
    type: row.type,
    contents: row.contents,
    parameters: row.parameters,
    timestamp: row.timestamp instanceof Date ? row.timestamp.toISOString() : String(row.timestamp || ''),
  };
  if (row.chatId) {
    try {
      const bus = require('../event-bus');
      const { TOPIC } = require('../resolvers/subscriptions');
      bus.publish(TOPIC.onMessageReceived, row.chatId, payload);
    } catch (e) {
      console.warn('[sendWanMessage] event-bus publish failed:', e.message);
    }
    // Best-effort: push to WebSocket SCF so raw-WS clients (other instances) receive the message.
    pushToWebSocketBridge('onMessageReceived', row.chatId, payload).catch((e) => {
      console.warn('[sendWanMessage] WebSocket bridge push failed:', e.message);
    });
  }
  return row;
}

/**
 * Push an event to the WebSocket SCF so any subscribed (graphql-ws or tcb JSON) client
 * receives it. The WebSocket SCF dispatches the payload to all matching subscribers.
 *
 * Env vars:
 *   - GRAPHQL_ENDPOINT_HOST: host part of the GraphQL endpoint (e.g.
 *     "sccb0-xxx.service.tcloudbase.com"). When unset, the function is a no-op.
 *   - WEBSOCKET_PUSH_SECRET: shared secret matching the WebSocket SCF's
 *     /ws/push endpoint. When unset, the bridge is skipped silently.
 *
 * Topic naming convention matches graphql subscription field names:
 *   onMessageReceived, onA2AMessageReceived, onPassiveCommand, ...
 */
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

async function getWanMessages(prisma, identity, ids) { return prisma.wanMessage.findMany({ where: { owner: identity.sub, ...(ids?.length ? { id: { in: ids.map(String) } } : {}) }, orderBy: { timestamp: 'desc' }, take: 200 }); }

async function mutateApiKeys(prisma, identity, ops) {
  const output = [];
  for (const op of ops || []) {
    const action = String(op.op || '').toLowerCase();
    if (['create', 'add', 'new'].includes(action)) { const raw = `ecan_cn_${crypto.randomBytes(24).toString('base64url')}`; const hash = crypto.createHash('sha256').update(raw).digest('hex'); const row = await prisma.apiCredential.create({ data: { owner: identity.sub, keyHash: hash, keyPrefix: raw.slice(0, 16), label: parse(op.options, {}).label } }); output.push({ id: row.id, api_key: raw, prefix: row.keyPrefix }); }
    else if (['remove', 'delete', 'revoke'].includes(action)) { const keys = String(op.keys || '').split(',').filter(Boolean); const hashes = keys.map((key) => crypto.createHash('sha256').update(key).digest('hex')); const changed = await prisma.apiCredential.updateMany({ where: { owner: identity.sub, OR: [{ id: { in: keys } }, { keyHash: { in: hashes } }] }, data: { status: 'revoked', revokedAt: new Date() } }); output.push({ revoked: changed.count }); }
    else output.push({ error: `Unsupported key operation: ${op.op}` });
  }
  return JSON.stringify(output);
}

async function queryApiKeys(prisma, identity, keys) {
  const rows = await prisma.apiCredential.findMany({ where: { owner: identity.sub }, orderBy: { createdAt: 'desc' }, take: 100 });
  return JSON.stringify(rows.map((row) => ({ id: row.id, aws_api_key: row.keyPrefix, option: row.status, created_at: row.createdAt })));
}

module.exports = { getWanMessages, mutateApiKeys, queryApiKeys, queryLegacy, removeLegacy, saveLegacy, sendWanMessage };
