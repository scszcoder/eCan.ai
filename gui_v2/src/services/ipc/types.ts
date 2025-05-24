/**
 * IPC 接口定义
 */
export interface IPC {
    web_to_python: (message: string) => void;
    python_to_web: {
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
    id: string;
    type: IPCMessageType;
    timestamp?: number;
}

/**
 * IPC 请求
 */
export interface IPCRequest extends IPCBaseMessage {
    type: 'request';
    method: string;
    params?: unknown;
    meta?: Record<string, unknown>;
}

/**
 * IPC 响应
 */
export interface IPCResponse extends IPCBaseMessage {
    type: 'response';
    method?: string;        // 回显请求的 method
    status: 'ok' | 'error'; // 调用结果状态
    result?: unknown;       // 正常返回的数据（status=ok 时必填）
    error?: IPCError;       // 错误信息（status=error 时必填）
    meta?: Record<string, unknown>;  // 扩展元信息
}

/**
 * IPC 错误
 */
export interface IPCError {
    code: string | number;  // 错误码
    message: string;        // 错误描述
    details?: unknown;      // 额外错误上下文
}

/**
 * IPC 请求处理器
 */
export interface IPCRequestHandler {
    (request: IPCRequest): Promise<unknown>;
}

/**
 * IPC 响应处理器
 */
export interface IPCResponseHandler {
    (response: IPCResponse): void;
}

/**
 * IPC 错误处理器
 */
export interface IPCErrorHandler {
    (error: IPCError): void;
}

/**
 * 创建 IPC 请求
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
        meta
    };
}

/**
 * 创建成功响应
 */
export function createSuccessResponse(
    id: string,
    result: unknown
): IPCResponse {
    return {
        id,
        type: 'response',
        status: 'ok',
        result
    };
}

/**
 * 创建错误响应
 */
export function createErrorResponse(
    id: string,
    code: string,
    message: string
): IPCResponse {
    return {
        id,
        type: 'response',
        status: 'error',
        error: {
            code,
            message
        }
    };
}

/**
 * 生成请求 ID
 */
function generateRequestId(): string {
    return Math.random().toString(36).substring(2, 15);
}

/**
 * Qt WebChannel 接口定义
 */
export interface QtWebChannel {
    web_to_python: (message: string) => IPCResponse;
    python_to_web: {
        connect: (callback: (message: string) => void) => void;
    };
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