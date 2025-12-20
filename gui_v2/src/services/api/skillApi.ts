/**
 * Skill API Service
 * 技能Related to API 调用封装
 */

import { createIPCAPI } from '../ipc/api';
import type { IPCAPI } from '../ipc/api';
import { ResourceAPI, APIResponse } from '../../stores/base/types';
import { Skill } from '../../types/domain/skill';
import { logger } from '../../utils/logger';

/**
 * Skill API Service类
 * Implementation ResourceAPI Interface，提供Standard化的 CRUD Operation
 */
export class SkillAPI implements ResourceAPI<Skill> {
  private _api?: IPCAPI;

  private get api(): IPCAPI {
    if (!this._api) {
      this._api = createIPCAPI();
    }
    return this._api;
  }

  /**
   * GetAll技能
   */
  async getAll(username: string, skillIds: string[] = []): Promise<APIResponse<Skill[]>> {
    try {
      logger.debug('[SkillAPI] Fetching all skills for user:', username);

      const response = await this.api.getAgentSkills(username, skillIds);

      if (response && response.success && response.data) {
        // Process不同的Response格式
        let skills: Skill[] = [];

        if (Array.isArray(response.data)) {
          skills = response.data;
        } else if (response.data && typeof response.data === 'object' && 'skills' in response.data) {
          skills = (response.data as any).skills || [];
        }

        logger.info('[SkillAPI] Successfully fetched skills:', skills.length);

        return {
          success: true,
          data: skills,
        };
      } else {
        logger.error('[SkillAPI] Response failed:', response);
        throw new Error(response.error?.message || 'Failed to fetch skills');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      logger.error('[SkillAPI] Error fetching skills:', errorMessage);

      return {
        success: false,
        error: {
          code: 'FETCH_SKILLS_ERROR',
          message: errorMessage,
        },
      };
    }
  }

  /**
   * 根据 ID Get单个技能
   */
  async getById(username: string, id: string): Promise<APIResponse<Skill>> {
    try {
      logger.debug('[SkillAPI] Fetching skill by ID:', id);
      
      // 通过 getAll 然后Filter
      const allSkillsResponse = await this.getAll(username, [id]);
      
      if (allSkillsResponse.success && allSkillsResponse.data) {
        const skill = allSkillsResponse.data.find(s => s.id === id);
        
        if (skill) {
          return {
            success: true,
            data: skill,
          };
        } else {
          throw new Error(`Skill not found: ${id}`);
        }
      } else {
        throw new Error(allSkillsResponse.error?.message || 'Failed to fetch skill');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      logger.error('[SkillAPI] Error fetching skill by ID:', errorMessage);
      
      return {
        success: false,
        error: {
          code: 'FETCH_SKILL_ERROR',
          message: errorMessage,
        },
      };
    }
  }

  /**
   * Create新技能
   */
  async create(username: string, skill: Skill): Promise<APIResponse<Skill>> {
    try {
      logger.debug('[SkillAPI] Creating new skill:', skill.name);
      
      // If no id, call newAgentSkill to let backend generate one; otherwise saveAgentSkill (upsert)
      const response = skill.id
        ? await this.api.saveAgentSkill(username, skill)
        : await this.api.newAgentSkill(username, skill);

      if (response && response.success) {
        logger.debug('[SkillAPI] Successfully created/saved skill');

        // Prefer backend returned data if available (may contain generated id)
        const createdData = (response as any).data as Skill | undefined;
        const resultSkill = createdData ?? skill;

        return {
          success: true,
          data: resultSkill,
        };
      }
      throw new Error(response?.error?.message || 'Failed to create skill');
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      logger.error('[SkillAPI] Error creating skill:', errorMessage);
      
      return {
        success: false,
        error: {
          code: 'CREATE_SKILL_ERROR',
          message: errorMessage,
        },
      };
    }
  }

  /**
   * Update技能
   */
  async update(username: string, id: string, updates: Partial<Skill>): Promise<APIResponse<Skill>> {
    try {
      logger.debug('[SkillAPI] Updating skill:', id);
      
      // 先Get完整的技能Data
      const skillResponse = await this.getById(username, id);
      
      if (!skillResponse.success || !skillResponse.data) {
        throw new Error('Skill not found');
      }
      
      const updatedSkill = { ...skillResponse.data, ...updates };
      
      const response = await this.api.saveAgentSkill(username, updatedSkill);
      
      if (response && response.success) {
        logger.debug('[SkillAPI] Successfully updated skill');
        
        return {
          success: true,
          data: updatedSkill,
        };
      } else {
        throw new Error(response.error?.message || 'Failed to update skill');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      logger.error('[SkillAPI] Error updating skill:', errorMessage);
      
      return {
        success: false,
        error: {
          code: 'UPDATE_SKILL_ERROR',
          message: errorMessage,
        },
      };
    }
  }

  /**
   * Delete技能
   */
  async delete(username: string, id: string): Promise<APIResponse<void>> {
    try {
      logger.debug('[SkillAPI] Deleting skill:', id);
      
      // Note：Backend可能没有专门的Delete技能Interface
      // 这里可能Need调用其他Interfaceor标记为DeleteStatus
      logger.warn('[SkillAPI] Delete skill not implemented in backend');
      
      return {
        success: false,
        error: {
          code: 'NOT_IMPLEMENTED',
          message: 'Delete skill operation is not implemented',
        },
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      logger.error('[SkillAPI] Error deleting skill:', errorMessage);
      
      return {
        success: false,
        error: {
          code: 'DELETE_SKILL_ERROR',
          message: errorMessage,
        },
      };
    }
  }
}

// Export单例实例
export const skillApi = new SkillAPI();

