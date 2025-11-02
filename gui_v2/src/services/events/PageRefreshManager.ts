import { logger } from '../../utils/logger';
import { userStorageManager } from '../storage/UserStorageManager';
import { logoutManager } from '../LogoutManager';
import { handleOnboardingRequest } from '../onboarding/onboardingService';

// Operation type to execute after page refresh
export type PageRefreshAction = () => void | Promise<void>;

// Page refresh manager
export class PageRefreshManager {
    private static instance: PageRefreshManager;
    private isInitialized = false;
    private actions: Map<string, PageRefreshAction> = new Map();
    private cleanupFunctions: (() => void)[] = [];
    private isEnabled = false; // Disabled by default, only enabled after login success

    private constructor() {}

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

        logger.info('Initialize PageRefreshManager...');
        this.setupEventListeners();
        this.registerDefaultActions();
        this.registerLogoutCleanup();
        this.isInitialized = true;
        
        // Always attempt to restore user status from backend, regardless of localStorage data
        this.isEnabled = true;
        logger.info('PageRefreshManager initialization completed (always enabled, attempting to restore user status)');

        // Immediately execute restore operation once
        logger.info('🔄 Attempting to restore user status immediately');
        this.executeAllActions().catch(error => {
            logger.error('❌ Failed to execute restore operation during initialization:', error);
        });
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
        const handleLoad = () => {
            logger.info('🔄 Page reload completed, executing restore operation');
            this.executeAllActions();
        };

        // Add event listener
        window.addEventListener('load', handleLoad);

        // Save cleanup function reference
        this.cleanupFunctions = [
            () => window.removeEventListener('load', handleLoad)
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
                
                // TEST: Trigger onboarding message for testing with 3s delay
                // setTimeout(() => {
                //     handleOnboardingRequest('llm_provider_config', {
                //         suggestedAction: {
                //             type: 'navigate',
                //             path: '/settings',
                //             params: { tab: 'llm' }
                //         }
                //     });
                // }, 3000);
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
                logger.info('[PageRefreshManager] Cleanup completed');
            },
            priority: 20 // Medium priority
        });
    }
}

// Export singleton instance
export const pageRefreshManager = PageRefreshManager.getInstance(); 