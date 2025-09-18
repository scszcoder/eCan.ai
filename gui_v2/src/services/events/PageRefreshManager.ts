import { logger } from '../../utils/logger';
import { get_ipc_api } from '../../services/ipc_api';
import { AppDataStoreHandler } from '../../stores/AppDataStoreHandler';
import { userStorageManager } from '../storage/UserStorageManager';

// 页面刷新后的操作类型
export type PageRefreshAction = () => void | Promise<void>;

// 页面刷新管理器
export class PageRefreshManager {
    private static instance: PageRefreshManager;
    private isInitialized = false;
    private actions: Map<string, PageRefreshAction> = new Map();
    private cleanupFunctions: (() => void)[] = [];
    private isEnabled = false; // 默认禁用，只有在登录成功后才启用

    private constructor() {}

    // 单例模式
    public static getInstance(): PageRefreshManager {
        if (!PageRefreshManager.instance) {
            PageRefreshManager.instance = new PageRefreshManager();
        }
        return PageRefreshManager.instance;
    }



    // 初始化管理器
    public initialize(): void {
        if (this.isInitialized) {
            logger.warn('PageRefreshManager 已经初始化过了');
            return;
        }

        logger.info('初始化 PageRefreshManager...');
        this.setupEventListeners();
        this.registerDefaultActions();
        this.isInitialized = true;
        
        // 不管localStorage中是否有数据，都要尝试从后端获取用户状态
        this.isEnabled = true;
        logger.info('PageRefreshManager 初始化完成（总是启用，尝试恢复用户状态）');

        // 立即执行一次恢复操作
        logger.info('🔄 立即尝试恢复用户状态');
        this.executeAllActions().catch(error => {
            logger.error('❌ 初始化时执行恢复操作失败:', error);
        });
    }

    // 启用页面刷新操作（登录成功后调用）
    public enable(): void {
        this.isEnabled = true;
        logger.info('页面刷新操作已启用（用户已登录）');
    }

    // 禁用页面刷新操作（logout时调用）
    public disable(): void {
        this.isEnabled = false;
        logger.info('页面刷新操作已禁用（用户已登出）');
    }

    // 检查是否启用
    public isPageRefreshEnabled(): boolean {
        return this.isEnabled;
    }

    // 注册默认操作
    private registerDefaultActions(): void {
        // 注册获取登录信息的操作
        this.registerAction('getLastLoginInfo', async () => {
            try {
                logger.info('页面刷新后尝试恢复用户状态');

                // 使用统一存储管理器检查和恢复用户状态
                const restored = userStorageManager.restoreUserState();
                if (!restored) {
                    logger.info('没有找到有效的用户会话，跳过自动登录恢复');
                    return;
                }

                const userInfo = userStorageManager.getUserInfo();
                if (!userInfo) {
                    logger.error('用户信息恢复失败');
                    return;
                }

                logger.info('✅ 用户状态已恢复:', userInfo.username);

                // 验证会话有效性，尝试获取系统数据
                const appData = await get_ipc_api().getAll(userInfo.username);
                console.log('appData', appData);

                // 将API返回的数据保存到store中
                if (appData?.data) {
                    logger.info('PageRefreshManager: Get all system data successful');
                    // 更新 store
                    AppDataStoreHandler.updateStore(appData.data as any);
                    logger.info('PageRefreshManager: System data restored in store.');
                } else {
                    logger.error('PageRefreshManager: Get all system data failed');
                    // 如果获取系统数据失败，可能是会话过期，清理用户数据
                    if (appData?.error?.code === 'TOKEN_REQUIRED' || appData?.error?.code === 'UNAUTHORIZED') {
                        logger.warn('会话可能已过期，清理用户数据');
                        userStorageManager.clearAllUserData();
                    }
                }
                
                logger.info('页面刷新后执行动作完成');
            } catch (error) {
                logger.error('获取登录信息失败:', error);
            }
        });

        logger.info('默认操作注册完成');
    }

    // 设置事件监听器
    private setupEventListeners(): void {
        // 监听页面重新加载完成事件
        const handleLoad = () => {
            logger.info('🔄 页面重新加载完成，执行恢复操作');
            this.executeAllActions();
        };

        // 添加事件监听器
        window.addEventListener('load', handleLoad);

        // 保存清理函数引用
        this.cleanupFunctions = [
            () => window.removeEventListener('load', handleLoad)
        ];

        logger.info('页面刷新事件监听器设置完成');
    }

    // 清理事件监听器
    public cleanup(): void {
        if (!this.isInitialized) {
            return;
        }

        logger.info('清理 PageRefreshManager...');
        this.cleanupFunctions.forEach(cleanup => cleanup());
        this.cleanupFunctions = [];
        this.isInitialized = false;
        this.isEnabled = false; // 清理时禁用
        logger.info('PageRefreshManager 清理完成');
    }

    // 注册页面刷新后的操作
    public registerAction(name: string, action: PageRefreshAction): void {
        this.actions.set(name, action);
        logger.info(`注册页面刷新操作: ${name}`);
    }

    // 取消注册操作
    public unregisterAction(name: string): boolean {
        const removed = this.actions.delete(name);
        if (removed) {
            logger.info(`取消注册页面刷新操作: ${name}`);
        }
        return removed;
    }

    // 执行所有注册的操作
    public async executeAllActions(): Promise<void> {
        logger.info(`🔄 执行 ${this.actions.size} 个页面刷新操作`);
        
        const promises: Promise<void>[] = [];
        
        for (const [name, action] of this.actions) {
            try {
                logger.info(`执行操作: ${name}`);
                const result = action();
                if (result instanceof Promise) {
                    promises.push(result);
                }
            } catch (error) {
                logger.error(`执行操作 ${name} 失败:`, error);
            }
        }

        // 等待所有异步操作完成
        if (promises.length > 0) {
            try {
                await Promise.all(promises);
                logger.info('所有页面刷新操作执行完成');
            } catch (error) {
                logger.error('部分页面刷新操作执行失败:', error);
            }
        }
    }

    // 执行指定的操作
    public async executeAction(name: string): Promise<void> {
        // 检查是否启用
        if (!this.isEnabled) {
            logger.info('页面刷新操作已禁用（用户未登录），跳过执行');
            return;
        }

        const action = this.actions.get(name);
        if (!action) {
            logger.warn(`操作 ${name} 不存在`);
            return;
        }

        try {
            logger.info(`执行操作: ${name}`);
            const result = action();
            if (result instanceof Promise) {
                await result;
            }
            logger.info(`操作 ${name} 执行完成`);
        } catch (error) {
            logger.error(`执行操作 ${name} 失败:`, error);
            throw error;
        }
    }

    // 获取注册的操作列表
    public getRegisteredActions(): string[] {
        return Array.from(this.actions.keys());
    }

    // 获取管理器状态
    public getStatus(): { isInitialized: boolean; actionCount: number; isEnabled: boolean } {
        return {
            isInitialized: this.isInitialized,
            actionCount: this.actions.size,
            isEnabled: this.isEnabled
        };
    }
}

// 导出单例实例
export const pageRefreshManager = PageRefreshManager.getInstance(); 