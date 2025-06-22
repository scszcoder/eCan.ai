/**
 * IPC 客户端
 * 负责与 Python 后端进行通信
 */
import {
    IPC,
    IPCRequest,
    IPCResponse,
    IPCRequestHandler,
    IPCErrorHandler,
    createRequest,
    createErrorResponse,
    generateRequestId,
    isIPCResponse
} from './types';
import { getHandlers } from './handlers';
import { logger } from '../../utils/logger';

const DEFAULT_REQUEST_TIMEOUT = 30000; // 默认30秒超时

/**
 * IPC 客户端类
 * 实现了与 Python 后端的通信功能
 */
export class IPCClient {
    private static instance: IPCClient;
    private ipc: IPC | null = null;
    private requestHandlers: Record<string, IPCRequestHandler>;
    private errorHandler: IPCErrorHandler | null = null;
    private initPromise: Promise<void> | null = null;
    
    // 用于存储等待后台响应的请求
    private pendingRequests: Map<string, { resolve: (value: any) => void; reject: (reason?: any) => void; }> = new Map();

    private constructor() {
        this.requestHandlers = getHandlers();
        this.init();
    }

    /**
     * 初始化 IPC 客户端
     */
    private init(): void {
        logger.info('start ipc client init...');
        if (this.ipc) {
            return;
        }

        this.initPromise = new Promise((resolve) => {
            const handleWebChannelReady = () => {
                logger.info('WebChannel ready event triggered');
                if (!this.ipc && window.ipc) {
                    this.setIPC(window.ipc);
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
        if (this.ipc) {
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
    public static getInstance(): IPCClient {
        if (!IPCClient.instance) {
            IPCClient.instance = new IPCClient();
        }
        return IPCClient.instance;
    }

    /**
     * 设置 IPC 对象
     * @param ipc - IPC 接口实例
     */
    public setIPC(ipc: IPC): void {
        if (this.ipc) {
            logger.warn('IPC object already set, ignoring duplicate initialization');
            return;
        }
        this.ipc = ipc;
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
     * 发送请求到 Python 后端
     * @param method - 请求方法名
     * @param params - 请求参数
     * @returns Promise 对象，解析为 IPC 响应结果
     */
    public async sendRequest(method: string, params?: unknown, timeout: number = DEFAULT_REQUEST_TIMEOUT): Promise<any> {
        await this.waitForInit();

        if (!this.ipc) {
            throw createErrorResponse(generateRequestId(), 'INIT_ERROR', 'IPC not initialized');
        }

        const request = createRequest(method, params);
        logger.debug(`Sending request: ${method}`, params ? `with params: ${JSON.stringify(params)}` : '');

        // 1. 设置一个超时Promise
        let timeoutId: number;
        const timeoutPromise = new Promise((_, reject) => {
            timeoutId = window.setTimeout(() => {
                // 如果超时发生，从管理器中主动删除，这是它唯一的清理点
                this.pendingRequests.delete(request.id);
                reject(createErrorResponse(request.id, 'TIMEOUT_ERROR', `Request timed out after ${timeout / 1000} seconds.`));
            }, timeout);
        });

        // 2. 设置主请求的Promise
        const mainRequestPromise = new Promise(async (resolve, reject) => {
            // 将 Promise 的控制器存储起来，供 handleMessage 或超时使用
            this.pendingRequests.set(request.id, { resolve, reject });
            
            try {
                const responseStr = await this.ipc!.web_to_python(JSON.stringify(request));
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
            logger.debug(`python_to_web: Received message: ${message}`);
            const message_obj = JSON.parse(message);

            // 检查这是否是一个对后台任务的最终响应
            if (isIPCResponse(message_obj) && this.pendingRequests.has(message_obj.id)) {
                logger.debug(`Received pushed response for request ${message_obj.id}`);
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
        if (!this.ipc) {
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
            this.ipc.web_to_python(JSON.stringify(response));
            logger.debug('Response sent:' + JSON.stringify(response));
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
        if (!this.ipc) {
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
            this.ipc.web_to_python(JSON.stringify(response));
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
        if (!this.ipc) return;
        
        // 关键: 监听 python_to_web 信号
        if (this.ipc.python_to_web && typeof this.ipc.python_to_web.connect === 'function') {
            this.ipc.python_to_web.connect(this.handleMessage.bind(this));
            logger.info("Connected to python_to_web signal for pushed messages.");
        } else {
            logger.error("Could not connect to python_to_web signal. Pushed messages will not be received.");
        }
    }
} 