/**
 * 前端Logout管理器
 * 负责协调所有前端组件和服务的清理工作
 */
import { logger } from '../utils/logger';
import { get_ipc_api } from './ipc_api';

export interface CleanupFunction {
  name: string;
  cleanup: () => void | Promise<void>;
  priority?: number; // 优先级，数字越小越先执行
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
   * 注册清理函数
   */
  public registerCleanup(cleanup: CleanupFunction): void {
    this.cleanupFunctions.push(cleanup);
    // 按优先级排序，优先级小的先执行
    this.cleanupFunctions.sort((a, b) => (a.priority || 100) - (b.priority || 100));
    logger.debug(`[LogoutManager] Registered cleanup function: ${cleanup.name}`);
  }

  /**
   * 取消注册清理函数
   */
  public unregisterCleanup(name: string): void {
    const index = this.cleanupFunctions.findIndex(fn => fn.name === name);
    if (index !== -1) {
      this.cleanupFunctions.splice(index, 1);
      logger.debug(`[LogoutManager] Unregistered cleanup function: ${name}`);
    }
  }

  /**
   * 检查是否正在登出
   */
  public isLoggingOutNow(): boolean {
    return this.isLoggingOut;
  }

  /**
   * 执行logout流程
   */
  public async logout(): Promise<void> {
    if (this.isLoggingOut) {
      logger.warn('[LogoutManager] Logout already in progress, skipping...');
      return;
    }

    this.isLoggingOut = true;
    logger.info('[LogoutManager] Starting logout process...');

    try {
      // 1. 首先执行前端清理
      await this.executeCleanup();

      // 2. 然后调用后端logout
      await this.callBackendLogout();

      // 3. 清理本地存储
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
   * 执行所有注册的清理函数
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
        // 继续执行其他清理函数，不因为一个失败而停止
      }
    }

    logger.info('[LogoutManager] All cleanup functions executed');
  }

  /**
   * 调用后端logout API
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
      // 不抛出错误，因为前端清理已经完成
    }
  }

  /**
   * 清理本地存储
   */
  private clearLocalStorage(): void {
    try {
      logger.info('[LogoutManager] Clearing local storage...');
      
      // 清理用户相关的localStorage项
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

      // 清理sessionStorage
      sessionStorage.clear();
      logger.debug('[LogoutManager] Cleared sessionStorage');

      logger.info('[LogoutManager] Local storage cleanup completed');
    } catch (error) {
      logger.error('[LogoutManager] Error clearing local storage:', error);
    }
  }

  /**
   * 重置管理器状态（用于测试）
   */
  public reset(): void {
    this.cleanupFunctions = [];
    this.isLoggingOut = false;
    logger.debug('[LogoutManager] Manager state reset');
  }
}

// 导出单例实例
export const logoutManager = LogoutManager.getInstance();
