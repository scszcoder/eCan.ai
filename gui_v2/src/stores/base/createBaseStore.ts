/**
 * Base Store Factory
 * CreateStandard化的 Zustand store
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
 * CreateStandard化的资源 Store
 * 
 * @param options - Store Configuration选项
 * @param apiService - API Service实例
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
    // Data
    items: [],
    
    // Status
    loading: false,
    error: null,
    lastFetched: null,
    
    // Base CRUD Operation
    setItems: (items: T[]) => {
      logger.debug(`[${name}Store] Setting ${items.length} items`);
      const seenIds = new Set<string>();
      const deduped = items.filter((item) => {
        const id = String(item.id ?? '');
        if (!id || seenIds.has(id)) return false;
        seenIds.add(id);
        return true;
      });
      if (deduped.length !== items.length) {
        logger.warn(`[${name}Store] setItems: deduplicated ${items.length - deduped.length} duplicate(s)`);
      }
      set({ items: deduped, lastFetched: Date.now(), error: null });
    },
    
    addItem: (item: T) => {
      const currentItems = get().items;
      const itemId = item.id;
      const itemIdStr = itemId != null ? String(itemId) : '';
      const alreadyExists = (currentItems as T[]).some((existing: T) => {
        const existingId = (existing as any).id;
        return itemIdStr !== '' && String(existingId ?? '') === itemIdStr;
      });
      if (alreadyExists) {
        logger.debug(`[${name}Store] addItem: item id=${itemIdStr} already exists, skipping`);
        return;
      }
      logger.debug(`[${name}Store] Adding item:`, itemId);
      set((state: BaseStoreState<T>) => ({
        items: [...state.items, item]
      }));
    },
    
      updateItem: (id: string, updates: Partial<T>) => {
        const idStr = String(id);
        set((state: BaseStoreState<T>) => ({
          items: state.items.map(item => {
            const itemId = (item as any).id;
            return (itemId === id || String(itemId) === idStr) ? { ...item, ...updates } : item;
          })
        }));
      },
    
    removeItem: (id: string) => {
      const idStr = String(id);
      set((state: BaseStoreState<T>) => ({
        items: state.items.filter(item => {
          const itemId = (item as any).id;
          // Match by exact equality or string representation to handle mixed id types
          return itemId !== id && String(itemId) !== idStr;
        })
      }));
    },
    
    // QueryMethod
    getItemById: (id: string) => {
      const items = get().items;
      const idStr = String(id);
      return items.find((item: T) => String(item.id) === idStr) || null;
    },
    
    getItems: () => {
      return get().items;
    },
    
    // DataGet
    fetchItems: async (username: string, ...args: any[]) => {
      const state = get();

      // Check是否Need重新Get
      if (!state.shouldFetch()) {
        return;
      }

      set({ loading: true, error: null });

      try {
        const response = await apiService.getAll(username, ...args);

        if (response && response.success && response.data) {
          set({
            items: response.data,
            loading: false,
            lastFetched: Date.now(),
            error: null
          });
        } else {
          throw new Error(response.error?.message || `Failed to fetch ${name}s`);
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'An unknown error occurred';
        logger.error(`[${name}Store] Error fetching items:`, errorMessage);
        // Failure cooldown: without this, lastFetched stays null after a
        // failed fetch and shouldFetch() keeps returning true, so effect
        // re-runs hammer the backend in a tight loop (2026-08-31: new
        // customer machine fired queryAgentSkills several times per second,
        // each rejected UNAUTHENTICATED). Record the failure time so
        // shouldFetch() blocks refetches briefly; forceRefresh still works.
        (get() as any)._lastFailedAt = Date.now();
        set({ error: errorMessage, loading: false });
        throw error;
      }
    },
    
    shouldFetch: () => {
      // Failure cooldown (see fetchItems catch): block refetch storms after
      // an error — 15s is short enough to self-heal once auth is ready.
      const lastFailedAt = (get() as any)._lastFailedAt as number | undefined;
      if (lastFailedAt && Date.now() - lastFailedAt < 15_000) {
        return false;
      }
      const lastFetched = get().lastFetched;
      if (!lastFetched) {
        return true;
      }

      const now = Date.now();
      const diff = now - lastFetched;
      return diff > cacheDuration;
    },

    // 强制RefreshData（忽略Cache）
    forceRefresh: async (username: string, ...args: any[]) => {
      set({ lastFetched: null });
      await get().fetchItems(username, ...args);
    },

    // Status管理
    setLoading: (loading: boolean) => set({ loading }),

    setError: (error: string | null) => set({ error, loading: false }),

    clearData: () => {
      set({
        items: [],
        loading: false,
        error: null,
        lastFetched: null
      });
    },
  });

  // 根据Configuration决定是否使用 persist 中间件
  if (enablePersist) {
    return create<BaseStoreState<T>>()(
      persist(
        storeCreator,
        {
          name: `${name}-storage`,
          // 只持久化Data，不持久化 loading 和 error Status（除非明确指定）
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
 * CreateExtended的资源 Store
 * Allow在Standard store Base上AddCustomMethod
 * 
 * @param options - Store Configuration选项
 * @param apiService - API Service实例
 * @param extendStore - ExtendedFunction，ReceiveStandard store Status并返回ExtendedStatus
 * @returns Zustand store hook
 * 
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
    // CreateBase store Status（内联Implementation，避免使用 getState()）
    const baseState: BaseStoreState<T> = {
      // Data
      items: [],
      
      // Status
      loading: false,
      error: null,
      lastFetched: null,
      
      // Base CRUD Operation
      setItems: (items: T[]) => {
        set({ items, lastFetched: Date.now(), error: null });
      },

      addItem: (item: T) => {
        const currentItems = get().items;
        const itemId = item.id;
        const itemIdStr = itemId != null ? String(itemId) : '';
        const alreadyExists = (currentItems as T[]).some((existing: T) => {
          const existingId = (existing as any).id;
          return itemIdStr !== '' && String(existingId ?? '') === itemIdStr;
        });
        if (alreadyExists) {
          logger.debug(`[${name}Store] addItem: item id=${itemIdStr} already exists, skipping`);
          return;
        }
        set((state: BaseStoreState<T>) => ({
          items: [...state.items, item]
        }));
      },

      updateItem: (id: string, updates: Partial<T>) => {
        const idStr = String(id);
        set((state: BaseStoreState<T>) => ({
          items: state.items.map(item => {
            const itemId = (item as any).id;
            return (itemId === id || String(itemId) === idStr) ? { ...item, ...updates } : item;
          })
        }));
      },

      removeItem: (id: string) => {
        const idStr = String(id);
        set((state: BaseStoreState<T>) => ({
          items: state.items.filter(item => {
            const itemId = (item as any).id;
            return itemId !== id && String(itemId) !== idStr;
          })
        }));
      },
      
      // QueryMethod
      getItemById: (id: string) => {
        const idStr = String(id);
        return get().items.find((item: T) => {
          const itemId = (item as any).id;
          return itemId === id || String(itemId) === idStr;
        }) || null;
      },
      
      getItems: () => {
        return get().items;
      },
      
      // DataGet
      fetchItems: async (username: string, ...args: any[]) => {
        const state = get();

        // Check是否Need重新Get
        if (!state.shouldFetch()) {
          return;
        }

        set({ loading: true, error: null });

        try {
          const response = await apiService.getAll(username, ...args);

          if (response && response.success && response.data) {
            set({
              items: response.data,
              loading: false,
              lastFetched: Date.now(),
              error: null
            });
          } else {
            throw new Error(response.error?.message || `Failed to fetch ${name}s`);
          }
        } catch (error) {
          const errorMessage = error instanceof Error ? error.message : 'An unknown error occurred';
          logger.error(`[${name}Store] Error fetching items:`, errorMessage);
          // Failure cooldown — see the sibling copy above (UNAUTHENTICATED
          // refetch storm, 2026-08-31).
          (get() as any)._lastFailedAt = Date.now();
          set({ error: errorMessage, loading: false });
          throw error;
        }
      },

      shouldFetch: () => {
        // Failure cooldown (see fetchItems catch): block refetch storms after
        // an error — 15s is short enough to self-heal once auth is ready.
        const lastFailedAt = (get() as any)._lastFailedAt as number | undefined;
        if (lastFailedAt && Date.now() - lastFailedAt < 15_000) {
          return false;
        }
        const lastFetched = get().lastFetched;
        if (!lastFetched) {
          return true;
        }

        const now = Date.now();
        const diff = now - lastFetched;
        return diff > cacheDuration;
      },

      // 强制RefreshData（忽略Cache）
      forceRefresh: async (username: string, ...args: any[]) => {
        set({ lastFetched: null });
        await get().fetchItems(username, ...args);
      },

      // Status管理
      setLoading: (loading: boolean) => set({ loading }),

      setError: (error: string | null) => set({ error, loading: false }),

      clearData: () => {
        set({
          items: [],
          loading: false,
          error: null,
          lastFetched: null
        });
      },
    };
    
    // 然后应用Extended
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

