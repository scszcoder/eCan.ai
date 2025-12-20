/**
 * IPC Process器Register表
 * 管理 IPC RequestProcess器的Register和查找
 */
import { IPCRequestHandler } from './types';
import { logger } from '../../utils/logger';

/**
 * IPC Process器Register表类
 */
export class IPCHandlerRegistry {
    private static instance: IPCHandlerRegistry;
    private handlers: Map<string, IPCRequestHandler>;

    private constructor() {
        this.handlers = new Map();
    }

    /**
     * GetRegisterForm例
     * @returns Register表实例
     */
    public static getInstance(): IPCHandlerRegistry {
        if (!IPCHandlerRegistry.instance) {
            IPCHandlerRegistry.instance = new IPCHandlerRegistry();
        }
        return IPCHandlerRegistry.instance;
    }

    /**
     * RegisterRequestProcess器
     * @param method - RequestMethod名
     * @param handler - RequestProcess器Function
     */
    public register(method: string, handler: IPCRequestHandler): void {
        if (this.handlers.has(method)) {
            logger.warn(`Handler for method '${method}' already exists, overwriting`);
        }
        this.handlers.set(method, handler);
        logger.info(`Handler registered for method '${method}'`);
    }

    /**
     * GetRequestProcess器
     * @param method - RequestMethod名
     * @returns RequestProcess器Function，If不存在则返回 undefined
     */
    public getHandler(method: string): IPCRequestHandler | undefined {
        return this.handlers.get(method);
    }

    /**
     * 列出All已Register的Process器
     * @returns Process器Method名List
     */
    public listHandlers(): string[] {
        return Array.from(this.handlers.keys());
    }

    /**
     * 清除AllProcess器
     * MainUsed forTest或Reset
     */
    public clearHandlers(): void {
        this.handlers.clear();
        logger.info('All handlers cleared');
    }
} 