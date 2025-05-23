import { BaseMessage, BaseResponse } from '../types';

/**
 * 消息处理器基类
 */
export abstract class BaseHandler {
    /**
     * 处理消息
     * @param message 接收到的消息
     * @returns 处理结果
     */
    public abstract handle(message: BaseMessage): Promise<BaseResponse>;

    /**
     * 获取处理器支持的消息类型
     */
    public abstract getSupportedTypes(): string[];

    /**
     * 检查是否支持处理该消息
     */
    public canHandle(message: BaseMessage): boolean {
        return this.getSupportedTypes().includes(message.type);
    }
} 