/**
 * IPC (Inter-Process Communication) 类型定义
 * 提供 Python 后端和 Web 前端之间的通信类型定义
 */

/**
 * IPC 接口定义
 * 定义了与 Python 后端通信的基本接口
 */
export interface IPCWebChannel {
    /** 发送消息到 Python 后端 */
    web_to_python: (message: string) => string;
    /** 接收来自 Python 后端的消息 */
    python_to_web: {
        /** 连接消息处理器 */
        connect: (callback: (message: string) => void) => void;
    };
}

/**
 * IPC 消息类型
 */
export type IPCMessageType = 'request' | 'response';

/**
 * IPC 基础消息接口
 */
export interface IPCBaseMessage {
    /** 消息唯一标识 */
    id: string;
    /** 消息类型 */
    type: IPCMessageType;
    /** 消息时间戳 */
    timestamp?: number;
}

/**
 * IPC 请求
 * 用于从 Web 前端发送到 Python 后端的请求
 */
export interface IPCRequest extends IPCBaseMessage {
    type: 'request';
    /** 请求方法名 */
    method: string;
    /** 请求参数 */
    params?: unknown;
    /** 元数据 */
    meta?: Record<string, unknown>;
}

/**
 * IPC 响应
 * 用于从 Python 后端返回给 Web 前端的响应
 */
export interface IPCResponse extends IPCBaseMessage {
    type: 'response';
    /** 回显请求的方法名 */
    method?: string;
    /** 响应状态 */
    status: 'success' | 'error' | 'pending';
    /** 响应结果（成功时） */
    result?: unknown;
    /** 错误信息（失败时） */
    error?: IPCError;
    /** 元数据 */
    meta?: Record<string, unknown>;
}

/**
 * IPC 错误
 * 定义了错误响应的结构
 */
export interface IPCError {
    /** 错误码 */
    code: string | number;
    /** 错误描述 */
    message: string;
    /** 额外错误信息 */
    details?: unknown;
}

/**
 * IPC 请求处理器
 * 用于处理来自 Python 后端的请求
 */
export interface IPCRequestHandler {
    (request: IPCRequest): Promise<unknown>;
}

/**
 * IPC 响应处理器
 * 用于处理来自 Python 后端的响应
 */
export interface IPCResponseHandler {
    (response: IPCResponse): void;
}

/**
 * IPC 错误处理器
 * 用于处理通信过程中的错误
 */
export interface IPCErrorHandler {
    (error: IPCError): void;
}

/**
 * 创建 IPC 请求
 * @param method - 请求方法名
 * @param params - 请求参数
 * @param meta - 元数据
 * @returns IPC 请求对象
 */
export function createRequest(
    method: string,
    params?: unknown,
    meta?: Record<string, unknown>
): IPCRequest {
    return {
        id: generateRequestId(),
        type: 'request',
        method,
        params,
        meta,
        timestamp: Date.now()
    };
}

/**
 * 创建成功响应
 * @param id - 请求 ID
 * @param result - 响应结果
 * @returns IPC 响应对象
 */
export function createSuccessResponse(
    id: string,
    result: unknown
): IPCResponse {
    return {
        id,
        type: 'response',
        status: 'success',
        result,
        timestamp: Date.now()
    };
}

/**
 * 创建错误响应
 * @param id - 请求 ID
 * @param code - 错误码
 * @param message - 错误描述
 * @param details - 额外错误信息
 * @returns IPC 响应对象
 */
export function createErrorResponse(
    id: string,
    code: string,
    message: string,
    details?: unknown
): IPCResponse {
    return {
        id,
        type: 'response',
        status: 'error',
        error: {
            code,
            message,
            details
        },
        timestamp: Date.now()
    };
}

/**
 * 创建 pending 响应
 * @param id - 请求 ID
 * @param message - 描述信息
 * @param details - 额外信息
 * @returns IPC 响应对象
 */
export function createPendingResponse(
    id: string,
    message: string,
    details?: unknown
): IPCResponse {
    return {
        id,
        type: 'response',
        status: 'pending',
        result: {
            message,
            details
        },
        timestamp: Date.now()
    };
}

/**
 * 生成请求 ID
 * @returns 唯一的请求 ID
 */
export function generateRequestId(): string {
    return crypto.randomUUID();
}

/**
 * Qt WebChannel 接口定义
 * 定义了与 Qt WebChannel 交互的接口
 */
export interface QtWebChannel {
    /** 发送消息到 Python 后端 */
    web_to_python: (message: string) => string;
    /** 接收来自 Python 后端的消息 */
    python_to_web: {
        /** 连接消息处理器 */
        connect: (callback: (message: string) => void) => void;
    };
}

// 全局 Window 类型扩展
declare global {
    interface Window {
        /** Qt WebChannel 传输对象 */
        qt: {
            webChannelTransport: {
                /** 发送消息 */
                send: (message: string) => void;
                /** 接收消息 */
                onmessage: (message: { data: string }) => void;
            };
        };
        /** IPC 对象 */
        ipc: IPCWebChannel;
    }
}

// 添加 isIPCResponse 类型守卫
export function isIPCResponse(obj: any): obj is IPCResponse {
    return obj && typeof obj.id === 'string' && obj.type === 'response' &&
           (obj.status === 'success' || obj.status === 'error' || obj.status === 'pending');
} 