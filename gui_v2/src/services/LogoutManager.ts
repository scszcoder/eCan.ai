/**
 * FrontendLogout管理器
 * 负责协调AllFrontendComponent和Service的Cleanup工作
 */
import { logger } from '../utils/logger';
import { get_ipc_api } from './ipc_api';

export interface CleanupFunction {
  name: string;
  cleanup: () => void | Promise<void>;
  priority?: number; // Priority，数字越小越先Execute
}

export class LogoutManager {
  private static instance: LogoutManager;
  private cleanupFunctions: CleanupFunction[] = [];
  private isLoggingOut = false;

  private constructor() {}

  public static getInstance(): LogoutManager {
    if (!LogoutManager.instance) {
      LogoutManager.instance = new LogoutManager();
    }
    return LogoutManager.instance;
  }

  /**
   * RegisterCleanupFunction
   */
  public registerCleanup(cleanup: CleanupFunction): void {
    this.cleanupFunctions.push(cleanup);
    // 按PrioritySort，Priority小的先Execute
    this.cleanupFunctions.sort((a, b) => (a.priority || 100) - (b.priority || 100));
    logger.debug(`[LogoutManager] Registered cleanup function: ${cleanup.name}`);
  }

  /**
   * CancelRegisterCleanupFunction
   */
  public unregisterCleanup(name: string): void {
    const index = this.cleanupFunctions.findIndex(fn => fn.name === name);
    if (index !== -1) {
      this.cleanupFunctions.splice(index, 1);
      logger.debug(`[LogoutManager] Unregistered cleanup function: ${name}`);
    }
  }

  /**
   * Check是否正在Logout
   */
  public isLoggingOutNow(): boolean {
    return this.isLoggingOut;
  }

  /**
   * Executelogout流程
   */
  public async logout(): Promise<void> {
    if (this.isLoggingOut) {
      logger.warn('[LogoutManager] Logout already in progress, skipping...');
      return;
    }

    this.isLoggingOut = true;
    logger.info('[LogoutManager] Starting logout process...');

    try {
      // 1. 首先ExecuteFrontendCleanup
      await this.executeCleanup();

      // 2. 然后调用Backendlogout
      await this.callBackendLogout();

      // 3. CleanupLocalStorage
      this.clearLocalStorage();

      logger.info('[LogoutManager] Logout process completed successfully');
    } catch (error) {
      logger.error('[LogoutManager] Error during logout process:', error);
      throw error;
    } finally {
      this.isLoggingOut = false;
    }
  }

  /**
   * ExecuteAllRegister的CleanupFunction
   */
  private async executeCleanup(): Promise<void> {
    logger.info(`[LogoutManager] Executing ${this.cleanupFunctions.length} cleanup functions...`);

    for (const cleanupFn of this.cleanupFunctions) {
      try {
        logger.debug(`[LogoutManager] Executing cleanup: ${cleanupFn.name}`);
        const result = cleanupFn.cleanup();
        if (result instanceof Promise) {
          await result;
        }
        logger.debug(`[LogoutManager] Cleanup completed: ${cleanupFn.name}`);
      } catch (error) {
        logger.error(`[LogoutManager] Error in cleanup function ${cleanupFn.name}:`, error);
        // 继续Execute其他CleanupFunction，不因为一个Failed而停止
      }
    }

    logger.info('[LogoutManager] All cleanup functions executed');
  }

  /**
   * 调用Backendlogout API
   */
  private async callBackendLogout(): Promise<void> {
    try {
      logger.info('[LogoutManager] Calling backend logout...');
      const api = get_ipc_api();
      if (api) {
        const response = await api.logout();
        if (response.success) {
          logger.info('[LogoutManager] Backend logout successful');
        } else {
          logger.error('[LogoutManager] Backend logout failed:', response.error);
        }
      } else {
        logger.warn('[LogoutManager] IPC API not available for logout');
      }
    } catch (error) {
      logger.error('[LogoutManager] Error calling backend logout:', error);
      // 不抛出Error，因为FrontendCleanup已经Completed
    }
  }

  /**
   * CleanupLocalStorage
   */
  private clearLocalStorage(): void {
    try {
      logger.info('[LogoutManager] Clearing local storage...');
      
      // CleanupUserRelated tolocalStorage项
      const keysToRemove = [
        'userSession',
        'loginSession',
        'userInfo',
        'authToken',
        'lastLoginInfo'
      ];

      keysToRemove.forEach(key => {
        if (localStorage.getItem(key)) {
          localStorage.removeItem(key);
          logger.debug(`[LogoutManager] Removed localStorage key: ${key}`);
        }
      });

      // CleanupsessionStorage
      sessionStorage.clear();
      logger.debug('[LogoutManager] Cleared sessionStorage');

      logger.info('[LogoutManager] Local storage cleanup completed');
    } catch (error) {
      logger.error('[LogoutManager] Error clearing local storage:', error);
    }
  }

  /**
   * Reset管理器Status（Used forTest）
   */
  public reset(): void {
    this.cleanupFunctions = [];
    this.isLoggingOut = false;
    logger.debug('[LogoutManager] Manager state reset');
  }
}

// Export单例实例
export const logoutManager = LogoutManager.getInstance();
