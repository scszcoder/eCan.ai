/**
 * Chat Store
 * Chat state management
 */

import { createExtendedResourceStore } from '../base/createBaseStore';
import { BaseStoreState } from '../base/types';
import { Chat, ChatType, Message } from '@/types/domain/chat';
import { ChatAPI } from '@/services/api/chatApi';
import { logger } from '@/utils/logger';

/**
 * Cache duration configuration
 */
const CACHE_DURATION = {
  SHORT: 1 * 60 * 1000,   // 1 minute
  MEDIUM: 5 * 60 * 1000,  // 5 minutes
  LONG: 15 * 60 * 1000,   // 15 minutes
};

/**
 * Chat Store extended state
 */
export interface ChatStoreState extends BaseStoreState<Chat> {
  // Extended query methods
  getChatsByType: (type: ChatType) => Chat[];
  getUnreadChats: () => Chat[];
  getPinnedChats: () => Chat[];
  getMutedChats: () => Chat[];
  searchChats: (query: string) => Chat[];
  
  // Extended operation methods
  createChat: (username: string, chat: Chat) => Promise<void>;
  markAsRead: (chatId: string) => void;
  togglePin: (chatId: string) => void;
  toggleMute: (chatId: string) => void;
  addMessage: (chatId: string, message: Message) => void;
}

/**
 * Chat Store
 * 
 * @example
 * ```typescript
 * const { items: chats, loading, fetchItems } = useChatStore();
 * 
 * // Get chat list
 * await fetchItems(username);
 * 
 * // Query unread chats
 * const unreadChats = useChatStore.getState().getUnreadChats();
 * 
 * // Create new chat
 * await useChatStore.getState().createChat(username, newChat);
 * ```
 */
export const useChatStore = createExtendedResourceStore<Chat, ChatStoreState>(
  {
    name: 'chat',
    persist: false,  // 关闭持久化，避免数据不一致
    cacheDuration: CACHE_DURATION.SHORT, // Chat data updates frequently, use short cache
  },
  new ChatAPI(),
  (baseState, set, get) => ({
    ...baseState,
    
    // Extended query methods
    getChatsByType: (type: ChatType) => {
      return get().items.filter(c => c.type === type);
    },
    
    getUnreadChats: () => {
      return get().items.filter(c => c.unread > 0);
    },
    
    getPinnedChats: () => {
      return get().items.filter(c => c.pinned === true);
    },
    
    getMutedChats: () => {
      return get().items.filter(c => c.muted === true);
    },
    
    searchChats: (query: string) => {
      const lowerQuery = query.toLowerCase();
      return get().items.filter(c => 
        c.name?.toLowerCase().includes(lowerQuery) ||
        c.lastMsg?.toLowerCase().includes(lowerQuery) ||
        c.members?.some(m => m.name.toLowerCase().includes(lowerQuery))
      );
    },
    
    // Extended operation methods
    createChat: async (username: string, chat: Chat) => {
      try {
        set({ loading: true, error: null });
        logger.info('[ChatStore] Creating chat:', chat);
        
        const api = new ChatAPI();
        const response = await api.create(username, chat);
        
        if (response.success && response.data) {
          get().addItem(response.data);
          logger.info('[ChatStore] Chat created successfully');
        } else {
          const errorMsg = response.error?.message || 'Failed to create chat';
          set({ error: errorMsg });
          throw new Error(errorMsg);
        }
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : 'Unknown error';
        logger.error('[ChatStore] Error creating chat:', errorMsg);
        set({ error: errorMsg });
        throw error;
      } finally {
        set({ loading: false });
      }
    },
    
    markAsRead: (chatId: string) => {
      const chat = get().getItemById(chatId);
      if (chat) {
        get().updateItem(chatId, { unread: 0 });
        logger.info('[ChatStore] Marked chat as read:', chatId);
      }
    },
    
    togglePin: (chatId: string) => {
      const chat = get().getItemById(chatId);
      if (chat) {
        get().updateItem(chatId, { pinned: !chat.pinned });
        logger.info('[ChatStore] Toggled pin for chat:', chatId, !chat.pinned);
      }
    },
    
    toggleMute: (chatId: string) => {
      const chat = get().getItemById(chatId);
      if (chat) {
        get().updateItem(chatId, { muted: !chat.muted });
        logger.info('[ChatStore] Toggled mute for chat:', chatId, !chat.muted);
      }
    },
    
    addMessage: (chatId: string, message: Message) => {
      const chat = get().getItemById(chatId);
      if (chat) {
        const updatedMessages = [...(chat.messages || []), message];
        get().updateItem(chatId, {
          messages: updatedMessages,
          lastMsg: message.content,
          lastMsgTime: message.createAt,
          unread: chat.unread + 1,
        });
        logger.info('[ChatStore] Added message to chat:', chatId);
      }
    },
  })
);

// Export types and enums
export { ChatType, MessageStatus, MemberStatus } from '@/types/domain/chat';
export type { Chat, Message, Member } from '@/types/domain/chat';

