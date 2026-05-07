/**
 * Unified Chat Service
 * 
 * Provides a unified chat API interface that routes to either:
 * - IPC (desktop mode): Uses Python backend via Qt WebChannel
 * - Cloud (web mode): Uses AppSync GraphQL API
 * 
 * This service maintains the same interface as the IPC chatApi,
 * allowing the Chat page to work seamlessly in both environments.
 */

import { isWebPlatform } from '@/config/platform';
import { cloudChatApi, A2AMessage, SendA2AMessageInput } from '@/services/api/cloudChatApi';
import { IPCAPI } from '@/services/ipc/api';
import { APIResponse } from '@/services/ipc/api';
import { logger } from '@/utils/logger';
import { Chat, Message, Attachment, FileInfo, FileContent, Member } from '@/pages/Chat/types/chat';

/**
 * Create error response matching APIResponse type
 */
function createErrorResponse<T>(message: string, code: string = 'CLOUD_ERROR'): APIResponse<T> {
  return {
    success: false,
    error: {
      code,
      message,
    }
  };
}

/**
 * Convert A2A message format to Chat page Message format
 */
function a2aMessageToChatMessage(a2aMsg: A2AMessage): Message {
  const textPart = a2aMsg.message.parts.find(p => p.type === 'text');
  const roleMap: Record<string, 'user' | 'assistant' | 'system' | 'agent'> = {
    'user': 'user',
    'assistant': 'assistant',
    'system': 'system',
    'agent': 'agent',
  };
  return {
    id: a2aMsg.id,
    chatId: a2aMsg.channelId,
    senderId: a2aMsg.senderId,
    senderName: a2aMsg.metadata?.senderName || a2aMsg.senderId,
    role: roleMap[a2aMsg.message.role] || 'user',
    content: textPart?.text || '',
    createAt: a2aMsg.timestamp ? new Date(a2aMsg.timestamp).getTime() : Date.now(),
    status: 'complete',
    attachments: [],
  };
}

/**
 * Convert Chat page Message to A2A message input
 */
function chatMessageToA2AInput(
  message: {
    chatId: string;
    role: string;
    content: string;
    senderId: string;
    createAt: string;
    id?: string;
    status?: string;
    senderName?: string;
    attachments?: Attachment[];
  },
  recipientId: string,
  sessionId?: string
): SendA2AMessageInput {
  return {
    channelId: message.chatId,
    sessionId: sessionId || cloudChatApi.generateSessionId(),
    senderId: message.senderId,
    recipientId,
    message: {
      role: message.role || 'user',
      parts: [{
        type: 'text',
        text: message.content
      }]
    },
    metadata: {
      senderName: message.senderName,
      originalId: message.id,
      createAt: message.createAt,
    },
    acceptedOutputModes: ['text']
  };
}

/**
 * Unified Chat API that works in both web and desktop environments
 */
export const unifiedChatService = {
  /**
   * Check if we're in web mode
   */
  isCloudMode(): boolean {
    return isWebPlatform();
  },

  /**
   * Get chats/threads for a user
   * In cloud mode, this fetches A2A message threads
   * In desktop mode, this uses IPC to get local chats
   */
  async getChats<T>(userId: string, deep?: boolean): Promise<APIResponse<T>> {
    if (this.isCloudMode()) {
      try {
        logger.info('[UnifiedChatService] Getting chats from cloud for user:', userId);
        
        // In cloud mode, we need to implement a way to get all channels for a user
        // For now, we'll return an empty list and let the user start new chats
        // TODO: Implement server-side getChatThreads query
        
        const threads = await cloudChatApi.getChatThreads(userId);
        
        // Convert to Chat format expected by the UI
        const chats: Chat[] = threads.map(thread => ({
          id: thread.id,
          name: thread.participantIds.filter(id => id !== userId).join(', '),
          type: 'private',
          members: thread.participantIds.map(id => ({
            userId: id,
            name: id,
            role: 'member'
          } as Member)),
          messages: [],
          unread: thread.unreadCount,
          lastMsg: thread.latestMessage?.message?.parts?.[0]?.text || '',
          lastMsgTime: thread.latestMessage?.timestamp ? new Date(thread.latestMessage.timestamp).getTime() : undefined,
          createdAt: '',
          updatedAt: '',
        }));
        
        return { success: true, data: chats as unknown as T };
      } catch (error) {
        logger.error('[UnifiedChatService] Error getting chats from cloud:', error);
        return createErrorResponse<T>(String(error));
      }
    } else {
      return IPCAPI.getInstance().chatApi.getChats<T>(userId, deep);
    }
  },

  /**
   * Search chats by text content
   */
  async searchChats<T>(userId: string, searchText: string, deep?: boolean): Promise<APIResponse<T>> {
    if (this.isCloudMode()) {
      try {
        logger.info('[UnifiedChatService] Searching chats from cloud:', searchText);
        // TODO: Implement cloud search - for now return empty
        return { success: true, data: [] as unknown as T };
      } catch (error) {
        logger.error('[UnifiedChatService] Error searching chats:', error);
        return createErrorResponse<T>(String(error));
      }
    } else {
      return IPCAPI.getInstance().chatApi.searchChats<T>(userId, searchText, deep);
    }
  },

  /**
   * Create a new chat/channel
   */
  async createChat<T>(chatData: any): Promise<APIResponse<T>> {
    if (this.isCloudMode()) {
      try {
        logger.info('[UnifiedChatService] Creating chat in cloud:', chatData);
        
        // In cloud mode, channels are created implicitly when first message is sent
        // Generate channel ID from participants
        const members = chatData.members || [];
        if (members.length < 2) {
          return createErrorResponse<T>('At least 2 members required');
        }
        
        const channelId = cloudChatApi.getChannelId(members[0].userId || members[0].id, members[1].userId || members[1].id);
        
        const chat: Chat = {
          id: channelId,
          name: chatData.name || members.map((m: any) => m.name).join(', '),
          type: chatData.type || 'private',
          members,
          messages: [],
          unread: 0,
          lastMsgTime: undefined,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        };

        // Also sync to local backend database to ensure chat exists for backend operations
        // This fixes the issue where chat_id exists in frontend but not in backend database
        try {
          logger.info('[UnifiedChatService] Syncing chat to local backend:', channelId);
          await IPCAPI.getInstance().chatApi.createChat<T>({
            id: channelId,
            members: members.map((m: any) => ({
              userId: m.userId || m.id,
              name: m.name,
              role: m.role || 'user',
              avatar: m.avatar,
              status: m.status || 'online',
              ext: m.ext || {},
              agentName: m.agentName || m.name
            })),
            name: chat.name,
            type: chat.type,
            avatar: chatData.avatar,
            agent_id: chatData.agent_id
          });
          logger.info('[UnifiedChatService] Chat synced to local backend successfully');
        } catch (syncError) {
          // Non-fatal: log but don't fail the operation
          logger.warn('[UnifiedChatService] Failed to sync chat to local backend:', syncError);
        }
        
        return { success: true, data: chat as unknown as T };
      } catch (error) {
        logger.error('[UnifiedChatService] Error creating chat:', error);
        return createErrorResponse<T>(String(error));
      }
    } else {
      return IPCAPI.getInstance().chatApi.createChat<T>(chatData);
    }
  },

  /**
   * Send a chat message
   */
  async sendChat<T>(message: {
    chatId: string;
    role: string;
    content: string;
    senderId: string;
    createAt: string;
    id?: string;
    status?: string;
    senderName?: string;
    time?: string;
    ext?: any;
    i_tag?: string;
    attachments?: Attachment[];
  }): Promise<APIResponse<T>> {
    if (this.isCloudMode()) {
      try {
        logger.info('[UnifiedChatService] Sending message to cloud:', message.chatId);
        
        // Extract recipient from chatId (format: userId1_userId2)
        const parts = message.chatId.split('_');
        const recipientId = parts.find(p => p !== message.senderId) || parts[1];
        
        // Get or generate session ID from ext or create new
        const sessionId = message.ext?.sessionId || cloudChatApi.generateSessionId();
        
        const input = chatMessageToA2AInput(message, recipientId, sessionId);
        const result = await cloudChatApi.sendA2AMessage(input);
        
        // Convert back to Message format
        const sentMessage = a2aMessageToChatMessage(result);
        
        return { success: true, data: sentMessage as unknown as T };
      } catch (error) {
        logger.error('[UnifiedChatService] Error sending message:', error);
        return createErrorResponse<T>(String(error));
      }
    } else {
      return IPCAPI.getInstance().chatApi.sendChat<T>(message);
    }
  },

  /**
   * Get messages for a specific chat
   */
  async getChatMessages<T>(params: {
    chatId: string;
    limit?: number;
    offset?: number;
    reverse?: boolean;
  }): Promise<APIResponse<T>> {
    if (this.isCloudMode()) {
      try {
        logger.info('[UnifiedChatService] Getting messages from cloud:', params.chatId);
        
        const connection = await cloudChatApi.getA2AMessages(
          params.chatId,
          params.limit || 50
        );
        
        // Convert A2A messages to Chat Message format
        const messages = connection.items.map(a2aMessageToChatMessage);
        
        // Sort by time (oldest first if reverse, newest first otherwise)
        messages.sort((a, b) => {
          const timeA = new Date(a.createAt).getTime();
          const timeB = new Date(b.createAt).getTime();
          return params.reverse ? timeB - timeA : timeA - timeB;
        });
        
        return { success: true, data: messages as unknown as T };
      } catch (error) {
        logger.error('[UnifiedChatService] Error getting messages:', error);
        return createErrorResponse<T>(String(error));
      }
    } else {
      return IPCAPI.getInstance().chatApi.getChatMessages<T>(params);
    }
  },

  /**
   * Get notifications for a chat
   */
  async getChatNotifications<T>(params: {
    chatId: string;
    limit?: number;
    offset?: number;
    reverse?: boolean;
  }): Promise<APIResponse<T>> {
    if (this.isCloudMode()) {
      // Cloud mode doesn't have separate notifications - return empty
      return { success: true, data: [] as unknown as T };
    } else {
      return IPCAPI.getInstance().chatApi.getChatNotifications<T>(params);
    }
  },

  /**
   * Delete a chat
   */
  async deleteChat<T>(chatId: string): Promise<APIResponse<T>> {
    if (this.isCloudMode()) {
      try {
        logger.info('[UnifiedChatService] Deleting chat in cloud:', chatId);
        // TODO: Implement cloud chat deletion
        // For now, just return success (messages will remain in DynamoDB with TTL)
        return { success: true, data: { deleted: true } as unknown as T };
      } catch (error) {
        logger.error('[UnifiedChatService] Error deleting chat:', error);
        return createErrorResponse<T>(String(error));
      }
    } else {
      return IPCAPI.getInstance().chatApi.deleteChat<T>(chatId);
    }
  },

  /**
   * Mark messages as read
   */
  async markMessageAsRead<T>(messageIds: string[], userId: string): Promise<APIResponse<T>> {
    if (this.isCloudMode()) {
      // TODO: Implement cloud read receipts
      return { success: true, data: { marked: messageIds.length } as unknown as T };
    } else {
      return IPCAPI.getInstance().chatApi.markMessageAsRead<T>(messageIds, userId);
    }
  },

  /**
   * Upload an attachment
   */
  async uploadAttachment<T>(params: {
    name: string;
    type: string;
    size: number;
    data: string | ArrayBuffer;
  }): Promise<APIResponse<T>> {
    if (this.isCloudMode()) {
      // TODO: Implement S3 upload for cloud attachments
      return createErrorResponse<T>('Attachments not yet supported in cloud mode');
    } else {
      return IPCAPI.getInstance().chatApi.uploadAttachment<T>(params);
    }
  },

  /**
   * Get file info
   */
  async getFileInfo(filePath: string): Promise<APIResponse<FileInfo>> {
    if (this.isCloudMode()) {
      return createErrorResponse<FileInfo>('File info not available in cloud mode');
    } else {
      return IPCAPI.getInstance().chatApi.getFileInfo(filePath);
    }
  },

  /**
   * Get file content
   */
  async getFileContent(filePath: string): Promise<APIResponse<FileContent>> {
    if (this.isCloudMode()) {
      return createErrorResponse<FileContent>('File content not available in cloud mode');
    } else {
      return IPCAPI.getInstance().chatApi.getFileContent(filePath);
    }
  },

  /**
   * Submit a chat form
   */
  async chatFormSubmit(chatId: string, messageId: string, formId: string, formData: any): Promise<APIResponse<FileContent>> {
    if (this.isCloudMode()) {
      return createErrorResponse<FileContent>('Form submission not yet supported in cloud mode');
    } else {
      return IPCAPI.getInstance().chatApi.chatFormSubmit(chatId, messageId, formId, formData);
    }
  },

  /**
   * Delete a message
   */
  async deleteMessage<T>(chatId: string, messageId: string): Promise<APIResponse<T>> {
    if (this.isCloudMode()) {
      // TODO: Implement message deletion in cloud
      return createErrorResponse<T>('Message deletion not yet supported in cloud mode');
    } else {
      return IPCAPI.getInstance().chatApi.deleteMessage<T>(chatId, messageId);
    }
  },

  /**
   * Clear unread count for a chat
   */
  async cleanChatUnRead<T>(chatId: string): Promise<APIResponse<T>> {
    if (this.isCloudMode()) {
      // TODO: Implement unread clearing in cloud
      return { success: true, data: { cleared: true } as unknown as T };
    } else {
      return IPCAPI.getInstance().chatApi.cleanChatUnRead<T>(chatId);
    }
  },

  /**
   * Subscribe to new messages for a channel (cloud mode only)
   * Returns unsubscribe function
   */
  subscribeToMessages(
    channelId: string,
    onMessage: (message: Message) => void,
    onError?: (error: Error) => void
  ): () => void {
    if (!this.isCloudMode()) {
      // Desktop mode uses IPC events, not subscriptions
      return () => {};
    }

    return cloudChatApi.subscribeToMessages(
      channelId,
      (a2aMsg) => {
        const message = a2aMessageToChatMessage(a2aMsg);
        onMessage(message);
      },
      onError
    );
  },

  /**
   * Start a new chat with an agent
   * This is a convenience method for the common use case
   */
  async startChatWithAgent(
    userId: string,
    userName: string,
    agentId: string,
    agentName: string
  ): Promise<APIResponse<Chat>> {
    const channelId = cloudChatApi.getChannelId(userId, agentId);
    
    const chat: Chat = {
      id: channelId,
      name: agentName,
      type: 'private',
      members: [
        { userId, name: userName, role: 'member' },
        { userId: agentId, name: agentName, role: 'agent' }
      ],
      messages: [],
      unread: 0,
      lastMsgTime: undefined,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    
    return { success: true, data: chat };
  },

  /**
   * Send a message to an agent and wait for response
   * This is a high-level method that handles the full flow
   */
  async sendMessageToAgent(
    userId: string,
    userName: string,
    agentId: string,
    text: string,
    sessionId?: string
  ): Promise<APIResponse<Message>> {
    const channelId = cloudChatApi.getChannelId(userId, agentId);
    const finalSessionId = sessionId || cloudChatApi.generateSessionId();
    
    const input: SendA2AMessageInput = {
      channelId,
      sessionId: finalSessionId,
      senderId: userId,
      recipientId: agentId,
      message: {
        role: 'user',
        parts: [{ type: 'text', text }]
      },
      metadata: {
        senderName: userName,
      },
      acceptedOutputModes: ['text']
    };
    
    try {
      const result = await cloudChatApi.sendA2AMessage(input);
      const message = a2aMessageToChatMessage(result);
      return { success: true, data: message };
    } catch (error) {
      logger.error('[UnifiedChatService] Error sending message to agent:', error);
      return createErrorResponse<Message>(String(error));
    }
  }
};

export default unifiedChatService;
