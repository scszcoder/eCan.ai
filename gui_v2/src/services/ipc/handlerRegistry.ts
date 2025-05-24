import { IPCRequest, IPCResponse } from './types';

// 定义处理器类型
type HandlerType = (request: IPCRequest, params: unknown) => Promise<IPCResponse>;

/**
 * IPC 处理器注册器
 */
export class IPCHandlerRegistry {
    private static handlers: Map<string, HandlerType> = new Map();

    /**
     * 注册处理器
     * @param method 方法名
     * @param handler 处理器函数
     */
    public static register(method: string, handler: HandlerType): void {
        this.handlers.set(method, handler);
    }

    /**
     * 获取处理器
     * @param method 方法名
     * @returns 处理器函数
     */
    public static getHandler(method: string): HandlerType | undefined {
        return this.handlers.get(method);
    }

    /**
     * 列出所有已注册的处理器
     * @returns 处理器名称列表
     */
    public static listHandlers(): string[] {
        return Array.from(this.handlers.keys());
    }
} 