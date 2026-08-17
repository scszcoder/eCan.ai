'use strict';

const crypto = require('node:crypto');

const DEFAULT_PREFIX = 'ecan-prompts';

function cleanKeySegment(value, label) {
  const segment = String(value || '').trim();
  if (!segment) throw new Error(`${label} is required for prompt snapshot`);
  return segment.replace(/[^A-Za-z0-9._@+-]/g, '_');
}

function promptSnapshotKey(owner, promptId, env = process.env) {
  const prefix = String(env.PROMPTS_COS_PREFIX || DEFAULT_PREFIX)
    .replace(/^\/+|\/+$/g, '')
    .split('/')
    .map((part) => cleanKeySegment(part, 'PROMPTS_COS_PREFIX'))
    .join('/');
  return `${prefix}/${cleanKeySegment(owner, 'owner')}/${cleanKeySegment(promptId, 'prompt id')}.json`;
}

function promptRevisionKey(owner, promptId, prompt, env = process.env, revisionId = crypto.randomBytes(6).toString('hex')) {
  const latestKey = promptSnapshotKey(owner, promptId, env);
  const revision = cleanKeySegment(
    prompt.updatedAt instanceof Date ? prompt.updatedAt.toISOString() : prompt.updatedAt || new Date().toISOString(),
    'updated timestamp',
  );
  return `${latestKey.slice(0, -5)}/versions/${revision}-${cleanKeySegment(revisionId, 'revision id')}.json`;
}

function requirePromptCosConfig(env = process.env) {
  const bucket = env.PROMPTS_COS_BUCKET || env.COS_BUCKET;
  const region = env.PROMPTS_COS_REGION || env.COS_REGION || env.TCB_REGION;
  if (!bucket) throw new Error('Missing PROMPTS_COS_BUCKET or COS_BUCKET environment variable');
  if (!region) throw new Error('Missing PROMPTS_COS_REGION or COS_REGION environment variable');
  if (!/^[a-z0-9][a-z0-9.-]+-\d+$/.test(bucket)) {
    throw new Error('Prompt COS bucket must include the Tencent Cloud APPID suffix');
  }
  return { bucket, region };
}

function createCosClient(env = process.env) {
  const COS = require('cos-nodejs-sdk-v5');
  const options = {};
  const secretId = env.TENCENTCLOUD_SECRETID || env.ECAN_TENCENT_SECRET_ID;
  const secretKey = env.TENCENTCLOUD_SECRETKEY || env.ECAN_TENCENT_SECRET_KEY;
  if (secretId && secretKey) {
    options.SecretId = secretId;
    options.SecretKey = secretKey;
    if (env.TENCENTCLOUD_SESSIONTOKEN) options.SecurityToken = env.TENCENTCLOUD_SESSIONTOKEN;
  }
  return new COS(options);
}

function putObject(client, params) {
  return new Promise((resolve, reject) => {
    client.putObject(params, (error, data) => (error ? reject(error) : resolve(data)));
  });
}

function getObject(client, params) {
  return new Promise((resolve, reject) => {
    client.getObject(params, (error, data) => (error ? reject(error) : resolve(data)));
  });
}

function getBucket(client, params) {
  return new Promise((resolve, reject) => {
    client.getBucket(params, (error, data) => (error ? reject(error) : resolve(data)));
  });
}

async function savePromptSnapshot(prompt, { client, env = process.env } = {}) {
  if (!prompt?.id || !prompt?.owner) throw new Error('Prompt id and owner are required for snapshot');
  const { bucket, region } = requirePromptCosConfig(env);
  const key = promptSnapshotKey(prompt.owner, prompt.id, env);
  const body = JSON.stringify({
    id: prompt.id,
    owner: prompt.owner,
    prompt: prompt.prompt,
    version: prompt.version || null,
    created_at: prompt.createdAt instanceof Date ? prompt.createdAt.toISOString() : prompt.createdAt,
    updated_at: prompt.updatedAt instanceof Date ? prompt.updatedAt.toISOString() : prompt.updatedAt,
  }, null, 2);
  const cos = client || createCosClient(env);
  const data = await putObject(cos, {
    Bucket: bucket,
    Region: region,
    Key: key,
    Body: body,
    ContentType: 'application/json; charset=utf-8',
  });
  let revisionKey = null;
  if (!data?.VersionId) {
    revisionKey = promptRevisionKey(prompt.owner, prompt.id, prompt, env);
    await putObject(cos, {
      Bucket: bucket,
      Region: region,
      Key: revisionKey,
      Body: body,
      ContentType: 'application/json; charset=utf-8',
    });
  }
  return { bucket, region, key, revisionKey, versionId: data?.VersionId || null, etag: data?.ETag || null };
}

async function getPromptSnapshot(owner, promptId, { client, env = process.env } = {}) {
  const { bucket, region } = requirePromptCosConfig(env);
  const key = promptSnapshotKey(owner, promptId, env);
  const data = await getObject(client || createCosClient(env), { Bucket: bucket, Region: region, Key: key });
  const body = Buffer.isBuffer(data?.Body) ? data.Body.toString('utf8') : String(data?.Body || '');
  return {
    bucket,
    region,
    key,
    versionId: data?.VersionId || null,
    etag: data?.ETag || null,
    contentLength: Number(data?.headers?.['content-length'] || Buffer.byteLength(body)),
    snapshot: JSON.parse(body),
  };
}

async function listPromptRevisions(owner, promptId, { client, env = process.env } = {}) {
  const { bucket, region } = requirePromptCosConfig(env);
  const prefix = `${promptSnapshotKey(owner, promptId, env).slice(0, -5)}/versions/`;
  const data = await getBucket(client || createCosClient(env), {
    Bucket: bucket,
    Region: region,
    Prefix: prefix,
    'Max-keys': 1000,
  });
  return {
    bucket,
    region,
    prefix,
    revisions: (data?.Contents || []).map((item) => ({
      key: item.Key,
      size: Number(item.Size),
      etag: item.ETag || null,
      lastModified: item.LastModified || null,
    })),
  };
}

module.exports = { getPromptSnapshot, listPromptRevisions, promptRevisionKey, promptSnapshotKey, requirePromptCosConfig, savePromptSnapshot };