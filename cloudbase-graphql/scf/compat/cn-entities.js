const { parseIds, parseJson } = require('./cn-relations');

function compact(value) { return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== undefined)); }
function ensureOwner(identity, requested) { if (requested && requested !== identity.sub) throw new Error('Cross-owner access is forbidden'); return identity.sub; }
function json(value) { return JSON.stringify(value); }

const entities = {
  Knowledge: {
    model: 'agentKnowledge', id: 'knid',
    input: (v, owner) => compact({ id: v.knid, owner, name: v.name || String(v.knid), description: v.description, path: v.path, status: v.status, config: compact({ rag: v.rag, metadata: parseJson(v.metadata, v.metadata) }) }),
    output: (v) => ({ ...v, knid: v.id, rag: v.config?.rag, metadata: v.config?.metadata }),
  },
  AvatarResource: {
    model: 'avatar', id: 'id',
    input: (v, owner) => compact({ id: v.id, owner, resourceType: v.resource_type || 'image', name: v.name, description: v.description, imagePath: v.image_path, videoPath: v.video_path, imageHash: v.image_hash, videoHash: v.video_hash, cloudImageUrl: v.cloud_image_url, cloudVideoUrl: v.cloud_video_url, cloudImageKey: v.cloud_image_key, cloudVideoKey: v.cloud_video_key, cloudSynced: v.cloud_synced, avatarMetadata: parseJson(v.avatar_metadata, {}), usageCount: v.usage_count, lastUsedAt: v.last_used_at ? new Date(v.last_used_at) : undefined, isPublic: v.is_public }),
    output: (v) => ({ ...v, resource_type: v.resourceType, image_path: v.imagePath, video_path: v.videoPath, image_hash: v.imageHash, video_hash: v.videoHash, cloud_image_url: v.cloudImageUrl, cloud_video_url: v.cloudVideoUrl, cloud_image_key: v.cloudImageKey, cloud_video_key: v.cloudVideoKey, cloud_synced: v.cloudSynced, avatar_metadata: v.avatarMetadata, usage_count: v.usageCount, last_used_at: v.lastUsedAt, is_public: v.isPublic }),
  },
  Skill: {
    model: 'agentSkill', id: 'skid',
    input: (v, owner) => compact({ id: v.skid, owner, name: v.name || String(v.skid), description: v.description, category: v.app || v.site, path: v.path, priceModel: v.price_model, price: v.price, isPublic: v.privacy !== 'private', config: compact({ platform: v.platform, app: v.app, site: v.site, site_name: v.site_name, page: v.page, main: v.main, runtime: v.runtime, privacy: v.privacy }) }),
    output: (v) => ({ ...v, skid: v.id, platform: v.config?.platform, app: v.config?.app, site: v.config?.site, site_name: v.config?.site_name, page: v.config?.page, main: v.config?.main, runtime: v.config?.runtime, price_model: v.priceModel, privacy: v.config?.privacy }),
  },
};

async function queryEntity(prisma, identity, name, { ids, qb, qs }) {
  const definition = entities[name];
  const selector = parseJson(qb ?? qs, {});
  ensureOwner(identity, selector.owner);
  const idList = parseIds(ids);
  const externalId = selector[definition.id] || selector.id;
  const rows = await prisma[definition.model].findMany({ where: { owner: identity.sub, ...(idList.length ? { id: { in: idList } } : {}), ...(externalId ? { id: String(externalId) } : {}) }, take: 200 });
  return json(rows.map(definition.output));
}

async function queryOrganizations(prisma, identity, { ids, qb }) {
  const selector = parseJson(qb, {});
  const idList = parseIds(ids);
  const rows = await prisma.org.findMany({ where: { ...(idList.length ? { id: { in: idList } } : {}), ...(selector.id ? { id: String(selector.id) } : {}) }, take: 200 });
  return json(rows);
}

async function saveEntities(prisma, identity, name, input, updateOnly = false) {
  const definition = entities[name]; const results = [];
  for (const raw of input || []) {
    try {
      const owner = ensureOwner(identity, raw.owner); const data = definition.input(raw, owner); const id = data.id;
      if (!id) throw new Error(`Missing ${definition.id}`);
      const existing = await prisma[definition.model].findFirst({ where: { id, owner }, select: { id: true } });
      if (updateOnly && !existing) throw new Error('Not found');
      const row = existing ? await prisma[definition.model].update({ where: { id }, data: compact({ ...data, id: undefined, owner: undefined }) }) : await prisma[definition.model].create({ data });
      results.push({ id: row.id, success: true });
    } catch (error) { results.push({ id: raw?.[definition.id] || null, success: false, error: error.message }); }
  }
  return json(results);
}

async function removeEntities(prisma, identity, name, input) {
  const definition = entities[name]; const results = [];
  for (const raw of input || []) {
    try { ensureOwner(identity, raw.owner); const changed = await prisma[definition.model].deleteMany({ where: { id: String(raw.oid), owner: identity.sub } }); results.push({ id: raw.oid, success: changed.count === 1, error: changed.count ? null : 'Not found' }); }
    catch (error) { results.push({ id: raw?.oid || null, success: false, error: error.message }); }
  }
  return json(results);
}

module.exports = { entities, queryEntity, queryOrganizations, removeEntities, saveEntities };
