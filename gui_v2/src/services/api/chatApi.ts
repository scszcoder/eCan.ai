/**
 * Chat API Service
 * 聊天 API Service
 */

import { ResourceAPI, APIResponse } from '@/stores/base/types';
import { Chat } from '@/types/domain/chat';
import { createIPCAPI } from '../ipc/api';
import type { IPCAPI } from '../ipc/api';
import { logger } from '@/utils/logger';

/**
 * Chat API Service类
 * Implementation ResourceAPI Interface，提供聊天的 CRUD Operation
 */
export class ChatAPI implements ResourceAPI<Chat> {
  private _api?: IPCAPI;

  private get api(): IPCAPI {
    if (!this._api) {
      this._api = createIPCAPI();
    }
    return this._api;
  }

  /**
   * GetAll聊天
   */
  async getAll(username: string): Promise<APIResponse<Chat[]>> {
    try {
      logger.info('[ChatAPI] Fetching chats for user:', username);
      
      const response = await this.api.getChats(username);
      
      logger.debug('[ChatAPI] Raw response:', response);
      
      if (!response || !response.success) {
        const errorMsg = response?.error || 'Failed to fetch chats';
        logger.error('[ChatAPI] Fetch failed:', errorMsg);
        return {
          success: false,
          error: {
            code: 'FETCH_ERROR',
            message: errorMsg,
          },
        };
      }

      // Process不同的Response格式
      let chats: Chat[] = [];
      
      if (Array.isArray(response.data)) {
        chats = response.data;
      } else if (response.data?.chats && Array.isArray(response.data.chats)) {
        chats = response.data.chats;
      } else if (response.data?.data && Array.isArray(response.data.data)) {
        chats = response.data.data;
      }

      logger.info('[ChatAPI] Successfully fetched', chats.length, 'chats');
      
      return {
        success: true,
        data: chats,
      };
    } catch (error) {
      logger.error('[ChatAPI] Error fetching chats:', error);
      return {
        success: false,
        error: {
          code: 'EXCEPTION',
          message: error instanceof Error ? error.message : 'Unknown error',
        },
      };
    }
  }

  /**
   * 根据 ID Get聊天
   */
  async getById(username: string, id: string): Promise<APIResponse<Chat>> {
    try {
      logger.info('[ChatAPI] Fetching chat:', id, 'for user:', username);
      
      const response = await this.api.getChat(username, id);
      
      if (!response || !response.success) {
        const errorMsg = response?.error || 'Failed to fetch chat';
        logger.error('[ChatAPI] Fetch failed:', errorMsg);
        return {
          success: false,
          error: {
            code: 'FETCH_ERROR',
            message: errorMsg,
          },
        };
      }

      logger.info('[ChatAPI] Successfully fetched chat:', id);
      
      return {
        success: true,
        data: response.data as Chat,
      };
    } catch (error) {
      logger.error('[ChatAPI] Error fetching chat:', error);
      return {
        success: false,
        error: {
          code: 'EXCEPTION',
          message: error instanceof Error ? error.message : 'Unknown error',
        },
      };
    }
  }

  /**
   * Create新的聊天
   */
  async create(username: string, chat: Chat): Promise<APIResponse<Chat>> {
    try {
      logger.info('[ChatAPI] Creating chat for user:', username, chat);
      
      const response = await this.api.createChat(username, chat);
      
      if (!response || !response.success) {
        const errorMsg = response?.error || 'Failed to create chat';
        logger.error('[ChatAPI] Create failed:', errorMsg);
        return {
          success: false,
          error: {
            code: 'CREATE_ERROR',
            message: errorMsg,
          },
        };
      }

      logger.info('[ChatAPI] Successfully created chat');
      
      return {
        success: true,
        data: response.data as Chat,
      };
    } catch (error) {
      logger.error('[ChatAPI] Error creating chat:', error);
      return {
        success: false,
        error: {
          code: 'EXCEPTION',
          message: error instanceof Error ? error.message : 'Unknown error',
        },
      };
    }
  }

  /**
   * Update聊天
   */
  async update(username: string, id: string, updates: Partial<Chat>): Promise<APIResponse<Chat>> {
    try {
      logger.info('[ChatAPI] Updating chat:', id, 'for user:', username, updates);
      
      const response = await this.api.updateChat(username, id, updates);
      
      if (!response || !response.success) {
        const errorMsg = response?.error || 'Failed to update chat';
        logger.error('[ChatAPI] Update failed:', errorMsg);
        return {
          success: false,
          error: {
            code: 'UPDATE_ERROR',
            message: errorMsg,
          },
        };
      }

      logger.info('[ChatAPI] Successfully updated chat:', id);
      
      return {
        success: true,
        data: response.data as Chat,
      };
    } catch (error) {
      logger.error('[ChatAPI] Error updating chat:', error);
      return {
        success: false,
        error: {
          code: 'EXCEPTION',
          message: error instanceof Error ? error.message : 'Unknown error',
        },
      };
    }
  }

  /**
   * Delete聊天
   */
  async delete(username: string, id: string): Promise<APIResponse<void>> {
    try {
      logger.info('[ChatAPI] Deleting chat:', id, 'for user:', username);
      
      const response = await this.api.deleteChat(username, id);
      
      if (!response || !response.success) {
        const errorMsg = response?.error || 'Failed to delete chat';
        logger.error('[ChatAPI] Delete failed:', errorMsg);
        return {
          success: false,
          error: {
            code: 'DELETE_ERROR',
            message: errorMsg,
          },
        };
      }

      logger.info('[ChatAPI] Successfully deleted chat:', id);
      
      return {
        success: true,
      };
    } catch (error) {
      logger.error('[ChatAPI] Error deleting chat:', error);
      return {
        success: false,
        error: {
          code: 'EXCEPTION',
          message: error instanceof Error ? error.message : 'Unknown error',
        },
      };
    }
  }
}

