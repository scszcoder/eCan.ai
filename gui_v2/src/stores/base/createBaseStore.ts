/**
 * Base Store Factory
 * 创建标准化的 Zustand store
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { 
  BaseResource, 
  BaseStoreState, 
  ResourceAPI, 
  StoreOptions,
  CACHE_DURATION 
} from './types';
import { logger } from '../../utils/logger';

/**
 * 创建标准化的资源 Store
 * 
 * @param options - Store 配置选项
 * @param apiService - API 服务实例
 * @returns Zustand store hook
 * 
 * @example
 * ```typescript
 * const useTaskStore = createResourceStore<Task>(
 *   { name: 'task', persist: true },
 *   new TaskAPI()
 * );
 * ```
 */
export function createResourceStore<T extends BaseResource>(
  options: StoreOptions,
  apiService: ResourceAPI<T>
) {
  const {
    name,
    persist: enablePersist = true,
    cacheDuration = CACHE_DURATION.MEDIUM,
    persistLoadingState = false,
  } = options;

  const storeCreator = (set: any, get: any): BaseStoreState<T> => ({
    // 数据
    items: [],
    
    // 状态
    loading: false,
    error: null,
    lastFetched: null,
    
    // 基础 CRUD 操作
    setItems: (items: T[]) => {
      logger.debug(`[${name}Store] Setting ${items.length} items`);
      set({ items, lastFetched: Date.now(), error: null });
    },
    
    addItem: (item: T) => {
      logger.debug(`[${name}Store] Adding item:`, item.id);
      set((state: BaseStoreState<T>) => ({
        items: [...state.items, item]
      }));
    },
    
    updateItem: (id: string, updates: Partial<T>) => {
      logger.debug(`[${name}Store] Updating item:`, id);
      set((state: BaseStoreState<T>) => ({
        items: state.items.map(item => 
          item.id === id ? { ...item, ...updates } : item
        )
      }));
    },
    
    removeItem: (id: string) => {
      logger.debug(`[${name}Store] Removing item:`, id);
      set((state: BaseStoreState<T>) => ({
        items: state.items.filter(item => item.id !== id)
      }));
    },
    
    // 查询方法
    getItemById: (id: string) => {
      const items = get().items;
      return items.find((item: T) => item.id === id) || null;
    },
    
    getItems: () => {
      return get().items;
    },
    
    // 数据获取
    fetchItems: async (username: string, ...args: any[]) => {
      const state = get();
      
      // 检查是否需要重新获取
      if (!state.shouldFetch()) {
        logger.debug(`[${name}Store] Using cached data`);
        return;
      }
      
      set({ loading: true, error: null });
      
      try {
        logger.info(`[${name}Store] Fetching items for user: ${username}`);
        const response = await apiService.getAll(username, ...args);
        
        if (response && response.success && response.data) {
          set({ 
            items: response.data, 
            loading: false, 
            lastFetched: Date.now(),
            error: null 
          });
          logger.info(`[${name}Store] Successfully fetched ${response.data.length} items`);
        } else {
          throw new Error(response.error?.message || `Failed to fetch ${name}s`);
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'An unknown error occurred';
        logger.error(`[${name}Store] Error fetching items:`, errorMessage);
        set({ error: errorMessage, loading: false });
        throw error;
      }
    },
    
    shouldFetch: () => {
      const lastFetched = get().lastFetched;
      if (!lastFetched) {
        logger.debug(`[${name}Store] No data fetched yet, should fetch`);
        return true;
      }
      
      const now = Date.now();
      const diff = now - lastFetched;
      const shouldFetch = diff > cacheDuration;
      
      if (shouldFetch) {
        logger.debug(`[${name}Store] Cache expired (${diff}ms > ${cacheDuration}ms), should fetch`);
      }
      
      return shouldFetch;
    },
    
    // 状态管理
    setLoading: (loading: boolean) => set({ loading }),
    
    setError: (error: string | null) => set({ error, loading: false }),
    
    clearData: () => {
      logger.info(`[${name}Store] Clearing all data`);
      set({ 
        items: [], 
        loading: false, 
        error: null, 
        lastFetched: null 
      });
    },
  });

  // 根据配置决定是否使用 persist 中间件
  if (enablePersist) {
    return create<BaseStoreState<T>>()(
      persist(
        storeCreator,
        {
          name: `${name}-storage`,
          // 只持久化数据，不持久化 loading 和 error 状态（除非明确指定）
          partialize: (state) => {
            const persistedState: any = {
              items: state.items,
              lastFetched: state.lastFetched,
            };
            
            if (persistLoadingState) {
              persistedState.loading = state.loading;
              persistedState.error = state.error;
            }
            
            return persistedState;
          },
        }
      )
    );
  } else {
    return create<BaseStoreState<T>>()(storeCreator);
  }
}

/**
 * 创建扩展的资源 Store
 * 允许在标准 store 基础上添加自定义方法
 * 
 * @param options - Store 配置选项
 * @param apiService - API 服务实例
 * @param extendStore - 扩展函数，接收标准 store 状态并返回扩展状态
 * @returns Zustand store hook
 * 
 * @example
 * ```typescript
 * const useAgentStore = createExtendedResourceStore<Agent, AgentStoreExtension>(
 *   { name: 'agent' },
 *   new AgentAPI(),
 *   (baseState) => ({
 *     ...baseState,
 *     getMyTwinAgent: () => {
 *       return baseState.items.find(a => a.card?.name === 'My Twin Agent') || null;
 *     }
 *   })
 * );
 * ```
 */
export function createExtendedResourceStore<
  T extends BaseResource,
  E extends BaseStoreState<T>
>(
  options: StoreOptions,
  apiService: ResourceAPI<T>,
  extendStore: (baseState: BaseStoreState<T>, set: any, get: any) => E
) {
  const {
    name,
    persist: enablePersist = true,
    cacheDuration = CACHE_DURATION.MEDIUM,
    persistLoadingState = false,
  } = options;

  const storeCreator = (set: any, get: any): E => {
    // 创建基础 store 状态（内联实现，避免使用 getState()）
    const baseState: BaseStoreState<T> = {
      // 数据
      items: [],
      
      // 状态
      loading: false,
      error: null,
      lastFetched: null,
      
      // 基础 CRUD 操作
      setItems: (items: T[]) => {
        logger.debug(`[${name}Store] Setting ${items.length} items`);
        set({ items, lastFetched: Date.now(), error: null });
      },
      
      addItem: (item: T) => {
        logger.debug(`[${name}Store] Adding item:`, item.id);
        set((state: BaseStoreState<T>) => ({
          items: [...state.items, item]
        }));
      },
      
      updateItem: (id: string, updates: Partial<T>) => {
        logger.debug(`[${name}Store] Updating item:`, id);
        set((state: BaseStoreState<T>) => ({
          items: state.items.map(item => 
            item.id === id ? { ...item, ...updates } : item
          )
        }));
      },
      
      removeItem: (id: string) => {
        logger.debug(`[${name}Store] Removing item:`, id);
        set((state: BaseStoreState<T>) => ({
          items: state.items.filter(item => item.id !== id)
        }));
      },
      
      // 查询方法
      getItemById: (id: string) => {
        const items = get().items;
        return items.find((item: T) => item.id === id) || null;
      },
      
      getItems: () => {
        return get().items;
      },
      
      // 数据获取
      fetchItems: async (username: string, ...args: any[]) => {
        const state = get();
        
        // 检查是否需要重新获取
        // 如果有缓存数据但是空数组，强制刷新
        const hasEmptyCache = state.items && state.items.length === 0 && state.lastFetched;
        if (!state.shouldFetch() && !hasEmptyCache) {
          logger.debug(`[${name}Store] Using cached data`);
          return;
        }
        
        if (hasEmptyCache) {
          logger.debug(`[${name}Store] Empty cache detected, forcing refresh`);
        }
        
        set({ loading: true, error: null });
        
        try {
          logger.info(`[${name}Store] Fetching items for user: ${username}`);
          const response = await apiService.getAll(username, ...args);
          
          if (response && response.success && response.data) {
            set({ 
              items: response.data, 
              loading: false, 
              lastFetched: Date.now(),
              error: null 
            });
            logger.info(`[${name}Store] Successfully fetched ${response.data.length} items`);
          } else {
            throw new Error(response.error?.message || `Failed to fetch ${name}s`);
          }
        } catch (error) {
          const errorMessage = error instanceof Error ? error.message : 'An unknown error occurred';
          logger.error(`[${name}Store] Error fetching items:`, errorMessage);
          set({ error: errorMessage, loading: false });
          throw error;
        }
      },
      
      shouldFetch: () => {
        const lastFetched = get().lastFetched;
        if (!lastFetched) {
          logger.debug(`[${name}Store] No data fetched yet, should fetch`);
          return true;
        }
        
        const now = Date.now();
        const diff = now - lastFetched;
        const shouldFetch = diff > cacheDuration;
        
        if (shouldFetch) {
          logger.debug(`[${name}Store] Cache expired (${diff}ms > ${cacheDuration}ms), should fetch`);
        }
        
        return shouldFetch;
      },
      
      // 状态管理
      setLoading: (loading: boolean) => set({ loading }),
      
      setError: (error: string | null) => set({ error, loading: false }),
      
      clearData: () => {
        logger.info(`[${name}Store] Clearing all data`);
        set({ 
          items: [], 
          loading: false, 
          error: null, 
          lastFetched: null 
        });
      },
    };
    
    // 然后应用扩展
    return extendStore(baseState, set, get);
  };

  if (enablePersist) {
    return create<E>()(
      persist(
        storeCreator,
        {
          name: `${name}-storage`,
          partialize: (state) => {
            const persistedState: any = {
              items: state.items,
              lastFetched: state.lastFetched,
            };
            
            if (persistLoadingState) {
              persistedState.loading = state.loading;
              persistedState.error = state.error;
            }
            
            return persistedState;
          },
        }
      )
    );
  } else {
    return create<E>()(storeCreator);
  }
}

