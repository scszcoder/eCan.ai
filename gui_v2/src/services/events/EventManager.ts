import { logger } from '../../utils/logger';
import { pageRefreshService, PageRefreshService } from './PageRefreshService';

// 事件服务接口
interface EventService {
    initialize(): void;
    cleanup(): void;
    getStatus(): { isInitialized: boolean; eventCount: number };
}

// 事件管理器类
export class EventManager {
    private static instance: EventManager;
    private services: Map<string, EventService> = new Map();
    private isInitialized = false;

    private constructor() {}

    // 单例模式
    public static getInstance(): EventManager {
        if (!EventManager.instance) {
            EventManager.instance = new EventManager();
        }
        return EventManager.instance;
    }

    // 注册事件服务
    public registerService(name: string, service: EventService): void {
        if (this.services.has(name)) {
            logger.warn(`事件服务 ${name} 已经存在，将被覆盖`);
        }
        this.services.set(name, service);
        logger.info(`注册事件服务: ${name}`);
    }

    // 获取事件服务
    public getService<T extends EventService>(name: string): T | undefined {
        return this.services.get(name) as T | undefined;
    }

    // 初始化所有服务
    public initialize(): void {
        if (this.isInitialized) {
            logger.warn('EventManager 已经初始化过了');
            return;
        }

        logger.info('初始化 EventManager...');
        
        // 注册默认服务
        this.registerDefaultServices();
        
        // 初始化所有服务
        this.services.forEach((service, name) => {
            try {
                service.initialize();
                logger.info(`事件服务 ${name} 初始化成功`);
            } catch (error) {
                logger.error(`事件服务 ${name} 初始化失败:`, error);
            }
        });

        this.isInitialized = true;
        logger.info('EventManager 初始化完成');
    }

    // 清理所有服务
    public cleanup(): void {
        if (!this.isInitialized) {
            return;
        }

        logger.info('清理 EventManager...');
        
        this.services.forEach((service, name) => {
            try {
                service.cleanup();
                logger.info(`事件服务 ${name} 清理成功`);
            } catch (error) {
                logger.error(`事件服务 ${name} 清理失败:`, error);
            }
        });

        this.isInitialized = false;
        logger.info('EventManager 清理完成');
    }

    // 获取所有服务状态
    public getAllServicesStatus(): Record<string, { isInitialized: boolean; eventCount: number }> {
        const status: Record<string, { isInitialized: boolean; eventCount: number }> = {};
        
        this.services.forEach((service, name) => {
            status[name] = service.getStatus();
        });

        return status;
    }

    // 获取管理器状态
    public getStatus(): { isInitialized: boolean; serviceCount: number } {
        return {
            isInitialized: this.isInitialized,
            serviceCount: this.services.size
        };
    }

    // 注册默认服务
    private registerDefaultServices(): void {
        // 注册页面刷新服务
        this.registerService('pageRefresh', pageRefreshService);
        
        // 这里可以注册其他事件服务
        // this.registerService('otherEvent', otherEventService);
    }

    // 获取服务列表
    public getServiceNames(): string[] {
        return Array.from(this.services.keys());
    }

    // 检查服务是否存在
    public hasService(name: string): boolean {
        return this.services.has(name);
    }

    // 移除服务
    public removeService(name: string): boolean {
        const service = this.services.get(name);
        if (service) {
            try {
                service.cleanup();
                this.services.delete(name);
                logger.info(`移除事件服务: ${name}`);
                return true;
            } catch (error) {
                logger.error(`移除事件服务 ${name} 失败:`, error);
                return false;
            }
        }
        return false;
    }
}

// 导出单例实例
export const eventManager = EventManager.getInstance(); 