import { logger } from '@/utils/logger';
import { eventBus } from '@/utils/eventBus';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUserStore } from '@/stores/userStore';
import { avatarEventManager } from '@/services/avatarEventManager';
import { ScenePriority } from '@/types/avatarScene';

import { useAdStore } from '@/stores/adStore';
import { localWebSocketClient } from './localWebSocketClient';
import { initWebSocketEventListeners } from './wsEventListeners';

const DEFAULT_WS_ENDPOINT = 'wss://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-realtime-api.us-east-1.amazonaws.com/graphql';
const DEFAULT_WS_HOST = '3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com';

const SUB_A2A = `subscription OnA2AMessageReceived($channelId: String!) {\n  onA2AMessageReceived(channelId: $channelId) {\n    id\n    channelId\n    senderId\n    sessionId\n    timestamp\n    message {\n      role\n      parts {\n        type\n        text\n        data\n        metadata\n        file {\n          name\n          uri\n          mimeType\n          bytes\n        }\n      }\n    }\n  }\n}`;

const SUB_ACCOUNT_NOTIFICATION = `subscription OnAccountNotification($owner: String!) {\n  onAccountNotification(owner: $owner) {\n    id\n    owner\n    ntype\n    title\n    message\n    cta_url\n    payload\n    created_at\n  }\n}`;

const SUB_AGENT_SCENE = `subscription OnAgentSceneEvent($acctSiteID: String!) {\n  onAgentSceneEvent(acctSiteID: $acctSiteID) {\n    id\n    scene_id\n    acctSiteID\n    agent_ids\n    status\n    label\n    description\n    actions\n    dialogs\n    duration_ms\n    trigger_events\n    images\n    thumbnails\n    video\n    timestamp\n  }\n}`;

const SUB_SCENE_COMPLETE = `subscription OnSceneComplete($acctSiteID: String!) {\n  onSceneComplete(acctSiteID: $acctSiteID) {\n    id\n    scene_id\n    request_id\n    acctSiteID\n    agent_ids\n    status\n    description\n    actions\n    dialogs\n    duration_ms\n    error\n    emotion\n    mind_state\n    thumbnail\n    timestamp\n    video\n  }\n}`;

const SUB_TASK_STATUS = `subscription OnTaskStatus($runner: String!) {\n  onTaskStatus(runner: $runner) {\n    id\n    runID\n    runner\n    error\n    success\n    status\n    timestamp\n  }\n}`;

const SUB_SKILL_EDITOR_STREAM = `subscription OnSkillEditorStreamEvent($owner: String!) {\n  onSkillEditorStreamEvent(owner: $owner) {\n    eventId\n    owner\n    sessionId\n    flowgramId\n    eventType\n    payload\n    timestamp\n  }\n}`;  // Note: owner is String! not ID!

let activeSocket: WebSocket | null = null;
let active = false;
let userStoreUnsubscribe: (() => void) | null = null;
let currentA2AChannelId: string | null = null;
let a2aSubscriptionId: string | null = null;

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

const sendStop = (ws: WebSocket, id: string) => {
  ws.send(JSON.stringify({
    id,
    type: 'stop'
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
  console.log('[AppSyncSubscriptions] emitAccountNotification:', notification);
  eventBus.emit('account:notification', notification);
  
  // Handle ad banner notifications
  const ntype = notification?.ntype || '';
  if (ntype === 'AD_BANNER' || ntype === 'WS_TEST') {
    const adStore = useAdStore.getState();
    const message = notification?.message || notification?.title || '';
    const payload = typeof notification?.payload === 'string' 
      ? JSON.parse(notification.payload) 
      : notification?.payload || {};
    
    // Set banner ad with 60 second expiry (or from payload)
    const durationMs = payload?.durationMs || 60000;
    adStore.setBannerAd({
      id: notification?.id || `ad-${Date.now()}`,
      text: message,
      expiresAt: Date.now() + durationMs,
    });
    console.log('[AppSyncSubscriptions] Set banner ad:', message);
    
    // If payload has popup HTML, set popup ad too
    if (payload?.popupHtml) {
      adStore.setPopupAd({
        id: notification?.id || `popup-${Date.now()}`,
        htmlContent: payload.popupHtml,
        expiresAt: Date.now() + durationMs,
      });
    }
  }
};

const emitA2AMessage = (message: any) => {
  eventBus.emit('a2a:message', message);
};

const emitTaskStatus = (taskStatus: any) => {
  eventBus.emit('task:status', taskStatus);
};

const emitSkillEditorStreamEvent = (evt: any) => {
  console.log('[AppSyncSubscriptions] emitSkillEditorStreamEvent called with:', evt);
  const eventType = String(evt?.eventType || '').trim();
  const sessionId = String(evt?.sessionId || '').trim();
  const payload = maybeParseAwsJson(evt?.payload);

  console.log('[AppSyncSubscriptions] parsed event:', { eventType, sessionId, payload });

  if (!eventType) {
    console.log('[AppSyncSubscriptions] No eventType, ignoring');
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
  // Handle skill editor log events from cloud worker
  if (eventType === 'skill_editor.log') {
    const level = String(payload?.level || 'log').toLowerCase();
    const message = String(payload?.message || '');
    const entry = {
      type: level as 'log' | 'warning' | 'error',
      text: message,
      timestamp: payload?.timestamp || Date.now(),
      nodeId: payload?.node_id,
    };
    console.log('[AppSyncSubscriptions] skill_editor.log received, emitting to skill-editor:log', entry);
    eventBus.emit('skill-editor:log', entry);
    return;
  }
};

// Internal function to actually create the WebSocket connection
const connectWebSocket = (owner: string) => {
  if (active) {
    console.log('[AppSyncSubscriptions] Already connected, skipping');
    return;
  }

  const env = getEnv();
  const settings = useSettingsStore.getState().settings;

  const wsEndpoint = (settings?.ws_api_endpoint || env.VITE_APPSYNC_WS_ENDPOINT || DEFAULT_WS_ENDPOINT).trim();
  const wsHost = (settings?.ws_api_host || env.VITE_APPSYNC_WS_HOST || DEFAULT_WS_HOST).trim();
  const apiKey = (settings?.wan_api_key || env.VITE_APPSYNC_API_KEY || '').trim();

  const channelId = (env.VITE_A2A_CHANNEL_ID || '').trim();
  const acctSiteID = (env.VITE_ACCT_SITE_ID || `site-${owner}`).trim();
  const taskRunner = (env.VITE_TASK_RUNNER || owner || '').trim();

  console.log('[AppSyncSubscriptions] Connecting WebSocket with config:', {
    wsEndpoint,
    wsHost,
    apiKey: apiKey ? `${apiKey.substring(0, 8)}...` : 'MISSING',
    channelId,
    owner,
    acctSiteID,
    taskRunner,
  });

  if (!apiKey) {
    logger.warn('[AppSyncSubscriptions] Missing API key; AppSync subscriptions disabled');
    
    // In desktop mode (no API key), connect to local WebSocket instead
    // The Python backend subscribes to AppSync and forwards notifications via local WebSocket
    console.log('[AppSyncSubscriptions] Attempting to connect local WebSocket for desktop mode...');
    initWebSocketEventListeners();
    // Force=true to bypass shouldUseLocalWebSocket check - we already know we need it
    localWebSocketClient.connect(true).then(connected => {
      if (connected) {
        console.log('[AppSyncSubscriptions] ✅ Local WebSocket connected - will receive push notifications via local server');
      } else {
        console.log('[AppSyncSubscriptions] ⚠️ Local WebSocket not connected - push notifications may not work');
      }
    }).catch(err => {
      console.error('[AppSyncSubscriptions] Local WebSocket connection error:', err);
    });
    return;
  }

  if (!owner) {
    console.log('[AppSyncSubscriptions] No owner yet, waiting for login...');
    return;
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
        console.log('[AppSyncSubscriptions] Starting skill editor subscription with owner:', owner);
        sendStart(ws, subscriptionIds.skillEditorStream, SUB_SKILL_EDITOR_STREAM, { owner }, headers);
      } else {
        console.warn('[AppSyncSubscriptions] No owner provided; skill editor subscription skipped');
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

    if (messageData.type === 'start_ack') {
      console.log('[AppSyncSubscriptions] Subscription started:', messageData.id);
      return;
    }

    if (messageData.type === 'data') {
      const payload = messageData.payload?.data || {};
      console.log('[AppSyncSubscriptions] Received data message, keys:', Object.keys(payload));
      if (payload.onA2AMessageReceived) {
        console.log('[AppSyncSubscriptions] onA2AMessageReceived:', payload.onA2AMessageReceived);
        emitA2AMessage(payload.onA2AMessageReceived);
      }
      if (payload.onAccountNotification) {
        console.log('[AppSyncSubscriptions] onAccountNotification:', payload.onAccountNotification);
        emitAccountNotification(payload.onAccountNotification);
      }
      if (payload.onAgentSceneEvent) {
        console.log('[AppSyncSubscriptions] onAgentSceneEvent:', payload.onAgentSceneEvent);
        emitAgentSceneEvent(payload.onAgentSceneEvent);
      }
      if (payload.onSceneComplete) {
        console.log('[AppSyncSubscriptions] onSceneComplete:', payload.onSceneComplete);
        emitSceneComplete(payload.onSceneComplete);
      }
      if (payload.onTaskStatus) {
        console.log('[AppSyncSubscriptions] onTaskStatus:', payload.onTaskStatus);
        emitTaskStatus(payload.onTaskStatus);
      }
      if (payload.onSkillEditorStreamEvent) {
        console.log('[AppSyncSubscriptions] >>> onSkillEditorStreamEvent RECEIVED <<<', payload.onSkillEditorStreamEvent);
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
};

// Main entry point - subscribes to user store and connects when user logs in
export const startWebSubscriptions = () => {
  console.log('[AppSyncSubscriptions] startWebSubscriptions called');
  
  // Check if already have a user
  const currentUsername = useUserStore.getState().username;
  if (currentUsername) {
    console.log('[AppSyncSubscriptions] User already logged in:', currentUsername);
    connectWebSocket(currentUsername);
  } else {
    console.log('[AppSyncSubscriptions] No user yet, will connect after login');
  }

  // Subscribe to user store changes to connect when user logs in
  if (!userStoreUnsubscribe) {
    userStoreUnsubscribe = useUserStore.subscribe((state, prevState) => {
      const newUsername = state.username;
      const oldUsername = prevState?.username;
      
      console.log('[AppSyncSubscriptions] User state changed:', { oldUsername, newUsername });
      
      if (newUsername && newUsername !== oldUsername) {
        // User logged in - connect subscriptions
        console.log('[AppSyncSubscriptions] User logged in, connecting subscriptions for:', newUsername);
        // Close existing connection if any
        if (active) {
          stopWebSubscriptions();
        }
        connectWebSocket(newUsername);
      } else if (!newUsername && oldUsername) {
        // User logged out - disconnect subscriptions
        console.log('[AppSyncSubscriptions] User logged out, disconnecting subscriptions');
        stopWebSubscriptions();
      }
    });
  }

  return () => {
    if (activeSocket && (activeSocket.readyState === WebSocket.OPEN || activeSocket.readyState === WebSocket.CONNECTING)) {
      activeSocket.close(1000, 'AppSync subscriptions closed');
    }
    active = false;
    activeSocket = null;
    if (userStoreUnsubscribe) {
      userStoreUnsubscribe();
      userStoreUnsubscribe = null;
    }
  };
};

export const stopWebSubscriptions = () => {
  if (activeSocket && (activeSocket.readyState === WebSocket.OPEN || activeSocket.readyState === WebSocket.CONNECTING)) {
    activeSocket.close(1000, 'AppSync subscriptions stopped');
  }
  active = false;
  activeSocket = null;
};

/**
 * Subscribe to A2A messages for a specific channel
 * Call this when entering a chat to receive real-time messages
 * @param channelId The channel ID to subscribe to (e.g., "email~agentId")
 */
export const subscribeToA2AChannel = (channelId: string) => {
  console.log('[AppSyncSubscriptions] subscribeToA2AChannel called with:', channelId);
  
  if (!channelId) {
    console.warn('[AppSyncSubscriptions] No channelId provided');
    return;
  }
  
  // If already subscribed to this channel, skip
  if (currentA2AChannelId === channelId) {
    console.log('[AppSyncSubscriptions] Already subscribed to channel:', channelId);
    return;
  }
  
  // If socket not ready, log warning
  if (!activeSocket || activeSocket.readyState !== WebSocket.OPEN) {
    console.warn('[AppSyncSubscriptions] WebSocket not ready, cannot subscribe to A2A channel');
    return;
  }
  
  const env = getEnv();
  const settings = useSettingsStore.getState().settings;
  const wsHost = (settings?.ws_api_host || env.VITE_APPSYNC_WS_HOST || DEFAULT_WS_HOST).trim();
  const apiKey = (settings?.wan_api_key || env.VITE_APPSYNC_API_KEY || '').trim();
  
  const headers = {
    host: wsHost,
    'x-api-key': apiKey,
  };
  
  // Unsubscribe from previous channel if any
  if (a2aSubscriptionId && currentA2AChannelId) {
    console.log('[AppSyncSubscriptions] Unsubscribing from previous channel:', currentA2AChannelId);
    sendStop(activeSocket, a2aSubscriptionId);
  }
  
  // Subscribe to new channel
  a2aSubscriptionId = `sub-a2a-${Date.now()}`;
  currentA2AChannelId = channelId;
  console.log('[AppSyncSubscriptions] Starting A2A subscription for channel:', channelId, 'id:', a2aSubscriptionId);
  sendStart(activeSocket, a2aSubscriptionId, SUB_A2A, { channelId }, headers);
};

/**
 * Unsubscribe from current A2A channel
 */
export const unsubscribeFromA2AChannel = () => {
  if (a2aSubscriptionId && activeSocket && activeSocket.readyState === WebSocket.OPEN) {
    console.log('[AppSyncSubscriptions] Unsubscribing from A2A channel:', currentA2AChannelId);
    sendStop(activeSocket, a2aSubscriptionId);
  }
  a2aSubscriptionId = null;
  currentA2AChannelId = null;
};
