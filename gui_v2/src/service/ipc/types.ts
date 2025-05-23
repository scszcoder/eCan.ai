/**
 * IPC 消息类型定义
 */

// 基础消息类型
export type MessageType = 'message' | 'config' | 'command' | 'event';

// 基础消息接口
export interface BaseMessage {
    type: MessageType;
    timestamp: number;
}

// 文本消息
export interface TextMessage extends BaseMessage {
    type: 'message';
    content: string;
}

// 配置消息
export interface ConfigMessage extends BaseMessage {
    type: 'config';
    action: 'get' | 'set';
    key: string;
    value?: unknown;
}

// 命令消息
export interface CommandMessage extends BaseMessage {
    type: 'command';
    command: string;
    args?: unknown[];
}

// 事件消息
export interface EventMessage extends BaseMessage {
    type: 'event';
    event: string;
    data?: unknown;
}

// 基础响应接口
export interface BaseResponse<T = unknown> {
    success: boolean;
    data?: T;
    error?: string;
}

// 配置数据
export interface ConfigData {
    [key: string]: unknown;
}

// 命令数据
export interface CommandData {
    command: string;
    args?: unknown[];
}

// 事件数据
export interface EventData {
    event: string;
    data?: unknown;
}

/**
 * IPC 接口定义
 */
export interface IPC {
    // 发送消息到 Python
    sendMessage(message: TextMessage): Promise<BaseResponse>;
    
    // 获取配置
    getConfig(key: string): Promise<BaseResponse<unknown>>;
    
    // 设置配置
    setConfig(key: string, value: unknown): Promise<BaseResponse>;
    
    // 执行命令
    executeCommand(command: string, args?: unknown[]): Promise<BaseResponse>;
    
    // 发送事件
    sendEvent(event: string, data?: unknown): Promise<BaseResponse>;
}

// 全局 Window 类型扩展
declare global {
    interface Window {
        qt: {
            webChannelTransport: {
                sendMessage: (message: string) => void;
                messageReceived: (message: string) => void;
            };
        };
        ipc: IPC;
    }
} 