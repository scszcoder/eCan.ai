/**
 * Skill API Service
 * 技能相关的 API 调用封装
 */

import { createIPCAPI } from '../ipc/api';
import type { IPCAPI } from '../ipc/api';
import { ResourceAPI, APIResponse } from '../../stores/base/types';
import { Skill, CreateSkillInput, UpdateSkillInput } from '../../types/domain/skill';
import { logger } from '../../utils/logger';

/**
 * Skill API 服务类
 * 实现 ResourceAPI 接口，提供标准化的 CRUD 操作
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
   * 获取所有技能
   */
  async getAll(username: string, skillIds: string[] = []): Promise<APIResponse<Skill[]>> {
    try {
      logger.debug('[SkillAPI] Fetching all skills for user:', username);

      const response = await this.api.getSkills(username, skillIds);

      // logger.debug('[SkillAPI] Raw response:', JSON.stringify(response, null, 2));

      if (response && response.success && response.data) {
        // 处理不同的响应格式
        let skills: Skill[] = [];

        logger.debug('[SkillAPI] response.data type:', typeof response.data);
        logger.debug('[SkillAPI] response.data is Array:', Array.isArray(response.data));
        logger.debug('[SkillAPI] response.data has skills:', response.data && typeof response.data === 'object' && 'skills' in response.data);

        if (Array.isArray(response.data)) {
          skills = response.data;
          logger.debug('[SkillAPI] Using response.data as array');
        } else if (response.data && typeof response.data === 'object' && 'skills' in response.data) {
          skills = (response.data as any).skills || [];
          logger.debug('[SkillAPI] Using response.data.skills, count:', skills.length);
        }

        logger.debug('[SkillAPI] Successfully fetched skills:', skills.length);

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
   * 根据 ID 获取单个技能
   */
  async getById(username: string, id: string): Promise<APIResponse<Skill>> {
    try {
      logger.debug('[SkillAPI] Fetching skill by ID:', id);
      
      // 通过 getAll 然后过滤
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
   * 创建新技能
   */
  async create(username: string, skill: Skill): Promise<APIResponse<Skill>> {
    try {
      logger.debug('[SkillAPI] Creating new skill:', skill.name);
      
      const response = await this.api.saveSkill(username, skill);
      
      if (response && response.success) {
        logger.debug('[SkillAPI] Successfully created skill');
        
        return {
          success: true,
          data: skill,
        };
      } else {
        throw new Error(response.error?.message || 'Failed to create skill');
      }
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
   * 更新技能
   */
  async update(username: string, id: string, updates: Partial<Skill>): Promise<APIResponse<Skill>> {
    try {
      logger.debug('[SkillAPI] Updating skill:', id);
      
      // 先获取完整的技能数据
      const skillResponse = await this.getById(username, id);
      
      if (!skillResponse.success || !skillResponse.data) {
        throw new Error('Skill not found');
      }
      
      const updatedSkill = { ...skillResponse.data, ...updates };
      
      const response = await this.api.saveSkills(username, [updatedSkill]);
      
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
   * 删除技能
   */
  async delete(username: string, id: string): Promise<APIResponse<void>> {
    try {
      logger.debug('[SkillAPI] Deleting skill:', id);
      
      // 注意：后端可能没有专门的删除技能接口
      // 这里可能需要调用其他接口或者标记为删除状态
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

// 导出单例实例
export const skillApi = new SkillAPI();

