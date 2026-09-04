/**
 * Unified Event Handler
 * 
 * Centralizes event processing from multiple sources:
 * - AppSync WebSocket subscriptions (cloud)
 * - Local WebSocket (desktop mode)
 * - IPC (Python backend)
 * 
 * This eliminates duplicate event handling logic across the codebase.
 */

import { eventBus } from '@/utils/eventBus';
import { logger } from '@/utils/logger';
import { useAdStore } from '@/stores/adStore';
import i18n from '@/i18n';

export type EventSource = 'appsync' | 'local-ws' | 'ipc';

export interface StandardizedEvent {
  type: string;
  payload: any;
  source: EventSource;
  timestamp: number;
  sessionId?: string;
}

/**
 * Unified Event Handler Class
 * Routes events from different sources to appropriate handlers
 */
export class UnifiedEventHandler {
  private static instance: UnifiedEventHandler;

  private constructor() {}

  private humanizeSkillEditorError(message: string): string {
    const raw = String(message || '').trim();
    if (!raw) return raw;

    return raw;
  }

  static getInstance(): UnifiedEventHandler {
    if (!UnifiedEventHandler.instance) {
      UnifiedEventHandler.instance = new UnifiedEventHandler();
    }
    return UnifiedEventHandler.instance;
  }

  /**
   * Main entry point for all events
   */
  handle(event: StandardizedEvent): void {
    const { type, source } = event;
    
    // Only log non-routine events to reduce noise
    const routineEvents = ['skill_editor_log', 'update_skill_run_stat', 'subscribed'];
    if (!routineEvents.includes(type)) {
      logger.debug(`[UnifiedEventHandler] Processing event: ${type} from ${source}`);
    }

    // Route to specific handler based on event type
    switch (type) {
      // Skill Editor Chat Streaming
      case 'skill_editor.chat.stream_chunk':
        this.handleSkillEditorChatChunk(event);
        break;
      
      case 'skill_editor.chat.stream_end':
        this.handleSkillEditorChatEnd(event);
        break;
      
      case 'skill_editor.chat.error':
        this.handleSkillEditorChatError(event);
        break;
      
      // Skill Editor Events (canvas commands, etc.)
      case 'skill_editor.event':
        this.handleSkillEditorEvent(event);
        break;
      
      case 'skill_editor.log':
      case 'skill_editor_log':  // Support both formats (dot and underscore)
        this.handleSkillEditorLog(event);
        break;
      
      // Skill Run Status
      case 'update_skill_run_stat':
        this.handleSkillRunStat(event);
        break;
      
      case 'update_tasks_stat':
        this.handleTasksStat(event);
        break;
      
      // Chat Events
      case 'push_chat_message':
        this.handleChatMessage(event);
        break;
      
      case 'push_chat_notification':
        this.handleChatNotification(event);
        break;
      
      // LightRAG Events
      case 'lightrag.queryStream.chunk':
        this.handleLightRagChunk(event);
        break;
      
      case 'lightrag.queryStream.done':
        this.handleLightRagDone(event);
        break;
      
      case 'lightrag.queryStream.error':
        this.handleLightRagError(event);
        break;
      
      // Organization/Agent Updates
      case 'update_org_agents':
        this.handleOrgAgentsUpdate(event);
        break;
      
      // Account Info (routine event, no action needed)
      case 'push_account_info':
        logger.debug('[UnifiedEventHandler] push_account_info event received and handled (routine heartbeat)');
        // This is a routine heartbeat/info event from backend, no further action needed
        break;

      // LightRAG provider cache invalidated — emitted by
      // ``gui/manager/provider_settings_helper.py`` after a provider
      // save/clear rotates an eCanAI key or parser engine. The
      // Knowledge → Settings tab listens on the eventBus channel
      // ``lightrag:providersUpdated`` to re-pull parser field values
      // and bump the ragStore version (see LightRAGPorted/index.tsx).
      case 'lightrag.providersUpdated':
        eventBus.emit('lightrag:providersUpdated', event.payload);
        break;

      // LightRAG restart outcome — emitted by
      // ``_broadcast_lightrag_restart_notice`` after a provider
      // rotation triggers a child-process restart. ``status`` is one
      // of ``ok`` | ``skipped`` | ``failed``; UIs surface it as a
      // toast. Forwarded via eventBus so callers don't have to
      // subscribe to the raw WS frame.
      case 'lightrag.restartNotice':
        eventBus.emit('lightrag:restartNotice', event.payload);
        break;

      // WebSocket subscription confirmation - no action needed
      case 'subscribed':
        break;
      
      // WebSocket ping/pong heartbeat - no action needed, just consume silently
      case 'pong':
      case 'ping':
        // These are routine heartbeat events from WebSocket keepalive
        // No logging needed to reduce noise
        return;
      
      // Onboarding events - route to onboarding service
      case 'onboarding_message':
        // Forward to onboarding service via eventBus
        eventBus.emit('onboarding-message', event.payload);
        return;
      
      // Agent status update events - route to agent store/listeners
      case 'update_agents_status':
        // Emit event for agent store components to handle
        eventBus.emit('agents-status-update', event.payload);
        return;

      case 'update_home_agents':
        // Emit event for home agents components to handle
        eventBus.emit('home-agents-update', event.payload);
        return;
      
      default:
        logger.warn(`[UnifiedEventHandler] Unknown event type: ${type}`);
    }
  }

  // ==================== Skill Editor Chat Handlers ====================

  private handleSkillEditorChatChunk(event: StandardizedEvent): void {
    const { sessionId, messageId, chunk, chunkIndex } = event.payload;
    
    // Skip empty chunks (e.g. "streaming started" signals with no content)
    if (!chunk && !messageId) {
      return;
    }
    
    eventBus.emit('skill_editor:chat:stream_chunk', {
      sessionId: sessionId || event.sessionId,
      messageId,
      chunk,
      chunkIndex,
      source: event.source
    });
  }

  private handleSkillEditorChatEnd(event: StandardizedEvent): void {
    const { sessionId, messageId, fullContent, ...rest } = event.payload;
    
    eventBus.emit('skill_editor:chat:stream_end', {
      sessionId: sessionId || event.sessionId,
      messageId,
      fullContent,
      source: event.source,
      ...rest,  // forward clarification, a2ui, plan, state, etc.
    });
  }

  private handleSkillEditorChatError(event: StandardizedEvent): void {
    const { sessionId, code, message } = event.payload;
    const friendlyMessage = this.humanizeSkillEditorError(message);
    
    eventBus.emit('skill_editor:chat:error', {
      sessionId: sessionId || event.sessionId,
      code,
      message: friendlyMessage,
      rawMessage: message,
      source: event.source
    });
  }

  // ==================== Skill Editor Event Handlers ====================

  private handleSkillEditorEvent(event: StandardizedEvent): void {
    const { sessionId, type: eventType, payload, commandType } = event.payload;
    
    eventBus.emit('skill_editor:event', {
      sessionId: sessionId || event.sessionId,
      type: eventType || commandType,
      payload,
      source: event.source
    });
  }

  private handleSkillEditorLog(event: StandardizedEvent): void {
    // Support both formats:
    // - Backend IPC: { type: 'log', text: 'message' }
    // - AppSync/WS: { level: 'log', message: 'text', node_id: 'xxx' }
    const { level, type, message, text, timestamp, node_id } = event.payload;
    
    const logLevel = level || type || 'log';
    const logText = message || text || '';
    
    const entry = {
      type: logLevel.toLowerCase() as 'log' | 'warning' | 'error',
      text: logText,
      timestamp: timestamp || event.timestamp,
      nodeId: node_id,
      source: event.source
    };
    
    eventBus.emit('skill-editor:log', entry);

    // Detect LLM quota-limit errors and surface them on the main banner.
    // Matches browser-use style messages such as:
    //   "14 failures: ValueError, preview contains: Upstream openai 429 ...
    //    You exceeded your current quota, please check your plan and billing details"
    try {
      detectLlmQuotaError(logText);
    } catch (err) {
      logger.debug('[UnifiedEventHandler] quota-error detection failed:', err);
    }
  }

  // ==================== Skill Run Status Handlers ====================

  private handleSkillRunStat(event: StandardizedEvent): void {
    const payload = event.payload;
    
    // Normalize field names (handle both camelCase and snake_case)
    const normalizedPayload = {
      agentTaskId: payload.agentTaskId,
      currentNode: payload.currentNode || payload.current_node,
      status: payload.status,
      langgraphState: payload.langgraphState || payload.nodeState,
      timestamp: payload.timestamp || event.timestamp,
      source: event.source
    };
    
    eventBus.emit('ws:update_skill_run_stat', normalizedPayload);
  }

  private handleTasksStat(event: StandardizedEvent): void {
    const { agentTaskId, langgraphState, timestamp } = event.payload;
    
    eventBus.emit('ws:update_tasks_stat', {
      agentTaskId,
      langgraphState,
      timestamp: timestamp || event.timestamp,
      source: event.source
    });
  }

  // ==================== Chat Handlers ====================

  private handleChatMessage(event: StandardizedEvent): void {
    const { chatId, message } = event.payload;
    
    eventBus.emit('ws:push_chat_message', {
      chatId,
      message,
      source: event.source
    });
  }

  private handleChatNotification(event: StandardizedEvent): void {
    const { chatId, content, isRead, timestamp, uid } = event.payload;
    
    eventBus.emit('ws:push_chat_notification', {
      chatId,
      content,
      isRead,
      timestamp: timestamp || event.timestamp,
      uid,
      source: event.source
    });
  }

  // ==================== LightRAG Handlers ====================

  private handleLightRagChunk(event: StandardizedEvent): void {
    const { id, chunk } = event.payload;
    
    eventBus.emit('lightrag:queryStream:chunk', {
      id,
      chunk,
      source: event.source
    });
  }

  private handleLightRagDone(event: StandardizedEvent): void {
    const { id } = event.payload;
    
    eventBus.emit('lightrag:queryStream:done', {
      id,
      source: event.source
    });
  }

  private handleLightRagError(event: StandardizedEvent): void {
    const { id, error } = event.payload;
    
    eventBus.emit('lightrag:queryStream:error', {
      id,
      error,
      source: event.source
    });
  }

  // ==================== Organization/Agent Handlers ====================

  private handleOrgAgentsUpdate(event: StandardizedEvent): void {
    eventBus.emit('org-agents-update', {
      source: event.source,
      timestamp: event.timestamp,
      data: event.payload
    });
  }
}

// Export singleton instance
export const unifiedEventHandler = UnifiedEventHandler.getInstance();

// ==================== LLM Quota-Error Detection ====================

// Patterns that identify a billing/quota exhaustion error from any LLM
// provider. We match if the log contains either the explicit phrase
// "exceeded your current quota" OR the combination of an HTTP 429 status
// with a billing/quota-ish keyword, so variants across providers trigger.
const QUOTA_EXACT_RE = /exceeded\s+your\s+current\s+quota/i;
const QUOTA_GENERIC_RE = /\b429\b[\s\S]{0,200}?(quota|billing|insufficient_quota|rate[_\s-]?limit)/i;

// Throttle: once we've shown the banner, don't spam the store on every
// subsequent log line carrying the same error. A 60s cooldown matches the
// default banner duration below.
let lastQuotaBannerAt = 0;
const QUOTA_BANNER_COOLDOWN_MS = 60_000;
const QUOTA_BANNER_DURATION_MS = 60_000;

function detectLlmQuotaError(logText: string): void {
  if (!logText || typeof logText !== 'string') return;
  if (!QUOTA_EXACT_RE.test(logText) && !QUOTA_GENERIC_RE.test(logText)) return;

  const now = Date.now();
  if (now - lastQuotaBannerAt < QUOTA_BANNER_COOLDOWN_MS) return;
  lastQuotaBannerAt = now;

  // Prefer i18n translation but fall back to literal strings if the keys
  // are missing (i18n.t returns the key itself when unresolved).
  const key = 'common.llm_quota_limit_banner';
  const translated = i18n.t(key);
  const fallback = (i18n.language || '').toLowerCase().startsWith('zh')
    ? 'AI模型额度已用尽，请检查账单或更换模型'
    : 'LLM Reached Quota Limit';
  const text = translated && translated !== key ? translated : fallback;

  useAdStore.getState().setErrorBanner({
    id: `llm-quota-${now}`,
    text,
    variant: 'error',
    expiresAt: now + QUOTA_BANNER_DURATION_MS,
  });
  logger.warn('[UnifiedEventHandler] LLM quota-limit error detected; error banner raised');
}

/**
 * Helper function to create standardized event from raw data
 */
export function createStandardizedEvent(
  type: string,
  payload: any,
  source: EventSource,
  sessionId?: string
): StandardizedEvent {
  return {
    type,
    payload,
    source,
    timestamp: Date.now(),
    sessionId
  };
}
