import { logger } from '@/utils/logger';
import { eventBus } from '@/utils/eventBus';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUserStore } from '@/stores/userStore';
import { avatarEventManager } from '@/services/avatarEventManager';
import { ScenePriority } from '@/types/avatarScene';

const DEFAULT_WS_ENDPOINT = 'wss://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-realtime-api.us-east-1.amazonaws.com/graphql';
const DEFAULT_WS_HOST = '3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com';

const SUB_A2A = `subscription OnA2AMessageReceived($channelId: String!) {\n  onA2AMessageReceived(channelId: $channelId) {\n    id\n    channelId\n    senderId\n    sessionId\n    timestamp\n    message {\n      role\n      parts {\n        type\n        text\n        data\n        metadata\n        file {\n          name\n          uri\n          mimeType\n          bytes\n        }\n      }\n    }\n  }\n}`;

const SUB_ACCOUNT_NOTIFICATION = `subscription OnAccountNotification($owner: ID!) {\n  onAccountNotification(owner: $owner) {\n    id\n    owner\n    type\n    title\n    message\n    cta_url\n    payload\n    created_at\n  }\n}`;

const SUB_AGENT_SCENE = `subscription OnAgentSceneEvent($acctSiteID: String!) {\n  onAgentSceneEvent(acctSiteID: $acctSiteID) {\n    id\n    scene_id\n    acctSiteID\n    agent_ids\n    status\n    label\n    description\n    actions\n    dialogs\n    duration_ms\n    trigger_events\n    images\n    thumbnails\n    video\n    timestamp\n  }\n}`;

const SUB_SCENE_COMPLETE = `subscription OnSceneComplete($acctSiteID: String!) {\n  onSceneComplete(acctSiteID: $acctSiteID) {\n    id\n    scene_id\n    request_id\n    acctSiteID\n    agent_ids\n    status\n    description\n    actions\n    dialogs\n    duration_ms\n    error\n    emotion\n    mind_state\n    thumbnail\n    timestamp\n    video\n  }\n}`;

const SUB_TASK_STATUS = `subscription OnTaskStatus($runner: String!) {\n  onTaskStatus(runner: $runner) {\n    id\n    runID\n    runner\n    error\n    success\n    status\n    timestamp\n  }\n}`;

const SUB_SKILL_EDITOR_STREAM = `subscription OnSkillEditorStreamEvent($owner: ID!) {\n  onSkillEditorStreamEvent(owner: $owner) {\n    eventId\n    owner\n    sessionId\n    flowgramId\n    eventType\n    payload\n    timestamp\n  }\n}`;

let activeSocket: WebSocket | null = null;
let active = false;

const getEnv = () => (typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env : {});

const toBase64 = (value: string) => {
  try {
    return window.btoa(unescape(encodeURIComponent(value)));
  } catch {
    return window.btoa(value);
  }
};

const maybeParseAwsJson = (value: any) => {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) return value;
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
      try {
        return JSON.parse(trimmed);
      } catch {
        return value;
      }
    }
  }
  return value;
};

const buildRealtimeUrl = (endpoint: string, headers: Record<string, string>) => {
  const headerParam = toBase64(JSON.stringify(headers));
  const payloadParam = toBase64(JSON.stringify({}));
  return `${endpoint}?header=${encodeURIComponent(headerParam)}&payload=${encodeURIComponent(payloadParam)}`;
};

const sendStart = (ws: WebSocket, id: string, query: string, variables: Record<string, any>, headers: Record<string, string>) => {
  ws.send(JSON.stringify({
    id,
    type: 'start',
    payload: {
      data: JSON.stringify({ query, variables }),
      extensions: { authorization: headers }
    }
  }));
};

const emitAgentSceneEvent = (scene: any) => {
  eventBus.emit('scene:agentEvent', scene);
  const agentId = Array.isArray(scene?.agent_ids) ? scene.agent_ids[0] : undefined;
  if (agentId) {
    avatarEventManager.emit('custom', agentId, { scene }, ScenePriority.NORMAL, 'appsync');
  }
};

const emitSceneComplete = (sceneResult: any) => {
  eventBus.emit('scene:complete', sceneResult);
  const agentId = Array.isArray(sceneResult?.agent_ids) ? sceneResult.agent_ids[0] : undefined;
  if (agentId) {
    avatarEventManager.emit('custom', agentId, { sceneResult }, ScenePriority.NORMAL, 'appsync');
  }
};

const emitAccountNotification = (notification: any) => {
  eventBus.emit('account:notification', notification);
};

const emitA2AMessage = (message: any) => {
  eventBus.emit('a2a:message', message);
};

const emitTaskStatus = (taskStatus: any) => {
  eventBus.emit('task:status', taskStatus);
};

const emitSkillEditorStreamEvent = (evt: any) => {
  const eventType = String(evt?.eventType || '').trim();
  const sessionId = String(evt?.sessionId || '').trim();
  const payload = maybeParseAwsJson(evt?.payload);

  if (!eventType) {
    return;
  }

  if (eventType === 'skill_editor.chat.stream_chunk') {
    eventBus.emit('skill_editor:chat:stream_chunk', { sessionId, ...(payload || {}) });
    return;
  }
  if (eventType === 'skill_editor.chat.stream_end') {
    eventBus.emit('skill_editor:chat:stream_end', { sessionId, ...(payload || {}) });
    return;
  }
  if (eventType === 'skill_editor.chat.error') {
    eventBus.emit('skill_editor:chat:error', { sessionId, ...(payload || {}) });
    return;
  }
  if (eventType === 'skill_editor.event') {
    eventBus.emit('skill_editor:event', { sessionId, ...(payload || {}) });
    return;
  }
};

export const startWebSubscriptions = () => {
  if (active) {
    logger.warn('[AppSyncSubscriptions] Already running');
    return () => {};
  }

  const env = getEnv();
  const settings = useSettingsStore.getState().settings;
  const username = useUserStore.getState().username;

  const wsEndpoint = (settings?.ws_api_endpoint || env.VITE_APPSYNC_WS_ENDPOINT || DEFAULT_WS_ENDPOINT).trim();
  const wsHost = (settings?.ws_api_host || env.VITE_APPSYNC_WS_HOST || DEFAULT_WS_HOST).trim();
  const apiKey = (settings?.wan_api_key || env.VITE_APPSYNC_API_KEY || '').trim();

  const channelId = (env.VITE_A2A_CHANNEL_ID || '').trim();
  const owner = (env.VITE_ACCOUNT_OWNER || username || '').trim();
  const acctSiteID = (env.VITE_ACCT_SITE_ID || '').trim();
  const taskRunner = (env.VITE_TASK_RUNNER || '').trim();

  if (!apiKey) {
    logger.warn('[AppSyncSubscriptions] Missing API key; subscriptions disabled');
    return () => {};
  }

  const headers = {
    host: wsHost,
    'x-api-key': apiKey,
  };

  const realtimeUrl = buildRealtimeUrl(wsEndpoint, headers);

  active = true;
  const ws = new WebSocket(realtimeUrl, 'graphql-ws');
  activeSocket = ws;

  const subscriptionIds: Record<string, string> = {};

  ws.onopen = () => {
    logger.info('[AppSyncSubscriptions] Socket open, sending connection_init');
    ws.send(JSON.stringify({ type: 'connection_init' }));
  };

  ws.onmessage = (event) => {
    let messageData: any;
    try {
      messageData = JSON.parse(event.data as string);
    } catch {
      return;
    }

    if (messageData.type === 'connection_ack') {
      logger.info('[AppSyncSubscriptions] connection_ack received');

      if (channelId) {
        subscriptionIds.a2a = `sub-a2a-${Date.now()}`;
        sendStart(ws, subscriptionIds.a2a, SUB_A2A, { channelId }, headers);
      } else {
        logger.warn('[AppSyncSubscriptions] No channelId provided; A2A subscription skipped');
      }

      if (owner) {
        subscriptionIds.account = `sub-account-${Date.now()}`;
        sendStart(ws, subscriptionIds.account, SUB_ACCOUNT_NOTIFICATION, { owner }, headers);
      } else {
        logger.warn('[AppSyncSubscriptions] No owner provided; account notification subscription skipped');
      }

      if (owner) {
        subscriptionIds.skillEditorStream = `sub-skill-editor-stream-${Date.now()}`;
        sendStart(ws, subscriptionIds.skillEditorStream, SUB_SKILL_EDITOR_STREAM, { owner }, headers);
      } else {
        logger.warn('[AppSyncSubscriptions] No owner provided; skill editor subscription skipped');
      }

      if (acctSiteID) {
        subscriptionIds.scene = `sub-scene-${Date.now()}`;
        sendStart(ws, subscriptionIds.scene, SUB_AGENT_SCENE, { acctSiteID }, headers);
        subscriptionIds.sceneComplete = `sub-scene-complete-${Date.now()}`;
        sendStart(ws, subscriptionIds.sceneComplete, SUB_SCENE_COMPLETE, { acctSiteID }, headers);
      } else {
        logger.warn('[AppSyncSubscriptions] No acctSiteID provided; agent scene subscription skipped');
      }

      if (taskRunner) {
        subscriptionIds.taskStatus = `sub-task-status-${Date.now()}`;
        sendStart(ws, subscriptionIds.taskStatus, SUB_TASK_STATUS, { runner: taskRunner }, headers);
      } else {
        logger.warn('[AppSyncSubscriptions] Missing runner; task status subscription skipped');
      }
      return;
    }

    if (messageData.type === 'data') {
      const payload = messageData.payload?.data || {};
      if (payload.onA2AMessageReceived) {
        emitA2AMessage(payload.onA2AMessageReceived);
      }
      if (payload.onAccountNotification) {
        emitAccountNotification(payload.onAccountNotification);
      }
      if (payload.onAgentSceneEvent) {
        emitAgentSceneEvent(payload.onAgentSceneEvent);
      }
      if (payload.onSceneComplete) {
        emitSceneComplete(payload.onSceneComplete);
      }
      if (payload.onTaskStatus) {
        emitTaskStatus(payload.onTaskStatus);
      }
      if (payload.onSkillEditorStreamEvent) {
        emitSkillEditorStreamEvent(payload.onSkillEditorStreamEvent);
      }
      return;
    }

    if (messageData.type === 'error' || messageData.type === 'connection_error') {
      logger.error('[AppSyncSubscriptions] Error payload', messageData);
    }
  };

  ws.onerror = (event) => {
    logger.error('[AppSyncSubscriptions] WebSocket error', event);
  };

  ws.onclose = (event) => {
    logger.info('[AppSyncSubscriptions] Socket closed', { code: event.code, reason: event.reason });
    active = false;
    activeSocket = null;
  };

  return () => {
    if (activeSocket && (activeSocket.readyState === WebSocket.OPEN || activeSocket.readyState === WebSocket.CONNECTING)) {
      activeSocket.close(1000, 'AppSync subscriptions closed');
    }
    active = false;
    activeSocket = null;
  };
};

export const stopWebSubscriptions = () => {
  if (activeSocket && (activeSocket.readyState === WebSocket.OPEN || activeSocket.readyState === WebSocket.CONNECTING)) {
    activeSocket.close(1000, 'AppSync subscriptions stopped');
  }
  active = false;
  activeSocket = null;
};
