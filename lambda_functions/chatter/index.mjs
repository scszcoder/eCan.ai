import { DynamoDBClient, GetItemCommand, QueryCommand, UpdateItemCommand } from "@aws-sdk/client-dynamodb";
import { unmarshall } from "@aws-sdk/util-dynamodb";
import { ChatOpenAI } from "@langchain/openai";
import { ChatAnthropic } from "@langchain/anthropic";
import { ChatGoogleGenerativeAI } from "@langchain/google-genai";
import { HumanMessage, SystemMessage, AIMessage } from "@langchain/core/messages";
import { randomUUID } from "node:crypto";

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
  "next_actions": []
}

Required fields:
- "msg_to_sender" (string, required): The text message to send back to the user
- "qa_to_sender" (object, optional): Any structured data, questions, or UI hints for the frontend
- "topic_switched" (boolean, required): Set to true if the conversation topic has significantly changed and a new session should be started
- "work_related" (boolean, required): Set to true if the user's message is related to work/tasks, false for casual chat or off-topic
- "request_answered" (boolean, required): Set to true if you have fully answered/addressed the user's request, false if more information is needed or the request is incomplete
- "next_actions" (array, required): List of follow-up actions to execute. Each action is an object with:
  - "action": The action type (e.g., "run_task", "schedule_task", "fetch_data", "notify_user")
  - "task_name": Name of the task to run (if applicable)
  - Other action-specific parameters as needed
  Example: [{"action": "run_task", "task_name": "send_email", "params": {"to": "user@example.com"}}]

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
 * Get agent system prompt from Agent_Prompts table
 * Key: owner_id (modified username), agent_id
 */
async function getAgentPrompt(ownerId, agentId) {
  console.log(`[chatter] Getting prompt for owner=${ownerId}, agent=${agentId}`);
  
  try {
    const result = await dynamodb.send(new GetItemCommand({
      TableName: AGENT_PROMPTS_TABLE,
      Key: {
        owner_id: { S: ownerId },
        agent_id: { S: agentId }
      }
    }));
    
    if (result.Item) {
      const item = unmarshall(result.Item);
      console.log(`[chatter] Found prompt: ${item.system_prompt?.substring(0, 100)}...`);
      return item.system_prompt || null;
    }
    
    console.log(`[chatter] No prompt found for this agent`);
    return null;
  } catch (err) {
    console.error(`[chatter] Error getting prompt:`, err);
    return null;
  }
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
    next_actions: []
  };
}

/**
 * Send response back to frontend via AppSync
 */
async function sendResponse(channelId, sessionId, senderId, recipientId, parsedResponse) {
  const { msg_to_sender, qa_to_sender, work_related, request_answered, next_actions } = parsedResponse;
  
  // Build metadata object with all structured data
  const metadata = {
    ...qa_to_sender,
    work_related,
    request_answered,
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
 * Process a user message and generate LLM response
 */
async function processUserMessage(message) {
  const { channelId, sessionId, senderId, recipientId, timestamp } = message;
  
  // Parse recipientId to get owner and agent info
  // Expected format: "owner_id:agent_id" or just "agent_id"
  let ownerId = senderId; // Default to sender as owner
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
  
  // Build messages for LLM
  const messages = buildMessages(agentPrompt, chatHistory, message);
  
  if (messages.length === 0) {
    console.log(`[chatter] No messages to send to LLM`);
    return;
  }
  
  // Create LLM and get response
  const llm = createLLM(LLM_PROVIDER, LLM_MODEL, LLM_TEMPERATURE);
  console.log(`[chatter] Invoking LLM...`);
  
  const response = await llm.invoke(messages);
  const responseText = response.content;
  
  console.log(`[chatter] LLM raw response: ${responseText.substring(0, 300)}...`);
  
  // Parse the JSON response
  const parsed = parseLLMResponse(responseText);
  console.log(`[chatter] Parsed response:`, JSON.stringify(parsed).substring(0, 200));
  
  // Check if topic switched - create new session for response
  let responseSessionId = currentSessionId;
  if (parsed.topic_switched && !sessionSwitched) {
    console.log(`[chatter] Topic switched - creating new session for response`);
    responseSessionId = generateSessionId();
  }
  
  // Send response back via AppSync
  await sendResponse(
    channelId, 
    responseSessionId, 
    agentId, 
    senderId, 
    parsed
  );
  
  console.log(`[chatter] Response sent successfully to session ${responseSessionId}`);
}
