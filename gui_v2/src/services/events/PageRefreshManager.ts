import { logger } from '../../utils/logger';
import { APIResponse } from '../ipc';
import { get_ipc_api } from '../ipc_api';
import { useSystemStore } from '../../stores/systemStore';
import type { SystemData } from '../../types';
import { useUserStore } from '@/stores/userStore';

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

    // 检查用户是否已登录
    private checkUserLoginStatus(): boolean {
        const isAuthenticated = localStorage.getItem('isAuthenticated') === 'true';
        const token = localStorage.getItem('token');
        return isAuthenticated && !!token;
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
        
        // 检查用户登录状态，如果已登录则自动启用
        if (this.checkUserLoginStatus()) {
            this.isEnabled = true;
            logger.info('PageRefreshManager 初始化完成（用户已登录，自动启用）');
        } else {
            this.isEnabled = false;
            logger.info('PageRefreshManager 初始化完成（用户未登录，默认禁用）');
        }
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
                logger.info('页面刷新后获取登录信息');
                // 这里调用您的API
                const response: APIResponse<any> = await get_ipc_api().getLastLoginInfo();
				if (response?.data?.last_login) {
					const { username, password, machine_role } = response.data.last_login;
					logger.info('last_login', response.data.last_login);
                    localStorage.setItem('username', username);
			
                    useUserStore.getState().setUsername(username);
                    // 获取系统数据
					const systemData = await get_ipc_api().getAll(username);
					
					// 将API返回的数据保存到store中
					if (systemData?.data) {
                        logger.info('Get all system data successful');
                        console.log('systemData', systemData.data);
						const systemStore = useSystemStore.getState();
						systemStore.setData(systemData.data as SystemData);
						logger.info('system data 数据已保存到store中');
					} else {
                        logger.error('Get all system data failed');
                    }
				} else {
					logger.error('获取登录信息失败');
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
            logger.info('页面重新加载完成，检查是否执行操作');
            
            // 检查是否启用页面刷新操作
            if (!this.isEnabled) {
                logger.info('页面刷新操作已禁用（用户未登录），跳过执行');
                return;
            }
            
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
        // 检查是否启用
        if (!this.isEnabled) {
            logger.info('页面刷新操作已禁用（用户未登录），跳过执行');
            return;
        }

        logger.info(`执行 ${this.actions.size} 个页面刷新操作`);
        
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