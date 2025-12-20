import { logger } from '../../utils/logger';
import { userStorageManager } from '../storage/UserStorageManager';
import { logoutManager } from '../LogoutManager';

// Operation type to execute after page refresh
export type PageRefreshAction = () => void | Promise<void>;

// Page refresh manager
export class PageRefreshManager {
    private static instance: PageRefreshManager;
    private isInitialized = false;
    private actions: Map<string, PageRefreshAction> = new Map();
    private cleanupFunctions: (() => void)[] = [];
    private isEnabled = false; // Disabled by default, only enabled after login success

    private static readonly STORAGE_PAGE_LOAD_HASH = 'page_load_hash';
    private static readonly STORAGE_PAGE_WAS_REFRESH = 'page_was_refresh';
    private static readonly STORAGE_SKILL_EDITOR_RELOAD_CONSUMED = 'skill_editor_reload_consumed';

    private constructor() {}

    private static safeGet(key: string): string {
        try {
            return sessionStorage.getItem(key) || '';
        } catch {
            return '';
        }
    }

    private static safeSet(key: string, value: string): void {
        try {
            sessionStorage.setItem(key, value);
        } catch {
            // ignore
        }
    }

    public static getPageLoadHash(): string {
        return PageRefreshManager.safeGet(PageRefreshManager.STORAGE_PAGE_LOAD_HASH);
    }

    public static wasPageRefresh(): boolean {
        return PageRefreshManager.safeGet(PageRefreshManager.STORAGE_PAGE_WAS_REFRESH) === 'true';
    }

    public static isSkillEditorReloadConsumed(): boolean {
        return PageRefreshManager.safeGet(PageRefreshManager.STORAGE_SKILL_EDITOR_RELOAD_CONSUMED) === 'true';
    }

    public static resetSkillEditorReloadConsumed(): void {
        PageRefreshManager.safeSet(PageRefreshManager.STORAGE_SKILL_EDITOR_RELOAD_CONSUMED, 'false');
    }

    public static consumeSkillEditorReload(): void {
        PageRefreshManager.safeSet(PageRefreshManager.STORAGE_SKILL_EDITOR_RELOAD_CONSUMED, 'true');
    }

    public static isReloadSkillEditor(): boolean {
        const pageLoadHash = PageRefreshManager.getPageLoadHash();
        const pageWasRefresh = PageRefreshManager.wasPageRefresh();
        const reloadConsumed = PageRefreshManager.isSkillEditorReloadConsumed();
        return pageWasRefresh && pageLoadHash.includes('skill_editor') && !reloadConsumed;
    }

    // Singleton pattern
    public static getInstance(): PageRefreshManager {
        if (!PageRefreshManager.instance) {
            PageRefreshManager.instance = new PageRefreshManager();
        }
        return PageRefreshManager.instance;
    }



    // Initialize the manager
    public initialize(): void {
        if (this.isInitialized) {
            logger.warn('PageRefreshManager has already been initialized');
            return;
        }

        PageRefreshManager.safeSet(PageRefreshManager.STORAGE_PAGE_LOAD_HASH, window.location.hash || '');
        PageRefreshManager.resetSkillEditorReloadConsumed();

        logger.info('Initialize PageRefreshManager...');
        this.setupEventListeners();
        this.registerDefaultActions();
        this.registerLogoutCleanup();
        this.isInitialized = true;
        
        // 禁用应用启动时的自动登录，但保留页面刷新后的会话恢复
        // 通过检查 sessionStorage 来判断是否是应用首次启动
        const isAppRestart = !sessionStorage.getItem('app_session_active');

        // Persist a reliable refresh marker for this page load.
        // In some desktop runtimes (Qt WebEngine), performance.navigation.type may not be reliable.
        PageRefreshManager.safeSet(PageRefreshManager.STORAGE_PAGE_WAS_REFRESH, isAppRestart ? 'false' : 'true');
        
        if (isAppRestart) {
            // 应用首次启动：清除 localStorage，强制显示登录界面
            logger.info('App first launch detected, clearing user session data');
            userStorageManager.clearAllUserData();
            this.isEnabled = false;
            // 标记会话已激活
            sessionStorage.setItem('app_session_active', 'true');
        } else {
            // 页面刷新：保留会话恢复功能
            logger.info('Page refresh detected, session restoration enabled');
            this.isEnabled = true;
        }
        
        logger.info('PageRefreshManager initialization completed');
    }

    // Enable page refresh operations (called after login success)
    public enable(): void {
        this.isEnabled = true;
        logger.info('Page refresh operations enabled (user logged in)');
    }

    // Disable page refresh operations (called on logout)
    public disable(): void {
        this.isEnabled = false;
        logger.info('Page refresh operations disabled (user logged out)');
    }

    // Check if enabled
    public isPageRefreshEnabled(): boolean {
        return this.isEnabled;
    }

    // Register default operations
    private registerDefaultActions(): void {
        // Register operation to get login information
        this.registerAction('getLastLoginInfo', async () => {
            try {
                logger.info('Attempting to restore user status after page refresh');

                // Use unified storage manager to check and restore user status
                const restored = userStorageManager.restoreUserState();
                if (!restored) {
                    logger.info('No valid user session found, skipping auto login restoration');
                    return;
                }

                const userInfo = userStorageManager.getUserInfo();
                if (!userInfo) {
                    logger.error('User information restoration failed');
                    return;
                }

                logger.info('✅ User status restored:', userInfo.username);

                // // Validate session validity by attempting to get system data
                // const appData = await get_ipc_api().getAll(userInfo.username);
                // console.log('appData', appData);

                // // Save API response data to store
                // if (appData?.data) {
                //     logger.info('PageRefreshManager: Get all system data successful');
                //     // Update store
                //     AppDataStoreHandler.updateStore(appData.data as any);
                //     logger.info('PageRefreshManager: System data restored in store.');
                // } else {
                //     logger.error('PageRefreshManager: Get all system data failed');
                //     // If getting system data failed, session may be expired, cleanup user data
                //     if (appData?.error?.code === 'TOKEN_REQUIRED' || appData?.error?.code === 'UNAUTHORIZED') {
                //         logger.warn('Session may have expired, cleaning up user data');
                //         userStorageManager.clearAllUserData();
                //     }
                // }
                
                logger.info('Action execution completed after page refresh');
            } catch (error) {
                logger.error('Failed to get login information:', error);
            }
        });

        logger.info('Default operations registration completed');
    }

    // Setup event listeners
    private setupEventListeners(): void {
        // Listen for page reload completed event
        const handleLoad = async () => {
            logger.info('🔄 Page reload completed, executing page refresh operations');
            try {
                await this.executeAllActions();
                logger.info('✅ Page refresh operations finished');
            } catch (e) {
                logger.warn('Some page refresh operations failed (continuing to onboarding):', e);
            }
        };

        // Add event listeners
        window.addEventListener('load', handleLoad);
        window.addEventListener('DOMContentLoaded', handleLoad);

        // If the document is already loaded (SPA scenario), trigger immediately once
        if (document.readyState === 'complete' || document.readyState === 'interactive') {
            // schedule to next tick to ensure services are ready
            logger.info('[PageRefreshManager] Document already loaded, invoking handleLoad immediately');
            setTimeout(() => { void handleLoad(); }, 0);
        }

        // Save cleanup function reference
        this.cleanupFunctions = [
            () => window.removeEventListener('load', handleLoad),
            () => window.removeEventListener('DOMContentLoaded', handleLoad)
        ];

        logger.info('Page refresh event listener setup completed');
    }

    // Cleanup event listeners
    public cleanup(): void {
        if (!this.isInitialized) {
            return;
        }

        logger.info('Cleanup PageRefreshManager...');
        this.cleanupFunctions.forEach(cleanup => cleanup());
        this.cleanupFunctions = [];
        this.isInitialized = false;
        this.isEnabled = false; // Disable during cleanup
        logger.info('PageRefreshManager cleanup completed');
    }

    // Register operation to execute after page refresh
    public registerAction(name: string, action: PageRefreshAction): void {
        this.actions.set(name, action);
        logger.info(`Register page refresh operation: ${name}`);
    }

    // Unregister operation
    public unregisterAction(name: string): boolean {
        const removed = this.actions.delete(name);
        if (removed) {
            logger.info(`Unregister page refresh operation: ${name}`);
        }
        return removed;
    }

    // Execute all registered operations
    public async executeAllActions(): Promise<void> {
        logger.info(`🔄 Executing ${this.actions.size} page refresh operations`);
        
        const promises: Promise<void>[] = [];
        
        for (const [name, action] of this.actions) {
            try {
                logger.info(`Execute operation: ${name}`);
                const result = action();
                if (result instanceof Promise) {
                    promises.push(result);
                }
            } catch (error) {
                logger.error(`Execute operation ${name} failed:`, error);
            }
        }

        // Wait for all async operations to complete
        if (promises.length > 0) {
            try {
                await Promise.all(promises);
                logger.info('All page refresh operations executed successfully');
            } catch (error) {
                logger.error('Some page refresh operations failed:', error);
            }
        }
    }

    // Execute specific operation
    public async executeAction(name: string): Promise<void> {
        // Check if enabled
        if (!this.isEnabled) {
            logger.info('Page refresh operations disabled (user not logged in), skipping execution');
            return;
        }

        const action = this.actions.get(name);
        if (!action) {
            logger.warn(`Operation ${name} does not exist`);
            return;
        }

        try {
            logger.info(`Execute operation: ${name}`);
            const result = action();
            if (result instanceof Promise) {
                await result;
            }
            logger.info(`Operation ${name} execution completed`);
        } catch (error) {
            logger.error(`Execute operation ${name} failed:`, error);
            throw error;
        }
    }

    // Get registered operations list
    public getRegisteredActions(): string[] {
        return Array.from(this.actions.keys());
    }

    // Get manager status
    public getStatus(): { isInitialized: boolean; actionCount: number; isEnabled: boolean } {
        return {
            isInitialized: this.isInitialized,
            actionCount: this.actions.size,
            isEnabled: this.isEnabled
        };
    }

    /**
     * Register logout cleanup function
     */
    private registerLogoutCleanup(): void {
        logoutManager.registerCleanup({
            name: 'PageRefreshManager',
            cleanup: () => {
                logger.info('[PageRefreshManager] Cleaning up for logout...');
                this.disable(); // Disable page refresh operations
                this.cleanup(); // Cleanup event listeners
                this.actions.clear(); // Clear all registered operations
                // 清除 sessionStorage 标记，确保下次启动显示登录界面
                sessionStorage.removeItem('app_session_active');
                logger.info('[PageRefreshManager] Cleanup completed (session marker cleared)');
            },
            priority: 20 // Medium priority
        });
    }
}

// Export singleton instance
export const pageRefreshManager = PageRefreshManager.getInstance(); 