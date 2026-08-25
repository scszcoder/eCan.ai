/**
 * FrontendLogout管理器
 * 负责协调AllFrontendComponent和Service的Cleanup工作
 */
import { logger } from '../utils/logger';
import { get_ipc_api } from './ipc_api';
import { cloudbaseAuth } from './auth/cloudbaseAuth';
import { resetAuthAdapter } from './auth/AuthProvider';
import { localWebSocketClient } from './web/localWebSocketClient';

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
        
        // Wait for backend cleanup to complete (server shutdown, resource cleanup, etc.)
        // This ensures the backend has enough time to properly clean up before frontend redirects
        logger.info('[LogoutManager] Waiting for backend cleanup to complete...');
        await new Promise(resolve => setTimeout(resolve, 1500));
        logger.info('[LogoutManager] Backend cleanup wait completed');
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
        // Authentication
        'ipc_auth_token',
        'token',
        'isAuthenticated',
        'authToken',
        
        // User info
        'username',
        'user_info',
        'userRole',
        'userSession',
        'loginSession',
        'userInfo',
        
        // Session
        'loginTime',
        'lastLogin',
        'lastLoginInfo',
        'session_id',
        'sessionExpiresAt',
        'lastActivity',
        
        // Preferences
        'language',
        'theme',
        'appData',
        'userPreferences',
        
        // Token refresh
        'token_expired_notification_shown'
      ];

      keysToRemove.forEach(key => {
        if (localStorage.getItem(key)) {
          localStorage.removeItem(key);
          logger.debug(`[LogoutManager] Removed localStorage key: ${key}`);
        }
      });

      // 清理所有以特定前缀开头的 key
      const allKeys = Object.keys(localStorage);
      allKeys.forEach(key => {
        if (key.startsWith('pref_') || 
            key.startsWith('user_') || 
            key.startsWith('session_') ||
            key.startsWith('temp_') ||
            key.startsWith('cache_') ||
            key.startsWith('draft_')) {
          localStorage.removeItem(key);
          logger.debug(`[LogoutManager] Removed prefixed key: ${key}`);
        }
      });

      // CleanupsessionStorage
      sessionStorage.clear();
      logger.debug('[LogoutManager] Cleared sessionStorage');

      // Clear CloudBase (CN app) auth singleton state.
      //
      // Regression fix: prior to this, logging out left `cloudbase_token`,
      // `cloudbase_refresh_token`, and `cloudbase_user_info` in localStorage
      // and the in-memory `cloudbaseAuth.token / userInfo / _refreshToken`
      // non-null. After logout the user is redirected back to /login where
      // LoginCN re-mounts and re-checks cloudbase state — leftover tokens
      // caused ``isLoggedIn()`` to return true and surfaced as
      // "登录后看不到微信 tab，邮箱/电话流程不可用" on the CN build.
      //
      // Both backends stay healthy: cloudbaseAuth.clearAuthState() only
      // touches browser-side state, and resetAuthAdapter() drops the
      // cached AuthProvider singleton (currentSession is also cleared).
      try {
        cloudbaseAuth.clearAuthState();
        resetAuthAdapter();
        logger.info('[LogoutManager] Cleared CloudBase (CN) auth singleton');
      } catch (e) {
        logger.warn('[LogoutManager] Failed to clear CloudBase auth state:', e);
      }

      // Stop the dev-mode LocalWebSocket reconnect loop.  When the user
      // logs out, the backend `python3 main.py` is also tearing down —
      // continuing to retry ws://localhost:4668/ws/skill-editor every 3s
      // produces ~10 ERR_CONNECTION_REFUSED errors in the browser console
      // for no benefit.  We re-enable auto-reconnect on the next LoginCN
      // mount (see LoginCN useEffect) so the link comes back automatically
      // after the backend restarts.
      try {
        localWebSocketClient.disconnect();
        logger.info('[LogoutManager] Stopped LocalWebSocketClient reconnect loop');
      } catch (e) {
        logger.warn('[LogoutManager] Failed to stop LocalWebSocketClient:', e);
      }

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
