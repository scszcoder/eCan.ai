/**
 * Knowledge API Service
 * 知识库 API Service
 */

import { ResourceAPI, APIResponse } from '@/stores/base/types';
import { Knowledge } from '@/types/domain/knowledge';
import { createIPCAPI } from '../ipc/api';
import type { IPCAPI } from '../ipc/api';
import { logger } from '@/utils/logger';

/**
 * Knowledge API Service类
 * Implementation ResourceAPI Interface，提供知识库的 CRUD Operation
 */
export class KnowledgeAPI implements ResourceAPI<Knowledge> {
  private _api?: IPCAPI;

  private get api(): IPCAPI {
    if (!this._api) {
      this._api = createIPCAPI();
    }
    return this._api;
  }

  /**
   * GetAll知识库条目
   */
  async getAll(username: string, agentId?: string): Promise<APIResponse<Knowledge[]>> {
    try {
      logger.info('[KnowledgeAPI] Fetching knowledges for user:', username, 'agentId:', agentId);
      
      const response = await this.api.getKnowledges(username, agentId ? [agentId] : []);
      
      logger.debug('[KnowledgeAPI] Raw response:', response);
      
      if (!response || !response.success) {
        const errorMsg = response?.error || 'Failed to fetch knowledges';
        logger.error('[KnowledgeAPI] Fetch failed:', errorMsg);
        return {
          success: false,
          error: {
            code: 'FETCH_ERROR',
            message: errorMsg,
          },
        };
      }

      // Process不同的Response格式
      let knowledges: Knowledge[] = [];
      
      if (Array.isArray(response.data)) {
        knowledges = response.data;
      } else if (response.data?.knowledges && Array.isArray(response.data.knowledges)) {
        knowledges = response.data.knowledges;
      } else if (response.data?.data && Array.isArray(response.data.data)) {
        knowledges = response.data.data;
      }

      logger.info('[KnowledgeAPI] Successfully fetched', knowledges.length, 'knowledges');
      
      return {
        success: true,
        data: knowledges,
      };
    } catch (error) {
      logger.error('[KnowledgeAPI] Error fetching knowledges:', error);
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
   * 根据 ID Get知识库条目
   */
  async getById(username: string, id: string): Promise<APIResponse<Knowledge>> {
    try {
      logger.info('[KnowledgeAPI] Fetching knowledge:', id, 'for user:', username);
      
      const response = await this.api.getKnowledge(username, id);
      
      if (!response || !response.success) {
        const errorMsg = response?.error || 'Failed to fetch knowledge';
        logger.error('[KnowledgeAPI] Fetch failed:', errorMsg);
        return {
          success: false,
          error: {
            code: 'FETCH_ERROR',
            message: errorMsg,
          },
        };
      }

      logger.info('[KnowledgeAPI] Successfully fetched knowledge:', id);
      
      return {
        success: true,
        data: response.data as Knowledge,
      };
    } catch (error) {
      logger.error('[KnowledgeAPI] Error fetching knowledge:', error);
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
   * Create新的知识库条目
   */
  async create(username: string, knowledge: Knowledge): Promise<APIResponse<Knowledge>> {
    try {
      logger.info('[KnowledgeAPI] Creating knowledge for user:', username, knowledge);
      
      const response = await this.api.createKnowledge(username, knowledge);
      
      if (!response || !response.success) {
        const errorMsg = response?.error || 'Failed to create knowledge';
        logger.error('[KnowledgeAPI] Create failed:', errorMsg);
        return {
          success: false,
          error: {
            code: 'CREATE_ERROR',
            message: errorMsg,
          },
        };
      }

      logger.info('[KnowledgeAPI] Successfully created knowledge');
      
      return {
        success: true,
        data: response.data as Knowledge,
      };
    } catch (error) {
      logger.error('[KnowledgeAPI] Error creating knowledge:', error);
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
   * Update知识库条目
   */
  async update(username: string, id: string, updates: Partial<Knowledge>): Promise<APIResponse<Knowledge>> {
    try {
      logger.info('[KnowledgeAPI] Updating knowledge:', id, 'for user:', username, updates);
      
      const response = await this.api.updateKnowledge(username, id, updates);
      
      if (!response || !response.success) {
        const errorMsg = response?.error || 'Failed to update knowledge';
        logger.error('[KnowledgeAPI] Update failed:', errorMsg);
        return {
          success: false,
          error: {
            code: 'UPDATE_ERROR',
            message: errorMsg,
          },
        };
      }

      logger.info('[KnowledgeAPI] Successfully updated knowledge:', id);
      
      return {
        success: true,
        data: response.data as Knowledge,
      };
    } catch (error) {
      logger.error('[KnowledgeAPI] Error updating knowledge:', error);
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
   * Delete知识库条目
   */
  async delete(username: string, id: string): Promise<APIResponse<void>> {
    try {
      logger.info('[KnowledgeAPI] Deleting knowledge:', id, 'for user:', username);
      
      const response = await this.api.deleteKnowledge(username, id);
      
      if (!response || !response.success) {
        const errorMsg = response?.error || 'Failed to delete knowledge';
        logger.error('[KnowledgeAPI] Delete failed:', errorMsg);
        return {
          success: false,
          error: {
            code: 'DELETE_ERROR',
            message: errorMsg,
          },
        };
      }

      logger.info('[KnowledgeAPI] Successfully deleted knowledge:', id);
      
      return {
        success: true,
      };
    } catch (error) {
      logger.error('[KnowledgeAPI] Error deleting knowledge:', error);
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

