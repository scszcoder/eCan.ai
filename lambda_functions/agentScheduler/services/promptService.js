/**
 * S3-based Prompt Service for agentScheduler Lambda
 * 
 * Reads prompts from S3 bucket ecan-skills:
 * - Public/sample prompts: public/prompts/sample_prompts/*.json (readOnly)
 * - User prompts: {normalized_owner}/prompts/*.json (editable)
 * 
 * Prompt files are named: {prompt_name}_{prompt_id}.json
 * e.g., ebay_orders0_pr-92939.json
 */

const crypto = require("crypto");
const {
  S3Client,
  GetObjectCommand,
  PutObjectCommand,
  DeleteObjectCommand,
  ListObjectsV2Command
} = require("@aws-sdk/client-s3");

const REGION = process.env.AWS_REGION || "us-east-1";
const BUCKET = process.env.SKILL_BUCKET || "ecan-skills";
const PUBLIC_PROMPTS_PREFIX = "public/prompts/sample_prompts";
const DEFAULT_VERSION = "0.1";

const s3 = new S3Client({ region: REGION });

/**
 * Normalize owner email to S3-safe folder name
 * Replace @ and . with _
 */
function normalizeOwnerForPath(owner) {
  if (!owner) return "unknown";
  return owner.replace(/[@.]/g, "_");
}

/**
 * Get user prompts prefix
 */
function getUserPromptsPrefix(owner) {
  const normalized = normalizeOwnerForPath(owner);
  return `${normalized}/prompts`;
}

/**
 * Generate a unique prompt ID
 */
function genId() {
  return `pr-${crypto.randomBytes(4).toString("hex")}`;
}

/**
 * Stream to string helper
 */
async function streamToString(stream) {
  if (!stream) return "";
  const chunks = [];
  for await (const chunk of stream) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  return Buffer.concat(chunks).toString("utf-8");
}

/**
 * Get JSON from S3
 */
async function s3GetJson(key) {
  try {
    const res = await s3.send(new GetObjectCommand({ Bucket: BUCKET, Key: key }));
    const content = await streamToString(res.Body);
    return JSON.parse(content);
  } catch (err) {
    if (err.name === "NoSuchKey" || err.Code === "NoSuchKey") {
      return null;
    }
    throw err;
  }
}

/**
 * Put JSON to S3
 */
async function s3PutJson(key, data) {
  await s3.send(new PutObjectCommand({
    Bucket: BUCKET,
    Key: key,
    Body: JSON.stringify(data, null, 2),
    ContentType: "application/json"
  }));
}

/**
 * Delete object from S3
 */
async function s3Delete(key) {
  await s3.send(new DeleteObjectCommand({ Bucket: BUCKET, Key: key }));
}

/**
 * List all JSON files in a prefix
 */
async function s3ListJsonFiles(prefix) {
  const keys = [];
  let continuationToken;
  do {
    const res = await s3.send(new ListObjectsV2Command({
      Bucket: BUCKET,
      Prefix: prefix,
      ContinuationToken: continuationToken
    }));
    const contents = res.Contents || [];
    for (const obj of contents) {
      if (obj.Key && obj.Key.endsWith(".json")) {
        keys.push({ key: obj.Key, lastModified: obj.LastModified });
      }
    }
    continuationToken = res.NextContinuationToken;
  } while (continuationToken);
  return keys;
}

/**
 * Extract prompt ID from filename
 * Filename format: {name}_{id}.json or just {id}.json
 */
function extractPromptIdFromFilename(filename) {
  // Remove .json extension
  const base = filename.replace(/\.json$/, "");
  // Check if filename contains an underscore - ID is after the last underscore if it looks like pr-xxxxx
  const parts = base.split("_");
  const lastPart = parts[parts.length - 1];
  if (lastPart && lastPart.startsWith("pr-")) {
    return lastPart;
  }
  // Otherwise treat the whole basename as the ID
  return base;
}

/**
 * Build prompt filename from title and ID
 */
function buildPromptFilename(title, id) {
  const safeTitle = (title || "prompt")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 50);
  return `${safeTitle}_${id}.json`;
}

/**
 * Normalize prompt data to standard format
 * GraphQL schema expects: id!, owner!, prompt! (AWSJSON), version, created_at, updated_at
 */
function normalizePrompt(raw, { source, readOnly, lastModified }) {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  
  // Build the prompt content object (this goes into the AWSJSON prompt field)
  const promptContent = {
    title: raw.title || "",
    topic: raw.topic || "",
    usageCount: parseInt(raw.usageCount || 0, 10),
    sections: raw.sections || [],
    userSections: raw.userSections || [],
    humanInputs: raw.humanInputs || raw.human_inputs || [],
    source: source,
    readOnly: Boolean(readOnly)
  };
  
  // If raw.prompt exists and is an object, merge it
  if (raw.prompt && typeof raw.prompt === "object") {
    Object.assign(promptContent, raw.prompt);
  } else if (raw.prompt && typeof raw.prompt === "string") {
    // If prompt is a string (legacy), include as content
    promptContent.content = raw.prompt;
  }
  
  // Handle lastModified in content
  if (lastModified instanceof Date) {
    promptContent.lastModified = lastModified.toISOString();
  } else if (raw.lastModified) {
    promptContent.lastModified = raw.lastModified;
  }
  
  // Return normalized prompt matching GraphQL schema
  return {
    id: raw.id || "",
    owner: raw.owner || "",
    prompt: promptContent, // AWSJSON! - must not be null
    version: raw.version || DEFAULT_VERSION,
    created_at: raw.created_at || new Date().toISOString(),
    updated_at: raw.updated_at || new Date().toISOString()
  };
}

/**
 * Load all prompts from a prefix
 */
async function loadPromptsFromPrefix(prefix, { source, readOnly }) {
  const prompts = [];
  try {
    const files = await s3ListJsonFiles(prefix);
    for (const file of files) {
      try {
        const data = await s3GetJson(file.key);
        if (data) {
          // Extract ID from filename if not in data
          if (!data.id) {
            const filename = file.key.split("/").pop();
            data.id = extractPromptIdFromFilename(filename);
          }
          const normalized = normalizePrompt(data, {
            source,
            readOnly,
            lastModified: file.lastModified
          });
          if (normalized && normalized.id) {
            prompts.push(normalized);
          }
        }
      } catch (err) {
        console.warn(`[promptService] Failed to load prompt from ${file.key}: ${err.message}`);
      }
    }
  } catch (err) {
    console.error(`[promptService] Failed to list prompts from ${prefix}: ${err.message}`);
  }
  return prompts;
}

/**
 * Find prompt file key by ID in a prefix
 */
async function findPromptKeyById(prefix, promptId) {
  try {
    const files = await s3ListJsonFiles(prefix);
    for (const file of files) {
      const filename = file.key.split("/").pop();
      if (filename.includes(promptId)) {
        return file.key;
      }
    }
  } catch (err) {
    console.warn(`[promptService] Failed to find prompt ${promptId} in ${prefix}: ${err.message}`);
  }
  return null;
}

/**
 * Add a new prompt (user prompts only)
 * Also handles updates - if a prompt with the same ID exists, delete the old file first
 */
async function addPrompt(data = {}) {
  const owner = data.owner;
  if (!owner) {
    throw new Error("Owner is required to add a prompt");
  }
  
  const id = data.id || genId();
  const now = new Date().toISOString();
  
  // Parse the nested prompt content if it's a JSON string (from GraphQL AWSJSON)
  let promptContent = {};
  if (data.prompt) {
    if (typeof data.prompt === 'string') {
      try {
        promptContent = JSON.parse(data.prompt);
      } catch (e) {
        console.warn('[promptService] Failed to parse prompt JSON:', e.message);
      }
    } else if (typeof data.prompt === 'object') {
      promptContent = data.prompt;
    }
  }
  
  // Extract fields from nested prompt content, falling back to top-level data
  const title = promptContent.title || data.title || data.topic || "Untitled";
  const topic = promptContent.topic || data.topic || "";
  
  const prefix = getUserPromptsPrefix(owner);
  
  // Check if a prompt with this ID already exists (for update/rename scenarios)
  // If it exists with a different filename (title changed), delete the old file
  const existingKey = await findPromptKeyById(prefix, id);
  const newFilename = buildPromptFilename(title, id);
  const newKey = `${prefix}/${newFilename}`;
  
  if (existingKey && existingKey !== newKey) {
    // Title changed - delete old file
    console.log(`[promptService] Prompt title changed, deleting old file: ${existingKey}`);
    await s3Delete(existingKey);
  }
  
  // Load existing prompt to preserve created_at if updating
  let created_at = now;
  if (existingKey) {
    const existing = await s3GetJson(existingKey);
    if (existing && existing.created_at) {
      created_at = existing.created_at;
    }
  }
  
  const prompt = {
    id,
    title,
    topic,
    owner,
    version: data.version || promptContent.version || DEFAULT_VERSION,
    usageCount: promptContent.usageCount || data.usageCount || 0,
    sections: promptContent.sections || data.sections || [],
    userSections: promptContent.userSections || data.userSections || [],
    humanInputs: promptContent.humanInputs || data.humanInputs || [],
    created_at,
    updated_at: now
  };
  
  // Store the nested prompt content for GraphQL compatibility
  prompt.prompt = {
    ...promptContent,
    title,
    topic,
    source: promptContent.source || 'my_prompts',
    readOnly: false
  };
  
  await s3PutJson(newKey, prompt);
  
  return { success: true, id };
}

/**
 * Update an existing prompt (user prompts only)
 */
async function updatePrompt(id, owner, fields = {}) {
  if (!id) {
    throw new Error("Prompt id is required");
  }
  if (!owner) {
    throw new Error("Owner is required to update a prompt");
  }
  
  const prefix = getUserPromptsPrefix(owner);
  const existingKey = await findPromptKeyById(prefix, id);
  
  if (!existingKey) {
    return { success: false, id, error: "NOT_FOUND: Prompt not found" };
  }
  
  // Load existing prompt
  const existing = await s3GetJson(existingKey);
  if (!existing) {
    return { success: false, id, error: "NOT_FOUND: Prompt not found" };
  }
  
  const now = new Date().toISOString();
  
  // Merge fields
  const updated = {
    ...existing,
    ...fields,
    id, // preserve ID
    owner, // preserve owner
    updated_at: now
  };
  
  // If title changed, we might need to rename the file
  const newTitle = fields.title || existing.title || "Untitled";
  const newFilename = buildPromptFilename(newTitle, id);
  const newKey = `${prefix}/${newFilename}`;
  
  // Save to new key
  await s3PutJson(newKey, updated);
  
  // If key changed, delete old file
  if (newKey !== existingKey) {
    await s3Delete(existingKey);
  }
  
  return { success: true, id };
}

/**
 * Delete a prompt (user prompts only)
 */
async function deletePrompt(id, owner) {
  if (!id) {
    throw new Error("Prompt id is required");
  }
  if (!owner) {
    throw new Error("Owner is required to remove a prompt");
  }
  
  const prefix = getUserPromptsPrefix(owner);
  const key = await findPromptKeyById(prefix, id);
  
  if (!key) {
    return { success: false, id, error: "NOT_FOUND: Prompt not found" };
  }
  
  await s3Delete(key);
  return { success: true };
}

/**
 * Get a single prompt by ID
 * Searches user prompts first, then public prompts
 */
async function getPromptById(id, owner) {
  if (!id) {
    return null;
  }
  
  // Search user prompts first if owner provided
  if (owner) {
    const userPrefix = getUserPromptsPrefix(owner);
    const userKey = await findPromptKeyById(userPrefix, id);
    if (userKey) {
      const data = await s3GetJson(userKey);
      if (data) {
        return normalizePrompt({ ...data, id }, {
          source: "my_prompts",
          readOnly: false
        });
      }
    }
  }
  
  // Search public/sample prompts
  const publicKey = await findPromptKeyById(PUBLIC_PROMPTS_PREFIX, id);
  if (publicKey) {
    const data = await s3GetJson(publicKey);
    if (data) {
      return normalizePrompt({ ...data, id }, {
        source: "sample_prompts",
        readOnly: true
      });
    }
  }
  
  return null;
}

/**
 * List all prompts for an owner
 * Returns both user prompts and public sample prompts
 */
async function listPrompts(owner) {
  const allPrompts = [];
  
  // Load user prompts
  if (owner) {
    const userPrefix = getUserPromptsPrefix(owner);
    const userPrompts = await loadPromptsFromPrefix(userPrefix, {
      source: "my_prompts",
      readOnly: false
    });
    // Set owner on user prompts
    userPrompts.forEach(p => { p.owner = owner; });
    allPrompts.push(...userPrompts);
  }
  
  // Load public/sample prompts
  const publicPrompts = await loadPromptsFromPrefix(PUBLIC_PROMPTS_PREFIX, {
    source: "sample_prompts",
    readOnly: true
  });
  allPrompts.push(...publicPrompts);
  
  return allPrompts;
}

/**
 * Query prompts with filters
 */
async function queryPrompts({ id, owner, version, search } = {}) {
  if (!owner) {
    throw new Error("Owner is required to query prompts");
  }
  
  // If ID is specified, get single prompt
  if (id) {
    const prompt = await getPromptById(id, owner);
    if (!prompt) {
      return [];
    }
    if (version && prompt.version !== version) {
      return [];
    }
    if (search) {
      const haystack = JSON.stringify(prompt).toLowerCase();
      if (!haystack.includes(search.toLowerCase())) {
        return [];
      }
    }
    return [prompt];
  }
  
  // Get all prompts and filter
  let prompts = await listPrompts(owner);
  
  if (version) {
    prompts = prompts.filter(p => p.version === version);
  }
  
  if (search) {
    const searchLower = search.toLowerCase();
    prompts = prompts.filter(p => {
      const haystack = JSON.stringify(p).toLowerCase();
      return haystack.includes(searchLower);
    });
  }
  
  return prompts;
}

module.exports = {
  addPrompt,
  updatePrompt,
  deletePrompt,
  getPromptById,
  listPrompts,
  queryPrompts
};
