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
    const routineEvents = ['skill_editor_log'];
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
      
      default:
        logger.warn(`[UnifiedEventHandler] Unknown event type: ${type}`);
    }
  }

  // ==================== Skill Editor Chat Handlers ====================

  private handleSkillEditorChatChunk(event: StandardizedEvent): void {
    const { sessionId, messageId, chunk, chunkIndex } = event.payload;
    
    eventBus.emit('skill_editor:chat:stream_chunk', {
      sessionId: sessionId || event.sessionId,
      messageId,
      chunk,
      chunkIndex,
      source: event.source
    });
  }

  private handleSkillEditorChatEnd(event: StandardizedEvent): void {
    const { sessionId, messageId, fullContent } = event.payload;
    
    eventBus.emit('skill_editor:chat:stream_end', {
      sessionId: sessionId || event.sessionId,
      messageId,
      fullContent,
      source: event.source
    });
  }

  private handleSkillEditorChatError(event: StandardizedEvent): void {
    const { sessionId, code, message } = event.payload;
    
    eventBus.emit('skill_editor:chat:error', {
      sessionId: sessionId || event.sessionId,
      code,
      message,
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
