import { randomUUID } from "node:crypto";
import { S3Client, PutObjectCommand, GetObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

const S3_BUCKET = process.env.S3_BUCKET;
const APPSYNC_API_URL = process.env.APPSYNC_API_URL;
const APPSYNC_API_KEY = process.env.APPSYNC_API_KEY;
const DEFAULT_OWNER = process.env.NOTIFY_OWNER;
const DEFAULT_EXPIRES = Number.parseInt(process.env.PRESIGNED_EXPIRES || "900", 10);

// ============================================================
// GraphQL Mutations for each subscription type
// ============================================================

// sendA2AMessage -> onA2AMessageReceived(channelId)
const SEND_A2A_MESSAGE = `
mutation SendA2AMessage($input: A2AMessageInput!) {
  sendA2AMessage(input: $input) {
    id channelId senderId sessionId timestamp
    message { role parts { type text } }
  }
}
`;

// publishAccountNotification -> onAccountNotification(owner)
const PUBLISH_ACCOUNT_NOTIFICATION = `
mutation PublishAccountNotification($input: AccountNotificationInput!) {
  publishAccountNotification(input: $input) {
    id owner ntype title message payload created_at
  }
}
`;

// updateScene -> onAgentSceneEvent(acctSiteID)
const UPDATE_SCENE = `
mutation UpdateScene($input: SceneInput!) {
  updateScene(input: $input) {
    id scene_id acctSiteID agent_ids label status timestamp
  }
}
`;

// endLongLLMTask -> onLongLLMTaskComplete(acctSiteID)
const END_LONG_LLM_TASK = `
mutation EndLongLLMTask($input: [LongLLMTaskResultInput!]!) {
  endLongLLMTask(input: $input) {
    id acctSiteID agentID taskID status timestamp
  }
}
`;

// publishPassiveCommand -> onPassiveCommand(clientId, runId)
const PUBLISH_PASSIVE_COMMAND = `
mutation PublishPassiveCommand($input: PassiveBrowserCommandEnvelopeInput!) {
  publishPassiveCommand(input: $input) {
    id clientId runId stepId command timestamp
  }
}
`;

// sendPuzzleSolution -> onPuzzleResultReceived
const SEND_PUZZLE_SOLUTION = `
mutation SendPuzzleSolution($input: PuzzleSolutionInput) {
  sendPuzzleSolution(input: $input) {
    id request_id solver_id solution timestamp
  }
}
`;

// updateStory -> onStoryUpdate(acctSiteID)
const UPDATE_STORY = `
mutation UpdateStory($input: StoryUpdateInput!) {
  updateStory(input: $input) {
    id acctSiteID title status agent_ids updated_at
  }
}
`;

// publishTaskStatus -> onTaskStatus(runner)
const PUBLISH_TASK_STATUS = `
mutation PublishTaskStatus($input: TaskStatusInput!) {
  publishTaskStatus(input: $input) {
    id runID runner success error status timestamp
  }
}
`;

// publishSkillEditorStreamEvent -> onSkillEditorStreamEvent(owner)
const PUBLISH_SKILL_EDITOR_STREAM_EVENT = `
mutation PublishSkillEditorStreamEvent($input: SkillEditorStreamEventInput!) {
  publishSkillEditorStreamEvent(input: $input) {
    eventId owner sessionId flowgramId eventType payload timestamp
  }
}
`;

// ============================================================
// Helper functions
// ============================================================

const requireEnv = (value, name) => {
  if (!value) {
    console.error(`[cloud_tester] ERROR: Missing required env var: ${name}`);
    throw new Error(`Missing required env var: ${name}`);
  }
  console.log(`[cloud_tester] Env ${name} is set`);
  return value;
};

const appSyncRequest = async (url, apiKey, payload, operationName) => {
  console.log(`[cloud_tester] AppSync request: ${operationName}`);
  console.log(`[cloud_tester] Variables:`, JSON.stringify(payload.variables, null, 2));
  
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": apiKey,
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json();
  
  if (!response.ok) {
    console.error(`[cloud_tester] AppSync request failed: ${response.status} ${response.statusText}`);
    console.error(`[cloud_tester] Response data:`, JSON.stringify(data));
    throw new Error(`AppSync request failed: ${response.status} ${response.statusText}`);
  }
  
  if (data.errors) {
    console.error(`[cloud_tester] AppSync errors for ${operationName}:`, JSON.stringify(data.errors, null, 2));
  } else {
    console.log(`[cloud_tester] AppSync SUCCESS for ${operationName}:`, JSON.stringify(data.data, null, 2));
  }
  
  return data;
};

// ============================================================
// Test runners for each mutation
// ============================================================

const testSendA2AMessage = async (url, apiKey, params) => {
  const channelId = params.channelId || "test-channel-" + randomUUID().slice(0, 8);
  console.log(`[cloud_tester] testSendA2AMessage: channelId=${channelId}`);
  const input = {
    channelId,
    senderId: params.senderId || "cloud_tester",
    sessionId: params.sessionId || randomUUID(),
    message: {
      role: "assistant",
      parts: [{ type: "text", text: `[WS_Test] A2A test message at ${new Date().toISOString()}` }]
    }
  };
  return appSyncRequest(url, apiKey, { query: SEND_A2A_MESSAGE, variables: { input } }, "sendA2AMessage");
};

const testPublishAccountNotification = async (url, apiKey, params) => {
  console.log(`[cloud_tester] testPublishAccountNotification: owner=${params.owner}`);
  const input = {
    owner: params.owner || "test-owner",
    ntype: "AD_BANNER",
    title: "🎉 Special Announcement",
    message: "🚀 Welcome to eCan.ai! Your AI-powered automation platform. New features: Cloud Workers now available! Try Skill Editor for building custom automations. Limited time: 50% off premium plans! 🎯",
    payload: JSON.stringify({ 
      id: `ad-${Date.now()}`,
      text: "🚀 Welcome to eCan.ai! Your AI-powered automation platform. New features: Cloud Workers now available! Try Skill Editor for building custom automations. Limited time: 50% off premium plans! 🎯",
      expiresAt: Date.now() + 60000, // 60 seconds from now
      test: true, 
      timestamp: Date.now(), 
      testName: params.testName 
    })
  };
  return appSyncRequest(url, apiKey, { query: PUBLISH_ACCOUNT_NOTIFICATION, variables: { input } }, "publishAccountNotification");
};

const testUpdateScene = async (url, apiKey, params) => {
  const sceneId = randomUUID();
  console.log(`[cloud_tester] testUpdateScene: acctSiteID=${params.acctSiteID}, sceneId=${sceneId}`);
  const input = {
    acctSiteID: params.acctSiteID || "test-site",
    scene_id: sceneId,
    agent_ids: ["test-agent-1"],
    label: `[${params.testName}] Test Scene`,
    clip: "test-clip",
    status: "PENDING",
    images: ["https://example.com/test.png"],
    thumbnails: ["https://example.com/thumb.png"],
    video: ["https://example.com/video.mp4"]
  };
  return appSyncRequest(url, apiKey, { query: UPDATE_SCENE, variables: { input } }, "updateScene");
};

const testEndLongLLMTask = async (url, apiKey, params) => {
  const taskId = randomUUID();
  console.log(`[cloud_tester] testEndLongLLMTask: acctSiteID=${params.acctSiteID}, taskId=${taskId}`);
  const input = [{
    acctSiteID: params.acctSiteID || "test-site",
    agentID: "test-agent",
    taskID: taskId,
    status: "completed",
    results: JSON.stringify({ test: true, message: `[${params.testName}] LongLLM task completed` })
  }];
  return appSyncRequest(url, apiKey, { query: END_LONG_LLM_TASK, variables: { input } }, "endLongLLMTask");
};

const testPublishPassiveCommand = async (url, apiKey, params) => {
  const clientId = params.clientId || "test-client-" + randomUUID().slice(0, 8);
  const runId = params.runId || randomUUID();
  console.log(`[cloud_tester] testPublishPassiveCommand: clientId=${clientId}, runId=${runId}`);
  const input = {
    clientId,
    runId,
    stepId: randomUUID(),
    // AWSJSON type requires the value to be a JSON string (gets double-serialized)
    command: JSON.stringify({ action: "test", message: `[${params.testName}] Passive command test`, timestamp: Date.now() })
  };
  return appSyncRequest(url, apiKey, { query: PUBLISH_PASSIVE_COMMAND, variables: { input } }, "publishPassiveCommand");
};

const testSendPuzzleSolution = async (url, apiKey, params) => {
  const requestId = params.request_id || randomUUID();
  console.log(`[cloud_tester] testSendPuzzleSolution: request_id=${requestId}`);
  const input = {
    request_id: requestId,
    solver_id: "cloud_tester",
    solution: [JSON.stringify({ answer: "test", message: `[${params.testName}] Puzzle solution` })]
  };
  return appSyncRequest(url, apiKey, { query: SEND_PUZZLE_SOLUTION, variables: { input } }, "sendPuzzleSolution");
};

const testUpdateStory = async (url, apiKey, params) => {
  const storyId = params.storyId || randomUUID();
  console.log(`[cloud_tester] testUpdateStory: storyId=${storyId}, acctSiteID=${params.acctSiteID}`);
  // Note: updateStory requires an existing story ID, so this might fail if story doesn't exist
  const input = {
    id: storyId,
    acctSiteID: params.acctSiteID || "test-site",
    title: `[${params.testName}] Test Story Update`,
    status: "DRAFT",
    agent_ids: ["test-agent-1"]
  };
  return appSyncRequest(url, apiKey, { query: UPDATE_STORY, variables: { input } }, "updateStory");
};

const testPublishTaskStatus = async (url, apiKey, params) => {
  const runner = params.runner || "test-runner";
  const runId = randomUUID();
  console.log(`[cloud_tester] testPublishTaskStatus: runner=${runner}, runId=${runId}`);
  const input = {
    runner,
    runID: runId,
    success: true,
    status: JSON.stringify({ phase: "test", message: `[${params.testName}] Task status test` })
  };
  return appSyncRequest(url, apiKey, { query: PUBLISH_TASK_STATUS, variables: { input } }, "publishTaskStatus");
};

const testPublishSkillEditorStreamEvent = async (url, apiKey, params) => {
  const sessionId = params.sessionId || randomUUID();
  console.log(`[cloud_tester] testPublishSkillEditorStreamEvent: owner=${params.owner}, sessionId=${sessionId}`);
  
  // Send a skill_editor.log event - this is what cloud_logger.py sends for runtime logs
  // The frontend (appSyncSubscriptions.ts) listens for this and emits to skill-editor:log
  // which SkillConsolePanel.tsx displays in the console
  const input = {
    owner: params.owner || "test-owner",
    sessionId,
    eventType: "skill_editor.log",  // Must match what cloud_logger.py sends
    payload: JSON.stringify({
      level: "log",  // Can be: log, info, debug, warning, error
      message: `[C2C_WS_Test] Cloud tester log message at ${new Date().toISOString()} - If you see this in Skill Editor Console, pub/sub is working!`,
      timestamp: new Date().toISOString(),
      node_id: "test-node",
      extra: { source: "cloud_tester", testName: params.testName }
    })
  };
  return appSyncRequest(url, apiKey, { query: PUBLISH_SKILL_EDITOR_STREAM_EVENT, variables: { input } }, "publishSkillEditorStreamEvent");
};

// Send cloud worker command via publishSkillEditorStreamEvent
// The worker expects eventType or payload.type to be one of:
// run_step, run_paused, run_resumed, run_cancelled, ping
const testCloudWorkerCommand = async (url, apiKey, params, cmdType) => {
  const sessionId = params.sessionId || params.run_id || randomUUID();
  const flowgramId = params.flowgramId || params.flowgram_id || params.skill_id || "test-flowgram";
  
  // Map command types to event types expected by worker_main.py
  const eventTypeMap = {
    "step": "run_step",
    "ping": "ping",
    "pause": "run_paused",
    "resume": "run_resumed",
    "stop": "run_cancelled",
  };
  const eventType = eventTypeMap[cmdType] || cmdType;
  
  console.log(`[cloud_tester] testCloudWorkerCommand: owner=${params.owner}, sessionId=${sessionId}, eventType=${eventType}`);
  
  const input = {
    owner: params.owner || "test-owner",
    sessionId,
    flowgramId,
    eventType: eventType,  // Worker checks envelope.eventType first
    payload: JSON.stringify({
      type: eventType,  // Worker also checks payload.type as fallback
      run_id: sessionId,  // Worker uses this to match the run
      timestamp: new Date().toISOString(),
      source: "cloud_tester",
      testName: params.testName
    })
  };
  return appSyncRequest(url, apiKey, { query: PUBLISH_SKILL_EDITOR_STREAM_EVENT, variables: { input } }, `publishSkillEditorStreamEvent (${eventType})`);
};

const testStepCloudWorker = async (url, apiKey, params) => {
  return testCloudWorkerCommand(url, apiKey, { ...params, testName: "Step_Cloud_Worker" }, "step");
};

const testPingCloudWorker = async (url, apiKey, params) => {
  return testCloudWorkerCommand(url, apiKey, { ...params, testName: "Ping_Cloud_Worker" }, "ping");
};

// Send passive command to client via publishPassiveCommand
const testSendPassiveCmd = async (url, apiKey, params) => {
  // Hard-coded to match what clients subscribe to
  const clientId = "songc_yahoo_com_SCHOME";
  const runId = "0123456789";
  const stepId = params.stepId || params.step_id || randomUUID();
  console.log(`[cloud_tester] testSendPassiveCmd: clientId=${clientId}, runId=${runId}`);
  
  // Allow custom command payload or use default test command
  // Command format: { actions: [{click: {index}}, {input: {index, text}}], results: {} }
  let command = params.command;
  
  // If command is a simple string (like 'passive_ping'), wrap it in an object
  if (typeof command === 'string') {
    // Try to parse as JSON first
    try {
      command = JSON.parse(command);
    } catch (e) {
      // Not valid JSON, wrap string in an action object
      command = { action: command, timestamp: Date.now() };
    }
  }
  
  // If no command provided, use default test command
  if (!command) {
    command = { action: "ping" };
  }
  
  // PassiveBrowserCommand model requires run_id and step_id inside the command payload
  command.run_id = runId;
  command.step_id = stepId;
  
  const input = {
    clientId,
    runId,
    stepId,
    // AWSJSON requires a valid JSON string
    command: JSON.stringify(command)
  };
  return appSyncRequest(url, apiKey, { query: PUBLISH_PASSIVE_COMMAND, variables: { input } }, "publishPassiveCommand (Send_PASSIVE_CMD)");
};

// ============================================================
// Test suite runners
// ============================================================

const runC2LTest = async (url, apiKey, params) => {
  console.log("==========================================");
  console.log("[cloud_tester] Running C2L_WS_Test (Cloud to Local)...");
  console.log("[cloud_tester] Params:", JSON.stringify(params, null, 2));
  console.log("==========================================");
  
  const results = {
    testName: "C2L_WS_Test",
    timestamp: new Date().toISOString(),
    tests: {}
  };

  // C2L subscriptions (for local client):
  // onA2AMessageReceived, onAccountNotification, onAgentSceneEvent, onLongLLMTaskComplete,
  // onPassiveCommand, onPuzzleResultReceived, onStoryUpdate, onTaskStatus

  try {
    console.log("\n--- Test 1/8: sendA2AMessage -> onA2AMessageReceived ---");
    results.tests.a2aMessage = await testSendA2AMessage(url, apiKey, params);
  } catch (e) {
    console.error("[cloud_tester] sendA2AMessage FAILED:", e.message);
    results.tests.a2aMessage = { error: e.message };
  }

  try {
    console.log("\n--- Test 2/8: publishAccountNotification -> onAccountNotification ---");
    results.tests.accountNotification = await testPublishAccountNotification(url, apiKey, { ...params, testName: "C2L_WS_Test" });
  } catch (e) {
    console.error("[cloud_tester] publishAccountNotification FAILED:", e.message);
    results.tests.accountNotification = { error: e.message };
  }

  try {
    console.log("\n--- Test 3/8: updateScene -> onAgentSceneEvent ---");
    results.tests.agentSceneEvent = await testUpdateScene(url, apiKey, { ...params, testName: "C2L_WS_Test" });
  } catch (e) {
    console.error("[cloud_tester] updateScene FAILED:", e.message);
    results.tests.agentSceneEvent = { error: e.message };
  }

  try {
    console.log("\n--- Test 4/8: endLongLLMTask -> onLongLLMTaskComplete ---");
    results.tests.longLLMTaskComplete = await testEndLongLLMTask(url, apiKey, { ...params, testName: "C2L_WS_Test" });
  } catch (e) {
    console.error("[cloud_tester] endLongLLMTask FAILED:", e.message);
    results.tests.longLLMTaskComplete = { error: e.message };
  }

  try {
    console.log("\n--- Test 5/8: publishPassiveCommand -> onPassiveCommand ---");
    results.tests.passiveCommand = await testPublishPassiveCommand(url, apiKey, { ...params, testName: "C2L_WS_Test" });
  } catch (e) {
    console.error("[cloud_tester] publishPassiveCommand FAILED:", e.message);
    results.tests.passiveCommand = { error: e.message };
  }

  try {
    console.log("\n--- Test 6/8: sendPuzzleSolution -> onPuzzleResultReceived ---");
    results.tests.puzzleSolution = await testSendPuzzleSolution(url, apiKey, { ...params, testName: "C2L_WS_Test" });
  } catch (e) {
    console.error("[cloud_tester] sendPuzzleSolution FAILED:", e.message);
    results.tests.puzzleSolution = { error: e.message };
  }

  try {
    console.log("\n--- Test 7/8: updateStory -> onStoryUpdate ---");
    results.tests.storyUpdate = await testUpdateStory(url, apiKey, { ...params, testName: "C2L_WS_Test" });
  } catch (e) {
    console.error("[cloud_tester] updateStory FAILED:", e.message);
    results.tests.storyUpdate = { error: e.message };
  }

  try {
    console.log("\n--- Test 8/8: publishTaskStatus -> onTaskStatus ---");
    results.tests.taskStatus = await testPublishTaskStatus(url, apiKey, { ...params, testName: "C2L_WS_Test" });
  } catch (e) {
    console.error("[cloud_tester] publishTaskStatus FAILED:", e.message);
    results.tests.taskStatus = { error: e.message };
  }

  console.log("\n==========================================");
  console.log("[cloud_tester] C2L_WS_Test COMPLETED");
  console.log("[cloud_tester] Results summary:", JSON.stringify(results, null, 2));
  console.log("==========================================");
  return results;
};

const runC2CTest = async (url, apiKey, params) => {
  console.log("==========================================");
  console.log("[cloud_tester] Running C2C_WS_Test (Cloud to Cloud/Web)...");
  console.log("[cloud_tester] Params:", JSON.stringify(params, null, 2));
  console.log("==========================================");
  
  const results = {
    testName: "C2C_WS_Test",
    timestamp: new Date().toISOString(),
    tests: {}
  };

  // C2C subscriptions (for web app):
  // onA2AMessageReceived, onAccountNotification, onAgentSceneEvent, onStoryUpdate,
  // onPuzzleResultReceived, onSkillEditorStreamEvent, onTaskStatus

  try {
    console.log("\n--- Test 1/7: sendA2AMessage -> onA2AMessageReceived ---");
    results.tests.a2aMessage = await testSendA2AMessage(url, apiKey, params);
  } catch (e) {
    console.error("[cloud_tester] sendA2AMessage FAILED:", e.message);
    results.tests.a2aMessage = { error: e.message };
  }

  try {
    console.log("\n--- Test 2/7: publishAccountNotification -> onAccountNotification ---");
    results.tests.accountNotification = await testPublishAccountNotification(url, apiKey, { ...params, testName: "C2C_WS_Test" });
  } catch (e) {
    console.error("[cloud_tester] publishAccountNotification FAILED:", e.message);
    results.tests.accountNotification = { error: e.message };
  }

  try {
    console.log("\n--- Test 3/7: updateScene -> onAgentSceneEvent ---");
    results.tests.agentSceneEvent = await testUpdateScene(url, apiKey, { ...params, testName: "C2C_WS_Test" });
  } catch (e) {
    console.error("[cloud_tester] updateScene FAILED:", e.message);
    results.tests.agentSceneEvent = { error: e.message };
  }

  try {
    console.log("\n--- Test 4/7: updateStory -> onStoryUpdate ---");
    results.tests.storyUpdate = await testUpdateStory(url, apiKey, { ...params, testName: "C2C_WS_Test" });
  } catch (e) {
    console.error("[cloud_tester] updateStory FAILED:", e.message);
    results.tests.storyUpdate = { error: e.message };
  }

  try {
    console.log("\n--- Test 5/7: sendPuzzleSolution -> onPuzzleResultReceived ---");
    results.tests.puzzleSolution = await testSendPuzzleSolution(url, apiKey, { ...params, testName: "C2C_WS_Test" });
  } catch (e) {
    console.error("[cloud_tester] sendPuzzleSolution FAILED:", e.message);
    results.tests.puzzleSolution = { error: e.message };
  }

  try {
    console.log("\n--- Test 6/7: publishSkillEditorStreamEvent -> onSkillEditorStreamEvent ---");
    results.tests.skillEditorStreamEvent = await testPublishSkillEditorStreamEvent(url, apiKey, { ...params, testName: "C2C_WS_Test" });
  } catch (e) {
    console.error("[cloud_tester] publishSkillEditorStreamEvent FAILED:", e.message);
    results.tests.skillEditorStreamEvent = { error: e.message };
  }

  try {
    console.log("\n--- Test 7/7: publishTaskStatus -> onTaskStatus ---");
    results.tests.taskStatus = await testPublishTaskStatus(url, apiKey, { ...params, testName: "C2C_WS_Test" });
  } catch (e) {
    console.error("[cloud_tester] publishTaskStatus FAILED:", e.message);
    results.tests.taskStatus = { error: e.message };
  }

  console.log("\n==========================================");
  console.log("[cloud_tester] C2C_WS_Test COMPLETED");
  console.log("[cloud_tester] Results summary:", JSON.stringify(results, null, 2));
  console.log("==========================================");
  return results;
};

const runPresignedTest = async (params) => {
  console.log("==========================================");
  console.log("[cloud_tester] Running PRESIGNED_TEST (legacy)...");
  console.log("[cloud_tester] Params:", JSON.stringify(params, null, 2));
  console.log("==========================================");
  
  const bucket = requireEnv(S3_BUCKET, "S3_BUCKET");
  const appsyncUrl = requireEnv(APPSYNC_API_URL, "APPSYNC_API_URL");
  const appsyncKey = requireEnv(APPSYNC_API_KEY, "APPSYNC_API_KEY");

  const owner = params.owner || DEFAULT_OWNER;
  if (!owner) {
    console.error("[cloud_tester] Missing owner in params or NOTIFY_OWNER env var");
    throw new Error("Missing owner in params or NOTIFY_OWNER env var");
  }

  const key = params.key || `presigned-tests/${randomUUID()}.txt`;
  const contentType = params.contentType || params.content_type || "text/plain";
  const expiresIn = Number.parseInt(params.expiresIn || params.expires_in || DEFAULT_EXPIRES, 10);

  console.log(`[cloud_tester] Generating presigned URLs for bucket=${bucket}, key=${key}, contentType=${contentType}, expiresIn=${expiresIn}`);

  const s3 = new S3Client({});
  const uploadUrl = await getSignedUrl(
    s3,
    new PutObjectCommand({
      Bucket: bucket,
      Key: key,
      ContentType: contentType,
    }),
    { expiresIn }
  );
  console.log("[cloud_tester] Generated upload URL");

  const downloadUrl = await getSignedUrl(
    s3,
    new GetObjectCommand({
      Bucket: bucket,
      Key: key,
    }),
    { expiresIn }
  );
  console.log("[cloud_tester] Generated download URL");

  const payload = {
    type: "presigned_test",
    bucket,
    key,
    contentType,
    upload: {
      url: uploadUrl,
      method: "PUT",
      headers: { "Content-Type": contentType },
    },
    download: {
      url: downloadUrl,
      method: "GET",
    },
  };

  const variables = {
    input: {
      owner,
      ntype: "PRESIGNED_TEST",
      title: params.title || "Presigned URL Test",
      message: params.message || "Presigned upload/download links",
      payload: JSON.stringify(payload),
    },
  };

  console.log("[cloud_tester] Sending notification to AppSync...");
  const appsyncResponse = await appSyncRequest(appsyncUrl, appsyncKey, {
    query: PUBLISH_ACCOUNT_NOTIFICATION,
    variables,
  }, "publishAccountNotification (presigned)");

  console.log("[cloud_tester] PRESIGNED_TEST COMPLETED");
  return {
    statusCode: 200,
    payload,
    appsyncResponse,
  };
};

// ============================================================
// Lambda handler
// ============================================================

export const handler = async (event = {}) => {
  console.log("==========================================");
  console.log("[cloud_tester] Lambda INVOKED");
  console.log("[cloud_tester] Event:", JSON.stringify(event, null, 2));
  console.log("==========================================");
  
  const appsyncUrl = requireEnv(APPSYNC_API_URL, "APPSYNC_API_URL");
  const appsyncKey = requireEnv(APPSYNC_API_KEY, "APPSYNC_API_KEY");

  // Extract test input from event
  // Event can come from:
  // 1. AppSync resolver: { arguments: { input: [{name, id, input}] } }
  // 2. Direct invocation with array: { input: [{name, id, input}] }
  // 3. Direct invocation with single test: { name: "C2C_WS_Test", input: {...} }
  // 4. Legacy presigned test: { owner: "...", key: "..." }
  
  let testInputs = [];
  
  if (event.arguments?.input) {
    // AppSync resolver format
    testInputs = event.arguments.input;
    console.log("[cloud_tester] Received input from AppSync arguments, count:", testInputs.length);
  } else if (Array.isArray(event.input)) {
    // Direct invocation with array of tests
    testInputs = event.input;
    console.log("[cloud_tester] Received array input, count:", testInputs.length);
  } else if (event.name) {
    // Direct invocation with single test: { name: "...", input: {...} }
    // Merge the params from event.input into the test object
    const params = typeof event.input === 'string' ? JSON.parse(event.input) : (event.input || {});
    testInputs = [{ 
      name: event.name, 
      id: event.id || randomUUID(),
      params  // Store parsed params directly
    }];
    console.log("[cloud_tester] Received single test object with name:", event.name);
  } else {
    // Legacy: no test name, run presigned test
    console.log("[cloud_tester] No test inputs, running legacy presigned test");
    return runPresignedTest(event);
  }

  if (testInputs.length === 0) {
    console.error("[cloud_tester] ERROR: No test inputs provided");
    return {
      statusCode: 400,
      error: "No test inputs provided. Expected 'input' array with test objects containing 'name' field."
    };
  }

  const allResults = [];

  for (let i = 0; i < testInputs.length; i++) {
    const testInput = testInputs[i];
    const testName = testInput.name || testInput.test_name;
    const testId = testInput.id || randomUUID();
    
    // Parse input params - can come from testInput.params (single test) or testInput.input (array format)
    let params = {};
    if (testInput.params) {
      // Already parsed from single test format
      params = testInput.params;
    } else if (testInput.input) {
      params = typeof testInput.input === 'string' ? JSON.parse(testInput.input) : testInput.input;
    } else {
      // Use all fields except name/id as params
      params = { ...testInput };
      delete params.name;
      delete params.id;
      delete params.test_name;
    }
    
    console.log(`\n[cloud_tester] ========== Processing test ${i + 1}/${testInputs.length} ==========`);
    console.log(`[cloud_tester] Test name: ${testName}, id: ${testId}`);
    console.log(`[cloud_tester] Test params:`, JSON.stringify(params, null, 2));

    let result;
    
    switch (testName) {
      case "C2L_WS_Test":
      case "C2L_WS_TEST":
        result = await runC2LTest(appsyncUrl, appsyncKey, params);
        break;
        
      case "C2C_WS_Test":
      case "C2C_WS_TEST":
        result = await runC2CTest(appsyncUrl, appsyncKey, params);
        break;
        
      case "PRESIGNED_TEST":
      case "presigned_test":
        result = await runPresignedTest(params);
        break;

      case "Step_Cloud_Worker":
      case "STEP_CLOUD_WORKER":
        result = await testStepCloudWorker(appsyncUrl, appsyncKey, params);
        break;

      case "Ping_Cloud_Worker":
      case "PING_CLOUD_WORKER":
        result = await testPingCloudWorker(appsyncUrl, appsyncKey, params);
        break;

      case "Send_PASSIVE_CMD":
      case "SEND_PASSIVE_CMD":
        result = await testSendPassiveCmd(appsyncUrl, appsyncKey, params);
        break;
        
      default:
        console.warn(`[cloud_tester] WARNING: Unknown test name: ${testName}`);
        result = { 
          error: `Unknown test name: ${testName}`, 
          supportedTests: ["C2L_WS_Test", "C2C_WS_Test", "PRESIGNED_TEST", "Step_Cloud_Worker", "Ping_Cloud_Worker", "Send_PASSIVE_CMD"] 
        };
    }

    allResults.push({
      testId,
      testName,
      ...result
    });
  }

  console.log("\n==========================================");
  console.log("[cloud_tester] ALL TESTS COMPLETED");
  console.log("[cloud_tester] Total tests run:", allResults.length);
  console.log("[cloud_tester] Final results:", JSON.stringify(allResults, null, 2));
  console.log("==========================================");

  return JSON.stringify({
    statusCode: 200,
    results: allResults
  });
};
