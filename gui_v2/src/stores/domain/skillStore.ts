/**
 * Skill Store
 * Skill data management store
 * 
 * Uses standardized store pattern with complete CRUD functionality
 */

import { createExtendedResourceStore } from '../base/createBaseStore';
import { BaseStoreState, CACHE_DURATION } from '../base/types';
import { Skill, SkillLevel, SkillStatus } from '../../types/domain/skill';
import { skillApi } from '../../services/api/skillApi';

/**
 * Skill Store extended interface
 * Adds skill-specific query methods on top of the base store
 */
export interface SkillStoreState extends BaseStoreState<Skill> {
  // Current selected skill name (compatible with old skillStore)
  skillname: string | null;
  setSkillname: (skillname: string | null) => void;

  // Cache invalidation
  invalidateCache: () => void;

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
  skillApi,
  (baseState, set, get) => ({
    ...baseState,

    // Current selected skill name (compatible with old skillStore)
    skillname: null,
    setSkillname: (skillname: string | null) => set({ skillname }),

    // Cache invalidation
    invalidateCache: () => set({ lastFetched: null }),
    
    // Extended query methods
    getSkillsByOwner: (owner: string) => {
      const items = get().items;
      return (items as Skill[]).filter(skill => skill.owner === owner);
    },

    getSkillsByLevel: (level: SkillLevel) => {
      const items = get().items;
      return (items as Skill[]).filter(skill => skill.level === level);
    },

    getSkillsByStatus: (status: SkillStatus) => {
      const items = get().items;
      return (items as Skill[]).filter(skill => skill.status === status);
    },

    getActiveSkills: () => {
      const items = get().items;
      return (items as Skill[]).filter(skill => skill.status === SkillStatus.ACTIVE);
    },

    getSkillsByCategory: (category: string) => {
      const items = get().items;
      return (items as Skill[]).filter(skill => skill.category === category);
    },

    getSkillsByTag: (tag: string) => {
      const items = get().items;
      return (items as Skill[]).filter(skill =>
        skill.tags && skill.tags.includes(tag)
      );
    },
    
    // Extended operation methods
    createSkill: async (username: string, skill: Skill) => {
      set({ loading: true, error: null });

      // Generate a temporary ID for optimistic update
      const tempId = `temp-${Date.now()}`;
      const optimisticSkill = { ...skill, id: tempId };

      // Add to local state immediately (optimistic update)
      get().addItem(optimisticSkill);

      try {
        const response = await skillApi.create(username, skill);

        if (response.success && response.data) {
          // Remove temp item and add real item
          get().removeItem(tempId);
          get().addItem(response.data);
          set({ loading: false });
        } else {
          // Rollback: remove temp item
          get().removeItem(tempId);
          throw new Error(response.error?.message || 'Failed to create skill');
        }
      } catch (error) {
        // Rollback: remove temp item
        get().removeItem(tempId);
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        set({ error: errorMessage, loading: false });
        throw error;
      }
    },
    
    updateSkill: async (username: string, skillId: string, updates: Partial<Skill>) => {
      set({ loading: true, error: null });

      // Store previous state for rollback
      const previousItems = [...get().items];
      const previousItem = previousItems.find(item => item.id === skillId);

      // Update local state immediately (optimistic update)
      get().updateItem(skillId, updates);

      try {
        const response = await skillApi.update(username, skillId, updates);

        if (response.success && response.data) {
          // Ensure we have the latest data from server
          get().updateItem(skillId, response.data);
          set({ loading: false });
        } else {
          // Rollback to previous state
          if (previousItem) {
            set({ items: previousItems });
          }
          throw new Error(response.error?.message || 'Failed to update skill');
        }
      } catch (error) {
        // Rollback to previous state
        if (previousItem) {
          set({ items: previousItems });
        }
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        set({ error: errorMessage, loading: false });
        throw error;
      }
    },
    
    deleteSkill: async (username: string, skillId: string) => {
      set({ loading: true, error: null });

      // Store previous state for rollback
      const previousItems = [...get().items];

      // Remove from local state immediately (optimistic update)
      get().removeItem(skillId);

      try {
        const response = await skillApi.delete(username, skillId);

        if (response.success) {
          set({ loading: false });
        } else {
          // Rollback to previous state
          set({ items: previousItems });
          throw new Error(response.error?.message || 'Failed to delete skill');
        }
      } catch (error) {
        // Rollback to previous state
        set({ items: previousItems });
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        set({ error: errorMessage, loading: false });
        throw error;
      }
    },
  })
);

