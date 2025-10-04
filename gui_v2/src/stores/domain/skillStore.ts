/**
 * Skill Store
 * 技能数据管理 Store
 * 
 * 使用标准化的 store 模式，提供完整的 CRUD 功能
 */

import { createExtendedResourceStore } from '../base/createBaseStore';
import { BaseStoreState, CACHE_DURATION } from '../base/types';
import { Skill, SkillLevel, SkillStatus } from '../../types/domain/skill';
import { SkillAPI } from '../../services/api/skillApi';

/**
 * Skill Store 扩展接口
 * 在基础 store 之上添加技能特定的查询方法
 */
export interface SkillStoreState extends BaseStoreState<Skill> {
  // 当前选中的技能名称（兼容旧的 skillStore）
  skillname: string | null;
  setSkillname: (skillname: string | null) => void;
  
  // 扩展查询方法
  getSkillsByOwner: (owner: string) => Skill[];
  getSkillsByLevel: (level: SkillLevel) => Skill[];
  getSkillsByStatus: (status: SkillStatus) => Skill[];
  getActiveSkills: () => Skill[];
  getSkillsByCategory: (category: string) => Skill[];
  getSkillsByTag: (tag: string) => Skill[];
  
  // 扩展操作方法
  createSkill: (username: string, skill: Skill) => Promise<void>;
  updateSkill: (username: string, skillId: string, updates: Partial<Skill>) => Promise<void>;
  deleteSkill: (username: string, skillId: string) => Promise<void>;
}

/**
 * Skill Store
 * 
 * @example
 * ```typescript
 * const { items: skills, loading, fetchItems } = useSkillStore();
 * 
 * // 获取技能
 * await fetchItems(username);
 * 
 * // 查询特定级别的技能
 * const entrySkills = useSkillStore.getState().getSkillsByLevel(SkillLevel.ENTRY);
 * 
 * // 创建新技能
 * await useSkillStore.getState().createSkill(username, newSkill);
 * ```
 */
export const useSkillStore = createExtendedResourceStore<Skill, SkillStoreState>(
  {
    name: 'skill',
    persist: true,
    cacheDuration: CACHE_DURATION.MEDIUM,
  },
  new SkillAPI(),
  (baseState, set, get) => ({
    ...baseState,
    
    // 当前选中的技能名称（兼容旧的 skillStore）
    skillname: null,
    setSkillname: (skillname: string | null) => set({ skillname }),
    
    // 扩展查询方法
    getSkillsByOwner: (owner: string) => {
      const items = get().items;
      return items.filter(skill => skill.owner === owner);
    },
    
    getSkillsByLevel: (level: SkillLevel) => {
      const items = get().items;
      return items.filter(skill => skill.level === level);
    },
    
    getSkillsByStatus: (status: SkillStatus) => {
      const items = get().items;
      return items.filter(skill => skill.status === status);
    },
    
    getActiveSkills: () => {
      const items = get().items;
      return items.filter(skill => skill.status === SkillStatus.ACTIVE);
    },
    
    getSkillsByCategory: (category: string) => {
      const items = get().items;
      return items.filter(skill => skill.category === category);
    },
    
    getSkillsByTag: (tag: string) => {
      const items = get().items;
      return items.filter(skill => 
        skill.tags && skill.tags.includes(tag)
      );
    },
    
    // 扩展操作方法
    createSkill: async (username: string, skill: Skill) => {
      set({ loading: true, error: null });
      
      try {
        const api = new SkillAPI();
        const response = await api.create(username, skill);
        
        if (response.success && response.data) {
          // 添加到本地状态
          get().addItem(response.data);
          set({ loading: false });
        } else {
          throw new Error(response.error?.message || 'Failed to create skill');
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        set({ error: errorMessage, loading: false });
        throw error;
      }
    },
    
    updateSkill: async (username: string, skillId: string, updates: Partial<Skill>) => {
      set({ loading: true, error: null });
      
      try {
        const api = new SkillAPI();
        const response = await api.update(username, skillId, updates);
        
        if (response.success && response.data) {
          // 更新本地状态
          get().updateItem(skillId, updates);
          set({ loading: false });
        } else {
          throw new Error(response.error?.message || 'Failed to update skill');
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        set({ error: errorMessage, loading: false });
        throw error;
      }
    },
    
    deleteSkill: async (username: string, skillId: string) => {
      set({ loading: true, error: null });
      
      try {
        const api = new SkillAPI();
        const response = await api.delete(username, skillId);
        
        if (response.success) {
          // 从本地状态移除
          get().removeItem(skillId);
          set({ loading: false });
        } else {
          throw new Error(response.error?.message || 'Failed to delete skill');
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        set({ error: errorMessage, loading: false });
        throw error;
      }
    },
  })
);

