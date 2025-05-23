import { BaseHandler } from './BaseHandler';
import { TextMessage, BaseResponse } from '../types';

/**
 * 文本消息处理器
 */
export class TextMessageHandler extends BaseHandler {
    public getSupportedTypes(): string[] {
        return ['message'];
    }

    public async handle(message: TextMessage): Promise<BaseResponse> {
        try {
            // 处理文本消息的具体逻辑
            console.log('Processing text message:', message.content);
            
            return {
                status: 'success',
                message: 'Text message processed successfully',
                timestamp: new Date().toISOString()
            };
        } catch (error) {
            return {
                status: 'error',
                message: error instanceof Error ? error.message : 'Unknown error',
                timestamp: new Date().toISOString()
            };
        }
    }
} 