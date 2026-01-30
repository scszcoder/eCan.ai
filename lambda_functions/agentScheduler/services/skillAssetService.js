const {
  S3Client,
  ListObjectsV2Command,
  GetObjectCommand,
  HeadObjectCommand,
  PutObjectCommand
} = require("@aws-sdk/client-s3");
const http = require("http");
const https = require("https");
const { URL } = require("url");

const REGION = process.env.AWS_REGION || "us-east-1";
const SKILL_BUCKET = process.env.SKILL_BUCKET || process.env.SKILLS_BUCKET || "ecan-skills";
const SKILL_ASSET_API_URL = process.env.SKILL_ASSET_API_URL;
const ASSET_API_TIMEOUT_MS = Number(process.env.SKILL_ASSET_API_TIMEOUT_MS || 15000);

const s3 = new S3Client({ region: REGION });

function normalizeOwnerFolder(owner) {
  if (!owner) {
    return "anonymous";
  }
  return owner
    .trim()
    .toLowerCase()
    .replace(/@/g, "_")
    .replace(/\./g, "_")
    .replace(/[^a-z0-9/_-]/g, "_");
}

function normalizeSkillPath(pathInput, fallbackName, fallbackId) {
  let raw = pathInput || fallbackName || fallbackId;
  if (!raw) {
    return null;
  }
  raw = raw.trim();
  if (!raw) {
    return null;
  }
  raw = raw.replace(/^s3:\/\//i, "");
  if (raw.toLowerCase().startsWith(`${SKILL_BUCKET.toLowerCase()}/`)) {
    raw = raw.slice(SKILL_BUCKET.length + 1);
  }
  raw = raw.replace(/\\/g, "/");
  raw = raw.replace(/\.{2,}/g, "_");
  raw = raw.replace(/[^a-zA-Z0-9/_-]/g, "_");
  return raw.replace(/^\/+/, "").replace(/\/+$/, "");
}

function buildOwnerScopedPath(ownerFolder, skillPath) {
  if (!skillPath) {
    return ownerFolder;
  }
  const normalized = skillPath.replace(/^\/+/, "");
  if (normalized.startsWith(`${ownerFolder}/`)) {
    return normalized;
  }
  return `${ownerFolder}/${normalized}`;
}

async function ensureFolderPlaceholder(bucket, prefix) {
  if (!prefix) {
    return;
  }
  const folderKey = prefix.replace(/\/+$/, "") + "/";
  try {
    await s3.send(new HeadObjectCommand({ Bucket: bucket, Key: folderKey }));
  } catch (err) {
    const statusCode = err?.$metadata?.httpStatusCode;
    const isMissing = err?.name === "NotFound" || statusCode === 404 || err?.Code === "NotFound";
    if (!isMissing) {
      throw err;
    }
    await s3.send(
      new PutObjectCommand({
        Bucket: bucket,
        Key: folderKey,
        Body: ""
      })
    );
  }
}

async function ensureSkillFolders(bucket, ownerFolder, ownerScopedPath) {
  await ensureFolderPlaceholder(bucket, ownerFolder);
  if (ownerScopedPath && ownerScopedPath !== ownerFolder) {
    await ensureFolderPlaceholder(bucket, ownerScopedPath);
  }
}

async function listSkillObjects(bucket, prefix) {
  const objects = [];
  let continuation;
  do {
    const params = {
      Bucket: bucket,
      Prefix: prefix,
      ContinuationToken: continuation
    };
    const response = await s3.send(new ListObjectsV2Command(params));
    const contents = response.Contents || [];
    for (const item of contents) {
      if (!item.Key || item.Key.endsWith("/")) {
        continue;
      }
      const relativePath = item.Key.slice(prefix.length);
      if (!relativePath) {
        continue;
      }
      objects.push({
        key: item.Key,
        relativePath,
        size: item.Size || 0,
        lastModified: item.LastModified ? new Date(item.LastModified) : null
      });
    }
    continuation = response.IsTruncated ? response.NextContinuationToken : undefined;
  } while (continuation);
  return objects;
}

async function buildManifest(owner, skillDescriptor = {}) {
  const ownerFolder = normalizeOwnerFolder(owner);
  const normalizedPath = normalizeSkillPath(
    skillDescriptor.path,
    skillDescriptor.name,
    skillDescriptor.id
  );
  if (!normalizedPath) {
    return null;
  }
  const ownerScopedPath = buildOwnerScopedPath(ownerFolder, normalizedPath);
  await ensureSkillFolders(SKILL_BUCKET, ownerFolder, ownerScopedPath);
  const prefix = ownerScopedPath.replace(/\/+$/, "") + "/";
  const objects = await listSkillObjects(SKILL_BUCKET, prefix);
  const relativeSkillPath = ownerScopedPath.slice(ownerFolder.length).replace(/^\/+/, "");
  const relativePaths = objects.map((obj) => obj.relativePath);
  return {
    bucket: SKILL_BUCKET,
    ownerFolder,
    relativeSkillPath,
    prefix,
    objects,
    relativePaths,
    sourceString: relativePaths.join(",")
  };
}

function streamToBuffer(stream) {
  if (!stream) {
    return Promise.resolve(Buffer.alloc(0));
  }
  return new Promise((resolve, reject) => {
    const chunks = [];
    stream.on("data", (chunk) => chunks.push(chunk));
    stream.on("error", reject);
    stream.on("end", () => resolve(Buffer.concat(chunks)));
  });
}

function buildHttpOptions(targetUrl, method = "POST", headers = {}, timeout = ASSET_API_TIMEOUT_MS) {
  const urlObj = new URL(targetUrl);
  return {
    protocol: urlObj.protocol,
    hostname: urlObj.hostname,
    port: urlObj.port || (urlObj.protocol === "https:" ? 443 : 80),
    path: `${urlObj.pathname}${urlObj.search}`,
    method,
    headers,
    timeout
  };
}

function sendHttpRequest({ url, method, headers = {}, body, timeout }) {
  const options = buildHttpOptions(url, method, headers, timeout);
  const client = options.protocol === "https:" ? https : http;
  return new Promise((resolve, reject) => {
    const req = client.request(options, (res) => {
      const chunks = [];
      res.on("data", (chunk) => chunks.push(chunk));
      res.on("end", () => {
        const payload = Buffer.concat(chunks).toString();
        if (res.statusCode >= 400) {
          reject(new Error(`HTTP ${res.statusCode}: ${payload || ""}`));
          return;
        }
        resolve({
          statusCode: res.statusCode,
          headers: res.headers,
          body: payload
        });
      });
    });
    req.on("error", reject);
    if (body) {
      req.write(body);
    }
    req.end();
  });
}

async function postJson(url, payload) {
  const body = JSON.stringify(payload || {});
  const headers = {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(body)
  };
  const response = await sendHttpRequest({ url, method: "POST", headers, body });
  if (!response.body) {
    return {};
  }
  try {
    return JSON.parse(response.body);
  } catch (err) {
    throw new Error(`Failed to parse JSON from ${url}: ${err.message}`);
  }
}

async function uploadAssetFromS3(bucket, key, targetUrl, contentType = "application/octet-stream") {
  const object = await s3.send(new GetObjectCommand({ Bucket: bucket, Key: key }));
  const bodyBuffer = await streamToBuffer(object.Body);
  const headers = {
    "Content-Type": contentType,
    "Content-Length": bodyBuffer.length
  };
  await sendHttpRequest({ url: targetUrl, method: "PUT", headers, body: bodyBuffer });
}

async function syncManifestWithCloud({ owner, skillId, skillName, manifest }) {
  if (!SKILL_ASSET_API_URL || !manifest) {
    return null;
  }
  const payload = {
    owner,
    skillId,
    skillName,
    bucket: manifest.bucket,
    prefix: manifest.prefix,
    source: manifest.sourceString,
    files: manifest.relativePaths
  };
  const response = await postJson(SKILL_ASSET_API_URL, payload);
  const uploadTargets = Array.isArray(response?.uploadUrls) ? response.uploadUrls : [];
  for (const target of uploadTargets) {
    if (!target?.url || !target?.path) {
      continue;
    }
    const key = `${manifest.prefix}${target.path}`.replace(/\/+/g, "/");
    await uploadAssetFromS3(manifest.bucket, key, target.url, target.contentType);
  }
  return response;
}

module.exports = {
  buildManifest,
  normalizeOwnerFolder,
  normalizeSkillPath,
  syncManifestWithCloud
};
