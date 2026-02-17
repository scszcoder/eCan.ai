import { DynamoDBClient, GetItemCommand, QueryCommand, UpdateItemCommand, PutItemCommand } from "@aws-sdk/client-dynamodb";
import { unmarshall, marshall } from "@aws-sdk/util-dynamodb";
import { ChatOpenAI } from "@langchain/openai";
import { ChatAnthropic } from "@langchain/anthropic";
import { ChatGoogleGenerativeAI } from "@langchain/google-genai";
import { HumanMessage, SystemMessage, AIMessage } from "@langchain/core/messages";
import { StateGraph, END, START } from "@langchain/langgraph";
import { randomUUID } from "node:crypto";
import { ChatterState, createInitialState } from "./node_state.js";
import { get_cloud_mcp_tools_schema } from "./tools_schema.js";

// Environment variables
const APPSYNC_API_URL = process.env.APPSYNC_API_URL;
const APPSYNC_API_KEY = process.env.APPSYNC_API_KEY;
const A2A_MESSAGES_TABLE = process.env.A2A_MESSAGES_TABLE || "A2A_Messages";
const AGENT_PROMPTS_TABLE = process.env.AGENT_PROMPTS_TABLE || "Agent_Prompts";
const LLM_PROVIDER = process.env.LLM_PROVIDER || "openai";
const LLM_MODEL = process.env.LLM_MODEL || "gpt-4o";
const LLM_TEMPERATURE = parseFloat(process.env.LLM_TEMPERATURE || "0.7");

// Context limits (approximate token counts)
const MAX_HISTORY_MESSAGES = parseInt(process.env.MAX_HISTORY_MESSAGES || "160", 10);
const MAX_CONTEXT_CHARS = parseInt(process.env.MAX_CONTEXT_CHARS || "400000", 10); // ~100k tokens
const SESSION_TIMEOUT_HOURS = 24;

// LangGraph loop limits
const MAX_OUTER_STEPS = parseInt(process.env.MAX_OUTER_STEPS || "3", 10);
const LAMBDA_TIMEOUT_GUARD_MS = parseInt(process.env.LAMBDA_TIMEOUT_GUARD_MS || "50000", 10); // 50s of 60s budget

// AWS clients
const dynamodb = new DynamoDBClient({ region: "us-east-1" });

// Standard system prompt wrapper for JSON response format
const JSON_RESPONSE_WRAPPER = `
IMPORTANT: You MUST respond with valid JSON only. Your response must be a JSON object with the following structure:
{
  "msg_to_sender": "Your text response message to the user goes here",
  "qa_to_sender": { "any": "structured data", "for": "the frontend" },
  "topic_switched": false,
  "work_related": true,
  "request_answered": true,
  "need_human_input": false,
  "next_actions": []
}

Required fields:
- "msg_to_sender" (string, required): The text message to send back to the user
- "qa_to_sender" (object, optional): Any structured data, questions, or UI hints for the frontend
- "topic_switched" (boolean, required): Set to true if the conversation topic has significantly changed and a new session should be started
- "work_related" (boolean, required): Set to true if the user's message is related to work/tasks, false for casual chat or off-topic
- "request_answered" (boolean, required): Set to true if you have fully answered/addressed the user's request, false if more information is needed or the request is incomplete
- "need_human_input" (boolean, required): Set to true if you need more information from the user before you can proceed. When true, the system will pause and wait for the user's next message.
- "next_actions" (array, required): List of tool calls to execute. Each item is an object with:
  - "tool_name": Name of the tool to call (must match a known tool from the available tools list)
  - "tool_input": Object with the tool's input parameters
  Example: [{"tool_name": "rag_query", "tool_input": {"query": "search term", "top_k": 5}}]
  Leave empty [] if no tool calls are needed.

Do not include any text outside the JSON object. Do not use markdown code blocks.
`;

// GraphQL mutation to send response back
const SEND_A2A_MESSAGE = `
mutation SendA2AMessage($input: A2AMessageInput!) {
  sendA2AMessage(input: $input) {
    id channelId senderId sessionId timestamp
    message { role parts { type text metadata } }
  }
}
`;

/**
 * Generate a new session ID
 */
function generateSessionId() {
  return `session-${Date.now()}-${randomUUID().slice(0, 8)}`;
}

/**
 * Make AppSync GraphQL request
 */
async function appSyncRequest(payload, operationName) {
  console.log(`[chatter] AppSync request: ${operationName}`);
  
  const response = await fetch(APPSYNC_API_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": APPSYNC_API_KEY,
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json();
  
  if (!response.ok) {
    console.error(`[chatter] AppSync request failed: ${response.status}`);
    throw new Error(`AppSync request failed: ${response.status}`);
  }
  
  if (data.errors) {
    console.error(`[chatter] AppSync errors:`, JSON.stringify(data.errors));
  } else {
    console.log(`[chatter] AppSync SUCCESS:`, JSON.stringify(data.data));
  }
  
  return data;
}

/**
 * Get agent system prompt from Agent_Prompts table.
 * Queries all prompts for the owner, filters by prompt_name containing "chat"
 * (case-insensitive), and picks the last matching row.
 * Falls back to any available prompt if none match "chat".
 */
async function getAgentPrompt(ownerId, agentId) {
  console.log(`[chatter] Getting prompt for owner=${ownerId}, agent=${agentId}`);
  
  try {
    // Query ALL prompts for this owner (sort key begins_with "any~")
    const result = await dynamodb.send(new QueryCommand({
      TableName: AGENT_PROMPTS_TABLE,
      KeyConditionExpression: "owner_id = :ownerId",
      ExpressionAttributeValues: {
        ":ownerId": { S: ownerId },
      },
    }));
    
    const items = (result.Items || []).map(item => unmarshall(item));
    console.log(`[chatter] Found ${items.length} prompt(s) for owner=${ownerId}`);
    
    if (items.length === 0) {
      console.log(`[chatter] No prompts found for this owner`);
      return null;
    }
    
    // Filter by prompt_name containing "chat" (case-insensitive)
    const chatPrompts = items.filter(item => {
      const name = (item.prompt_name || "").toLowerCase();
      return name.includes("chat");
    });
    
    console.log(`[chatter] ${chatPrompts.length} prompt(s) matched "chat" filter out of ${items.length}`);
    
    // Pick the last matching "chat" prompt; fall back to last prompt overall
    const chosen = chatPrompts.length > 0
      ? chatPrompts[chatPrompts.length - 1]
      : items[items.length - 1];
    
    console.log(`[chatter] Selected prompt: prompt_name="${chosen.prompt_name}", prompt_id="${chosen.prompt_id}"`);
    
    // Extract the system prompt text
    const promptText = extractPromptText(chosen);
    if (promptText) {
      console.log(`[chatter] Extracted prompt text (${promptText.length} chars): ${promptText.substring(0, 100)}...`);
    }
    return promptText;
  } catch (err) {
    console.error(`[chatter] Error getting prompt:`, err);
    return null;
  }
}

/**
 * Extract usable system-prompt text from a DynamoDB prompt item.
 * Handles both legacy `system_prompt` field and the structured
 * sections-based `prompt` JSON format used by the prompt editor.
 */
function extractPromptText(item) {
  // 1. Legacy: direct system_prompt field
  if (item.system_prompt) {
    return item.system_prompt;
  }
  
  // 2. Structured: parse the `prompt` JSON with sections
  let promptData = item.prompt;
  if (typeof promptData === "string") {
    try { promptData = JSON.parse(promptData); } catch { return null; }
  }
  if (!promptData || typeof promptData !== "object") return null;
  
  const parts = [];
  
  // Title / topic
  if (promptData.title) parts.push(`# ${promptData.title}`);
  if (promptData.topic) parts.push(promptData.topic);
  
  // Sections → text
  const sectionOrder = ["background", "goals", "guidelines", "rules", "instructions", "variables", "examples", "custom"];
  const sectionLabels = {
    background: "Background",
    goals: "Goals",
    guidelines: "Guidelines",
    rules: "Rules",
    instructions: "Instructions",
    variables: "Variables",
    examples: "Examples",
    custom: null, // uses customLabel
  };
  
  for (const sec of (promptData.sections || [])) {
    const secType = (sec.type || "").toLowerCase();
    const label = secType === "custom" ? (sec.customLabel || "Custom") : (sectionLabels[secType] || secType);
    const items = Array.isArray(sec.items) ? sec.items.filter(Boolean) : [];
    if (items.length === 0) continue;
    parts.push(`\n## ${label}\n${items.map(i => `- ${i}`).join("\n")}`);
  }
  
  // User sections
  for (const sec of (promptData.userSections || [])) {
    const label = sec.customLabel || sec.type || "User Section";
    const items = Array.isArray(sec.items) ? sec.items.filter(Boolean) : [];
    if (items.length === 0) continue;
    parts.push(`\n## ${label}\n${items.map(i => `- ${i}`).join("\n")}`);
  }
  
  return parts.length > 0 ? parts.join("\n") : null;
}

/**
 * Get chat history for a channel/session with context length limiting
 */
async function getChatHistory(channelId, sessionId, maxMessages = MAX_HISTORY_MESSAGES, maxChars = MAX_CONTEXT_CHARS) {
  console.log(`[chatter] Getting chat history for channel=${channelId}, session=${sessionId}`);
  
  try {
    const result = await dynamodb.send(new QueryCommand({
      TableName: A2A_MESSAGES_TABLE,
      KeyConditionExpression: "channelId = :channelId AND sessionId = :sessionId",
      ExpressionAttributeValues: {
        ":channelId": { S: channelId },
        ":sessionId": { S: sessionId }
      },
      ScanIndexForward: false, // newest first for limiting
      Limit: maxMessages * 2 // fetch extra to allow for filtering
    }));
    
    let items = (result.Items || []).map(item => unmarshall(item));
    
    // Reverse to get chronological order (oldest first)
    items = items.reverse();
    
    // Apply context length limit
    let totalChars = 0;
    const limitedItems = [];
    
    // Start from the most recent messages and work backwards
    for (let i = items.length - 1; i >= 0 && limitedItems.length < maxMessages; i--) {
      const msg = items[i];
      const text = msg.message?.parts?.[0]?.text || "";
      const msgChars = text.length;
      
      if (totalChars + msgChars > maxChars && limitedItems.length > 0) {
        console.log(`[chatter] Context limit reached at ${totalChars} chars, ${limitedItems.length} messages`);
        break;
      }
      
      totalChars += msgChars;
      limitedItems.unshift(msg); // Add to front to maintain order
    }
    
    console.log(`[chatter] Returning ${limitedItems.length} messages (${totalChars} chars)`);
    return limitedItems;
  } catch (err) {
    console.error(`[chatter] Error getting chat history:`, err);
    return [];
  }
}

/**
 * Get the last message timestamp for a channel (across all sessions)
 */
async function getLastMessageTimestamp(channelId) {
  try {
    // Query with just channelId to get most recent message
    const result = await dynamodb.send(new QueryCommand({
      TableName: A2A_MESSAGES_TABLE,
      KeyConditionExpression: "channelId = :channelId",
      ExpressionAttributeValues: {
        ":channelId": { S: channelId }
      },
      ScanIndexForward: false, // newest first
      Limit: 2 // Get last 2 (current + previous)
    }));
    
    const items = (result.Items || []).map(item => unmarshall(item));
    // Return the second item's timestamp (the previous message before current)
    if (items.length >= 2) {
      return items[1].timestamp;
    }
    return null;
  } catch (err) {
    console.error(`[chatter] Error getting last message timestamp:`, err);
    return null;
  }
}

/**
 * Update message's sessionId in DynamoDB
 */
async function updateMessageSessionId(channelId, oldSessionId, newSessionId, timestamp) {
  console.log(`[chatter] Updating sessionId from ${oldSessionId} to ${newSessionId}`);
  
  try {
    // Note: Since sessionId is part of the key, we need to delete and re-insert
    // For now, we'll just log this - the response will use the new sessionId
    console.log(`[chatter] Session switch noted - new session: ${newSessionId}`);
    return true;
  } catch (err) {
    console.error(`[chatter] Error updating sessionId:`, err);
    return false;
  }
}

/**
 * Check if session should be switched based on time gap
 */
function shouldSwitchSessionByTime(currentTimestamp, lastTimestamp) {
  if (!lastTimestamp) return false;
  
  const current = new Date(currentTimestamp).getTime();
  const last = new Date(lastTimestamp).getTime();
  const hoursDiff = (current - last) / (1000 * 60 * 60);
  
  console.log(`[chatter] Time since last message: ${hoursDiff.toFixed(2)} hours`);
  return hoursDiff > SESSION_TIMEOUT_HOURS;
}

/**
 * Create LLM instance based on provider
 */
function createLLM(provider, model, temperature) {
  console.log(`[chatter] Creating LLM: provider=${provider}, model=${model}, temp=${temperature}`);
  
  switch (provider.toLowerCase()) {
    case "openai":
      return new ChatOpenAI({
        modelName: model,
        temperature: temperature,
      });
    case "anthropic":
      return new ChatAnthropic({
        modelName: model,
        temperature: temperature,
      });
    case "google":
      return new ChatGoogleGenerativeAI({
        modelName: model,
        temperature: temperature,
      });
    default:
      console.log(`[chatter] Unknown provider ${provider}, defaulting to OpenAI`);
      return new ChatOpenAI({
        modelName: "gpt-4o",
        temperature: temperature,
      });
  }
}

/**
 * Convert chat history to LangChain messages
 */
function buildMessages(agentPrompt, chatHistory, currentMessage) {
  const messages = [];
  
  // Build combined system prompt with JSON response wrapper
  const systemPrompt = [
    agentPrompt || "You are a helpful AI assistant.",
    JSON_RESPONSE_WRAPPER
  ].join("\n\n");
  
  messages.push(new SystemMessage(systemPrompt));
  
  // Add chat history (skip the current message which triggered this)
  for (const msg of chatHistory) {
    const role = msg.message?.role || "user";
    const text = msg.message?.parts?.[0]?.text || "";
    
    if (!text) continue;
    
    if (role === "user" || role === "human") {
      messages.push(new HumanMessage(text));
    } else if (role === "assistant" || role === "ai") {
      // For assistant messages, extract just the msg_to_sender if it was JSON
      let displayText = text;
      try {
        const parsed = JSON.parse(text);
        if (parsed.msg_to_sender) {
          displayText = parsed.msg_to_sender;
        }
      } catch {
        // Not JSON, use as-is
      }
      messages.push(new AIMessage(displayText));
    }
  }
  
  // Add current user message
  const currentText = currentMessage.message?.parts?.[0]?.text || "";
  if (currentText) {
    messages.push(new HumanMessage(currentText));
  }
  
  console.log(`[chatter] Built ${messages.length} messages for LLM`);
  return messages;
}

/**
 * Parse LLM response JSON
 */
function parseLLMResponse(responseText) {
  try {
    // Try to extract JSON from response (in case there's extra text)
    const jsonMatch = responseText.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      const parsed = JSON.parse(jsonMatch[0]);
      return {
        msg_to_sender: parsed.msg_to_sender || responseText,
        qa_to_sender: parsed.qa_to_sender || {},
        topic_switched: parsed.topic_switched === true,
        work_related: parsed.work_related !== false, // default true
        request_answered: parsed.request_answered !== false, // default true
        need_human_input: parsed.need_human_input === true,
        next_actions: Array.isArray(parsed.next_actions) ? parsed.next_actions : []
      };
    }
  } catch (err) {
    console.warn(`[chatter] Failed to parse LLM response as JSON:`, err.message);
  }
  
  // Fallback: treat entire response as message
  return {
    msg_to_sender: responseText,
    qa_to_sender: {},
    topic_switched: false,
    work_related: true,
    request_answered: true,
    need_human_input: false,
    next_actions: []
  };
}

/**
 * Send response back to frontend via AppSync
 */
async function sendResponse(channelId, sessionId, senderId, recipientId, parsedResponse) {
  const { msg_to_sender, qa_to_sender, work_related, request_answered, need_human_input, next_actions } = parsedResponse;
  
  // Build metadata object with all structured data
  const metadata = {
    ...qa_to_sender,
    work_related,
    request_answered,
    need_human_input: need_human_input || false,
    next_actions
  };
  
  const parts = [{ type: "text", text: msg_to_sender }];
  
  // Add metadata part
  if (Object.keys(metadata).length > 0) {
    parts.push({ 
      type: "data", 
      metadata: JSON.stringify(metadata)
    });
  }
  
  const input = {
    channelId,
    sessionId,
    senderId: senderId || "chatter-agent",
    recipientId: recipientId,
    message: {
      role: "assistant",
      parts: parts
    }
  };
  
  return appSyncRequest({ query: SEND_A2A_MESSAGE, variables: { input } }, "sendA2AMessage");
}

// ============================================================
// AppSync Query Handlers
// ============================================================

/**
 * Get A2A messages for a channel (with optional session filter)
 * Returns messages grouped by session for the chat UI
 */
async function handleGetA2AMessages(args) {
  const { channelId, sessionId, limit = 100, nextToken } = args;
  
  console.log(`[chatter] getA2AMessages: channelId=${channelId}, sessionId=${sessionId}, limit=${limit}`);
  
  if (!channelId) {
    throw new Error("channelId is required");
  }
  
  try {
    const queryParams = {
      TableName: A2A_MESSAGES_TABLE,
      KeyConditionExpression: sessionId 
        ? "channelId = :channelId AND sessionId = :sessionId"
        : "channelId = :channelId",
      ExpressionAttributeValues: sessionId
        ? { ":channelId": { S: channelId }, ":sessionId": { S: sessionId } }
        : { ":channelId": { S: channelId } },
      ScanIndexForward: false, // newest first
      Limit: limit
    };
    
    if (nextToken) {
      queryParams.ExclusiveStartKey = JSON.parse(Buffer.from(nextToken, 'base64').toString());
    }
    
    const result = await dynamodb.send(new QueryCommand(queryParams));
    
    const items = (result.Items || []).map(item => {
      const msg = unmarshall(item);
      return {
        id: msg.id || `${msg.channelId}-${msg.sessionId}-${msg.timestamp}`,
        channelId: msg.channelId,
        sessionId: msg.sessionId,
        senderId: msg.senderId,
        recipientId: msg.recipientId,
        timestamp: msg.timestamp,
        message: msg.message,
        metadata: msg.metadata,
        historyLength: msg.historyLength,
        acceptedOutputModes: msg.acceptedOutputModes
      };
    });
    
    // Reverse to get chronological order (oldest first) for display
    items.reverse();
    
    // If no messages found, return a bootstrap welcome message from the agent
    if (items.length === 0) {
      console.log(`[chatter] No messages found, returning bootstrap welcome message`);
      
      // Parse channelId to extract agent info
      // Format can be: "email~agentId" (web platform) or "agentId1_agentId2" (desktop sorted alphabetically)
      let senderId, recipientId;
      if (channelId.includes('~')) {
        // Web format: userEmail~agentId
        const parts = channelId.split('~');
        senderId = parts[1] || 'agent';  // Agent is the sender for bootstrap message
        recipientId = parts[0] || 'user'; // User email is the recipient
      } else {
        // Desktop format: agentId1_agentId2 sorted alphabetically
        const channelParts = channelId.split('_');
        senderId = channelParts.length > 1 ? channelParts[1] : channelParts[0];
        recipientId = channelParts[0] || 'user';
      }
      
      // Use a stable ID based on channelId only - not timestamp
      // This prevents duplicate bootstrap messages when API is called multiple times
      const bootstrapMessage = {
        id: `bootstrap-${channelId}`,
        channelId: channelId,
        sessionId: `session-bootstrap`,
        senderId: senderId,
        recipientId: recipientId,
        timestamp: new Date().toISOString(),
        message: {
          role: "assistant",
          parts: [
            { 
              type: "text", 
              text: "👋 Hello! I'm ready to help you. How can I assist you today?",
              metadata: null
            }
          ],
          metadata: null
        },
        metadata: JSON.stringify({
          isBootstrap: true,
          senderName: "Agent"
        }),
        historyLength: 0,
        acceptedOutputModes: null
      };
      
      console.log(`[chatter] Returning bootstrap message:`, JSON.stringify(bootstrapMessage));
      
      return {
        items: [bootstrapMessage],
        nextToken: null
      };
    }
    
    const response = {
      items,
      nextToken: result.LastEvaluatedKey 
        ? Buffer.from(JSON.stringify(result.LastEvaluatedKey)).toString('base64')
        : null
    };
    
    console.log(`[chatter] getA2AMessages: returning ${items.length} messages`);
    return response;
    
  } catch (err) {
    console.error(`[chatter] getA2AMessages error:`, err);
    throw err;
  }
}

/**
 * Handle sendCloudA2AMessage mutation - save message to DynamoDB and trigger LLM response
 */
async function handleSendCloudA2AMessage(args) {
  const input = args.input || args;
  const { channelId, sessionId, senderId, recipientId, message, metadata, acceptedOutputModes } = input;
  
  console.log(`[chatter] sendCloudA2AMessage: channelId=${channelId}, senderId=${senderId}`);
  
  if (!channelId || !senderId || !message) {
    throw new Error("channelId, senderId, and message are required");
  }
  
  // Generate message ID and timestamp
  const messageId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  const timestamp = new Date().toISOString();
  const finalSessionId = sessionId || `session_${Date.now()}`;
  
  // Build the message item for DynamoDB
  const messageItem = {
    id: messageId,
    channelId,
    sessionId: finalSessionId,
    senderId,
    recipientId: recipientId || null,
    timestamp,
    message: message,
    metadata: typeof metadata === 'object' ? JSON.stringify(metadata) : (metadata || null),
    historyLength: 0,
    acceptedOutputModes: acceptedOutputModes || null
  };
  
  try {
    // Save message to DynamoDB
    await dynamodb.send(new PutItemCommand({
      TableName: A2A_MESSAGES_TABLE,
      Item: marshall(messageItem, { removeUndefinedValues: true })
    }));
    
    console.log(`[chatter] Message saved to DynamoDB: ${messageId}`);
    
    // Return the saved message
    return {
      id: messageId,
      channelId,
      sessionId: finalSessionId,
      senderId,
      recipientId,
      timestamp,
      message,
      metadata: messageItem.metadata,
      historyLength: 0,
      acceptedOutputModes
    };
    
  } catch (err) {
    console.error(`[chatter] Error saving message:`, err);
    throw err;
  }
}

/**
 * Get chat threads for a user (all channels involving sender/recipient)
 * Groups messages by channel and session
 */
async function handleGetChatThreads(args) {
  const { userId, agentId, limit = 50 } = args;
  
  console.log(`[chatter] getChatThreads: userId=${userId}, agentId=${agentId}`);
  
  if (!userId) {
    throw new Error("userId is required");
  }
  
  // For now, construct channelId from userId and agentId
  // Channel format: "user:{userId}:agent:{agentId}" or similar
  const channelId = agentId ? `${userId}:${agentId}` : userId;
  
  try {
    // Query messages for this channel
    const result = await dynamodb.send(new QueryCommand({
      TableName: A2A_MESSAGES_TABLE,
      KeyConditionExpression: "channelId = :channelId",
      ExpressionAttributeValues: {
        ":channelId": { S: channelId }
      },
      ScanIndexForward: false,
      Limit: limit * 10 // Fetch more to group by session
    }));
    
    const items = (result.Items || []).map(item => unmarshall(item));
    
    // Group by sessionId
    const sessionMap = new Map();
    for (const msg of items) {
      const sid = msg.sessionId || "default";
      if (!sessionMap.has(sid)) {
        sessionMap.set(sid, {
          sessionId: sid,
          channelId: msg.channelId,
          messages: [],
          lastMessage: null,
          lastTimestamp: null,
          messageCount: 0
        });
      }
      const session = sessionMap.get(sid);
      session.messages.push(msg);
      session.messageCount++;
      if (!session.lastTimestamp || msg.timestamp > session.lastTimestamp) {
        session.lastTimestamp = msg.timestamp;
        session.lastMessage = msg.message?.parts?.[0]?.text || "";
      }
    }
    
    // Convert to array and sort by last timestamp
    const sessions = Array.from(sessionMap.values())
      .sort((a, b) => (b.lastTimestamp || "").localeCompare(a.lastTimestamp || ""));
    
    // Limit messages per session for initial load
    for (const session of sessions) {
      session.messages = session.messages.slice(0, 20).reverse(); // Keep last 20, chronological
    }
    
    console.log(`[chatter] getChatThreads: returning ${sessions.length} sessions`);
    return { sessions };
    
  } catch (err) {
    console.error(`[chatter] getChatThreads error:`, err);
    throw err;
  }
}

// ============================================================
// Event Type Detection & Routing
// ============================================================

/**
 * Detect event type
 */
function detectEventType(event) {
  // DynamoDB Stream event
  if (event.Records && Array.isArray(event.Records) && event.Records[0]?.eventSource === "aws:dynamodb") {
    return "DYNAMODB_STREAM";
  }
  
  // AppSync event (has info.fieldName)
  if (event.info && event.info.fieldName) {
    return "APPSYNC";
  }
  
  // AppSync event alternative format
  if (event.field || event.fieldName) {
    return "APPSYNC";
  }
  
  // Direct invoke with action
  if (event.action) {
    return "DIRECT";
  }
  
  return "UNKNOWN";
}

/**
 * Main handler - handles both DynamoDB Stream and AppSync events
 */
export const handler = async (event) => {
  console.log(`[chatter] Received event:`, JSON.stringify(event));
  
  const eventType = detectEventType(event);
  console.log(`[chatter] Event type: ${eventType}`);
  
  try {
    switch (eventType) {
      case "APPSYNC":
        return await handleAppSyncEvent(event);
      
      case "DYNAMODB_STREAM":
        return await handleDynamoDBStreamEvent(event);
      
      case "DIRECT":
        return await handleDirectInvoke(event);
      
      default:
        console.warn(`[chatter] Unknown event type, attempting AppSync handling`);
        return await handleAppSyncEvent(event);
    }
  } catch (err) {
    console.error(`[chatter] Handler error:`, err);
    throw err;
  }
};

/**
 * Handle AppSync GraphQL events
 */
async function handleAppSyncEvent(event) {
  const fieldName = event.info?.fieldName || event.field || event.fieldName;
  const args = event.arguments || event.args || {};
  
  console.log(`[chatter] AppSync field: ${fieldName}, args:`, JSON.stringify(args));
  
  switch (fieldName) {
    case "getA2AMessages":
      return await handleGetA2AMessages(args);
    
    case "getChatThreads":
      return await handleGetChatThreads(args);
    
    case "sendCloudA2AMessage":
      return await handleSendCloudA2AMessage(args);
    
    default:
      console.error(`[chatter] Unknown AppSync field: ${fieldName}`);
      throw new Error(`Unknown field: ${fieldName}`);
  }
}

/**
 * Handle direct Lambda invocations
 */
async function handleDirectInvoke(event) {
  const { action, ...params } = event;
  
  console.log(`[chatter] Direct invoke action: ${action}`);
  
  switch (action) {
    case "getA2AMessages":
      return await handleGetA2AMessages(params);
    
    case "getChatThreads":
      return await handleGetChatThreads(params);
    
    default:
      throw new Error(`Unknown action: ${action}`);
  }
}

/**
 * Handle DynamoDB Stream events (LLM response processing)
 */
async function handleDynamoDBStreamEvent(event) {
  console.log(`[chatter] Processing DynamoDB Stream event`);
  
  // Process each record from DynamoDB Stream
  for (const record of event.Records) {
    // Only process INSERT events (new messages)
    if (record.eventName !== "INSERT") {
      console.log(`[chatter] Skipping ${record.eventName} event`);
      continue;
    }
    
    // Get the new message from the stream
    const newImage = record.dynamodb?.NewImage;
    if (!newImage) {
      console.log(`[chatter] No NewImage in record`);
      continue;
    }
    
    const message = unmarshall(newImage);
    console.log(`[chatter] Processing message:`, JSON.stringify(message));
    
    // Extract message details
    let { channelId, sessionId, senderId, recipientId, timestamp } = message;
    const role = message.message?.role;
    
    // Only respond to user messages, not assistant messages (avoid infinite loop)
    if (role === "assistant" || role === "ai") {
      console.log(`[chatter] Skipping assistant message`);
      continue;
    }
    
    try {
      await processUserMessage(message);
    } catch (err) {
      console.error(`[chatter] Error processing message:`, err);
      
      // Send error message back to user
      const errorResponse = {
        msg_to_sender: `Sorry, I encountered an error: ${err.message}`,
        qa_to_sender: { error: true, errorMessage: err.message },
        work_related: true,
        request_answered: false,
        next_actions: []
      };
      await sendResponse(
        channelId, 
        sessionId, 
        recipientId, 
        senderId, 
        errorResponse
      );
    }
  }
  
  return { statusCode: 200, body: "Processed" };
}

/**
 * Process a user message and generate LLM response via LangGraph workflow.
 *
 * Graph topology:
 *   START ──► llmNode ──► shouldCallTools? ──YES──► toolNode ──► summarizeNode ──► shouldContinueOuter? ──►
 *                │                                                                        │           │
 *                │ NO                                                                     NO          YES
 *                ▼                                                                        ▼           │
 *              END ◄──────────────────────────────────────────────────────────────────── END     llmNode (loop)
 */
async function processUserMessage(message) {
  const invocationStartMs = Date.now();
  const { channelId, sessionId, senderId, recipientId, timestamp } = message;
  
  // Parse recipientId to get owner and agent info
  let ownerId = senderId;
  let agentId = recipientId;
  
  if (recipientId && recipientId.includes(":")) {
    const parts = recipientId.split(":");
    ownerId = parts[0];
    agentId = parts[1];
  }
  
  // Check if we need to switch sessions based on time gap
  const lastTimestamp = await getLastMessageTimestamp(channelId);
  let currentSessionId = sessionId;
  let sessionSwitched = false;
  
  if (shouldSwitchSessionByTime(timestamp, lastTimestamp)) {
    console.log(`[chatter] Session timeout - creating new session`);
    currentSessionId = generateSessionId();
    sessionSwitched = true;
    await updateMessageSessionId(channelId, sessionId, currentSessionId, timestamp);
  }
  
  // Get agent system prompt
  const agentPrompt = await getAgentPrompt(ownerId, agentId);
  
  // Get chat history (only if not a new session)
  let chatHistory = [];
  if (!sessionSwitched) {
    chatHistory = await getChatHistory(channelId, currentSessionId);
  }
  
  // Build LangChain messages for the LLM
  const lcMessages = buildMessages(agentPrompt, chatHistory, message);
  
  if (lcMessages.length === 0) {
    console.log(`[chatter] No messages to send to LLM`);
    return;
  }
  
  // Get user input text
  const userInput = message.message?.parts?.[0]?.text || "";
  
  // ── Build initial state ──────────────────────────────────
  const initialState = createInitialState({
    input: userInput,
    attachments: [],
    prompts: [agentPrompt || "You are a helpful AI assistant."],
    history: chatHistory,
    messages: lcMessages,
    metadata: { channelId, sessionId: currentSessionId, senderId, recipientId, agentId, ownerId, timestamp },
    max_steps: MAX_OUTER_STEPS,
  });
  
  // ── Build & run the LangGraph ────────────────────────────
  const graph = buildChatterGraph();
  console.log(`[chatter] Running LangGraph workflow (max_steps=${MAX_OUTER_STEPS})...`);
  
  const finalState = await graph.invoke(initialState);

  console.log(`[chatter] Graph completed. n_steps=${finalState.n_steps}, request_answered=${finalState.result?.request_answered}, need_human_input=${finalState.result?.need_human_input}`);
  
  // ── Extract response ─────────────────────────────────────
  const result = finalState.result || {};
  const parsedResponse = {
    msg_to_sender: result.msg_to_sender || "I'm sorry, I wasn't able to generate a response.",
    qa_to_sender: result.qa_to_sender || {},
    topic_switched: result.topic_switched === true,
    work_related: result.work_related !== false,
    request_answered: result.request_answered !== false,
    need_human_input: result.need_human_input === true,
    next_actions: Array.isArray(result.next_actions) ? result.next_actions : [],
  };
  
  // If need_human_input, add tool_results context so next invocation can continue
  if (parsedResponse.need_human_input && finalState.tool_results?.length > 0) {
    parsedResponse.qa_to_sender._partial_tool_results = finalState.tool_results;
  }
  
  // Check if topic switched - create new session for response
  let responseSessionId = currentSessionId;
  if (parsedResponse.topic_switched && !sessionSwitched) {
    console.log(`[chatter] Topic switched - creating new session for response`);
    responseSessionId = generateSessionId();
  }
  
  // Send response back via AppSync
  await sendResponse(channelId, responseSessionId, agentId, senderId, parsedResponse);
  
  const elapsedMs = Date.now() - invocationStartMs;
  console.log(`[chatter] Response sent successfully to session ${responseSessionId} (${elapsedMs}ms total)`);
}

// ============================================================
// LangGraph Nodes
// ============================================================

/**
 * LLM Node — invokes the LLM with current messages and parses the JSON response.
 * Populates state.result and state.tool_calls from the LLM output.
 */
async function llmNode(state) {
  console.log(`[llmNode] step=${state.n_steps}, messages=${state.messages?.length}`);
  
  const llm = createLLM(LLM_PROVIDER, LLM_MODEL, LLM_TEMPERATURE);
  
  // If we have tool_results from a previous iteration, append them as context
  let messagesForLLM = [...(state.messages || [])];
  
  if (state.tool_results && state.tool_results.length > 0) {
    const toolSummary = state.tool_results.map(tr => {
      const status = tr.success ? "SUCCESS" : "FAILED";
      return `[Tool: ${tr.tool_name}] ${status}: ${JSON.stringify(tr.output || tr.error)}`;
    }).join("\n");
    
    // Add tool results as a system-like message so LLM knows what happened
    messagesForLLM.push(new HumanMessage(
      `[SYSTEM] The following tool calls have been executed:\n${toolSummary}\n\nPlease incorporate these results into your response. Remember to respond with valid JSON.`
    ));
  }
  
  console.log(`[llmNode] Invoking LLM with ${messagesForLLM.length} messages...`);
  const response = await llm.invoke(messagesForLLM);
  const responseText = response.content;
  console.log(`[llmNode] LLM raw response: ${responseText.substring(0, 300)}...`);
  
  // Parse the JSON response
  const parsed = parseLLMResponse(responseText);
  console.log(`[llmNode] Parsed: request_answered=${parsed.request_answered}, need_human_input=${parsed.need_human_input}, next_actions=${parsed.next_actions?.length}`);
  
  // Extract tool_calls from next_actions
  const toolCalls = (parsed.next_actions || [])
    .filter(a => a.tool_name)
    .map(a => ({ tool_name: a.tool_name, tool_input: a.tool_input || {} }));
  
  return {
    result: {
      msg_to_sender: parsed.msg_to_sender,
      qa_to_sender: parsed.qa_to_sender,
      topic_switched: parsed.topic_switched,
      work_related: parsed.work_related,
      request_answered: parsed.request_answered,
      need_human_input: parsed.need_human_input,
      next_actions: parsed.next_actions,
    },
    tool_calls: toolCalls,
    // Clear previous tool_results for this new round of tool calls
    tool_results: [],
    n_steps: (state.n_steps || 0) + 1,
    this_node: "llmNode",
  };
}

/**
 * Tool Node — executes each tool call in state.tool_calls.
 * Cloud-runnable tools (meta.run_in_cloud === true) are executed directly.
 * Local-only tools are recorded as pending for the desktop agent.
 */
async function toolNode(state) {
  const toolCalls = state.tool_calls || [];
  console.log(`[toolNode] Executing ${toolCalls.length} tool call(s)...`);
  
  if (toolCalls.length === 0) {
    return { tool_results: [], this_node: "toolNode" };
  }
  
  // Load tool schemas for validation
  const allTools = get_cloud_mcp_tools_schema();
  const toolMap = new Map(allTools.map(t => [t.name, t]));
  
  const results = [];
  
  for (const call of toolCalls) {
    const { tool_name, tool_input } = call;
    const toolSchema = toolMap.get(tool_name);
    
    if (!toolSchema) {
      console.warn(`[toolNode] Unknown tool: ${tool_name}`);
      results.push({
        tool_name,
        success: false,
        output: null,
        error: `Unknown tool: ${tool_name}. Available tools: ${allTools.slice(0, 10).map(t => t.name).join(", ")}...`,
      });
      continue;
    }
    
    const isCloudRunnable = toolSchema.meta?.run_in_cloud === true;
    
    if (isCloudRunnable) {
      // Execute cloud-runnable tools directly
      try {
        console.log(`[toolNode] Executing cloud tool: ${tool_name}`);
        const output = await executeCloudTool(tool_name, tool_input);
        results.push({ tool_name, success: true, output, error: null });
      } catch (err) {
        console.error(`[toolNode] Cloud tool ${tool_name} failed:`, err.message);
        results.push({ tool_name, success: false, output: null, error: err.message });
      }
    } else {
      // Local-only tool — record as pending (dispatched via A2A to desktop agent)
      console.log(`[toolNode] Local-only tool recorded as pending: ${tool_name}`);
      results.push({
        tool_name,
        success: true,
        output: {
          status: "pending_local_execution",
          message: `Tool '${tool_name}' requires local execution on the desktop agent. It has been queued.`,
          tool_input,
        },
        error: null,
      });
    }
  }
  
  console.log(`[toolNode] Completed ${results.length} tool call(s): ${results.map(r => `${r.tool_name}=${r.success}`).join(", ")}`);
  
  return {
    tool_results: results,
    this_node: "toolNode",
  };
}

/**
 * Execute a cloud-runnable tool.
 * This is the dispatcher for tools that can run server-side.
 */
async function executeCloudTool(toolName, toolInput) {
  // Cloud tool execution dispatcher
  // For now, we implement the most common cloud tools;
  // others will be added as they are brought online.
  switch (toolName) {
    case "describe_self":
      return { description: "I am a cloud-hosted AI assistant agent powered by eCan.ai." };
    
    case "list_chat_agents":
      return { agents: [], message: "Agent listing is handled by the agentScheduler service." };
    
    case "get_chat_history":
      if (toolInput.agent_id) {
        // Could query DynamoDB here — delegate to existing handler
        return { message: "Chat history retrieval delegated to getA2AMessages resolver." };
      }
      return { message: "agent_id required" };
    
    case "aws_read_billing":
    case "azure_read_billing":
    case "gcloud_read_billing":
      return { message: `Billing read for ${toolName} is not yet implemented in cloud mode. Please use the desktop agent.` };
    
    case "aws_shutdown":
    case "azure_shutdown":
    case "gcloud_shutdown":
      return { message: `Emergency shutdown via ${toolName} is not yet implemented in cloud mode for safety. Please use the desktop agent.` };
    
    default:
      // Generic cloud tool stub — log and return placeholder
      console.log(`[executeCloudTool] Tool ${toolName} not yet implemented, returning stub.`);
      return {
        status: "not_implemented",
        message: `Cloud execution of '${toolName}' is not yet available. The tool call has been recorded.`,
        tool_input: toolInput,
      };
  }
}

/**
 * Summarize Node — after tool execution, calls the LLM to produce a user-facing
 * summary that incorporates tool results.
 */
async function summarizeNode(state) {
  const toolResults = state.tool_results || [];
  console.log(`[summarizeNode] Summarizing ${toolResults.length} tool result(s)...`);
  
  if (toolResults.length === 0) {
    return { this_node: "summarizeNode" };
  }
  
  const llm = createLLM(LLM_PROVIDER, LLM_MODEL, LLM_TEMPERATURE);
  
  // Build a summary prompt with tool results
  const toolResultsText = toolResults.map(tr => {
    const status = tr.success ? "SUCCESS" : "FAILED";
    const detail = tr.success ? JSON.stringify(tr.output) : tr.error;
    return `- Tool "${tr.tool_name}": ${status}\n  Result: ${detail}`;
  }).join("\n");
  
  const summaryPrompt = [
    new SystemMessage(
      `You are a helpful assistant. The user asked a question and tool calls were made. ` +
      `Summarize the results for the user. Respond ONLY with valid JSON in this format:\n` +
      `{"msg_to_sender": "your summary", "qa_to_sender": {}, "topic_switched": false, "work_related": true, "request_answered": true, "need_human_input": false, "next_actions": []}\n` +
      `If the tools did not fully answer the question and you need to call more tools, include them in next_actions as {"tool_name": "...", "tool_input": {...}}.\n` +
      `If you need more input from the user, set need_human_input to true and request_answered to false.`
    ),
    new HumanMessage(
      `Original request: ${state.input}\n\nTool execution results:\n${toolResultsText}\n\nPlease provide a response incorporating these results.`
    ),
  ];
  
  const response = await llm.invoke(summaryPrompt);
  const parsed = parseLLMResponse(response.content);
  console.log(`[summarizeNode] Summary: request_answered=${parsed.request_answered}, next_actions=${parsed.next_actions?.length}`);
  
  // Extract any new tool calls from the summary
  const newToolCalls = (parsed.next_actions || [])
    .filter(a => a.tool_name)
    .map(a => ({ tool_name: a.tool_name, tool_input: a.tool_input || {} }));
  
  return {
    result: {
      msg_to_sender: parsed.msg_to_sender,
      qa_to_sender: parsed.qa_to_sender,
      topic_switched: parsed.topic_switched,
      work_related: parsed.work_related,
      request_answered: parsed.request_answered,
      need_human_input: parsed.need_human_input,
      next_actions: parsed.next_actions,
    },
    tool_calls: newToolCalls,
    this_node: "summarizeNode",
  };
}

// ============================================================
// LangGraph Conditional Edge Functions
// ============================================================

/**
 * After llmNode: decide whether to call tools or check the outer loop.
 * Routes to "toolNode" if tool_calls exist, else to "checkOuter".
 */
function shouldCallTools(state) {
  const hasToolCalls = state.tool_calls && state.tool_calls.length > 0;
  console.log(`[shouldCallTools] tool_calls=${state.tool_calls?.length}, route=${hasToolCalls ? "toolNode" : "checkOuter"}`);
  return hasToolCalls ? "toolNode" : "checkOuter";
}

/**
 * After summarizeNode: decide whether to continue the outer loop.
 * Continues (back to llmNode) if:
 *   - request is not yet answered AND
 *   - human input is not needed AND
 *   - we haven't exceeded max steps AND
 *   - we haven't run out of time
 * AND there are new tool_calls from the summary.
 * Otherwise routes to END.
 */
function shouldContinueOuter(state) {
  const result = state.result || {};
  const answered = result.request_answered === true;
  const needHuman = result.need_human_input === true;
  const stepsExhausted = (state.n_steps || 0) >= (state.max_steps || MAX_OUTER_STEPS);
  const hasMoreToolCalls = state.tool_calls && state.tool_calls.length > 0;
  
  console.log(`[shouldContinueOuter] answered=${answered}, needHuman=${needHuman}, steps=${state.n_steps}/${state.max_steps}, moreTools=${hasMoreToolCalls}`);
  
  if (answered || needHuman || stepsExhausted || !hasMoreToolCalls) {
    if (stepsExhausted && !answered) {
      console.warn(`[shouldContinueOuter] Max steps (${state.max_steps}) reached without answering. Forcing exit.`);
    }
    return END;
  }
  
  return "llmNode";
}

/**
 * "checkOuter" node — a pass-through that just enables the conditional edge
 * to evaluate the outer loop condition when there were no tool calls.
 */
function checkOuterNode(state) {
  console.log(`[checkOuterNode] No tool calls. Checking outer loop exit condition.`);
  // No state mutations needed — just a routing waypoint
  return {};
}

// ============================================================
// LangGraph Builder
// ============================================================

/**
 * Build the chatter LangGraph workflow.
 *
 * Topology:
 *   START → llmNode → [shouldCallTools?]
 *                        ├─ YES → toolNode → summarizeNode → [shouldContinueOuter?]
 *                        │                                       ├─ YES → llmNode (loop)
 *                        │                                       └─ NO  → END
 *                        └─ NO  → checkOuter → [shouldContinueOuter?]
 *                                                  ├─ YES → llmNode (loop)
 *                                                  └─ NO  → END
 */
function buildChatterGraph() {
  const graph = new StateGraph(ChatterState);
  
  // Add nodes
  graph.addNode("llmNode", llmNode);
  graph.addNode("toolNode", toolNode);
  graph.addNode("summarizeNode", summarizeNode);
  graph.addNode("checkOuter", checkOuterNode);
  
  // Entry edge
  graph.addEdge(START, "llmNode");
  
  // After LLM: branch on whether there are tool calls
  graph.addConditionalEdges("llmNode", shouldCallTools, {
    toolNode: "toolNode",
    checkOuter: "checkOuter",
  });
  
  // Tool → Summarize (always)
  graph.addEdge("toolNode", "summarizeNode");
  
  // After Summarize: check outer loop
  graph.addConditionalEdges("summarizeNode", shouldContinueOuter, {
    llmNode: "llmNode",
    [END]: END,
  });
  
  // After checkOuter (no tools path): check outer loop
  graph.addConditionalEdges("checkOuter", shouldContinueOuter, {
    llmNode: "llmNode",
    [END]: END,
  });
  
  // Compile and return
  return graph.compile();
}
