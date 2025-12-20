/**
 * Store Sync Manager
 * 统一管理All store 的DataSync
 */

import { logger } from '../../utils/logger';

/**
 * Store Interface - AllNeedSync的 store MustImplementation
 */
export interface SyncableStore {
  getState: () => {
    fetchItems: (username: string, ...args: any[]) => Promise<void>;
    clearData: () => void;
    shouldFetch: () => boolean;
  };
}

/**
 * SyncConfiguration
 */
export interface SyncConfig {
  /** 是否并行Sync */
  parallel?: boolean;
  /** 是否强制Refresh（忽略Cache） */
  force?: boolean;
  /** SyncTimeoutTime（毫秒） */
  timeout?: number;
}

/**
 * SyncResult
 */
export interface SyncResult {
  success: boolean;
  storeName: string;
  error?: string;
  duration?: number;
}

/**
 * Store Sync管理器
 * 
 * 负责协调多个 store 的DataSync，提供统一的SyncInterface
 * 
 * @example
 * ```typescript
 * const syncManager = StoreSyncManager.getInstance();
 * 
 * // Register stores
 * syncManager.register('agent', useAgentStore);
 * syncManager.register('task', useTaskStore);
 * 
 * // SyncAllData
 * await syncManager.syncAll(username);
 * 
 * // Sync特定 stores
 * await syncManager.sync(username, ['agent', 'task']);
 * 
 * // 清除AllData
 * syncManager.clearAll();
 * ```
 */
export class StoreSyncManager {
  private static instance: StoreSyncManager;
  private stores: Map<string, SyncableStore> = new Map();
  private syncInProgress: boolean = false;

  private constructor() {}

  /**
   * Get单例实例
   */
  static getInstance(): StoreSyncManager {
    if (!StoreSyncManager.instance) {
      StoreSyncManager.instance = new StoreSyncManager();
    }
    return StoreSyncManager.instance;
  }

  /**
   * Register store
   * 
   * @param name - Store Name
   * @param store - Store 实例
   */
  register(name: string, store: SyncableStore): void {
    if (this.stores.has(name)) {
      logger.warn(`[SyncManager] Store "${name}" is already registered, overwriting`);
    }
    
    this.stores.set(name, store);
    logger.debug(`[SyncManager] Registered store: ${name}`);
  }

  /**
   * 注销 store
   * 
   * @param name - Store Name
   */
  unregister(name: string): void {
    if (this.stores.has(name)) {
      this.stores.delete(name);
      logger.debug(`[SyncManager] Unregistered store: ${name}`);
    }
  }

  /**
   * Get已Register的 store List
   */
  getRegisteredStores(): string[] {
    return Array.from(this.stores.keys());
  }

  /**
   * SyncAll已Register的 stores
   * 
   * @param username - User名
   * @param config - SyncConfiguration
   * @returns SyncResult数组
   */
  async syncAll(
    username: string, 
    config: SyncConfig = {}
  ): Promise<SyncResult[]> {
    const storeNames = Array.from(this.stores.keys());
    return this.sync(username, storeNames, config);
  }

  /**
   * Sync指定的 stores
   * 
   * @param username - User名
   * @param storeNames - 要Sync的 store Name数组
   * @param config - SyncConfiguration
   * @returns SyncResult数组
   */
  async sync(
    username: string,
    storeNames: string[],
    config: SyncConfig = {}
  ): Promise<SyncResult[]> {
    const {
      parallel = true,
      force = false,
      timeout = 30000,
    } = config;

    if (this.syncInProgress) {
      logger.warn('[SyncManager] Sync already in progress, skipping');
      return [];
    }

    this.syncInProgress = true;
    logger.info(`[SyncManager] Starting sync for stores: ${storeNames.join(', ')}`);
    
    const startTime = Date.now();
    const results: SyncResult[] = [];

    try {
      if (parallel) {
        // 并行Sync
        const promises = storeNames.map(name => 
          this.syncStore(username, name, force, timeout)
        );
        const syncResults = await Promise.allSettled(promises);
        
        syncResults.forEach((result, index) => {
          if (result.status === 'fulfilled') {
            results.push(result.value);
          } else {
            results.push({
              success: false,
              storeName: storeNames[index],
              error: result.reason?.message || 'Unknown error',
            });
          }
        });
      } else {
        // 串行Sync
        for (const name of storeNames) {
          const result = await this.syncStore(username, name, force, timeout);
          results.push(result);
        }
      }

      const duration = Date.now() - startTime;
      const successCount = results.filter(r => r.success).length;
      const failCount = results.length - successCount;
      
      logger.info(
        `[SyncManager] Sync completed in ${duration}ms. ` +
        `Success: ${successCount}, Failed: ${failCount}`
      );

      return results;
    } finally {
      this.syncInProgress = false;
    }
  }

  /**
   * Sync单个 store
   * 
   * @param username - User名
   * @param storeName - Store Name
   * @param force - 是否强制Refresh
   * @param timeout - TimeoutTime
   * @returns SyncResult
   */
  private async syncStore(
    username: string,
    storeName: string,
    force: boolean,
    timeout: number
  ): Promise<SyncResult> {
    const store = this.stores.get(storeName);
    
    if (!store) {
      logger.error(`[SyncManager] Store "${storeName}" not found`);
      return {
        success: false,
        storeName,
        error: 'Store not registered',
      };
    }

    const startTime = Date.now();

    try {
      const state = store.getState();
      
      // Check是否NeedSync
      if (!force && !state.shouldFetch()) {
        logger.debug(`[SyncManager] Store "${storeName}" using cached data`);
        return {
          success: true,
          storeName,
          duration: Date.now() - startTime,
        };
      }

      // CreateTimeout Promise
      const timeoutPromise = new Promise<never>((_, reject) => {
        setTimeout(() => reject(new Error('Sync timeout')), timeout);
      });

      // ExecuteSync
      await Promise.race([
        state.fetchItems(username),
        timeoutPromise,
      ]);

      const duration = Date.now() - startTime;
      logger.debug(`[SyncManager] Store "${storeName}" synced in ${duration}ms`);

      return {
        success: true,
        storeName,
        duration,
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      logger.error(`[SyncManager] Error syncing store "${storeName}":`, errorMessage);

      return {
        success: false,
        storeName,
        error: errorMessage,
        duration: Date.now() - startTime,
      };
    }
  }

  /**
   * 清除All stores 的Data
   */
  clearAll(): void {
    logger.info('[SyncManager] Clearing all stores');
    
    this.stores.forEach((store, name) => {
      try {
        store.getState().clearData();
        logger.debug(`[SyncManager] Cleared store: ${name}`);
      } catch (error) {
        logger.error(`[SyncManager] Error clearing store "${name}":`, error);
      }
    });
  }

  /**
   * 清除指定 stores 的Data
   * 
   * @param storeNames - 要清除的 store Name数组
   */
  clear(storeNames: string[]): void {
    logger.info(`[SyncManager] Clearing stores: ${storeNames.join(', ')}`);
    
    storeNames.forEach(name => {
      const store = this.stores.get(name);
      if (store) {
        try {
          store.getState().clearData();
          logger.debug(`[SyncManager] Cleared store: ${name}`);
        } catch (error) {
          logger.error(`[SyncManager] Error clearing store "${name}":`, error);
        }
      } else {
        logger.warn(`[SyncManager] Store "${name}" not found`);
      }
    });
  }

  /**
   * Check是否有Sync正在进行
   */
  isSyncing(): boolean {
    return this.syncInProgress;
  }
}

// Export单例实例
export const storeSyncManager = StoreSyncManager.getInstance();

