/**
 * Skill Editor Chat Service
 * 
 * Provides IPC communication for the skill editor chat feature.
 * Handles sending messages, managing sessions, and receiving responses.
 */

import { IPCAPI } from '../../../services/ipc/api';
import { localWebSocketClient } from '../../../services/web/localWebSocketClient';
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
      const response = await IPCAPI.getInstance().executeRequest<{ session: ChatSession }>(
        'skill_editor.chat.create_session',
        { name, flowgramId }
      );
      
      if (response.success && response.data) {
        const result = response.data as { session: ChatSession };
        console.log('[SkillEditorChat] Session created:', result.session.id);
        return result.session;
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
      const response = await IPCAPI.getInstance().executeRequest<{ sessions: ChatSession[] }>(
        'skill_editor.chat.get_sessions',
        {}
      );
      
      if (response.success && response.data) {
        const result = response.data as { sessions: ChatSession[] };
        return result.sessions;
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
      const response = await IPCAPI.getInstance().executeRequest<{ messages: ChatMessage[] }>(
        'skill_editor.chat.get_history',
        { sessionId, limit, offset }
      );
      
      if (response.success && response.data) {
        const result = response.data as { messages: ChatMessage[] };
        return result.messages;
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
      const response = await IPCAPI.getInstance().executeRequest<ChatMessageResponse>(
        'skill_editor.chat.send_message',
        { sessionId, content, attachments, canvasContext },
        300000
      );
      console.log('[SkillEditorChat] Message response received:', { success: response.success });
      
      if (response.success && response.data) {
        return response.data as ChatMessageResponse;
      }
      
      console.error('[SkillEditorChat] Failed to send message:', response.error);
      return null;
    } catch (error) {
      const errorMessage = error instanceof Error ? `${error.name}: ${error.message}` : JSON.stringify(error);
      console.error('[SkillEditorChat] Error sending message:', errorMessage, error);
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
      const response = await IPCAPI.getInstance().executeRequest<ChatMessageResponse>(
        'skill_editor.chat.send_message',
        { sessionId, content, canvasContext, clarificationResponses },
        300000
      );
      console.log('[SkillEditorChat] Clarification response received:', { success: response.success });
      
      if (response.success && response.data) {
        return response.data as ChatMessageResponse;
      }
      
      console.error('[SkillEditorChat] Failed to send clarification:', response.error);
      return null;
    } catch (error) {
      const errorMessage = error instanceof Error ? `${error.name}: ${error.message}` : JSON.stringify(error);
      console.error('[SkillEditorChat] Error sending clarification:', errorMessage, error);
      return null;
    }
  }
  
  /**
   * Cancel ongoing LLM generation
   */
  async cancelGeneration(sessionId: string): Promise<boolean> {
    try {
      const response = await IPCAPI.getInstance().executeRequest<{ cancelled: boolean }>(
        'skill_editor.chat.cancel_generation',
        { sessionId }
      );
      
      if (response.success && response.data) {
        const result = response.data as { cancelled: boolean };
        return result.cancelled;
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
      const response = await IPCAPI.getInstance().executeRequest<{ deleted: boolean }>(
        'skill_editor.chat.delete_session',
        { sessionId }
      );
      
      if (response.success && response.data) {
        const result = response.data as { deleted: boolean };
        return result.deleted;
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
