/**
 * IPC 客户端
 * 负责与 Python 后端进行通信
 */
import {
    IPC,
    IPCRequest,
    IPCResponse,
    IPCRequestHandler,
    IPCResponseHandler,
    IPCErrorHandler,
    createRequest,
    createErrorResponse,
    generateRequestId
} from './types';

/**
 * IPC 客户端类
 * 实现了与 Python 后端的通信功能
 */
export class IPCClient {
    private static instance: IPCClient;
    private ipc: IPC | null = null;
    private requestHandlers: Map<string, IPCRequestHandler> = new Map();
    private responseHandlers: Map<string, IPCResponseHandler> = new Map();
    private errorHandler: IPCErrorHandler | null = null;
    private logger: Console;

    private constructor() {
        this.logger = console;
        this.init();
    }

    /**
     * 初始化 IPC 客户端
     */
    private init(): void {
        this.logger.info('start ipc client init...');
        // 如果已经初始化过，直接返回
        if (this.ipc) {
            return;
        }

        // 监听 webchannel-ready 事件
        const handleWebChannelReady = (event: Event) => {
            this.logger.info('WebChannel ready event triggered');
            // 再次检查是否已初始化，避免重复设置
            if (!this.ipc && window.ipc) {
                this.setIPC(window.ipc);
                this.logger.info('IPC initialized successfully');
                // 移除事件监听器
                window.removeEventListener('webchannel-ready', handleWebChannelReady);
            }
        };

        // 添加事件监听器
        window.addEventListener('webchannel-ready', handleWebChannelReady);
        this.logger.info('WebChannel ready event listener set up');

        // 如果 webchannel 已经就绪，立即初始化
        if (document.readyState === 'complete' && window.ipc) {
            handleWebChannelReady(new Event('webchannel-ready'));
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
            this.logger.warn('IPC object already set, ignoring duplicate initialization');
            return;
        }
        this.ipc = ipc;
        this.setupMessageHandler();
        this.logger.info('IPC object set and message handler initialized');
    }

    /**
     * 设置错误处理器
     * @param handler - 错误处理器函数
     */
    public setErrorHandler(handler: IPCErrorHandler): void {
        this.errorHandler = handler;
        this.logger.info('Error handler set');
    }

    /**
     * 注册请求处理器
     * @param method - 请求方法名
     * @param handler - 请求处理器函数
     */
    public registerRequestHandler(method: string, handler: IPCRequestHandler): void {
        if (this.requestHandlers.has(method)) {
            this.logger.warn(`Request handler for method '${method}' already exists, overwriting`);
        }
        this.requestHandlers.set(method, handler);
        this.logger.info(`Request handler registered for method '${method}'`);
    }

    /**
     * 发送请求到 Python 后端
     * @param method - 请求方法名
     * @param params - 请求参数
     * @returns Promise 对象，解析为 IPC 响应
     */
    public async sendRequest(method: string, params?: unknown): Promise<IPCResponse> {
        if (!this.ipc) {
            throw createErrorResponse(
                generateRequestId(),
                'INIT_ERROR',
                'IPC not initialized'
            );
        }

        const request = createRequest(method, params);
        this.logger.debug(`Sending request: ${method}`, params ? `with params: ${JSON.stringify(params)}` : '');

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

            if (response.status === 'ok') {
                return response;
            } else {
                throw response;
            }
        } catch (error) {
            this.logger.error(`Failed to send request ${method}:`, error);
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
            const data = JSON.parse(message) as IPCRequest;
            this.logger.debug('Received message:', data);

            if (data.type === 'request') {
                this.handleRequest(data);
            } else {
                this.logger.warn('Received non-request message:', data);
            }
        } catch (error) {
            this.logger.error('Failed to parse message:', error);
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
        const handler = this.requestHandlers.get(request.method);
        if (!handler) {
            this.logger.warn(`No handler registered for method '${request.method}'`);
            return;
        }

        try {
            const result = await handler(request);
            this.sendResponse(request.id, result);
        } catch (error) {
            this.logger.error(`Error handling request '${request.method}':`, error);
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
            this.logger.error('IPC object not set');
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
            this.logger.debug('Response sent:', response);
        } catch (error) {
            this.logger.error('Failed to send response:', error);
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
            this.logger.error('IPC object not set');
            return;
        }

        const response = createErrorResponse(requestId, error.code, error.message, error.details);

        try {
            this.ipc.web_to_python(JSON.stringify(response));
            this.logger.debug('Error response sent:', response);
        } catch (sendError) {
            this.logger.error('Failed to send error response:', sendError);
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
        this.logger.error('IPC error:', error);
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
            this.logger.info('IPC message handler set up');
        } else {
            this.logger.warn('IPC python_to_web not available');
        }
    }
} 