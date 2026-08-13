const crypto = require('node:crypto');

const DEFAULT_EXPIRES = 300;
const MAX_EXPIRES = 3600;
const MAX_OPS = 50;

function requireCosConfig(env = process.env) {
  const bucket = env.COS_BUCKET;
  const region = env.COS_REGION || env.TCB_REGION;
  if (!bucket) throw new Error('Missing COS_BUCKET environment variable');
  if (!region) throw new Error('Missing COS_REGION environment variable');
  if (!/^[a-z0-9][a-z0-9.-]+-\d+$/.test(bucket)) {
    throw new Error('COS_BUCKET must include the Tencent Cloud APPID suffix');
  }
  return { bucket, region };
}

function createCosClient(env = process.env) {
  // Lazy load keeps schema/security tooling usable before dependencies are installed.
  const COS = require('cos-nodejs-sdk-v5');
  const options = {};
  const secretId = env.TENCENTCLOUD_SECRETID || env.ECAN_TENCENT_SECRET_ID;
  const secretKey = env.TENCENTCLOUD_SECRETKEY || env.ECAN_TENCENT_SECRET_KEY;
  const token = env.TENCENTCLOUD_SESSIONTOKEN;
  if (secretId && secretKey) {
    options.SecretId = secretId;
    options.SecretKey = secretKey;
    if (token) options.SecurityToken = token;
  }
  return new COS(options);
}

function userNamespace(owner) {
  return crypto.createHash('sha256').update(owner).digest('hex').slice(0, 32);
}

function cleanSegments(value) {
  const normalized = String(value || '').replace(/\\/g, '/').replace(/^\/+/, '');
  const segments = normalized.split('/').filter(Boolean);
  if (segments.some((part) => part === '.' || part === '..' || part.includes('\0'))) {
    throw new Error('Unsafe COS object path');
  }
  return segments.map((part) => part.replace(/[^A-Za-z0-9._@+\-=]/g, '_'));
}

function optionPath(options) {
  if (!options) return [];
  const raw = String(options);
  const pathPart = raw.includes('|') ? raw.slice(raw.indexOf('|') + 1) : raw;
  const normalized = pathPart.replace(/\\/g, '/');
  for (const marker of ['runlogs/', 'my_skills/', 'skills/', 'public/']) {
    const index = normalized.indexOf(marker);
    if (index >= 0) return cleanSegments(normalized.slice(index));
  }
  // Do not preserve machine-specific absolute directory prefixes.
  return cleanSegments(normalized).slice(-8);
}

function objectKey(owner, operation) {
  const names = Array.isArray(operation.names) ? operation.names : [operation.names];
  if (names.length !== 1 || !names[0]) throw new Error('Each file operation requires one name');
  if (/^(?:[A-Za-z]:[\\/]|[\\/])/.test(String(names[0]))) throw new Error('Absolute COS object paths are forbidden');
  const parts = [...optionPath(operation.options), ...cleanSegments(names[0])];
  if (!parts.length) throw new Error('COS object name is empty');
  return `users/${userNamespace(owner)}/${parts.join('/')}`;
}

function expiresFrom(operation) {
  let requested = DEFAULT_EXPIRES;
  if (operation.expiresIn != null) requested = Number(operation.expiresIn);
  if (!Number.isFinite(requested) || requested < 60 || requested > MAX_EXPIRES) {
    throw new Error(`expiresIn must be between 60 and ${MAX_EXPIRES} seconds`);
  }
  return Math.floor(requested);
}

function callCos(client, method, params) {
  return new Promise((resolve, reject) => {
    client[method](params, (error, data) => (error ? reject(error) : resolve(data)));
  });
}

function signedUrl(client, params) {
  return new Promise((resolve, reject) => {
    client.getObjectUrl(params, (error, data) => {
      if (error) reject(error);
      else resolve(data?.Url || data);
    });
  });
}

async function executeFileOps({ owner, operations, client, env = process.env }) {
  if (!owner) throw new Error('Authenticated owner is required');
  if (!Array.isArray(operations) || operations.length < 1 || operations.length > MAX_OPS) {
    throw new Error(`fo must contain between 1 and ${MAX_OPS} operations`);
  }
  const { bucket, region } = requireCosConfig(env);
  const cos = client || createCosClient(env);
  const results = [];

  for (const operation of operations) {
    const op = String(operation.op || '').toLowerCase();
    const key = objectKey(owner, operation);
    const base = { Bucket: bucket, Region: region, Key: key };
    if (op === 'upload' || op === 'download') {
      const method = op === 'upload' ? 'PUT' : 'GET';
      const headers = op === 'upload' && operation.contentType ? { 'Content-Type': operation.contentType } : {};
      const url = await signedUrl(cos, { ...base, Method: method, Expires: expiresFrom(operation), Sign: true, Headers: headers });
      results.push({ op, key, url, method, headers });
    } else if (op === 'list') {
      const data = await callCos(cos, 'getBucket', { Bucket: bucket, Region: region, Prefix: key, 'Max-keys': 1000 });
      results.push({ op, prefix: key, objects: (data.Contents || []).map((item) => ({ key: item.Key, size: Number(item.Size), lastModified: item.LastModified, etag: item.ETag })) });
    } else if (op === 'delete') {
      await callCos(cos, 'deleteObject', base);
      results.push({ op, key, deleted: true });
    } else {
      throw new Error(`Unsupported file operation: ${operation.op}`);
    }
  }
  return results;
}

module.exports = { executeFileOps, objectKey, requireCosConfig, userNamespace };
