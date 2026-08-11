/**
 * Skill Editor Chat Service
 * 
 * Provides API communication for the skill editor chat feature.
 * Handles sending messages, managing sessions, and receiving responses.
 * 
 * Uses apiRouter for unified routing:
 * - Web mode: GraphQL/AppSync
 * - Desktop mode (VITE_IPC_MODE): IPC
 */

import { apiRouter } from '../../../services/api/api-router';
import { GRAPHQL_QUERIES, GRAPHQL_MUTATIONS } from '../../../services/api/api-config';
import { localWebSocketClient } from '../../../services/web/localWebSocketClient';
import { useUserStore } from '../../../stores/userStore';
import { userStorageManager } from '../../../services/storage/UserStorageManager';
import {
  ChatAttachment,
  CanvasPosition,
  ClarificationQuestion,
  ImplementationPlan,
  Flowgram,
  ValidationResult,
  PipelineState,
  ChatMessageResponse,
} from '../types';

// ============================================================
// Helpers
// ============================================================

/** Resolve the current user's identifier from Zustand store or localStorage.
 *  Prefer email so it matches the Lambda owner (Cognito email claims)
 *  and the AppSync subscription owner filter. */
const resolveUserId = (): string | null => {
  const info = userStorageManager.getUserInfo();
  return info?.email || info?.username || useUserStore.getState().username || null;
};

/** Parse an AWSJSON field (string → object). Returns the parsed value or the original if already parsed / null. */
const parseAwsJson = <T>(value: unknown): T | undefined => {
  if (value == null) return undefined;
  if (typeof value === 'object') return value as T; // already parsed
  if (typeof value === 'string') {
    try { return JSON.parse(value) as T; } catch { return undefined; }
  }
  return undefined;
};

/** Deserialise AWSJSON fields that AppSync returns as JSON strings. */
const deserialiseResponse = (raw: ChatMessageResponse): ChatMessageResponse => {
  return {
    ...raw,
    clarification: parseAwsJson<ClarificationQuestion[]>(raw.clarification) ?? undefined,
    plan: parseAwsJson<ImplementationPlan>(raw.plan) ?? undefined,
    flowgram: parseAwsJson<Flowgram>(raw.flowgram) ?? undefined,
    validation: parseAwsJson<ValidationResult>(raw.validation) ?? undefined,
  };
};

// ============================================================
// Types
// ============================================================

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  attachments?: ChatAttachment[];
  metadata?: Record<string, unknown>;
}

export interface ChatSession {
  id: string;
  name: string;
  flowgramId?: string;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
}

export interface CanvasContext {
  nodes: Array<{
    id: string;
    type: string;
    label: string;
    position: CanvasPosition;
  }>;
  edges: Array<{
    id: string;
    source: string;
    target: string;
  }>;
  skillName?: string;
  skillId?: string;
  lastFlowgramJson?: any;
}

// ============================================================
// Service Class
// ============================================================

class SkillEditorChatService {
  private static instance: SkillEditorChatService | null = null;
  
  private constructor() {}
  
  static getInstance(): SkillEditorChatService {
    if (!SkillEditorChatService.instance) {
      SkillEditorChatService.instance = new SkillEditorChatService();
    }
    return SkillEditorChatService.instance;
  }
  
  /**
   * Create a new chat session
   */
  async createSession(name?: string, flowgramId?: string): Promise<ChatSession | null> {
    console.log('[SkillEditorChat] Creating session:', { name, flowgramId });
    try {
      const response = await apiRouter.execute<{ id: string; name: string; flowgramId?: string; createdAt: string; updatedAt: string }>(
        {
          method: 'skill_editor.chat.create_session',
          graphql: {
            mutation: GRAPHQL_MUTATIONS.CREATE_SKILL_EDITOR_CHAT_SESSION,
            resultPath: 'createSkillEditorChatSession'
          }
        },
        { input: { name, flowgramId } }
      );
      
      if (response.success && response.data) {
        const data = response.data;
        const session: ChatSession = {
          id: data.id,
          name: data.name,
          flowgramId: data.flowgramId,
          messages: [],
          createdAt: new Date(data.createdAt).getTime(),
          updatedAt: new Date(data.updatedAt).getTime()
        };
        console.log('[SkillEditorChat] Session created:', session.id);
        return session;
      }
      
      console.error('[SkillEditorChat] Failed to create session:', response.error);
      return null;
    } catch (error) {
      console.error('[SkillEditorChat] Error creating session:', error);
      return null;
    }
  }
  
  /**
   * Get all chat sessions
   */
  async getSessions(): Promise<ChatSession[]> {
    try {
      // Get user ID from storage
      const { userStorageManager } = await import('../../../services/storage/UserStorageManager');
      const userId = userStorageManager.getUsername() || '';
      
      const response = await apiRouter.execute<Array<{ id: string; name: string; flowgramId?: string; createdAt: string; updatedAt: string }>>(
        {
          method: 'skill_editor.chat.get_sessions',
          graphql: {
            query: GRAPHQL_QUERIES.GET_SKILL_EDITOR_CHAT_SESSIONS,
            resultPath: 'getSkillEditorChatSessions'
          }
        },
        { userId }
      );
      
      if (response.success && response.data) {
        // Backend returns {sessions: [], count: number}
        const responseData = response.data as any;
        const sessions = Array.isArray(responseData) ? responseData : (responseData.sessions || []);
        return sessions.map((s: any) => ({
          id: s.id,
          name: s.name,
          flowgramId: s.flowgramId,
          messages: Array.isArray(s.messages)
            ? s.messages.map((m: any) => ({
                id: m.id,
                role: m.role as 'user' | 'assistant' | 'system',
                content: m.content,
                timestamp: typeof m.timestamp === 'number' ? m.timestamp : new Date(m.timestamp).getTime(),
                attachments: m.attachments,
                metadata: m.metadata,
              }))
            : [],
          createdAt: typeof s.createdAt === 'number' ? s.createdAt : new Date(s.createdAt).getTime(),
          updatedAt: typeof s.updatedAt === 'number' ? s.updatedAt : new Date(s.updatedAt).getTime(),
        }));
      }
      
      console.error('[SkillEditorChat] Failed to get sessions:', response.error);
      return [];
    } catch (error) {
      console.error('[SkillEditorChat] Error getting sessions:', error);
      return [];
    }
  }
  
  /**
   * Get chat history for a session
   */
  async getHistory(sessionId: string, limit?: number, offset?: number): Promise<ChatMessage[]> {
    try {
      const response = await apiRouter.execute<Array<{ id: string; role: string; content: string; timestamp: string; attachments?: any[]; metadata?: any }>>(
        {
          method: 'skill_editor.chat.get_history',
          graphql: {
            query: GRAPHQL_QUERIES.GET_SKILL_EDITOR_CHAT_HISTORY,
            resultPath: 'getSkillEditorChatHistory'
          }
        },
        { sessionId, limit, offset }
      );
      
      if (response.success && response.data) {
        // Backend returns {messages: [...], total, sessionId}
        const responseData = response.data as any;
        const messages = Array.isArray(responseData) ? responseData : (responseData.messages || []);
        return messages.map((m: any) => ({
          id: m.id,
          role: m.role as 'user' | 'assistant' | 'system',
          content: m.content,
          timestamp: typeof m.timestamp === 'number' ? m.timestamp : new Date(m.timestamp).getTime(),
          attachments: m.attachments,
          metadata: m.metadata
        }));
      }
      
      console.error('[SkillEditorChat] Failed to get history:', response.error);
      return [];
    } catch (error) {
      console.error('[SkillEditorChat] Error getting history:', error);
      return [];
    }
  }
  
  /**
   * Subscribe to streaming events for a session via local WebSocket
   */
  subscribeToSession(sessionId: string): void {
    if (localWebSocketClient.shouldUseLocalWebSocket()) {
      localWebSocketClient.connect().then(connected => {
        if (connected) {
          localWebSocketClient.subscribeToSession(sessionId);
          console.log('[SkillEditorChat] Subscribed to local WebSocket for session:', sessionId);
        }
      });
    }
  }

  /**
   * Unsubscribe from streaming events for a session
   */
  unsubscribeFromSession(sessionId: string): void {
    if (localWebSocketClient.shouldUseLocalWebSocket()) {
      localWebSocketClient.unsubscribeFromSession(sessionId);
      console.log('[SkillEditorChat] Unsubscribed from local WebSocket for session:', sessionId);
    }
  }

  /**
   * Send a chat message and get AI response
   */
  async sendMessage(
    sessionId: string,
    content: string,
    attachments?: ChatAttachment[],
    canvasContext?: CanvasContext
  ): Promise<ChatMessageResponse | null> {
    console.log('[SkillEditorChat] Sending message:', { sessionId, contentLength: content.length, hasAttachments: !!attachments?.length, hasCanvasContext: !!canvasContext });
    
    // Ensure we're subscribed to streaming events for this session
    this.subscribeToSession(sessionId);
    
    try {
      // Serialize AWSJSON fields as JSON strings for GraphQL
      const input: Record<string, any> = { sessionId, content };
      // Include userId so the backend can resolve the correct S3 user directory
      const userId = resolveUserId();
      if (userId) {
        input.userId = userId;
      }
      if (attachments && attachments.length > 0) {
        input.attachments = JSON.stringify(attachments);
      }
      if (canvasContext) {
        input.canvasContext = JSON.stringify(canvasContext);
      }
      
      const response = await apiRouter.execute<ChatMessageResponse>(
        {
          method: 'skill_editor.chat.send_message',
          graphql: {
            mutation: GRAPHQL_MUTATIONS.SEND_SKILL_EDITOR_CHAT_MESSAGE,
            resultPath: 'sendSkillEditorChatMessage'
          }
        },
        { input },
        { timeout: 300000 }
      );
      console.log('[SkillEditorChat] Message response received:', { success: response.success });
      
      if (response.success && response.data) {
        return deserialiseResponse(response.data as ChatMessageResponse);
      }
      
      // Re-throw timeout errors so the caller can handle them gracefully
      const errMsg = typeof response.error === 'object' && response.error?.message
        ? response.error.message
        : String(response.error || '');
      if (/timed?\s*out/i.test(errMsg)) {
        throw new Error(errMsg);
      }
      
      console.error('[SkillEditorChat] Failed to send message:', response.error);
      return null;
    } catch (error) {
      const errorMessage = error instanceof Error ? `${error.name}: ${error.message}` : JSON.stringify(error);
      // Re-throw timeout errors for the caller to show a friendly message
      if (/timed?\s*out/i.test(errorMessage)) {
        throw error;
      }
      console.error('[SkillEditorChat] Error sending message:', errorMessage, error);
      return null;
    }
  }
  
  /**
   * Execute a cloud-proposed `ecan` CLI command locally (desktop only).
   *
   * The cloud helper agent proposes agent/task CRUD as a structured command;
   * the local backend runs it (applying to the local DB + syncing to cloud) and
   * returns the CLI output, which the caller then posts back to the agent as
   * context. Web mode has no local CLI, so callers should gate on desktop.
   */
  async executeCommand(
    proposal: Record<string, unknown>,
  ): Promise<{ success: boolean; returnCode: number; stdout: string; stderr: string; command: string } | null> {
    try {
      const input: Record<string, any> = { proposal };
      const userId = resolveUserId();
      if (userId) {
        input.userId = userId;
      }
      const response = await apiRouter.execute<{ success: boolean; returnCode: number; stdout: string; stderr: string; command: string }>(
        { method: 'skill_editor.chat.execute_command' },
        { input },
        { timeout: 130000 }
      );
      if (response.success && response.data) {
        return response.data;
      }
      console.error('[SkillEditorChat] executeCommand failed:', response.error);
      return null;
    } catch (error) {
      console.error('[SkillEditorChat] executeCommand error:', error);
      return null;
    }
  }

  /**
   * Send a message with clarification responses
   */
  async sendMessageWithClarification(
    sessionId: string,
    content: string,
    clarificationResponses: Record<string, string[]>,
    canvasContext?: CanvasContext
  ): Promise<ChatMessageResponse | null> {
    console.log('[SkillEditorChat] Sending message with clarification:', { 
      sessionId, 
      contentLength: content.length, 
      numResponses: Object.keys(clarificationResponses).length 
    });
    try {
      // Serialize AWSJSON fields as JSON strings for GraphQL
      const input: Record<string, any> = { sessionId, content };
      // Include userId so the backend can resolve the correct S3 user directory
      const userId = resolveUserId();
      if (userId) {
        input.userId = userId;
      }
      if (canvasContext) {
        input.canvasContext = JSON.stringify(canvasContext);
      }
      if (clarificationResponses && Object.keys(clarificationResponses).length > 0) {
        input.clarificationResponses = JSON.stringify(clarificationResponses);
      }
      
      const response = await apiRouter.execute<ChatMessageResponse>(
        {
          method: 'skill_editor.chat.send_message',
          graphql: {
            mutation: GRAPHQL_MUTATIONS.SEND_SKILL_EDITOR_CHAT_MESSAGE,
            resultPath: 'sendSkillEditorChatMessage'
          }
        },
        { input },
        { timeout: 300000 }
      );
      console.log('[SkillEditorChat] Clarification response received:', { success: response.success });
      
      if (response.success && response.data) {
        return deserialiseResponse(response.data as ChatMessageResponse);
      }
      
      // Re-throw timeout errors so the caller can handle them gracefully
      const errMsg = typeof response.error === 'object' && response.error?.message
        ? response.error.message
        : String(response.error || '');
      if (/timed?\s*out/i.test(errMsg)) {
        throw new Error(errMsg);
      }
      
      console.error('[SkillEditorChat] Failed to send clarification:', response.error);
      return null;
    } catch (error) {
      const errorMessage = error instanceof Error ? `${error.name}: ${error.message}` : JSON.stringify(error);
      // Re-throw timeout errors for the caller to show a friendly message
      if (/timed?\s*out/i.test(errorMessage)) {
        throw error;
      }
      console.error('[SkillEditorChat] Error sending clarification:', errorMessage, error);
      return null;
    }
  }
  
  /**
   * Cancel ongoing LLM generation
   */
  async cancelGeneration(sessionId: string): Promise<boolean> {
    try {
      const response = await apiRouter.execute<boolean>(
        {
          method: 'skill_editor.chat.cancel_generation',
          graphql: {
            mutation: GRAPHQL_MUTATIONS.CANCEL_SKILL_EDITOR_CHAT_GENERATION,
            resultPath: 'cancelSkillEditorChatGeneration'
          }
        },
        { sessionId }
      );
      
      if (response.success) {
        return response.data === true;
      }
      
      return false;
    } catch (error) {
      console.error('[SkillEditorChat] Error cancelling generation:', error);
      return false;
    }
  }
  
  /**
   * Delete a chat session
   */
  async deleteSession(sessionId: string): Promise<boolean> {
    try {
      const response = await apiRouter.execute<boolean>(
        {
          method: 'skill_editor.chat.delete_session',
          graphql: {
            mutation: GRAPHQL_MUTATIONS.DELETE_SKILL_EDITOR_CHAT_SESSION,
            resultPath: 'deleteSkillEditorChatSession'
          }
        },
        { sessionId }
      );
      
      if (response.success) {
        const result = response.data as any;
        if (result === true) {
          return true;
        }
        if (result && typeof result === 'object') {
          return result.deleted === true || result.success === true;
        }
        return Boolean(result);
      }
      
      return false;
    } catch (error) {
      console.error('[SkillEditorChat] Error deleting session:', error);
      return false;
    }
  }
}

// Export singleton instance
export const skillEditorChatService = SkillEditorChatService.getInstance();

export default skillEditorChatService;
