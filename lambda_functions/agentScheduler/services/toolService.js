/**
 * S3-based Tool Service for agentScheduler Lambda
 * 
 * Reads MCP tools from S3 bucket ecan-skills:
 * - Public tools: public/mcp_tools/mcp_tools_schema.json (readOnly)
 * - User tools: {normalized_owner}/tools/*.json (editable)
 * 
 * The public MCP tools schema contains an array of tool definitions.
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
const PUBLIC_TOOLS_KEY = "public/mcp_tools/cloud_mcp_tools_schema.json";
const DEFAULT_VERSION = "1.0";

const s3 = new S3Client({ region: REGION });

/**
 * Normalize owner email to S3-safe folder name
 */
function normalizeOwnerForPath(owner) {
  if (!owner) return "unknown";
  return owner.replace(/[@.]/g, "_");
}

/**
 * Get user tools prefix
 */
function getUserToolsPrefix(owner) {
  const normalized = normalizeOwnerForPath(owner);
  return `${normalized}/tools`;
}

/**
 * Generate a unique tool ID
 */
function genId() {
  return `tool_${crypto.randomBytes(8).toString("hex")}`;
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
 * Build tool filename from name and ID
 */
function buildToolFilename(name, id) {
  const safeName = (name || "tool")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 50);
  return `${safeName}_${id}.json`;
}

/**
 * Parse level to integer (GraphQL expects Int)
 */
function parseLevel(level) {
  if (typeof level === "number") return level;
  if (typeof level === "string") {
    const parsed = parseInt(level, 10);
    if (!isNaN(parsed)) return parsed;
    // Map string levels to integers
    const levelMap = { basic: 0, intermediate: 1, advanced: 2, expert: 3 };
    return levelMap[level.toLowerCase()] ?? 0;
  }
  return 0;
}

/**
 * Normalize tool data to standard format
 * Preserves all original fields from the schema while adding standard metadata.
 */
function normalizeTool(raw, { source, readOnly, owner }) {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  
  const tool = {
    id: raw.id || raw.name || "",
    name: raw.name || "",
    title: raw.title || null,
    description: raw.description || "",
    owner: owner || raw.owner || "",
    tool_type: raw.tool_type || raw.type || "mcp",
    version: raw.version || DEFAULT_VERSION,
    path: raw.path || "",
    level: parseLevel(raw.level),
    config: raw.config || {},
    capabilities: raw.capabilities || [],
    limitations: raw.limitations || [],
    dependencies: raw.dependencies || [],
    public: raw.public !== false, // default to true for MCP tools
    rentable: raw.rentable || false,
    price: parseFloat(raw.price) || 0,
    price_model: raw.price_model || null,
    status: raw.status || "active",
    settings: raw.settings || {},
    source: source,
    readOnly: Boolean(readOnly),
    // Preserve original tool schema fields
    inputSchema: raw.inputSchema || null,
    outputSchema: raw.outputSchema || null,
    icons: raw.icons || null,
    annotations: raw.annotations || null,
    meta: raw.meta || {}
  };
  
  return tool;
}

/**
 * Load public MCP tools from schema file
 */
async function loadPublicTools() {
  const tools = [];
  try {
    const data = await s3GetJson(PUBLIC_TOOLS_KEY);
    if (data) {
      // The schema could be an array of tools or an object with a tools array
      let toolsArray = [];
      if (Array.isArray(data)) {
        toolsArray = data;
      } else if (data.tools && Array.isArray(data.tools)) {
        toolsArray = data.tools;
      } else if (data.mcpTools && Array.isArray(data.mcpTools)) {
        toolsArray = data.mcpTools;
      }
      
      for (const toolData of toolsArray) {
        const normalized = normalizeTool(toolData, {
          source: "mcp_tools",
          readOnly: true,
          owner: "system"
        });
        if (normalized && normalized.id) {
          tools.push(normalized);
        }
      }
    }
  } catch (err) {
    console.error(`[toolService] Failed to load public tools: ${err.message}`);
  }
  return tools;
}

/**
 * Load user tools from their folder
 */
async function loadUserTools(owner) {
  const tools = [];
  if (!owner) return tools;
  
  const prefix = getUserToolsPrefix(owner);
  try {
    const files = await s3ListJsonFiles(prefix);
    for (const file of files) {
      try {
        const data = await s3GetJson(file.key);
        if (data) {
          // Extract ID from filename if not in data
          if (!data.id) {
            const filename = file.key.split("/").pop();
            data.id = filename.replace(/\.json$/, "").split("_").pop();
          }
          const normalized = normalizeTool(data, {
            source: "my_tools",
            readOnly: false,
            owner
          });
          if (normalized && normalized.id) {
            tools.push(normalized);
          }
        }
      } catch (err) {
        console.warn(`[toolService] Failed to load tool from ${file.key}: ${err.message}`);
      }
    }
  } catch (err) {
    console.error(`[toolService] Failed to list user tools: ${err.message}`);
  }
  return tools;
}

/**
 * Find user tool file key by ID
 */
async function findUserToolKeyById(owner, toolId) {
  if (!owner || !toolId) return null;
  
  const prefix = getUserToolsPrefix(owner);
  try {
    const files = await s3ListJsonFiles(prefix);
    for (const file of files) {
      const filename = file.key.split("/").pop();
      if (filename.includes(toolId)) {
        return file.key;
      }
    }
  } catch (err) {
    console.warn(`[toolService] Failed to find tool ${toolId}: ${err.message}`);
  }
  return null;
}

/**
 * Add a new tool (user tools only)
 */
async function addTool(tool) {
  const owner = tool.owner;
  if (!owner) {
    throw new Error("Owner is required to add a tool");
  }
  
  const requestedId = tool.id;
  const id = requestedId || genId();
  
  // Check for existing tool with same ID
  if (requestedId) {
    const existing = await getToolById(requestedId);
    if (existing && existing.owner === owner) {
      return { success: false, id: requestedId, error: "ID_TAKEN: Tool id already exists" };
    }
  }
  
  const now = new Date().toISOString();
  const toolData = {
    id,
    name: tool.name || "",
    description: tool.description || "",
    owner,
    tool_type: tool.tool_type || "custom",
    version: tool.version || DEFAULT_VERSION,
    path: tool.path || "",
    level: tool.level || "basic",
    config: tool.config || {},
    capabilities: tool.capabilities || [],
    limitations: tool.limitations || [],
    dependencies: tool.dependencies || [],
    public: tool.public || false,
    rentable: tool.rentable || false,
    price: tool.price || 0,
    price_model: tool.price_model || null,
    status: tool.status || "active",
    settings: tool.settings || {},
    created_at: now,
    updated_at: now
  };
  
  if (tool.inputSchema) {
    toolData.inputSchema = tool.inputSchema;
  }
  
  const prefix = getUserToolsPrefix(owner);
  const filename = buildToolFilename(toolData.name, id);
  const key = `${prefix}/${filename}`;
  
  await s3PutJson(key, toolData);
  
  return { success: true, id };
}

/**
 * Update an existing tool (user tools only)
 */
async function updateTool(id, owner, fields) {
  if (!id) {
    throw new Error("Tool id is required");
  }
  if (!owner) {
    throw new Error("Owner is required to update a tool");
  }
  
  const existingKey = await findUserToolKeyById(owner, id);
  if (!existingKey) {
    return { success: false, id, error: "NOT_FOUND: Tool not found" };
  }
  
  const existing = await s3GetJson(existingKey);
  if (!existing) {
    return { success: false, id, error: "NOT_FOUND: Tool not found" };
  }
  
  const now = new Date().toISOString();
  const updated = {
    ...existing,
    ...fields,
    id, // preserve ID
    owner, // preserve owner
    updated_at: now
  };
  
  // Handle potential filename change if name changed
  const newName = fields.name || existing.name || "tool";
  const newFilename = buildToolFilename(newName, id);
  const prefix = getUserToolsPrefix(owner);
  const newKey = `${prefix}/${newFilename}`;
  
  await s3PutJson(newKey, updated);
  
  // Delete old file if key changed
  if (newKey !== existingKey) {
    await s3Delete(existingKey);
  }
  
  return { success: true, id };
}

/**
 * Delete a tool (user tools only)
 */
async function deleteTool(id, owner) {
  if (!id) {
    throw new Error("Tool id is required");
  }
  if (!owner) {
    throw new Error("Owner is required to delete a tool");
  }
  
  const key = await findUserToolKeyById(owner, id);
  if (!key) {
    return { success: false, id, error: "NOT_FOUND: Tool not found" };
  }
  
  await s3Delete(key);
  return { success: true };
}

/**
 * Get a tool by ID
 * Searches user tools first, then public tools
 */
async function getToolById(id) {
  if (!id) return null;
  
  // Search public tools
  const publicTools = await loadPublicTools();
  const publicTool = publicTools.find(t => t.id === id || t.name === id);
  if (publicTool) {
    return publicTool;
  }
  
  return null;
}

/**
 * Get all tools owned by a user
 * Returns both user tools and public MCP tools
 */
async function getToolsByOwner(owner) {
  const allTools = [];
  
  // Load user's custom tools
  if (owner) {
    const userTools = await loadUserTools(owner);
    allTools.push(...userTools);
  }
  
  // Load public MCP tools
  const publicTools = await loadPublicTools();
  allTools.push(...publicTools);
  
  return allTools;
}

/**
 * Query tools with filters
 */
async function queryTools({ id, name, description }) {
  // Get all tools (both user and public)
  const publicTools = await loadPublicTools();
  let tools = [...publicTools];
  
  if (id) {
    tools = tools.filter(t => t.id === id || t.name === id);
  }
  
  if (name) {
    const nameLower = name.toLowerCase();
    tools = tools.filter(t => 
      (t.name || "").toLowerCase().includes(nameLower)
    );
  }
  
  if (description) {
    const descLower = description.toLowerCase();
    tools = tools.filter(t => 
      (t.description || "").toLowerCase().includes(descLower)
    );
  }
  
  return tools;
}

module.exports = {
  addTool,
  updateTool,
  deleteTool,
  getToolById,
  getToolsByOwner,
  queryTools
};
