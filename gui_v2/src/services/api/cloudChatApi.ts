/**
 * Cloud Chat API Service
 * 
 * Provides chat functionality for web platform using AppSync GraphQL
 * instead of IPC-based desktop APIs.
 * 
 * This service handles:
 * - Fetching chat messages via getA2AMessages query
 * - Sending messages via sendCloudA2AMessage mutation
 * - Subscribing to real-time message updates (TODO: requires WebSocket support)
 */

import { appSyncRequest } from '../web/appSyncClient';
import { GRAPHQL_QUERIES, GRAPHQL_MUTATIONS, GRAPHQL_SUBSCRIPTIONS } from './api-config';
import { logger } from '@/utils/logger';

export interface A2AMessagePart {
  type: string;
  text?: string;
  metadata?: Record<string, any>;
}

export interface A2AMessageBody {
  role: string;
  parts: A2AMessagePart[];
  metadata?: Record<string, any>;
}

export interface A2AMessage {
  id: string;
  channelId: string;
  sessionId: string;
  senderId: string;
  recipientId?: string;
  timestamp?: string;
  message: A2AMessageBody;
  metadata?: Record<string, any>;
  historyLength?: number;
  acceptedOutputModes?: string[];
}

export interface A2AMessageConnection {
  items: A2AMessage[];
  nextToken?: string;
}

export interface SendA2AMessageInput {
  channelId: string;
  sessionId: string;
  senderId: string;
  recipientId?: string;
  message: {
    role: string;
    parts: {
      type: string;
      text?: string;
    }[];
  };
  metadata?: Record<string, any>;
  acceptedOutputModes?: string[];
}

export interface ChatThread {
  id: string;  // channelId
  participantIds: string[];
  sessions: ChatSession[];
  latestMessage?: A2AMessage;
  unreadCount: number;
}

export interface ChatSession {
  id: string;  // sessionId
  channelId: string;
  messages: A2AMessage[];
  startedAt?: string;
  lastMessageAt?: string;
}

/**
 * Cloud Chat API - GraphQL-based chat operations for web platform
 */
export const cloudChatApi = {
  /**
   * Get A2A messages for a channel
   * @param channelId The channel ID (format: userId1_userId2 sorted alphabetically)
   * @param limit Maximum number of messages to return
   * @param nextToken Pagination token
   */
  async getA2AMessages(
    channelId: string, 
    limit?: number, 
    nextToken?: string
  ): Promise<A2AMessageConnection> {
    try {
      logger.info('[CloudChatApi] Getting A2A messages for channel:', channelId);
      
      const result = await appSyncRequest<{ getA2AMessages: A2AMessageConnection }>(
        GRAPHQL_QUERIES.GET_A2A_MESSAGES,
        { channelId, limit, nextToken },
        undefined,
        'get_a2a_messages'
      );
      
      const connection = result.getA2AMessages;
      logger.info('[CloudChatApi] Got', connection.items?.length || 0, 'messages');
      
      return connection;
    } catch (error) {
      logger.error('[CloudChatApi] Error getting A2A messages:', error);
      throw error;
    }
  },

  /**
   * Send an A2A message
   * @param input Message input containing channelId, senderId, message content
   */
  async sendA2AMessage(input: SendA2AMessageInput): Promise<A2AMessage> {
    try {
      logger.info('[CloudChatApi] Sending A2A message:', input.channelId);
      
      const result = await appSyncRequest<{ sendCloudA2AMessage: A2AMessage }>(
        GRAPHQL_MUTATIONS.SEND_CLOUD_A2A_MESSAGE,
        { input },
        undefined,
        'send_cloud_a2a_message'
      );
      
      const message = result.sendCloudA2AMessage;
      logger.info('[CloudChatApi] Message sent successfully:', message.id);
      
      return message;
    } catch (error) {
      logger.error('[CloudChatApi] Error sending A2A message:', error);
      throw error;
    }
  },

  /**
   * Subscribe to A2A messages for a channel
   * 
   * TODO: Implement WebSocket-based AppSync subscriptions
   * For now, this returns a no-op unsubscribe function.
   * Real-time updates can be achieved by polling getA2AMessages.
   * 
   * @param channelId The channel ID to subscribe to
   * @param onMessage Callback when a new message is received
   * @param onError Callback when an error occurs
   * @returns Unsubscribe function
   */
  subscribeToMessages(
    channelId: string,
    onMessage: (message: A2AMessage) => void,
    onError?: (error: Error) => void
  ): () => void {
    logger.warn('[CloudChatApi] Subscriptions not yet implemented - use polling instead');
    
    // TODO: Implement AppSync WebSocket subscriptions
    // For now, return a no-op unsubscribe function
    // The chat UI can poll getA2AMessages periodically for updates
    
    return () => {
      logger.debug('[CloudChatApi] Unsubscribe called (no-op)');
    };
  },

  /**
   * Generate channel ID from two participant IDs
   * Channel IDs are formed by sorting participant IDs alphabetically and joining with underscore
   * @param userId1 First participant ID
   * @param userId2 Second participant ID
   */
  getChannelId(userId1: string, userId2: string): string {
    const sorted = [userId1, userId2].sort();
    return `${sorted[0]}_${sorted[1]}`;
  },

  /**
   * Generate a new session ID (timestamp-based)
   */
  generateSessionId(): string {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  },

  /**
   * Get chat threads for a user
   * This fetches all messages where the user is either sender or recipient,
   * groups them by channel, and organizes into threads with sessions
   * 
   * Note: This is a client-side aggregation. For better performance with many chats,
   * consider adding a server-side getChatThreads query.
   * 
   * @param userId The user ID to get threads for
   */
  async getChatThreads(userId: string): Promise<ChatThread[]> {
    try {
      logger.info('[CloudChatApi] Getting chat threads for user:', userId);
      
      // For now, we need to know the channels the user is in
      // In a full implementation, you'd have a query like getUserChannels
      // For this initial version, we'll use a placeholder approach
      
      // TODO: Implement server-side getChatThreads query that returns
      // all channels/threads for a user with their latest message
      
      logger.warn('[CloudChatApi] getChatThreads not fully implemented - need server-side support');
      
      return [];
    } catch (error) {
      logger.error('[CloudChatApi] Error getting chat threads:', error);
      throw error;
    }
  },

  /**
   * Format a text message for sending
   * @param text The text content
   * @param senderId The sender's user ID
   * @param recipientId The recipient's user ID  
   * @param sessionId Optional session ID (will be generated if not provided)
   */
  formatTextMessage(
    text: string,
    senderId: string,
    recipientId: string,
    sessionId?: string
  ): SendA2AMessageInput {
    return {
      channelId: this.getChannelId(senderId, recipientId),
      sessionId: sessionId || this.generateSessionId(),
      senderId,
      recipientId,
      message: {
        role: 'user',
        parts: [{
          type: 'text',
          text
        }]
      },
      acceptedOutputModes: ['text']
    };
  }
};

export default cloudChatApi;
