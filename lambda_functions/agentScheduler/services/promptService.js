/**
 * DynamoDB-based Prompt Service for agentScheduler Lambda
 * 
 * Uses Agent_Prompts table:
 * - owner_id (PK): "public" for sample prompts, or user email
 * - agent_id (SK): "any~{prompt_id}" format
 * - prompt_id, prompt_name, prompt (JSON), suitable_modes, metadata, last_mod_date
 */

const crypto = require("crypto");
const {
  DynamoDBClient,
  GetItemCommand,
  PutItemCommand,
  DeleteItemCommand,
  QueryCommand
} = require("@aws-sdk/client-dynamodb");
const { marshall, unmarshall } = require("@aws-sdk/util-dynamodb");

const REGION = process.env.AWS_REGION || "us-east-1";
const PROMPTS_TABLE = process.env.PROMPTS_TABLE || "Agent_Prompts";
const PUBLIC_OWNER = "public";
const DEFAULT_VERSION = "0.1";

const dynamodb = new DynamoDBClient({ region: REGION });

/**
 * Generate a unique prompt ID
 */
function genId() {
  return `pr-${crypto.randomBytes(4).toString("hex")}`;
}

/**
 * Build the agent_id (sort key) from prompt_id
 * Format: "any~{prompt_id}"
 */
function buildAgentId(promptId) {
  return `any~${promptId}`;
}

/**
 * Extract prompt_id from agent_id
 */
function extractPromptIdFromAgentId(agentId) {
  if (!agentId) return null;
  const parts = agentId.split("~");
  return parts.length > 1 ? parts[1] : agentId;
}

/**
 * Convert DynamoDB item to normalized prompt format
 * GraphQL schema expects: id!, owner!, prompt! (AWSJSON), version, created_at, updated_at
 */
function dbItemToPrompt(item, { readOnly = false } = {}) {
  if (!item) return null;
  
  // Parse the prompt JSON field
  let promptContent = {};
  if (item.prompt) {
    if (typeof item.prompt === 'string') {
      try {
        promptContent = JSON.parse(item.prompt);
      } catch (e) {
        console.warn('[promptService] Failed to parse prompt JSON:', e.message);
      }
    } else if (typeof item.prompt === 'object') {
      promptContent = item.prompt;
    }
  }
  
  // Determine the source based on owner_id
  const source = item.owner_id === PUBLIC_OWNER ? 'sample_prompts' : 'my_prompts';
  const isReadOnly = item.owner_id === PUBLIC_OWNER || readOnly;
  
  // Build the prompt content object
  const normalizedPromptContent = {
    title: promptContent.title || item.prompt_name || "",
    topic: promptContent.topic || "",
    usageCount: parseInt(promptContent.usageCount || 0, 10),
    sections: promptContent.sections || [],
    userSections: promptContent.userSections || [],
    humanInputs: promptContent.humanInputs || promptContent.human_inputs || [],
    source: source,
    readOnly: isReadOnly,
    lastModified: item.last_mod_date || new Date().toISOString(),
    ...promptContent
  };
  
  const promptId = item.prompt_id || extractPromptIdFromAgentId(item.agent_id);
  
  return {
    id: promptId,
    owner: item.owner_id === PUBLIC_OWNER ? "" : item.owner_id,
    prompt: normalizedPromptContent,
    version: promptContent.version || DEFAULT_VERSION,
    created_at: promptContent.created_at || item.last_mod_date || new Date().toISOString(),
    updated_at: item.last_mod_date || new Date().toISOString()
  };
}

/**
 * Query prompts from DynamoDB by owner_id
 */
async function queryPromptsByOwner(ownerId) {
  console.log(`[promptService] queryPromptsByOwner: ownerId=${ownerId}`);
  const prompts = [];
  let lastEvaluatedKey;
  
  do {
    const params = {
      TableName: PROMPTS_TABLE,
      KeyConditionExpression: "owner_id = :ownerId AND begins_with(agent_id, :prefix)",
      ExpressionAttributeValues: marshall({
        ":ownerId": ownerId,
        ":prefix": "any~"
      }),
      ExclusiveStartKey: lastEvaluatedKey
    };
    
    const response = await dynamodb.send(new QueryCommand(params));
    console.log(`[promptService] queryPromptsByOwner response: Count=${response.Count}`);
    
    if (response.Items) {
      for (const item of response.Items) {
        const unmarshalled = unmarshall(item);
        const prompt = dbItemToPrompt(unmarshalled, { readOnly: ownerId === PUBLIC_OWNER });
        if (prompt) {
          prompts.push(prompt);
        }
      }
    }
    
    lastEvaluatedKey = response.LastEvaluatedKey;
  } while (lastEvaluatedKey);
  
  return prompts;
}

/**
 * Add a new prompt (user prompts only)
 * Also handles updates - if a prompt with the same ID exists, it will be overwritten
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
  
  // Build the prompt content to store
  const promptToStore = {
    title,
    topic,
    version: data.version || promptContent.version || DEFAULT_VERSION,
    usageCount: promptContent.usageCount || data.usageCount || 0,
    sections: promptContent.sections || data.sections || [],
    userSections: promptContent.userSections || data.userSections || [],
    humanInputs: promptContent.humanInputs || data.humanInputs || [],
    source: 'my_prompts',
    readOnly: false,
    created_at: promptContent.created_at || now,
    ...promptContent
  };
  
  // Prepare DynamoDB item
  const item = {
    owner_id: owner,
    agent_id: buildAgentId(id),
    prompt_id: id,
    prompt_name: title,
    prompt: JSON.stringify(promptToStore),
    suitable_modes: promptContent.suitable_modes || "all",
    metadata: JSON.stringify(promptContent.metadata || {}),
    last_mod_date: now
  };
  
  console.log(`[promptService] addPrompt: putting item to DynamoDB`, JSON.stringify({ owner_id: item.owner_id, agent_id: item.agent_id, prompt_id: item.prompt_id }));
  
  await dynamodb.send(new PutItemCommand({
    TableName: PROMPTS_TABLE,
    Item: marshall(item)
  }));
  
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
  
  const agentId = buildAgentId(id);
  const now = new Date().toISOString();
  
  // First, get the existing prompt
  const getResponse = await dynamodb.send(new GetItemCommand({
    TableName: PROMPTS_TABLE,
    Key: marshall({ owner_id: owner, agent_id: agentId })
  }));
  
  if (!getResponse.Item) {
    return { success: false, id, error: "NOT_FOUND: Prompt not found" };
  }
  
  const existing = unmarshall(getResponse.Item);
  
  // Parse existing prompt content
  let existingPromptContent = {};
  if (existing.prompt) {
    if (typeof existing.prompt === 'string') {
      try {
        existingPromptContent = JSON.parse(existing.prompt);
      } catch (e) {
        console.warn('[promptService] Failed to parse existing prompt JSON:', e.message);
      }
    } else {
      existingPromptContent = existing.prompt;
    }
  }
  
  // Parse new fields if they contain prompt content
  let newPromptContent = {};
  if (fields.prompt) {
    if (typeof fields.prompt === 'string') {
      try {
        newPromptContent = JSON.parse(fields.prompt);
      } catch (e) {
        console.warn('[promptService] Failed to parse new prompt JSON:', e.message);
      }
    } else {
      newPromptContent = fields.prompt;
    }
  }
  
  // Merge prompt content
  const mergedPromptContent = {
    ...existingPromptContent,
    ...newPromptContent,
    ...fields,
    source: 'my_prompts',
    readOnly: false
  };
  delete mergedPromptContent.prompt; // Remove nested prompt field
  
  // Build updated item
  const title = mergedPromptContent.title || fields.title || existing.prompt_name || "Untitled";
  
  const updatedItem = {
    owner_id: owner,
    agent_id: agentId,
    prompt_id: id,
    prompt_name: title,
    prompt: JSON.stringify(mergedPromptContent),
    suitable_modes: mergedPromptContent.suitable_modes || existing.suitable_modes || "all",
    metadata: JSON.stringify(mergedPromptContent.metadata || {}),
    last_mod_date: now
  };
  
  await dynamodb.send(new PutItemCommand({
    TableName: PROMPTS_TABLE,
    Item: marshall(updatedItem)
  }));
  
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
  
  const agentId = buildAgentId(id);
  
  // Check if it exists first
  const getResponse = await dynamodb.send(new GetItemCommand({
    TableName: PROMPTS_TABLE,
    Key: marshall({ owner_id: owner, agent_id: agentId })
  }));
  
  if (!getResponse.Item) {
    return { success: false, id, error: "NOT_FOUND: Prompt not found" };
  }
  
  await dynamodb.send(new DeleteItemCommand({
    TableName: PROMPTS_TABLE,
    Key: marshall({ owner_id: owner, agent_id: agentId })
  }));
  
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
  
  const agentId = buildAgentId(id);
  
  // Search user prompts first if owner provided
  if (owner) {
    try {
      const getResponse = await dynamodb.send(new GetItemCommand({
        TableName: PROMPTS_TABLE,
        Key: marshall({ owner_id: owner, agent_id: agentId })
      }));
      
      if (getResponse.Item) {
        const item = unmarshall(getResponse.Item);
        return dbItemToPrompt(item, { readOnly: false });
      }
    } catch (err) {
      console.warn(`[promptService] Failed to get user prompt ${id}: ${err.message}`);
    }
  }
  
  // Search public prompts
  try {
    const getResponse = await dynamodb.send(new GetItemCommand({
      TableName: PROMPTS_TABLE,
      Key: marshall({ owner_id: PUBLIC_OWNER, agent_id: agentId })
    }));
    
    if (getResponse.Item) {
      const item = unmarshall(getResponse.Item);
      return dbItemToPrompt(item, { readOnly: true });
    }
  } catch (err) {
    console.warn(`[promptService] Failed to get public prompt ${id}: ${err.message}`);
  }
  
  return null;
}

/**
 * List all prompts for an owner
 * Returns both user prompts and public sample prompts
 */
async function listPrompts(owner) {
  console.log(`[promptService] listPrompts called with owner: '${owner}'`);
  const allPrompts = [];
  
  // Load user prompts from DynamoDB
  if (owner) {
    console.log(`[promptService] listPrompts: querying user prompts for owner=${owner}`);
    const userPrompts = await queryPromptsByOwner(owner);
    console.log(`[promptService] listPrompts: loaded ${userPrompts.length} user prompts`);
    allPrompts.push(...userPrompts);
  } else {
    console.warn(`[promptService] listPrompts: No owner provided, skipping user prompts`);
  }
  
  // Load public/sample prompts from DynamoDB
  console.log(`[promptService] listPrompts: querying public prompts`);
  const publicPrompts = await queryPromptsByOwner(PUBLIC_OWNER);
  console.log(`[promptService] listPrompts: loaded ${publicPrompts.length} public prompts`);
  allPrompts.push(...publicPrompts);
  
  console.log(`[promptService] listPrompts: returning ${allPrompts.length} total prompts`);
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
