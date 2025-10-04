/**
 * Store Sync Manager
 * 统一管理所有 store 的数据同步
 */

import { logger } from '../../utils/logger';

/**
 * Store 接口 - 所有需要同步的 store 必须实现
 */
export interface SyncableStore {
  getState: () => {
    fetchItems: (username: string, ...args: any[]) => Promise<void>;
    clearData: () => void;
    shouldFetch: () => boolean;
  };
}

/**
 * 同步配置
 */
export interface SyncConfig {
  /** 是否并行同步 */
  parallel?: boolean;
  /** 是否强制刷新（忽略缓存） */
  force?: boolean;
  /** 同步超时时间（毫秒） */
  timeout?: number;
}

/**
 * 同步结果
 */
export interface SyncResult {
  success: boolean;
  storeName: string;
  error?: string;
  duration?: number;
}

/**
 * Store 同步管理器
 * 
 * 负责协调多个 store 的数据同步，提供统一的同步接口
 * 
 * @example
 * ```typescript
 * const syncManager = StoreSyncManager.getInstance();
 * 
 * // 注册 stores
 * syncManager.register('agent', useAgentStore);
 * syncManager.register('task', useTaskStore);
 * 
 * // 同步所有数据
 * await syncManager.syncAll(username);
 * 
 * // 同步特定 stores
 * await syncManager.sync(username, ['agent', 'task']);
 * 
 * // 清除所有数据
 * syncManager.clearAll();
 * ```
 */
export class StoreSyncManager {
  private static instance: StoreSyncManager;
  private stores: Map<string, SyncableStore> = new Map();
  private syncInProgress: boolean = false;

  private constructor() {}

  /**
   * 获取单例实例
   */
  static getInstance(): StoreSyncManager {
    if (!StoreSyncManager.instance) {
      StoreSyncManager.instance = new StoreSyncManager();
    }
    return StoreSyncManager.instance;
  }

  /**
   * 注册 store
   * 
   * @param name - Store 名称
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
   * @param name - Store 名称
   */
  unregister(name: string): void {
    if (this.stores.has(name)) {
      this.stores.delete(name);
      logger.debug(`[SyncManager] Unregistered store: ${name}`);
    }
  }

  /**
   * 获取已注册的 store 列表
   */
  getRegisteredStores(): string[] {
    return Array.from(this.stores.keys());
  }

  /**
   * 同步所有已注册的 stores
   * 
   * @param username - 用户名
   * @param config - 同步配置
   * @returns 同步结果数组
   */
  async syncAll(
    username: string, 
    config: SyncConfig = {}
  ): Promise<SyncResult[]> {
    const storeNames = Array.from(this.stores.keys());
    return this.sync(username, storeNames, config);
  }

  /**
   * 同步指定的 stores
   * 
   * @param username - 用户名
   * @param storeNames - 要同步的 store 名称数组
   * @param config - 同步配置
   * @returns 同步结果数组
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
        // 并行同步
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
        // 串行同步
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
   * 同步单个 store
   * 
   * @param username - 用户名
   * @param storeName - Store 名称
   * @param force - 是否强制刷新
   * @param timeout - 超时时间
   * @returns 同步结果
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
      
      // 检查是否需要同步
      if (!force && !state.shouldFetch()) {
        logger.debug(`[SyncManager] Store "${storeName}" using cached data`);
        return {
          success: true,
          storeName,
          duration: Date.now() - startTime,
        };
      }

      // 创建超时 Promise
      const timeoutPromise = new Promise<never>((_, reject) => {
        setTimeout(() => reject(new Error('Sync timeout')), timeout);
      });

      // 执行同步
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
   * 清除所有 stores 的数据
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
   * 清除指定 stores 的数据
   * 
   * @param storeNames - 要清除的 store 名称数组
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
   * 检查是否有同步正在进行
   */
  isSyncing(): boolean {
    return this.syncInProgress;
  }
}

// 导出单例实例
export const storeSyncManager = StoreSyncManager.getInstance();

