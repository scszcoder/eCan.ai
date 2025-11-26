/**
 * 增强的 IPC Client
 * 集成Request队列、Retry逻辑、token管理等Advanced功能
 * 负责与 Python Backend进行通信
 */
import {
    IPCRequest,
    IPCResponse,
    IPCRequestHandler,
    IPCErrorHandler,
    createRequest,
    createErrorResponse,
    generateRequestId,
    isIPCResponse
} from './types';
import { IPCWebChannel } from './types';
import { getHandlers } from './handlers';
import { logger } from '../../utils/logger';
import { userStorageManager } from '../storage/UserStorageManager';

// Legacy token storage for backward compatibility
const tokenStorage = {
    getToken: () => userStorageManager.getToken(),
    setToken: (token: string) => userStorageManager.setToken(token),
    removeToken: () => userStorageManager.removeToken()
};

// RequestPriority枚举
export enum RequestPriority {
  LOW = 0,
  NORMAL = 1,
  HIGH = 2,
  URGENT = 3
}

// RequestStatus枚举
export enum RequestStatus {
  PENDING = 'pending',
  EXECUTING = 'executing',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled',
  RETRYING = 'retrying'
}

// 队列中的RequestInterface
export interface QueuedRequest {
  id: string;
  method: string;
  params: any;
  priority: RequestPriority;
  status: RequestStatus;
  createdAt: number;
  updatedAt: number;
  retryCount: number;
  maxRetries: number;
  retryDelay: number;
  backoffMultiplier: number;
  timeout?: number;
  onSuccess?: (data: any) => void;
  onError?: (error: any) => void;
  onProgress?: (progress: any) => void;
  metadata?: Record<string, any>;
}

// Request选项Interface
export interface IPCRequestOptions {
  priority?: RequestPriority;
  timeout?: number;
  maxRetries?: number;
  retryDelay?: number;
  backoffMultiplier?: number;
  onProgress?: (progress: any) => void;
}

const DEFAULT_REQUEST_TIMEOUT = 60000; // Default60秒Timeout（1分钟）

/**
 * IPC Client类
 * Implementation了与 Python Backend的通信功能
 */
export class IPCWCClient {
    private static instance: IPCWCClient;
    private ipcWebChannel: IPCWebChannel | null = null;
    private requestHandlers: Record<string, IPCRequestHandler>;
    private errorHandler: IPCErrorHandler | null = null;  // Reserved for future error handling
    private initPromise: Promise<void> | null = null;
    private messageHandlerConnected: boolean = false;  // Track if message handler is already connected
    
    // Used forStorage等待后台Response的Request
    private pendingRequests: Map<string, { resolve: (value: any) => void; reject: (reason?: any) => void; }> = new Map();
    
    // Request队列管理
    private requestQueue: QueuedRequest[] = [];
    private requestMap = new Map<string, QueuedRequest>();
    private processingQueue = false;
    private maxConcurrentRequests = 5;
    private activeRequests = new Set<string>();
    
    // 队列SizeLimit（防止内存泄漏）
    private readonly MAX_PENDING_REQUESTS = 1000;
    private readonly MAX_QUEUE_SIZE = 500;

    private constructor() {
        this.requestHandlers = getHandlers();
        this.init();
    }

    /**
     * Initialize IPC Client
     */
    private init(): void {
        logger.info('start ipc wc client init...');
        console.log('[IPCWCClient] init:start');
        if (this.ipcWebChannel) {
            return;
        }

        this.initPromise = new Promise((resolve) => {
            const handleWebChannelReady = () => {
                logger.info('WebChannel ready event triggered');
                console.log('[IPCWCClient] webchannel-ready event received');
                if (!this.ipcWebChannel && window.ipc) {
                    this.setIPCWebChannel(window.ipc);
                    logger.info('IPC initialized successfully');
                    console.log('[IPCWCClient] IPC initialized successfully with window.ipc');
                    window.removeEventListener('webchannel-ready', handleWebChannelReady);
                    resolve();
                }
            };

            window.addEventListener('webchannel-ready', handleWebChannelReady);
            logger.info('WebChannel ready event listener set up');
            console.log('[IPCWCClient] Listening for webchannel-ready event');

            if (document.readyState === 'complete' && window.ipc) {
                console.log('[IPCWCClient] document ready and window.ipc present, initializing immediately');
                handleWebChannelReady();
            }
        });
    }

    /**
     * 等待 IPC InitializeCompleted
     */
    private async waitForInit(): Promise<void> {
        if (this.ipcWebChannel) {
            return;
        }
        if (this.initPromise) {
            // Prevent indefinite hang if native WebChannel is never injected
            const INIT_TIMEOUT_MS = 5000;
            console.log('[IPCWCClient] waitForInit: awaiting initPromise with timeout', INIT_TIMEOUT_MS);
            try {
                await Promise.race([
                    this.initPromise,
                    new Promise<void>((_, reject) =>
                        setTimeout(() => reject(new Error('IPC init timeout')), INIT_TIMEOUT_MS)
                    ),
                ]);
            } catch (e) {
                // After timeout, if still not initialized, throw INIT_ERROR
                if (!this.ipcWebChannel) {
                    console.error('[IPCWCClient] waitForInit: timeout waiting for WebChannel');
                    throw createErrorResponse(
                        generateRequestId(),
                        'INIT_ERROR',
                        'IPC not initialized: WebChannel bridge not ready. Ensure the Python backend has started and injected window.ipc.'
                    );
                }
            }
        } else {
            // No init promise set and no channel: surface clear error
            console.error('[IPCWCClient] waitForInit: no initPromise and no ipcWebChannel');
            throw createErrorResponse(
                generateRequestId(),
                'INIT_ERROR',
                'IPC not initialized: missing init promise and WebChannel bridge.'
            );
        }
    }

    /**
     * Get IPC Client单例
     * @returns IPC Client实例
     */
    public static getInstance(): IPCWCClient {
        if (!IPCWCClient.instance) {
            IPCWCClient.instance = new IPCWCClient();
        }
        return IPCWCClient.instance;
    }

    /**
     * Settings IPC 对象
     * @param ipcWebChannel - IPC Interface实例
     */
    public setIPCWebChannel(ipcWebChannel: IPCWebChannel): void {
        if (this.ipcWebChannel) {
            logger.warn('IPC object already set, ignoring duplicate initialization');
            return;
        }
        this.ipcWebChannel = ipcWebChannel;
        this.setupMessageHandler();
        logger.info('IPC object set and message handler initialized');
    }

    /**
     * SettingsErrorProcess器
     * @param handler - ErrorProcess器Function
     */
    public setErrorHandler(handler: IPCErrorHandler): void {
        this.errorHandler = handler;
        logger.info('Error handler set');
    }

    /**
     * 增强的SendRequestMethod，Support队列和Retry
     * @param method - RequestMethod名
     * @param params - RequestParameter
     * @param options - Request选项
     * @returns Promise 对象，Parse为 IPC ResponseResult
     */
    public async invoke(method: string, params?: unknown, options: IPCRequestOptions = {}): Promise<any> {
        // Configuration选项：是否使用队列（DefaultClose以保持Stable性）
        const useQueue = options.priority !== undefined || options.maxRetries !== undefined || options.onProgress !== undefined;

        if (useQueue) {
            return this.enqueueRequest(method, params, options);
        } else {
            // 直接SendRequest（When前行为）
            return this.sendRequest(method, params, options.timeout);
        }
    }

    /**
     * 将Request加入队列
     * @param method - RequestMethod名
     * @param params - RequestParameter
     * @param options - Request选项
     * @returns Promise 对象，Parse为 IPC ResponseResult
     */
    private async enqueueRequest(method: string, params?: unknown, options: IPCRequestOptions = {}): Promise<any> {
        return new Promise((resolve, reject) => {
            // Check队列SizeLimit
            if (this.requestQueue.length >= this.MAX_QUEUE_SIZE) {
                const error = new Error(`Request queue is full (${this.MAX_QUEUE_SIZE} requests). Cannot enqueue new request: ${method}`);
                logger.error('[IPCWCClient] Queue size limit exceeded:', error);
                reject(error);
                return;
            }
            
            const queuedRequest: QueuedRequest = {
                id: generateRequestId(),
                method,
                params,
                priority: options.priority || RequestPriority.NORMAL,
                status: RequestStatus.PENDING,
                createdAt: Date.now(),
                updatedAt: Date.now(),
                retryCount: 0,
                maxRetries: options.maxRetries || 3,
                retryDelay: options.retryDelay || 1000,
                backoffMultiplier: options.backoffMultiplier || 1.5,
                timeout: options.timeout,
                onSuccess: resolve,
                onError: reject,
                onProgress: options.onProgress,
                metadata: {}
            };

            // Add到队列和Map
            this.requestQueue.push(queuedRequest);
            this.requestMap.set(queuedRequest.id, queuedRequest);

            // 按PrioritySort队列
            this.requestQueue.sort((a, b) => b.priority - a.priority);

            // 开始Process队列
            this.processQueue();
        });
    }

    /**
     * SendRequestMethod，保持 SYSTEM_NOT_READY Retry机制
     * @param method - RequestMethod名
     * @param params - RequestParameter
     * @returns Promise 对象，Parse为 IPC ResponseResult
     */
    public async sendRequest(method: string, params?: unknown, timeout: number = DEFAULT_REQUEST_TIMEOUT): Promise<any> {
        // 对于 SYSTEM_NOT_READY Error的RetryConfiguration
        const maxRetries = 60; // MaximumRetry60次
        const retryDelay = 1000; // 初始Delay1秒
        const backoffMultiplier = 1.0; // 退避倍数
        const maxRetryTime = 60000; // MaximumRetryTime60秒

        let retryCount = 0;
        const startTime = Date.now();

        while (retryCount <= maxRetries) {
            try {
                const response = await this._sendSingleRequest(method, params, timeout);

                // IfSuccessornot SYSTEM_NOT_READY Error，直接返回
                if (response.status === 'success' ||
                    (response.status === 'error' && response.error?.code !== 'SYSTEM_NOT_READY')) {
                    return response;
                }

                // Check是否超过MaximumRetryTime
                if (Date.now() - startTime > maxRetryTime) {
                    logger.warn(`[IPCWCClient] ${method} exceeded max retry time (${maxRetryTime/1000}s), giving up`);
                    return response;
                }

                // If是 SYSTEM_NOT_READY 且还CanRetry
                if (retryCount < maxRetries) {
                    const delay = retryDelay * Math.pow(backoffMultiplier, retryCount);
                    logger.info(`[IPCWCClient] System not ready for ${method}, retrying in ${delay}ms (attempt ${retryCount + 1}/${maxRetries})`);

                    // 等待Delay后Retry
                    await new Promise(resolve => setTimeout(resolve, delay));
                    retryCount++;
                    continue;
                }

                // 达到MaximumRetry次数，返回最后的Response
                logger.warn(`[IPCWCClient] ${method} failed after ${maxRetries} retries - System initialization taking longer than expected`);
                return response;

            } catch (error) {
                // 对于NetworkError等，不进行Retry，直接抛出
                throw error;
            }
        }
    }

    /**
     * Send单个Request（InternalMethod）
     * @param method - RequestMethod名
     * @param params - RequestParameter
     * @param timeout - TimeoutTime
     * @returns Promise 对象，Parse为 IPC ResponseResult
     */
    private async _sendSingleRequest(method: string, params?: unknown, timeout: number = DEFAULT_REQUEST_TIMEOUT): Promise<any> {
        console.log('[IPCWCClient] _sendSingleRequest:start', method, { params, timeout });
        await this.waitForInit();

        if (!this.ipcWebChannel) {
            throw createErrorResponse(generateRequestId(), 'INIT_ERROR', 'IPC not initialized');
        }

        // Check pendingRequests SizeLimit
        if (this.pendingRequests.size >= this.MAX_PENDING_REQUESTS) {
            const error = `Too many pending requests (${this.MAX_PENDING_REQUESTS}). Cannot send new request: ${method}`;
            logger.error('[IPCWCClient] Pending requests limit exceeded:', error);
            throw createErrorResponse(generateRequestId(), 'QUEUE_FULL', error);
        }

        const request = createRequest(method, this.addAuthToken(method, params));
        const paramsStr = params ? JSON.stringify(params) : '';
        const truncatedParams = paramsStr.length > 500 ? paramsStr.substring(0, 500) + '...' : paramsStr;
        console.log('[IPCWCClient] sending web_to_python', { id: request.id, method, truncatedParams });

        // 对于LoginRequest，使用更长的TimeoutTime
        if (method === 'login') {
            timeout = Math.max(timeout, 180000); // Login至少3分钟Timeout
            logger.info(`[IPCWCClient] Login request detected, using extended timeout: ${timeout/1000}s`);
        }

        // 1. Settings一个TimeoutPromise
        let timeoutId: number;
        const timeoutPromise = new Promise((_, reject) => {
            timeoutId = window.setTimeout(() => {
                // IfTimeout发生，从管理器中主动Delete，这是它唯一的Cleanup点
                this.pendingRequests.delete(request.id);
                const errorMessage = method === 'login' 
                    ? `Login request timed out after ${timeout / 1000} seconds. This may be due to slow network or AWS service response.`
                    : `Request timed out after ${timeout / 1000} seconds.`;
                reject(createErrorResponse(request.id, 'TIMEOUT_ERROR', errorMessage));
            }, timeout);
        });

        // 2. Settings主Request的Promise
        const mainRequestPromise = new Promise(async (resolve, reject) => {
            // 将 Promise 的控制器Storage起来，供 handleMessage 或Timeout使用
            this.pendingRequests.set(request.id, { resolve, reject });
            
            try {
                const responseStr = await this.ipcWebChannel!.web_to_python(JSON.stringify(request));
                console.log('[IPCWCClient] immediate response received', { id: request.id, method });
                const immediateResponse = JSON.parse(responseStr) as IPCResponse;
                
                // If是Sync任务，它会立即Completed，我们不Need等待推送
                if (immediateResponse.status !== 'pending') {
                    // 从管理器中Remove，因为它已经Completed了
                    this.pendingRequests.delete(request.id);
                    resolve(immediateResponse);
                    console.log('[IPCWCClient] completed synchronously', { id: request.id, method });
                } else {
                    console.log('[IPCWCClient] pending response (await push)', { id: request.id, method });
                }
                // If是 'pending'，则我们什么都不做，把Cleanup工作留给 handleMessage 或Timeout
            } catch (error) {
                this.pendingRequests.delete(request.id); // SendFailed，也要Cleanup
                console.error('[IPCWCClient] send error', { id: request.id, method, error });
                reject(error instanceof Error ? createErrorResponse(request.id, 'SEND_ERROR', error.message) : error);
            }
        });

        try {
             // 3. 让主Request和Timeout"竞赛"
            return await Promise.race([mainRequestPromise, timeoutPromise]);
        } finally {
            // 4. 无论Result如何，清除定时器，防止它在RequestSuccess后依然Trigger
            clearTimeout(timeoutId!);
            console.log('[IPCWCClient] _sendSingleRequest:end', method);
        }
    }
    /**
     * Process来自 Python Backend的Message (包括Request和推送的Response)
     * @param message - Message字符串
     */
    private handleMessage(message: string): void {
        try {
            console.trace('[IPCWCClient] python_to_web message (FULL)', message);

            const message_obj = JSON.parse(message);

            // Check这是否是一个对后台任务的最终Response
            if (isIPCResponse(message_obj) && this.pendingRequests.has(message_obj.id)) {
                console.log('[IPCWCClient] pushed response for pending request', message_obj.id);
                const response = message_obj as IPCResponse;

                const promiseCallbacks = this.pendingRequests.get(message_obj.id)!;
                this.pendingRequests.delete(message_obj.id);
                promiseCallbacks.resolve(response);
                return; // Message已Process，直接返回
            }
            
            // Check这是否是 Python 主动发起的Request
            if (message_obj.type === 'request') {
                this.handleRequest(message_obj);
            } else {
                console.warn('[IPCWCClient] unhandled message', message_obj);
            }
        } catch (error) {
            console.error('[IPCWCClient] handleMessage parse error', error);
        }
    }

/**
 * ProcessRequestMessage
 * @param request - Request对象
 */
private async handleRequest(request: IPCRequest): Promise<void> {
    const handler = this.requestHandlers[request.method];
    if (!handler) {
        logger.warn(`No handler registered for method '${request.method}'`);
        this.sendErrorResponse(request.id, {
            code: 'HANDLER_ERROR',
            message: `No handler registered for method '${request.method}'`,
            details: ""
        });
        return;
    }

    try {
        const result = await handler(request);
        console.trace('[IPCWCClient] Request handled successfully:', request.method);
        this.sendResponse(request.id, result);
    } catch (error) {
        console.error('[IPCWCClient] Request handling error:', error);
        this.sendErrorResponse(request.id, {
            code: 'HANDLER_ERROR',
            message: error instanceof Error ? error.message : 'Handler error occurred',
            details: error
        });
    }
}

/**
 * SendResponse给Backend
 * @param requestId - RequestID
 * @param result - ResponseResult
 */
private sendResponse(requestId: string, result: any): void {
    if (!this.ipcWebChannel) {
        logger.error('Cannot send response: IPC channel not initialized');
        return;
    }

    const response: IPCResponse = {
        id: requestId,
        type: 'response',
        status: 'success',
        result: result,
        timestamp: Date.now()
    };

    try {
        this.ipcWebChannel.web_to_python(JSON.stringify(response));
        logger.debug(`Response sent for request ${requestId}`);
    } catch (error) {
        logger.error(`Failed to send response for request ${requestId}:`, error);
    }
}

/**
 * SendErrorResponse给Backend
 * @param requestId - RequestID
 * @param error - ErrorInformation
 */
private sendErrorResponse(requestId: string, error: { code: string; message: string; details?: any }): void {
    if (!this.ipcWebChannel) {
        logger.error('Cannot send error response: IPC channel not initialized');
        return;
    }

    const response: IPCResponse = {
        id: requestId,
        type: 'response',
        status: 'error',
        error: error,
        timestamp: Date.now()
    };

    try {
        this.ipcWebChannel.web_to_python(JSON.stringify(response));
        logger.debug(`Error response sent for request ${requestId}:`, error.message);
    } catch (sendError) {
        logger.error(`Failed to send error response for request ${requestId}:`, sendError);
    }
}

/**
 * SettingsMessageProcess器，Listen来自 Python 的Message
 */
private setupMessageHandler(): void {
    if (!this.ipcWebChannel) return;
    
    // Prevent duplicate connection
    if (this.messageHandlerConnected) {
        console.log('[IPCWCClient] Message handler already connected, skipping duplicate connection');
        return;
    }
    
    // 关键: Listen python_to_web 信号
    if (this.ipcWebChannel.python_to_web && typeof this.ipcWebChannel.python_to_web.connect === 'function') {
        this.ipcWebChannel.python_to_web.connect(this.handleMessage.bind(this));
        this.messageHandlerConnected = true;
        console.log('[IPCWCClient] Connected to python_to_web signal');
    } else {
        console.error('[IPCWCClient] Could not connect to python_to_web signal');
    }
}

/**
 * ProcessRequest队列
 */
private async processQueue(): Promise<void> {
    if (this.processingQueue || this.activeRequests.size >= this.maxConcurrentRequests) {
        return;
    }

    this.processingQueue = true;

    try {
        while (this.activeRequests.size < this.maxConcurrentRequests) {
            const request = this.dequeueRequest();
            if (!request) break;

            this.executeQueuedRequest(request);
        }
    } finally {
        this.processingQueue = false;
    }
}

    /**
     * 从队列中取出Request
     */
    private dequeueRequest(): QueuedRequest | null {
        const index = this.requestQueue.findIndex(req => req.status === RequestStatus.PENDING);
        if (index === -1) return null;

        const request = this.requestQueue[index];
        request.status = RequestStatus.EXECUTING;
        request.updatedAt = Date.now();

        return request;
    }

    /**
     * Execute队列中的Request
     */
    private async executeQueuedRequest(request: QueuedRequest): Promise<void> {
        this.activeRequests.add(request.id);

        try {
            const response = await this.sendRequest(request.method, request.params, request.timeout);

            request.status = RequestStatus.COMPLETED;
            request.updatedAt = Date.now();
            request.onSuccess?.(response);

            // 从队列中Remove已Completed的Request
            this.removeFromQueue(request.id);
        } catch (error) {
            await this.handleQueuedRequestError(request, error);
        } finally {
            this.activeRequests.delete(request.id);
            // 继续Process队列
            setTimeout(() => this.processQueue(), 0);
        }
    }

    /**
     * Process队列RequestError和Retry逻辑
     */
    private async handleQueuedRequestError(request: QueuedRequest, error: any): Promise<void> {
        const shouldRetry = this.isRetryableError(error) && request.retryCount < request.maxRetries;

        if (shouldRetry) {
            request.retryCount++;
            request.status = RequestStatus.RETRYING;
            request.updatedAt = Date.now();

            const delay = request.retryDelay * Math.pow(request.backoffMultiplier, request.retryCount - 1);

            // 对于 SYSTEM_NOT_READY Error，提供更友好的LogInformation
            if (error.code === 'SYSTEM_NOT_READY' || error.message?.includes('SYSTEM_NOT_READY')) {
                logger.info(`[IPC] System not ready for ${request.method}, retrying in ${delay}ms (attempt ${request.retryCount}/${request.maxRetries})`);
            } else {
                logger.info(`[IPC] Retrying ${request.method} in ${delay}ms (attempt ${request.retryCount}/${request.maxRetries}) - Error: ${error.code || error.message}`);
            }

            setTimeout(() => {
                request.status = RequestStatus.PENDING;
                this.processQueue();
            }, delay);
        } else {
            request.status = RequestStatus.FAILED;
            request.updatedAt = Date.now();

            // 对于 SYSTEM_NOT_READY Error，提供更Detailed的FailedInformation
            if (error.code === 'SYSTEM_NOT_READY' || error.message?.includes('SYSTEM_NOT_READY')) {
                logger.warn(`[IPC] ${request.method} failed after ${request.maxRetries} retries - System initialization taking longer than expected`);
            } else {
                logger.error(`[IPC] ${request.method} failed after ${request.maxRetries} retries - Final error: ${error.code || error.message}`);
            }

            request.onError?.(error);

            // 从队列中RemoveFailed的Request
            this.removeFromQueue(request.id);
        }
    }

    /**
     * 判断Error是否可Retry
     */
    private isRetryableError(error: any): boolean {
        const retryableErrors = [
            'NETWORK_ERROR',
            'TIMEOUT_ERROR',
            'SYSTEM_INITIALIZING',
            'CONNECTION_ERROR',
            'TEMPORARY_ERROR',
            'SYSTEM_NOT_READY',
            'SYSTEM_NOT_READY_TIMEOUT',
            'SYSTEM_CHECK_ERROR'
        ];

        return retryableErrors.includes(error.code) ||
               error.message?.includes('timeout') ||
               error.message?.includes('network');
    }

    /**
     * 从队列中RemoveRequest
     */
    private removeFromQueue(requestId: string): void {
        const index = this.requestQueue.findIndex(req => req.id === requestId);
        if (index !== -1) {
            this.requestQueue.splice(index, 1);
        }
        this.requestMap.delete(requestId);
    }

    /**
     * 清空队列
     */
    clearQueue(): void {
        this.requestQueue = [];
        this.requestMap.clear();
        this.activeRequests.clear();
        this.processingQueue = false;
    }

    /**
     * 为RequestAdd认证 token
     * Backend会根据白名单自动ProcesstokenValidate，Frontend统一Sendtoken
     */
    private addAuthToken(method: string, params: any): any {
        const token = tokenStorage.getToken();
        if (!token) {
            logger.debug(`No auth token available for method: ${method} (backend will handle whitelist)`);
            return params;
        }
        
        // IfParameter是对象，Add token Field
        if (params && typeof params === 'object' && params !== null) {
            return { ...params, token };
        }
        
        // 否则CreateInclude token 的对象
        return { token, params };
    }

    // ===== Public队列管理Interface =====

    /**
     * Get队列统计Information
     */
    public getQueueStats() {
        const stats = {
            total: this.requestQueue.length,
            pending: 0,
            executing: 0,
            completed: 0,
            failed: 0,
            retrying: 0
        };

        this.requestQueue.forEach(req => {
            switch (req.status) {
                case RequestStatus.PENDING:
                    stats.pending++;
                    break;
                case RequestStatus.EXECUTING:
                    stats.executing++;
                    break;
                case RequestStatus.COMPLETED:
                    stats.completed++;
                    break;
                case RequestStatus.FAILED:
                    stats.failed++;
                    break;
                case RequestStatus.RETRYING:
                    stats.retrying++;
                    break;
            }
        });

        return stats;
    }

    /**
     * 根据StatusGetRequestList
     */
    public getRequestsByStatus(status: RequestStatus): QueuedRequest[] {
        return this.requestQueue.filter(req => req.status === status);
    }

    /**
     * GetAllRequestList
     */
    public getAllRequests(): QueuedRequest[] {
        return [...this.requestQueue];
    }

    /**
     * CancelRequest
     */
    public cancelRequest(requestId: string): boolean {
        const request = this.requestMap.get(requestId);
        if (!request) return false;

        request.status = RequestStatus.CANCELLED;
        request.updatedAt = Date.now();
        this.removeFromQueue(requestId);
        
        return true;
    }

    /**
     * 清空队列
     */

}

// Export单例和便捷Method
export const ipcClient = IPCWCClient.getInstance();
export const ipcInvoke = (method: string, params?: any, options?: IPCRequestOptions): Promise<any> => {
    return ipcClient.invoke(method, params, options);
};

export { tokenStorage };
export type { IPCResponse };