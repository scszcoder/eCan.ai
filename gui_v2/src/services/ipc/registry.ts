/**
 * IPC 处理器注册表
 * 管理 IPC 请求处理器的注册和查找
 */
import { IPCRequestHandler } from './types';
import { logger } from '../../utils/logger';

/**
 * IPC 处理器注册表类
 */
export class IPCHandlerRegistry {
    private static instance: IPCHandlerRegistry;
    private handlers: Map<string, IPCRequestHandler>;

    private constructor() {
        this.handlers = new Map();
    }

    /**
     * 获取注册表单例
     * @returns 注册表实例
     */
    public static getInstance(): IPCHandlerRegistry {
        if (!IPCHandlerRegistry.instance) {
            IPCHandlerRegistry.instance = new IPCHandlerRegistry();
        }
        return IPCHandlerRegistry.instance;
    }

    /**
     * 注册请求处理器
     * @param method - 请求方法名
     * @param handler - 请求处理器函数
     */
    public register(method: string, handler: IPCRequestHandler): void {
        if (this.handlers.has(method)) {
            logger.warn(`Handler for method '${method}' already exists, overwriting`);
        }
        this.handlers.set(method, handler);
        logger.info(`Handler registered for method '${method}'`);
    }

    /**
     * 获取请求处理器
     * @param method - 请求方法名
     * @returns 请求处理器函数，如果不存在则返回 undefined
     */
    public getHandler(method: string): IPCRequestHandler | undefined {
        return this.handlers.get(method);
    }

    /**
     * 列出所有已注册的处理器
     * @returns 处理器方法名列表
     */
    public listHandlers(): string[] {
        return Array.from(this.handlers.keys());
    }

    /**
     * 清除所有处理器
     * 主要用于测试或重置
     */
    public clearHandlers(): void {
        this.handlers.clear();
        logger.info('All handlers cleared');
    }
} 