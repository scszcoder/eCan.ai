/**
 * Skill Editor Chat Service
 * 
 * Provides IPC communication for the skill editor chat feature.
 * Handles sending messages, managing sessions, and receiving responses.
 */

import { ipcClient } from '../../../services/ipc';
import { IPCResponse } from '../../../services/ipc/types';
import {
  ChatAttachment,
  CanvasPosition,
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
      const response: IPCResponse = await ipcClient.invoke('skill_editor.chat.create_session', {
        name,
        flowgramId,
      });
      
      if (response.status === 'success' && response.result) {
        const result = response.result as { session: ChatSession };
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
      const response: IPCResponse = await ipcClient.invoke('skill_editor.chat.get_sessions', {});
      
      if (response.status === 'success' && response.result) {
        const result = response.result as { sessions: ChatSession[] };
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
      const response: IPCResponse = await ipcClient.invoke('skill_editor.chat.get_history', {
        sessionId,
        limit,
        offset,
      });
      
      if (response.status === 'success' && response.result) {
        const result = response.result as { messages: ChatMessage[] };
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
   * Send a chat message and get AI response
   */
  async sendMessage(
    sessionId: string,
    content: string,
    attachments?: ChatAttachment[],
    canvasContext?: CanvasContext
  ): Promise<{ message: ChatMessage; sessionId: string; sessionName: string } | null> {
    console.log('[SkillEditorChat] Sending message:', { sessionId, contentLength: content.length, hasAttachments: !!attachments?.length, hasCanvasContext: !!canvasContext });
    try {
      const response: IPCResponse = await ipcClient.invoke('skill_editor.chat.send_message', {
        sessionId,
        content,
        attachments,
        canvasContext,
      }, { timeout: 60000 }); // 60 second timeout for LLM responses
      console.log('[SkillEditorChat] Message response received:', { status: response.status });
      
      if (response.status === 'success' && response.result) {
        return response.result as { message: ChatMessage; sessionId: string; sessionName: string };
      }
      
      console.error('[SkillEditorChat] Failed to send message:', response.error);
      return null;
    } catch (error) {
      console.error('[SkillEditorChat] Error sending message:', error);
      return null;
    }
  }
  
  /**
   * Cancel ongoing LLM generation
   */
  async cancelGeneration(sessionId: string): Promise<boolean> {
    try {
      const response: IPCResponse = await ipcClient.invoke('skill_editor.chat.cancel_generation', {
        sessionId,
      });
      
      if (response.status === 'success' && response.result) {
        const result = response.result as { cancelled: boolean };
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
      const response: IPCResponse = await ipcClient.invoke('skill_editor.chat.delete_session', {
        sessionId,
      });
      
      if (response.status === 'success' && response.result) {
        const result = response.result as { deleted: boolean };
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
