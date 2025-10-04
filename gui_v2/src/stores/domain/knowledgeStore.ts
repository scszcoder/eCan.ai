/**
 * Knowledge Store
 * 知识库状态管理
 */

import { createExtendedResourceStore } from '../base/createBaseStore';
import { BaseStoreState } from '../base/types';
import { Knowledge, KnowledgeType, KnowledgeStatus } from '@/types/domain/knowledge';
import { KnowledgeAPI } from '@/services/api/knowledgeApi';
import { logger } from '@/utils/logger';

/**
 * 缓存时间配置
 */
const CACHE_DURATION = {
  SHORT: 1 * 60 * 1000,   // 1 分钟
  MEDIUM: 5 * 60 * 1000,  // 5 分钟
  LONG: 15 * 60 * 1000,   // 15 分钟
};

/**
 * Knowledge Store 扩展状态
 */
export interface KnowledgeStoreState extends BaseStoreState<Knowledge> {
  // 扩展查询方法
  getKnowledgesByType: (type: KnowledgeType) => Knowledge[];
  getKnowledgesByStatus: (status: KnowledgeStatus) => Knowledge[];
  getKnowledgesByCategory: (category: string) => Knowledge[];
  getKnowledgesByOwner: (owner: string) => Knowledge[];
  searchKnowledges: (query: string) => Knowledge[];
  
  // 扩展操作方法
  createKnowledge: (username: string, knowledge: Knowledge) => Promise<void>;
  updateKnowledgeStatus: (username: string, id: string, status: KnowledgeStatus) => Promise<void>;
}

/**
 * Knowledge Store
 * 
 * @example
 * ```typescript
 * const { items: knowledges, loading, fetchItems } = useKnowledgeStore();
 * 
 * // 获取知识库
 * await fetchItems(username);
 * 
 * // 查询特定类型的知识
 * const docKnowledges = useKnowledgeStore.getState().getKnowledgesByType(KnowledgeType.DOCUMENT);
 * 
 * // 创建新知识
 * await useKnowledgeStore.getState().createKnowledge(username, newKnowledge);
 * ```
 */
export const useKnowledgeStore = createExtendedResourceStore<Knowledge, KnowledgeStoreState>(
  {
    name: 'knowledge',
    persist: true,
    cacheDuration: CACHE_DURATION.MEDIUM,
  },
  new KnowledgeAPI(),
  (baseState, set, get) => ({
    ...baseState,
    
    // 扩展查询方法
    getKnowledgesByType: (type: KnowledgeType) => {
      return get().items.filter(k => k.knowledge_type === type);
    },
    
    getKnowledgesByStatus: (status: KnowledgeStatus) => {
      return get().items.filter(k => k.status === status);
    },
    
    getKnowledgesByCategory: (category: string) => {
      return get().items.filter(k => 
        k.category === category || 
        k.categories?.includes(category)
      );
    },
    
    getKnowledgesByOwner: (owner: string) => {
      return get().items.filter(k => k.owner === owner);
    },
    
    searchKnowledges: (query: string) => {
      const lowerQuery = query.toLowerCase();
      return get().items.filter(k => 
        k.name?.toLowerCase().includes(lowerQuery) ||
        k.title?.toLowerCase().includes(lowerQuery) ||
        k.description?.toLowerCase().includes(lowerQuery) ||
        k.content?.toLowerCase().includes(lowerQuery) ||
        k.tags?.some(tag => tag.toLowerCase().includes(lowerQuery))
      );
    },
    
    // 扩展操作方法
    createKnowledge: async (username: string, knowledge: Knowledge) => {
      try {
        set({ loading: true, error: null });
        logger.info('[KnowledgeStore] Creating knowledge:', knowledge);
        
        const api = new KnowledgeAPI();
        const response = await api.create(username, knowledge);
        
        if (response.success && response.data) {
          get().addItem(response.data);
          logger.info('[KnowledgeStore] Knowledge created successfully');
        } else {
          const errorMsg = response.error?.message || 'Failed to create knowledge';
          set({ error: errorMsg });
          throw new Error(errorMsg);
        }
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : 'Unknown error';
        logger.error('[KnowledgeStore] Error creating knowledge:', errorMsg);
        set({ error: errorMsg });
        throw error;
      } finally {
        set({ loading: false });
      }
    },
    
    updateKnowledgeStatus: async (username: string, id: string, status: KnowledgeStatus) => {
      try {
        set({ loading: true, error: null });
        logger.info('[KnowledgeStore] Updating knowledge status:', id, status);
        
        const api = new KnowledgeAPI();
        const response = await api.update(username, id, { status });
        
        if (response.success && response.data) {
          get().updateItem(id, response.data);
          logger.info('[KnowledgeStore] Knowledge status updated successfully');
        } else {
          const errorMsg = response.error?.message || 'Failed to update knowledge status';
          set({ error: errorMsg });
          throw new Error(errorMsg);
        }
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : 'Unknown error';
        logger.error('[KnowledgeStore] Error updating knowledge status:', errorMsg);
        set({ error: errorMsg });
        throw error;
      } finally {
        set({ loading: false });
      }
    },
  })
);

// 导出类型和枚举
export { KnowledgeType, KnowledgeStatus } from '@/types/domain/knowledge';
export type { Knowledge } from '@/types/domain/knowledge';

