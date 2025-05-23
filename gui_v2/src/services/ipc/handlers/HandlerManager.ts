import { BaseHandler } from './BaseHandler';
import { BaseMessage, BaseResponse } from '../types';

/**
 * 消息处理器管理器
 */
export class HandlerManager {
    private static instance: HandlerManager;
    private handlers: BaseHandler[] = [];

    private constructor() {}

    public static getInstance(): HandlerManager {
        if (!HandlerManager.instance) {
            HandlerManager.instance = new HandlerManager();
        }
        return HandlerManager.instance;
    }

    /**
     * 注册消息处理器
     */
    public registerHandler(handler: BaseHandler): void {
        this.handlers.push(handler);
    }

    /**
     * 移除消息处理器
     */
    public removeHandler(handler: BaseHandler): void {
        this.handlers = this.handlers.filter(h => h !== handler);
    }

    /**
     * 处理消息
     */
    public async handleMessage(message: BaseMessage): Promise<BaseResponse> {
        const handler = this.handlers.find(h => h.canHandle(message));
        if (!handler) {
            return {
                status: 'error',
                message: `No handler found for message type: ${message.type}`,
                timestamp: new Date().toISOString()
            };
        }

        return handler.handle(message);
    }
} 