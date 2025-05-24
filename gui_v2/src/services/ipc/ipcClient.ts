import { logger } from '@/utils/logger';
import { IPCRequest, IPCResponse, QtWebChannel } from './types';

/**
 * IPC 客户端类
 * 处理与 Python 后端的通信
 */
export class IPCClient {
    private static instance: IPCClient;
    private ipc: QtWebChannel | null = null;
    private requestHandlers: Map<string, (params: unknown) => Promise<unknown>> = new Map();
    private pendingRequests: Map<string, {
        resolve: (value: unknown) => void;
        reject: (reason: Error) => void;
    }> = new Map();

    private constructor() {
        // 初始化时不需要做任何事情，等待 setIPC 被调用
    }

    public static getInstance(): IPCClient {
        if (!IPCClient.instance) {
            IPCClient.instance = new IPCClient();
        }
        return IPCClient.instance;
    }

    /**
     * 设置 IPC 对象
     * 这个方法应该在使用前被调用
     */
    public setIPC(ipc: QtWebChannel): void {
        this.ipc = ipc;
        this.setupMessageHandler();
    }

    /**
     * 设置消息处理器
     */
    private setupMessageHandler(): void {
        if (!this.ipc) {
            logger.error('IPC object not set');
            return;
        }

        this.ipc.python_to_web.connect((message: string) => {
            try {
                const data = JSON.parse(message);
                this.handleMessage(data);
            } catch (error) {
                logger.error('Error parsing message:', error);
            }
        });
    }

    /**
     * 处理接收到的消息
     */
    private handleMessage(data: IPCRequest | IPCResponse): void {
        if ('type' in data && data.type === 'request') {
            this.handleRequest(data as IPCRequest);
        }
    }

    /**
     * 处理请求消息
     */
    private async handleRequest(request: IPCRequest): Promise<void> {
        const handler = this.requestHandlers.get(request.method);
        if (!handler) {
            logger.warn(`No handler registered for method: ${request.method}`);
            return;
        }

        try {
            const result = await handler(request.params);
            this.sendResponse(request.id, result);
        } catch (error) {
            logger.error(`Error handling request ${request.method}:`, error);
            this.sendError(request.id, error instanceof Error ? error.message : String(error));
        }
    }

    /**
     * 处理响应消息
     */
    private handleResponse(response: IPCResponse): void {
        const pendingRequest = this.pendingRequests.get(response.id);
        if (pendingRequest) {
            if (response.status === 'error' && response.error) {
                // 处理错误响应
                pendingRequest.reject(new Error(response.error.message));
            } else if (response.status === 'ok' && 'result' in response) {
                // 处理成功响应
                pendingRequest.resolve(response.result);
            } else {
                // 处理无效响应
                pendingRequest.reject(new Error('Invalid response: missing result or error'));
            }
            this.pendingRequests.delete(response.id);
        } else {
            logger.warn(`No pending request found for response id: ${response.id}`);
        }
    }

    /**
     * 发送响应
     */
    private sendResponse(id: string, result: unknown): void {
        const response: IPCResponse = {
            id,
            type: 'response',
            status: 'ok',
            result,
            timestamp: Date.now()
        };
        this.sendToPython(response);
    }

    /**
     * 发送错误响应
     */
    private sendError(id: string, error: string): void {
        const response: IPCResponse = {
            id,
            type: 'response',
            status: 'error',
            error: {
                code: 'HANDLER_ERROR',
                message: error
            },
            timestamp: Date.now()
        };
        this.sendToPython(response);
    }

    /**
     * 发送消息到 Python
     */
    private sendToPython(message: IPCRequest | IPCResponse): void {
        if (!this.ipc) {
            logger.error('IPC object not set');
            return;
        }

        try {
            this.ipc.web_to_python(JSON.stringify(message));
        } catch (error) {
            logger.error('Error sending message to Python:', error);
        }
    }

    /**
     * 注册请求处理器
     */
    public registerRequestHandler(
        method: string,
        handler: (params: unknown) => Promise<unknown>
    ): void {
        this.requestHandlers.set(method, handler);
    }

    /**
     * 发送请求到 Python
     */
    public async sendRequest<T = unknown>(
        method: string,
        params?: unknown,
        meta?: Record<string, unknown>
    ): Promise<T> {
        return new Promise<T>((resolve, reject) => {
            const id = crypto.randomUUID();
            
            // 保存请求的 Promise 解析函数
            this.pendingRequests.set(id, {
                resolve: (value: unknown) => resolve(value as T),
                reject
            });

            // 发送请求
            const request: IPCRequest = {
                id,
                type: 'request',
                method,
                params,
                meta,
                timestamp: Date.now()
            };

            try {
                if (!this.ipc) {
                    throw new Error('IPC object not set');
                }

                const response = this.ipc.web_to_python(JSON.stringify(request));
                if (response.status === 'error' && response.error) {
                    reject(new Error(response.error.message));
                } else if (response.status === 'ok' && 'result' in response) {
                    resolve(response.result as T);
                } else {
                    reject(new Error('Invalid response: missing result or error'));
                }
            } catch (error) {
                reject(error instanceof Error ? error : new Error(String(error)));
            } finally {
                this.pendingRequests.delete(id);
            }
        });
    }
}

// 导出单例实例
export const ipcClient = IPCClient.getInstance(); 