/**
 * IPC 接口定义
 */
export interface IPC {
    web_to_python(message: string): Promise<string>;
}

/**
 * 消息类型
 */
export type MessageType = 'message' | 'config' | 'command' | 'event';

/**
 * 基础消息
 */
export interface BaseMessage {
    type: MessageType;
    timestamp: string;
}

/**
 * 文本消息
 */
export interface TextMessage extends BaseMessage {
    type: 'message';
    content: string;
}

/**
 * 配置消息
 */
export interface ConfigMessage extends BaseMessage {
    type: 'config';
    action: 'get' | 'set';
    key: string;
    value?: string;
}

/**
 * 命令消息
 */
export interface CommandMessage extends BaseMessage {
    type: 'command';
    command: string;
    args?: { args: unknown[] };
}

/**
 * 事件消息
 */
export interface EventMessage extends BaseMessage {
    type: 'event';
    event: string;
    data?: { data: unknown };
}

/**
 * 响应状态
 */
export type ResponseStatus = 'success' | 'error';

/**
 * 基础响应
 */
export interface BaseResponse<T = unknown> {
    status: ResponseStatus;
    message?: string;
    data?: T;
    timestamp: string;
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

// 全局 Window 类型扩展
declare global {
    interface Window {
        qt: {
            webChannelTransport: {
                send: (message: string) => void;
                onmessage: (message: { data: string }) => void;
            };
        };
        ipc: IPC;
    }
} 