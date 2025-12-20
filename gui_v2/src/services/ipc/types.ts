/**
 * IPC (Inter-Process Communication) TypeDefinition
 * 提供 Python Backend和 Web Frontend之间的通信TypeDefinition
 */

/**
 * IPC InterfaceDefinition
 * Definition了与 Python Backend通信的基本Interface
 */
export interface IPCWebChannel {
    /** SendMessage到 Python Backend */
    web_to_python: (message: string) => string;
    /** Receive来自 Python Backend的Message */
    python_to_web: {
        /** ConnectionMessageProcess器 */
        connect: (callback: (message: string) => void) => void;
    };
}

/**
 * IPC MessageType
 */
export type IPCMessageType = 'request' | 'response';

/**
 * IPC BaseMessageInterface
 */
export interface IPCBaseMessage {
    /** Message唯一标识 */
    id: string;
    /** MessageType */
    type: IPCMessageType;
    /** MessageTime戳 */
    timestamp?: number;
}

/**
 * IPC Request
 * Used for从 Web FrontendSend到 Python Backend的Request
 */
export interface IPCRequest extends IPCBaseMessage {
    type: 'request';
    /** RequestMethod名 */
    method: string;
    /** RequestParameter */
    params?: unknown;
    /** 元Data */
    meta?: Record<string, unknown>;
}

/**
 * IPC Response
 * Used for从 Python Backend返回给 Web Frontend的Response
 */
export interface IPCResponse extends IPCBaseMessage {
    type: 'response';
    /** 回显Request的Method名 */
    method?: string;
    /** ResponseStatus */
    status: 'success' | 'error' | 'pending';
    /** ResponseResult（Success时） */
    result?: unknown;
    /** ErrorInformation（Failed时） */
    error?: IPCError;
    /** 元Data */
    meta?: Record<string, unknown>;
}

/**
 * IPC Error
 * Definition了ErrorResponse的结构
 */
export interface IPCError {
    /** Error码 */
    code: string | number;
    /** ErrorDescription */
    message: string;
    /** 额外ErrorInformation */
    details?: unknown;
}

/**
 * IPC RequestProcess器
 * Used forProcess来自 Python Backend的Request
 */
export interface IPCRequestHandler {
    (request: IPCRequest): Promise<unknown>;
}

/**
 * IPC ResponseProcess器
 * Used forProcess来自 Python Backend的Response
 */
export interface IPCResponseHandler {
    (response: IPCResponse): void;
}

/**
 * IPC ErrorProcess器
 * Used forProcess通信过程中的Error
 */
export interface IPCErrorHandler {
    (error: IPCError): void;
}

/**
 * Create IPC Request
 * @param method - RequestMethod名
 * @param params - RequestParameter
 * @param meta - 元Data
 * @returns IPC Request对象
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
 * CreateSuccessResponse
 * @param id - Request ID
 * @param result - ResponseResult
 * @returns IPC Response对象
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
 * CreateErrorResponse
 * @param id - Request ID
 * @param code - Error码
 * @param message - ErrorDescription
 * @param details - 额外ErrorInformation
 * @returns IPC Response对象
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
 * Create pending Response
 * @param id - Request ID
 * @param message - DescriptionInformation
 * @param details - 额外Information
 * @returns IPC Response对象
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
 * 生成Request ID
 * @returns 唯一的Request ID
 */
export function generateRequestId(): string {
    return crypto.randomUUID();
}

/**
 * Qt WebChannel InterfaceDefinition
 * Definition了与 Qt WebChannel 交互的Interface
 */
export interface QtWebChannel {
    /** SendMessage到 Python Backend */
    web_to_python: (message: string) => string;
    /** Receive来自 Python Backend的Message */
    python_to_web: {
        /** ConnectionMessageProcess器 */
        connect: (callback: (message: string) => void) => void;
    };
}

// 全局 Window TypeExtended
declare global {
    interface Window {
        /** Qt WebChannel 传输对象 */
        qt: {
            webChannelTransport: {
                /** SendMessage */
                send: (message: string) => void;
                /** ReceiveMessage */
                onmessage: (message: { data: string }) => void;
            };
        };
        /** IPC 对象 */
        ipc: IPCWebChannel;
    }
}

// Add isIPCResponse Type守卫
export function isIPCResponse(obj: any): obj is IPCResponse {
    return obj && typeof obj.id === 'string' && obj.type === 'response' &&
           (obj.status === 'success' || obj.status === 'error' || obj.status === 'pending');
} 