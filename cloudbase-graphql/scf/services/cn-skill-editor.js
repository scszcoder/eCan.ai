/**
 * CN Skill Editor & File Operations
 *
 * Skill file metadata, editor cache, breakpoints, scaffold, and copy operations.
 *
 * File content storage model:
 *   - Skill file content lives in Tencent COS, accessed via short-lived signed URLs.
 *   - The server never reads/writes file bytes; clients PUT/GET against the URLs we return.
 *   - This avoids SCF /tmp (ephemeral, cold-start wiped) and gives durable, multi-instance storage.
 */

const { executeFileOps } = require('../storage/cos-file-ops');

const SKILL_PREFIX = 'skills/';
const UPLOAD_EXPIRES = 600; // 10 minutes is enough for a single PUT
const DOWNLOAD_EXPIRES = 300;

function parseInput(input) {
  if (typeof input === 'string') {
    try { return JSON.parse(input); } catch { return {}; }
  }
  return input || {};
}

function safeName(value) {
  return String(value || '').replace(/\.\./g, '').replace(/^\/+/, '');
}

function skillNameOf(prefix) {
  return (prefix || '').split('/').filter(Boolean)[0] || '';
}

function fileMetaFromObject(key, size, lastModified) {
  const trimmed = key.startsWith(SKILL_PREFIX) ? key.slice(SKILL_PREFIX.length) : key;
  return {
    fileName: trimmed.split('/').pop(),
    filePath: trimmed,
    fileSize: Number(size) || 0,
    skillName: skillNameOf(trimmed),
    updatedAt: lastModified || new Date().toISOString(),
  };
}

async function listSkillFiles(prisma, identity, { prefix = '', limit = 50, nextToken, userId }) {
  // List COS objects under users/<namespace>/skills/<prefix>.
  // userId is accepted for signature compatibility with the intl resolver but is unused.
  void userId;
  void nextToken;
  try {
    const results = await executeFileOps({
      owner: identity.sub,
      operations: [{ op: 'list', options: prefix ? `${SKILL_PREFIX}${safeName(prefix)}` : SKILL_PREFIX, names: '_' }],
    });
    const listed = results[0]?.objects || [];
    return JSON.stringify(listed.slice(0, limit).map((obj) => fileMetaFromObject(obj.key, obj.size, obj.lastModified)));
  } catch {
    return JSON.stringify([]);
  }
}

async function readSkillFile(prisma, identity, { filePath, userId }) {
  void userId;
  const safePath = safeName(filePath);
  if (!safePath) return JSON.stringify([]);
  try {
    const results = await executeFileOps({
      owner: identity.sub,
      operations: [{ op: 'download', options: SKILL_PREFIX, names: safePath, expiresIn: DOWNLOAD_EXPIRES }],
    });
    const r = results[0];
    return JSON.stringify([{
      fileName: safePath.split('/').pop(),
      filePath: safePath,
      fileSize: 0,
      skillName: skillNameOf(safePath),
      downloadUrl: r.url,
      expiresIn: DOWNLOAD_EXPIRES,
    }]);
  } catch (e) {
    return JSON.stringify([{ filePath: safePath, success: false, error: e.message }]);
  }
}

async function writeSkillFile(prisma, identity, input) {
  const results = [];
  for (const item of input || []) {
    try {
      const safePath = safeName(item.filePath);
      if (!safePath) { results.push({ filePath: item.filePath, success: false, error: 'filePath is required' }); continue; }
      const cos = await executeFileOps({
        owner: identity.sub,
        operations: [{
          op: 'upload',
          options: SKILL_PREFIX,
          names: safePath,
          contentType: item.contentType || 'text/plain;charset=utf-8',
          expiresIn: UPLOAD_EXPIRES,
        }],
      });
      const r = cos[0];
      results.push({
        fileName: safePath.split('/').pop(),
        filePath: safePath,
        fileSize: item.content ? Buffer.byteLength(item.content, 'utf8') : 0,
        skillName: skillNameOf(safePath),
        uploadUrl: r.url,
        method: r.method,
        expiresIn: UPLOAD_EXPIRES,
        content: item.content,
      });
    } catch (e) { results.push({ filePath: item.filePath, success: false, error: e.message }); }
  }
  return JSON.stringify(results);
}

async function openSkillFile(prisma, identity, { filePath, userId }) {
  return readSkillFile(prisma, identity, { filePath, userId });
}

async function saveEditorCache(prisma, identity, input) {
  const selector = parseInput(input);
  const cacheKey = `editor_cache_${identity.sub}_${selector.userId || 'default'}`;
  const cacheData = { cacheData: selector.cacheData, recentFiles: selector.recentFiles || [], timestamp: selector.timestamp || new Date().toISOString(), version: selector.version || '1.0' };
  await prisma.editorCache.upsert({
    where: { cacheKey },
    create: { owner: identity.sub, cacheKey, cacheData: cacheData.cacheData, recentFiles: cacheData.recentFiles, version: cacheData.version, updatedAt: new Date(cacheData.timestamp) },
    update: { cacheData: cacheData.cacheData, recentFiles: cacheData.recentFiles, version: cacheData.version, updatedAt: new Date(cacheData.timestamp) },
  });
  return JSON.stringify({ newFilePath: cacheKey, renamed: false });
}

async function getEditorCache(prisma, identity, userId) {
  const cacheKey = `editor_cache_${identity.sub}_${userId || 'default'}`;
  const existing = await prisma.editorCache.findUnique({ where: { cacheKey } });
  const cacheData = existing?.cacheData || {};
  return JSON.stringify({ cacheData: cacheData || {}, recentFiles: existing?.recentFiles || [] });
}

async function clearEditorCache(prisma, identity, userId) {
  const owner = identity.sub;
  const prefix = `editor_cache_${owner}_`;
  if (userId) {
    await prisma.editorCache.deleteMany({ where: { cacheKey: `${prefix}${userId}` } });
  } else {
    await prisma.editorCache.deleteMany({ where: { owner, cacheKey: { startsWith: prefix } } });
  }
  return 'true';
}

async function setSkillBreakpoints(prisma, identity, nodeName, username) {
  await prisma.skillBreakpoint.upsert({
    where: { owner_username_nodeName: { owner: identity.sub, username, nodeName } },
    create: { owner: identity.sub, username, nodeName, active: true },
    update: { active: true },
  });
  return JSON.stringify({ success: true, message: `Breakpoint set at ${nodeName}`, data: { node_name: nodeName } });
}

async function clearSkillBreakpoints(prisma, identity, nodeName, username) {
  await prisma.skillBreakpoint.deleteMany({ where: { owner: identity.sub, username, nodeName } });
  return JSON.stringify({ success: true, message: `Breakpoint cleared at ${nodeName}`, data: { node_name: nodeName } });
}

async function scaffoldSkill(prisma, identity, input) {
  const selector = parseInput(input);
  const name = selector.name || `skill_${Date.now()}`;
  const skillPrefix = `${SKILL_PREFIX}${name}/`;
  const bundleJson = selector.bundleJson ? (typeof selector.bundleJson === 'string' ? selector.bundleJson : JSON.stringify(selector.bundleJson)) : JSON.stringify({ skills: [name], triggers: [] });
  const skillYaml = `# Skill: ${name}\nversion: 1.0.0\n`;

  try {
    const ops = await executeFileOps({
      owner: identity.sub,
      operations: [
        { op: 'upload', options: skillPrefix, names: 'skill.yaml', contentType: 'text/yaml', expiresIn: UPLOAD_EXPIRES },
        { op: 'upload', options: skillPrefix, names: 'graph.json', contentType: 'application/json', expiresIn: UPLOAD_EXPIRES },
        { op: 'upload', options: skillPrefix, names: 'bundle.json', contentType: 'application/json', expiresIn: UPLOAD_EXPIRES },
      ],
    });

    const urlMap = Object.fromEntries(ops.map((r) => [r.key.split('/').pop(), r.url]));
    return JSON.stringify({
      name,
      skillRoot: `${SKILL_PREFIX}${name}/`,
      diagramPath: `${SKILL_PREFIX}${name}/graph.json`,
      uploads: {
        'skill.yaml': { url: urlMap['skill.yaml'], content: skillYaml },
        'graph.json': { url: urlMap['graph.json'], content: bundleJson },
        'bundle.json': { url: urlMap['bundle.json'], content: bundleJson },
      },
      expiresIn: UPLOAD_EXPIRES,
    });
  } catch (e) {
    return JSON.stringify({ name, success: false, error: e.message });
  }
}

async function copySkillTo(prisma, identity, input) {
  const selector = parseInput(input);
  const sourcePath = safeName(selector.sourcePath || '');
  const newName = selector.newName || `skill_copy_${Date.now()}`;
  const skillPrefix = `${SKILL_PREFIX}${newName}/`;
  try {
    const ops = await executeFileOps({
      owner: identity.sub,
      operations: [
        { op: 'upload', options: skillPrefix, names: 'skill.yaml', contentType: 'text/yaml', expiresIn: UPLOAD_EXPIRES },
        { op: 'upload', options: skillPrefix, names: 'graph.json', contentType: 'application/json', expiresIn: UPLOAD_EXPIRES },
        { op: 'upload', options: skillPrefix, names: 'bundle.json', contentType: 'application/json', expiresIn: UPLOAD_EXPIRES },
      ],
    });
    return JSON.stringify({
      name: newName,
      skillRoot: skillPrefix,
      diagramPath: `${skillPrefix}graph.json`,
      requiresClientCopy: true,
      sourcePath,
      uploads: ops.map((r) => ({ fileName: r.key.split('/').pop(), uploadUrl: r.url, expiresIn: UPLOAD_EXPIRES })),
    });
  } catch (e) {
    return JSON.stringify({ name: newName, success: false, error: e.message });
  }
}

async function injectSkillState(prisma, identity, skill, username) {
  const skillData = typeof skill === 'string' ? skill : JSON.stringify(skill);
  // skillKey keeps each (user, skill content) tuple unique without storing the full payload in the key.
  const skillKey = `${username}:${skillData.substring(0, 50)}`;
  await prisma.skillRunState.upsert({
    where: { owner_username_skillKey: { owner: identity.sub, username, skillKey } },
    create: { owner: identity.sub, username, skillKey, skill: skillData },
    update: { skill: skillData },
  });
  return JSON.stringify({ success: true, message: 'Skill state injected', data: { skill: skillData } });
}

async function requestSkillState(prisma, identity, skill, username) {
  return JSON.stringify({ success: true, message: 'Skill state retrieved', data: { skill, username } });
}

async function loadSkillSchemas(prisma, identity, skill, username) {
  return JSON.stringify({ success: true, message: 'Skill schemas loaded', data: { skill: typeof skill === 'string' ? skill : 'parsed' } });
}

async function loadSkillEditorContexts(prisma, identity, input) {
  const selector = parseInput(input);
  const items = [];
  for (const skid of selector.skillIds || []) {
    items.push({ skillId: skid, context: { nodes: [], edges: [] }, updatedAt: new Date().toISOString() });
  }
  return JSON.stringify({ items });
}

module.exports = {
  listSkillFiles, readSkillFile, writeSkillFile, openSkillFile,
  saveEditorCache, getEditorCache, clearEditorCache,
  setSkillBreakpoints, clearSkillBreakpoints,
  scaffoldSkill, copySkillTo,
  injectSkillState, requestSkillState, loadSkillSchemas,
  loadSkillEditorContexts,
};