/**
 * Skill Store
 * Skill data management store
 * 
 * Uses standardized store pattern with complete CRUD functionality
 */

import { createExtendedResourceStore } from '../base/createBaseStore';
import { BaseStoreState, CACHE_DURATION } from '../base/types';
import { Skill, SkillLevel, SkillStatus } from '../../types/domain/skill';
import { SkillAPI } from '../../services/api/skillApi';

/**
 * Skill Store extended interface
 * Adds skill-specific query methods on top of the base store
 */
export interface SkillStoreState extends BaseStoreState<Skill> {
  // Current selected skill name (compatible with old skillStore)
  skillname: string | null;
  setSkillname: (skillname: string | null) => void;
  
  // Extended query methods
  getSkillsByOwner: (owner: string) => Skill[];
  getSkillsByLevel: (level: SkillLevel) => Skill[];
  getSkillsByStatus: (status: SkillStatus) => Skill[];
  getActiveSkills: () => Skill[];
  getSkillsByCategory: (category: string) => Skill[];
  getSkillsByTag: (tag: string) => Skill[];
  
  // Extended operation methods
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
 * // Get skills
 * await fetchItems(username);
 * 
 * // Query skills of specific level
 * const entrySkills = useSkillStore.getState().getSkillsByLevel(SkillLevel.ENTRY);
 * 
 * // Create new skill
 * await useSkillStore.getState().createSkill(username, newSkill);
 * ```
 */
export const useSkillStore = createExtendedResourceStore<Skill, SkillStoreState>(
  {
    name: 'skill',
    persist: false,  // 关闭持久化，避免数据不一致
    cacheDuration: CACHE_DURATION.MEDIUM,
  },
  new SkillAPI(),
  (baseState, set, get) => ({
    ...baseState,
    
    // Current selected skill name (compatible with old skillStore)
    skillname: null,
    setSkillname: (skillname: string | null) => set({ skillname }),
    
    // Extended query methods
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
    
    // Extended operation methods
    createSkill: async (username: string, skill: Skill) => {
      set({ loading: true, error: null });
      
      try {
        const api = new SkillAPI();
        const response = await api.create(username, skill);
        
        if (response.success && response.data) {
          // Add to local state
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
          // Update local state
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
          // Remove from local state
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

