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
    generateRequestId
} from './types';
import { getHandlers } from './handlers';
import { logger } from '../../utils/logger';

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

    private constructor() {
        this.requestHandlers = getHandlers();
        this.init();
    }

    /**
     * 初始化 IPC 客户端
     */
    private init(): void {
        logger.info('start ipc client init...');
        // 如果已经初始化过，直接返回
        if (this.ipc) {
            return;
        }

        this.initPromise = new Promise((resolve) => {
            // 监听 webchannel-ready 事件
            const handleWebChannelReady = () => {
                logger.info('WebChannel ready event triggered');
                // 再次检查是否已初始化，避免重复设置
                if (!this.ipc && window.ipc) {
                    this.setIPC(window.ipc);
                    logger.info('IPC initialized successfully');
                    // 移除事件监听器
                    window.removeEventListener('webchannel-ready', handleWebChannelReady);
                    resolve();
                }
            };

            // 添加事件监听器
            window.addEventListener('webchannel-ready', handleWebChannelReady);
            logger.info('WebChannel ready event listener set up');

            // 如果 webchannel 已经就绪，立即初始化
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
        // 如果已经设置了 IPC 对象，直接返回
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
     * @returns Promise 对象，解析为 IPC 响应
     */
    public async sendRequest(method: string, params?: unknown): Promise<IPCResponse> {
        // 等待 IPC 初始化完成
        await this.waitForInit();

        if (!this.ipc) {
            throw createErrorResponse(
                generateRequestId(),
                'INIT_ERROR',
                'IPC not initialized'
            );
        }

        const request = createRequest(method, params);
        logger.debug(`Sending request: ${method}`, params ? `with params: ${JSON.stringify(params)}` : '');

        try {
            const responseStr = await this.ipc.web_to_python(JSON.stringify(request));
            const response = JSON.parse(responseStr) as IPCResponse;

            if (response.id !== request.id) {
                throw createErrorResponse(
                    request.id,
                    'ID_MISMATCH',
                    `Response ID mismatch: expected ${request.id}, got ${response.id}`
                );
            }

            // 直接返回响应，无论状态如何
            return response;
        } catch (error) {
            logger.error(`Failed to send request ${method}:`, error);
            if (error instanceof Error) {
                throw createErrorResponse(
                    request.id,
                    'SEND_ERROR',
                    error.message
                );
            }
            throw error;
        }
    }

    /**
     * 处理来自 Python 后端的消息
     * @param message - 消息字符串
     */
    private handleMessage(message: string): void {
        try {
            logger.info('Received message:', message);
            const request = JSON.parse(message) as IPCRequest;

            if (request.type === 'request') {
                this.handleRequest(request);
            } else {
                logger.warn('Received non-request type message:', request);
                this.sendErrorResponse(request.id, {
                    code: 'HANDLER_ERROR',
                    message: `Received non-request type message: ${request.type}`,
                    details: ""
                });
            }
        } catch (error) {
            logger.error('Failed to parse message:', error);
            this.handleError({
                code: 'PARSE_ERROR',
                message: 'Failed to parse message',
                details: error
            });
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

        const response = {
            id: requestId,
            type: 'response' as const,
            status: 'ok' as const,
            result,
            timestamp: Date.now()
        };

        try {
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
     * @param error - 错误信息
     */
    private sendErrorResponse(requestId: string, error: { code: string; message: string; details?: unknown }): void {
        if (!this.ipc) {
            logger.error('IPC object not set');
            return;
        }

        const response = createErrorResponse(requestId, error.code, error.message, error.details);

        try {
            this.ipc.web_to_python(JSON.stringify(response));
            logger.debug('Error response sent:', response);
        } catch (sendError) {
            logger.error('Failed to send error response:', sendError);
            this.handleError({
                code: 'SEND_ERROR',
                message: 'Failed to send error response',
                details: sendError
            });
        }
    }

    /**
     * 处理错误
     * @param error - 错误信息
     */
    private handleError(error: { code: string | number; message: string; details?: unknown }): void {
        logger.error('IPC error:', error);
        if (this.errorHandler) {
            this.errorHandler(error);
        }
    }

    /**
     * 设置消息处理器
     */
    private setupMessageHandler(): void {
        if (window.ipc?.python_to_web) {
            window.ipc.python_to_web.connect((message) => {
                this.handleMessage(message);
            });
            logger.info('IPC message handler set up');
        } else {
            logger.warn('IPC python_to_web not available');
        }
    }
} 