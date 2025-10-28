import { logger } from '../../utils/logger';
import { userStorageManager } from '../storage/UserStorageManager';
import { logoutManager } from '../LogoutManager';

// PageRefresh后的OperationType
export type PageRefreshAction = () => void | Promise<void>;

// PageRefresh管理器
export class PageRefreshManager {
    private static instance: PageRefreshManager;
    private isInitialized = false;
    private actions: Map<string, PageRefreshAction> = new Map();
    private cleanupFunctions: (() => void)[] = [];
    private isEnabled = false; // DefaultDisabled，只有在LoginSuccess后才Enabled

    private constructor() {}

    // 单例模式
    public static getInstance(): PageRefreshManager {
        if (!PageRefreshManager.instance) {
            PageRefreshManager.instance = new PageRefreshManager();
        }
        return PageRefreshManager.instance;
    }



    // Initialize管理器
    public initialize(): void {
        if (this.isInitialized) {
            logger.warn('PageRefreshManager 已经Initialize过了');
            return;
        }

        logger.info('Initialize PageRefreshManager...');
        this.setupEventListeners();
        this.registerDefaultActions();
        this.registerLogoutCleanup();
        this.isInitialized = true;
        
        // 不管localStorage中是否有Data，都要尝试从BackendGetUserStatus
        this.isEnabled = true;
        logger.info('PageRefreshManager InitializeCompleted（总是Enabled，尝试RestoreUserStatus）');

        // 立即Execute一次RestoreOperation
        logger.info('🔄 立即尝试RestoreUserStatus');
        this.executeAllActions().catch(error => {
            logger.error('❌ Initialize时ExecuteRestoreOperationFailed:', error);
        });
    }

    // EnabledPageRefreshOperation（LoginSuccess后调用）
    public enable(): void {
        this.isEnabled = true;
        logger.info('PageRefreshOperation已Enabled（User已Login）');
    }

    // DisabledPageRefreshOperation（logout时调用）
    public disable(): void {
        this.isEnabled = false;
        logger.info('PageRefreshOperation已Disabled（User已Logout）');
    }

    // Check是否Enabled
    public isPageRefreshEnabled(): boolean {
        return this.isEnabled;
    }

    // RegisterDefaultOperation
    private registerDefaultActions(): void {
        // RegisterGetLoginInformation的Operation
        this.registerAction('getLastLoginInfo', async () => {
            try {
                logger.info('PageRefresh后尝试RestoreUserStatus');

                // 使用统一Storage管理器Check和RestoreUserStatus
                const restored = userStorageManager.restoreUserState();
                if (!restored) {
                    logger.info('没有找到有效的User会话，跳过自动LoginRestore');
                    return;
                }

                const userInfo = userStorageManager.getUserInfo();
                if (!userInfo) {
                    logger.error('UserInformationRestoreFailed');
                    return;
                }

                logger.info('✅ UserStatus已Restore:', userInfo.username);

                // // Validate会话有效性，尝试GetSystemData
                // const appData = await get_ipc_api().getAll(userInfo.username);
                // console.log('appData', appData);

                // // 将API返回的DataSave到store中
                // if (appData?.data) {
                //     logger.info('PageRefreshManager: Get all system data successful');
                //     // Update store
                //     AppDataStoreHandler.updateStore(appData.data as any);
                //     logger.info('PageRefreshManager: System data restored in store.');
                // } else {
                //     logger.error('PageRefreshManager: Get all system data failed');
                //     // IfGetSystemDataFailed，可能是会话过期，CleanupUserData
                //     if (appData?.error?.code === 'TOKEN_REQUIRED' || appData?.error?.code === 'UNAUTHORIZED') {
                //         logger.warn('会话可能已过期，CleanupUserData');
                //         userStorageManager.clearAllUserData();
                //     }
                // }
                
                logger.info('PageRefresh后ExecuteActionCompleted');
            } catch (error) {
                logger.error('GetLoginInformationFailed:', error);
            }
        });

        logger.info('DefaultOperationRegisterCompleted');
    }

    // SettingsEventListen器
    private setupEventListeners(): void {
        // ListenPage重新LoadCompletedEvent
        const handleLoad = () => {
            logger.info('🔄 Page重新LoadCompleted，ExecuteRestoreOperation');
            this.executeAllActions();
        };

        // AddEventListen器
        window.addEventListener('load', handleLoad);

        // SaveCleanupFunctionReference
        this.cleanupFunctions = [
            () => window.removeEventListener('load', handleLoad)
        ];

        logger.info('PageRefreshEventListen器SettingsCompleted');
    }

    // CleanupEventListen器
    public cleanup(): void {
        if (!this.isInitialized) {
            return;
        }

        logger.info('Cleanup PageRefreshManager...');
        this.cleanupFunctions.forEach(cleanup => cleanup());
        this.cleanupFunctions = [];
        this.isInitialized = false;
        this.isEnabled = false; // Cleanup时Disabled
        logger.info('PageRefreshManager CleanupCompleted');
    }

    // RegisterPageRefresh后的Operation
    public registerAction(name: string, action: PageRefreshAction): void {
        this.actions.set(name, action);
        logger.info(`RegisterPageRefreshOperation: ${name}`);
    }

    // CancelRegisterOperation
    public unregisterAction(name: string): boolean {
        const removed = this.actions.delete(name);
        if (removed) {
            logger.info(`CancelRegisterPageRefreshOperation: ${name}`);
        }
        return removed;
    }

    // ExecuteAllRegister的Operation
    public async executeAllActions(): Promise<void> {
        logger.info(`🔄 Execute ${this.actions.size} 个PageRefreshOperation`);
        
        const promises: Promise<void>[] = [];
        
        for (const [name, action] of this.actions) {
            try {
                logger.info(`ExecuteOperation: ${name}`);
                const result = action();
                if (result instanceof Promise) {
                    promises.push(result);
                }
            } catch (error) {
                logger.error(`ExecuteOperation ${name} Failed:`, error);
            }
        }

        // 等待AllAsyncOperationCompleted
        if (promises.length > 0) {
            try {
                await Promise.all(promises);
                logger.info('AllPageRefreshOperationExecuteCompleted');
            } catch (error) {
                logger.error('部分PageRefreshOperationExecuteFailed:', error);
            }
        }
    }

    // Execute指定的Operation
    public async executeAction(name: string): Promise<void> {
        // Check是否Enabled
        if (!this.isEnabled) {
            logger.info('PageRefreshOperation已Disabled（User未Login），跳过Execute');
            return;
        }

        const action = this.actions.get(name);
        if (!action) {
            logger.warn(`Operation ${name} 不存在`);
            return;
        }

        try {
            logger.info(`ExecuteOperation: ${name}`);
            const result = action();
            if (result instanceof Promise) {
                await result;
            }
            logger.info(`Operation ${name} ExecuteCompleted`);
        } catch (error) {
            logger.error(`ExecuteOperation ${name} Failed:`, error);
            throw error;
        }
    }

    // GetRegister的OperationList
    public getRegisteredActions(): string[] {
        return Array.from(this.actions.keys());
    }

    // Get管理器Status
    public getStatus(): { isInitialized: boolean; actionCount: number; isEnabled: boolean } {
        return {
            isInitialized: this.isInitialized,
            actionCount: this.actions.size,
            isEnabled: this.isEnabled
        };
    }

    /**
     * RegisterlogoutCleanupFunction
     */
    private registerLogoutCleanup(): void {
        logoutManager.registerCleanup({
            name: 'PageRefreshManager',
            cleanup: () => {
                logger.info('[PageRefreshManager] Cleaning up for logout...');
                this.disable(); // DisabledPageRefreshOperation
                this.cleanup(); // CleanupEventListen器
                this.actions.clear(); // CleanupAllRegister的Operation
                logger.info('[PageRefreshManager] Cleanup completed');
            },
            priority: 20 // 中等Priority
        });
    }
}

// Export单例实例
export const pageRefreshManager = PageRefreshManager.getInstance(); 