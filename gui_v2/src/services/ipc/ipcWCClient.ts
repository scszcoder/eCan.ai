/**
 * 增强的 IPC 客户端
 * 集成请求队列、重试逻辑、token管理等高级功能
 * 负责与 Python 后端进行通信
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

// 请求优先级枚举
export enum RequestPriority {
  LOW = 0,
  NORMAL = 1,
  HIGH = 2,
  URGENT = 3
}

// 请求状态枚举
export enum RequestStatus {
  PENDING = 'pending',
  EXECUTING = 'executing',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled',
  RETRYING = 'retrying'
}

// 队列中的请求接口
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

// 请求选项接口
export interface IPCRequestOptions {
  priority?: RequestPriority;
  timeout?: number;
  maxRetries?: number;
  retryDelay?: number;
  backoffMultiplier?: number;
  onProgress?: (progress: any) => void;
}

const DEFAULT_REQUEST_TIMEOUT = 60000; // 默认60秒超时（1分钟）

/**
 * IPC 客户端类
 * 实现了与 Python 后端的通信功能
 */
export class IPCWCClient {
    private static instance: IPCWCClient;
    private ipcWebChannel: IPCWebChannel | null = null;
    private requestHandlers: Record<string, IPCRequestHandler>;
    private errorHandler: IPCErrorHandler | null = null;
    private initPromise: Promise<void> | null = null;
    
    // 用于存储等待后台响应的请求
    private pendingRequests: Map<string, { resolve: (value: any) => void; reject: (reason?: any) => void; }> = new Map();
    
    // 请求队列管理
    private requestQueue: QueuedRequest[] = [];
    private requestMap = new Map<string, QueuedRequest>();
    private processingQueue = false;
    private maxConcurrentRequests = 5;
    private activeRequests = new Set<string>();

    private constructor() {
        this.requestHandlers = getHandlers();
        this.init();
    }

    /**
     * 初始化 IPC 客户端
     */
    private init(): void {
        logger.info('start ipc wc client init...');
        if (this.ipcWebChannel) {
            return;
        }

        this.initPromise = new Promise((resolve) => {
            const handleWebChannelReady = () => {
                logger.info('WebChannel ready event triggered');
                if (!this.ipcWebChannel && window.ipc) {
                    this.setIPCWebChannel(window.ipc);
                    logger.info('IPC initialized successfully');
                    window.removeEventListener('webchannel-ready', handleWebChannelReady);
                    resolve();
                }
            };

            window.addEventListener('webchannel-ready', handleWebChannelReady);
            logger.info('WebChannel ready event listener set up');

            if (document.readyState === 'complete' && window.ipc) {
                handleWebChannelReady();
            }
        });
    }

    /**
     * 等待 IPC 初始化完成
     */
    private async waitForInit(): Promise<void> {
        if (this.ipcWebChannel) {
            return;
        }
        if (this.initPromise) {
            await this.initPromise;
        }
    }

    /**
     * 获取 IPC 客户端单例
     * @returns IPC 客户端实例
     */
    public static getInstance(): IPCWCClient {
        if (!IPCWCClient.instance) {
            IPCWCClient.instance = new IPCWCClient();
        }
        return IPCWCClient.instance;
    }

    /**
     * 设置 IPC 对象
     * @param ipcWebChannel - IPC 接口实例
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
     * 设置错误处理器
     * @param handler - 错误处理器函数
     */
    public setErrorHandler(handler: IPCErrorHandler): void {
        this.errorHandler = handler;
        logger.info('Error handler set');
    }

    /**
     * 增强的发送请求方法，支持队列和重试
     * @param method - 请求方法名
     * @param params - 请求参数
     * @param options - 请求选项
     * @returns Promise 对象，解析为 IPC 响应结果
     */
    public async invoke(method: string, params?: unknown, options: IPCRequestOptions = {}): Promise<any> {
        return new Promise<any>((resolve, reject) => {
            const queuedRequest: QueuedRequest = {
                id: generateRequestId(),
                method,
                params: this.addAuthToken(method, params),
                priority: options.priority || RequestPriority.NORMAL,
                status: RequestStatus.PENDING,
                createdAt: Date.now(),
                updatedAt: Date.now(),
                retryCount: 0,
                maxRetries: options.maxRetries || 10,
                retryDelay: options.retryDelay || 2000,
                backoffMultiplier: options.backoffMultiplier || 1.5,
                timeout: options.timeout,
                onSuccess: resolve,
                onError: reject,
                onProgress: options.onProgress
            };
            
            this.enqueueRequest(queuedRequest);
            this.processQueue();
        });
    }

    /**
     * 原有的发送请求方法，保持向后兼容
     * @param method - 请求方法名
     * @param params - 请求参数
     * @returns Promise 对象，解析为 IPC 响应结果
     */
    public async sendRequest(method: string, params?: unknown, timeout: number = DEFAULT_REQUEST_TIMEOUT): Promise<any> {
        await this.waitForInit();

        if (!this.ipcWebChannel) {
            throw createErrorResponse(generateRequestId(), 'INIT_ERROR', 'IPC not initialized');
        }

        const request = createRequest(method, this.addAuthToken(method, params));
        const paramsStr = params ? JSON.stringify(params) : '';
        const truncatedParams = paramsStr.length > 500 ? paramsStr.substring(0, 500) + '...' : paramsStr;
        logger.debug(`[IPCWCClient] Sending request: ${method}`, params ? `with params: ${truncatedParams}` : '');

        // 对于登录请求，使用更长的超时时间
        if (method === 'login') {
            timeout = Math.max(timeout, 180000); // 登录至少3分钟超时
            logger.info(`[IPCWCClient] Login request detected, using extended timeout: ${timeout/1000}s`);
        }

        // 1. 设置一个超时Promise
        let timeoutId: number;
        const timeoutPromise = new Promise((_, reject) => {
            timeoutId = window.setTimeout(() => {
                // 如果超时发生，从管理器中主动删除，这是它唯一的清理点
                this.pendingRequests.delete(request.id);
                const errorMessage = method === 'login' 
                    ? `Login request timed out after ${timeout / 1000} seconds. This may be due to slow network or AWS service response.`
                    : `Request timed out after ${timeout / 1000} seconds.`;
                reject(createErrorResponse(request.id, 'TIMEOUT_ERROR', errorMessage));
            }, timeout);
        });

        // 2. 设置主请求的Promise
        const mainRequestPromise = new Promise(async (resolve, reject) => {
            // 将 Promise 的控制器存储起来，供 handleMessage 或超时使用
            this.pendingRequests.set(request.id, { resolve, reject });
            
            try {
                const responseStr = await this.ipcWebChannel!.web_to_python(JSON.stringify(request));
                // logger.debug(`Received response: ${responseStr}`);
                const immediateResponse = JSON.parse(responseStr) as IPCResponse;
                
                // 如果是同步任务，它会立即完成，我们不需要等待推送
                if (immediateResponse.status !== 'pending') {
                    // 从管理器中移除，因为它已经完成了
                    this.pendingRequests.delete(request.id);
                    resolve(immediateResponse);
                } else {
                    logger.debug(`Received pending response for request ${request.id}`);
                }
                // 如果是 'pending'，则我们什么都不做，把清理工作留给 handleMessage 或超时
            } catch (error) {
                this.pendingRequests.delete(request.id); // 发送失败，也要清理
                logger.error(`Failed to send or process immediate response for ${method}:`, error);
                reject(error instanceof Error ? createErrorResponse(request.id, 'SEND_ERROR', error.message) : error);
            }
        });

        try {
             // 3. 让主请求和超时"竞赛"
            return await Promise.race([mainRequestPromise, timeoutPromise]);
        } finally {
            // 4. 无论结果如何，清除定时器，防止它在请求成功后依然触发
            clearTimeout(timeoutId!);
        }
    }

    /**
     * 处理来自 Python 后端的消息 (包括请求和推送的响应)
     * @param message - 消息字符串
     */
    private handleMessage(message: string): void {
        try {
            logger.debug(`[IPCWCClient] python_to_web: Received message: ${message}`);
            const message_obj = JSON.parse(message);

            // 检查这是否是一个对后台任务的最终响应
            if (isIPCResponse(message_obj) && this.pendingRequests.has(message_obj.id)) {
                logger.debug(`[IPCWCClient] Received pushed response for request ${message_obj.id}`);
                const response = message_obj as IPCResponse;

                const promiseCallbacks = this.pendingRequests.get(message_obj.id)!;
                this.pendingRequests.delete(message_obj.id);
                promiseCallbacks.resolve(response);
                return; // 消息已处理，直接返回
            }
            
            // 检查这是否是 Python 主动发起的请求
            if (message_obj.type === 'request') {
                this.handleRequest(message_obj);
            } else {
                logger.warn('Received unhandled message:', message_obj);
            }
        } catch (error) {
            logger.error('Failed to parse or handle message:', error);
        }
    }

    /**
     * 处理请求消息
     * @param request - 请求对象
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
            this.sendResponse(request.id, result);
        } catch (error) {
            logger.error(`Error handling request '${request.method}':`, error);
            this.sendErrorResponse(request.id, {
                code: 'HANDLER_ERROR',
                message: error instanceof Error ? error.message : 'Handler error occurred',
                details: error
            });
        }
    }

    /**
     * 发送响应到 Python 后端
     * @param requestId - 请求 ID
     * @param result - 响应结果
     */
    private sendResponse(requestId: string, result: unknown): void {
        if (!this.ipcWebChannel) {
            logger.error('IPC object not set');
            return;
        }

        const response: IPCResponse = {
            id: requestId,
            type: 'response' as const,
            status: 'success' as const, // 明确 status
            result,
            timestamp: Date.now()
        };

        try {
            // 注意：这里我们假设 python 端不需要这个调用的返回值
            this.ipcWebChannel.web_to_python(JSON.stringify(response));
            logger.debug('[IPCWCClient] Response sent:' + JSON.stringify(response));
        } catch (error) {
            logger.error('Failed to send response:', error);
            this.handleError({
                code: 'SEND_ERROR',
                message: 'Failed to send response',
                details: error
            });
        }
    }

    /**
     * 发送错误响应到 Python 后端
     * @param requestId - 请求 ID
     * @param error - 错误对象
     */
    private sendErrorResponse(requestId: string, error: { code: string; message: string; details?: unknown }): void {
        if (!this.ipcWebChannel) {
            logger.error('IPC object not set');
            return;
        }

        const response: IPCResponse = {
            id: requestId,
            type: 'response',
            status: 'error',
            error: {
                code: error.code,
                message: error.message,
                details: error.details
            },
            timestamp: Date.now()
        };

        try {
            this.ipcWebChannel.web_to_python(JSON.stringify(response));
            logger.debug('Error response sent:' + JSON.stringify(response));
        } catch (e) {
            logger.error('Failed to send error response:', e);
        }
    }

    /**
     * 处理内部错误
     * @param error - 错误对象
     */
    private handleError(error: { code: string | number; message: string; details?: unknown }): void {
        if (this.errorHandler) {
            this.errorHandler(error);
        } else {
            logger.error('Unhandled IPC Client error:', error);
        }
    }


    /**
     * 设置消息处理器，监听来自 Python 的消息
     */
    private setupMessageHandler(): void {
        if (!this.ipcWebChannel) return;
        
        // 关键: 监听 python_to_web 信号
        if (this.ipcWebChannel.python_to_web && typeof this.ipcWebChannel.python_to_web.connect === 'function') {
            this.ipcWebChannel.python_to_web.connect(this.handleMessage.bind(this));
            logger.info("[IPCWCClient] Connected to python_to_web signal for pushed messages.");
        } else {
            logger.error("[IPCWCClient] Could not connect to python_to_web signal. Pushed messages will not be received.");
        }
    }

    // ===== 队列管理方法 =====

    /**
     * 清理内存队列
     */
    public clearQueue(): void {
        logger.info('Clearing IPC request queue');
        this.requestQueue = [];
        this.requestMap.clear();
        this.activeRequests.clear();
        this.processingQueue = false;
    }


    /**
     * 将请求加入队列
     */
    private enqueueRequest(request: QueuedRequest): void {
        // 检查是否已存在相同请求（去重）
        const existingIndex = this.requestQueue.findIndex(req => 
            req.method === request.method && 
            JSON.stringify(req.params) === JSON.stringify(request.params) &&
            req.status === RequestStatus.PENDING
        );

        if (existingIndex !== -1) {
            logger.debug(`Duplicate request found, updating: ${request.method}`);
            this.requestQueue[existingIndex] = request;
        } else {
            this.requestQueue.push(request);
        }

        this.requestMap.set(request.id, request);
        
        // 按优先级排序
        this.requestQueue.sort((a, b) => b.priority - a.priority);
    }

    /**
     * 处理请求队列
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
     * 从队列中取出请求
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
     * 执行队列中的请求
     */
    private async executeQueuedRequest(request: QueuedRequest): Promise<void> {
        this.activeRequests.add(request.id);
        
        try {
            const response = await this.sendRequest(request.method, request.params, request.timeout);
            
            request.status = RequestStatus.COMPLETED;
            request.updatedAt = Date.now();
            request.onSuccess?.(response);
            
            // 从队列中移除已完成的请求
            this.removeFromQueue(request.id);
        } catch (error) {
            await this.handleQueuedRequestError(request, error);
        } finally {
            this.activeRequests.delete(request.id);
            // 继续处理队列
            setTimeout(() => this.processQueue(), 0);
        }
    }

    /**
     * 处理队列请求错误和重试逻辑
     */
    private async handleQueuedRequestError(request: QueuedRequest, error: any): Promise<void> {
        const shouldRetry = this.isRetryableError(error) && request.retryCount < request.maxRetries;
        
        if (shouldRetry) {
            request.retryCount++;
            request.status = RequestStatus.RETRYING;
            request.updatedAt = Date.now();
            
            const delay = request.retryDelay * Math.pow(request.backoffMultiplier, request.retryCount - 1);
            
            logger.info(`[IPC] Retrying ${request.id} in ${delay}ms (attempt ${request.retryCount}/${request.maxRetries})`);
            
            setTimeout(() => {
                request.status = RequestStatus.PENDING;
                this.processQueue();
            }, delay);
        } else {
            request.status = RequestStatus.FAILED;
            request.updatedAt = Date.now();
            request.onError?.(error);
            
            // 从队列中移除失败的请求
            this.removeFromQueue(request.id);
        }
    }

    /**
     * 判断错误是否可重试
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
     * 从队列中移除请求
     */
    private removeFromQueue(requestId: string): void {
        const index = this.requestQueue.findIndex(req => req.id === requestId);
        if (index !== -1) {
            this.requestQueue.splice(index, 1);
        }
        this.requestMap.delete(requestId);
    }

    /**
     * 为请求添加认证 token
     * 后端会根据白名单自动处理token验证，前端统一发送token
     */
    private addAuthToken(method: string, params: any): any {
        const token = tokenStorage.getToken();
        if (!token) {
            logger.debug(`No auth token available for method: ${method} (backend will handle whitelist)`);
            return params;
        }
        
        // 如果参数是对象，添加 token 字段
        if (params && typeof params === 'object' && params !== null) {
            return { ...params, token };
        }
        
        // 否则创建包含 token 的对象
        return { token, params };
    }

    // ===== 公共队列管理接口 =====

    /**
     * 获取队列统计信息
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
     * 根据状态获取请求列表
     */
    public getRequestsByStatus(status: RequestStatus): QueuedRequest[] {
        return this.requestQueue.filter(req => req.status === status);
    }

    /**
     * 获取所有请求列表
     */
    public getAllRequests(): QueuedRequest[] {
        return [...this.requestQueue];
    }

    /**
     * 取消请求
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

// 导出单例和便捷方法
export const ipcClient = IPCWCClient.getInstance();
export const ipcInvoke = (method: string, params?: any, options?: IPCRequestOptions): Promise<any> => {
    return ipcClient.invoke(method, params, options);
};

export { tokenStorage };
export type { IPCResponse };