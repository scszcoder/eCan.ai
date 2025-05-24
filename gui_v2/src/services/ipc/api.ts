/**
 * IPC API
 * 提供与 Python 后端通信的高级 API
 */
import { IPCClient } from './client';
import { IPCResponse } from './types';

/**
 * API 响应格式
 */
interface APIResponse<T = unknown> {
    /** 响应状态 */
    success: boolean;
    /** 响应数据 */
    data?: T;
    /** 错误信息 */
    error?: {
        /** 错误码 */
        code: string;
        /** 错误描述 */
        message: string;
        /** 额外错误信息 */
        details?: unknown;
    };
}

/**
 * IPC API 类
 * 封装了与 Python 后端通信的常用方法
 */
export class IPCAPI {
    private client: IPCClient;
    private logger: Console;

    /**
     * 创建 IPC API 实例
     * @param client - IPC 客户端实例
     */
    constructor(client: IPCClient) {
        this.client = client;
        this.logger = console;
    }

    /**
     * 转换 IPC 响应为 API 响应
     * @param response - IPC 响应
     * @returns API 响应
     */
    private transformResponse<T>(response: IPCResponse): APIResponse<T> {
        if (response.status === 'ok') {
            return {
                success: true,
                data: response.result as T
            };
        } else {
            return {
                success: false,
                error: {
                    code: String(response.error?.code || 'UNKNOWN_ERROR'),
                    message: response.error?.message || 'An unknown error occurred',
                    details: response.error?.details
                }
            };
        }
    }

    /**
     * 执行 IPC 请求并处理响应
     * @param method - 请求方法名
     * @param params - 请求参数
     * @returns Promise 对象，解析为 API 响应
     */
    private async executeRequest<T>(
        method: string,
        params: unknown
    ): Promise<APIResponse<T>> {
        try {
            this.logger.debug(`Executing ${method}`, params ? `with params: ${JSON.stringify(params)}` : '');
            const response = await this.client.sendRequest(method, params);
            return this.transformResponse<T>(response);
        } catch (error) {
            this.logger.error(`Failed to execute ${method}:`, error);
            if (error instanceof Error) {
                const errorResponse: APIResponse<T> = {
                    success: false,
                    error: {
                        code: 'EXECUTION_ERROR',
                        message: error.message,
                        details: error
                    }
                };
                return errorResponse;
            }
            if (error && typeof error === 'object' && 'error' in error) {
                const ipcError = error as { error: { code: string | number; message: string; details?: unknown } };
                const errorResponse: APIResponse<T> = {
                    success: false,
                    error: {
                        code: String(ipcError.error.code),
                        message: ipcError.error.message,
                        details: ipcError.error.details
                    }
                };
                return errorResponse;
            }
            const unknownErrorResponse: APIResponse<T> = {
                success: false,
                error: {
                    code: 'UNKNOWN_ERROR',
                    message: 'An unknown error occurred',
                    details: error
                }
            };
            return unknownErrorResponse;
        }
    }

    /**
     * 获取配置
     * @param key - 配置键名
     * @returns Promise 对象，解析为配置值
     */
    public async getConfig(key: string): Promise<APIResponse> {
        return this.executeRequest('get_config', { key });
    }

    /**
     * 设置配置
     * @param key - 配置键名
     * @param value - 配置值
     * @returns Promise 对象，解析为操作结果
     */
    public async setConfig(key: string, value: unknown): Promise<APIResponse> {
        return this.executeRequest('set_config', { key, value });
    }

    /**
     * 获取所有配置
     * @returns Promise 对象，解析为所有配置
     */
    public async getAllConfig(): Promise<APIResponse<Record<string, unknown>>> {
        return this.executeRequest<Record<string, unknown>>('get_all_config', undefined);
    }

    /**
     * 重置配置
     * @returns Promise 对象，解析为操作结果
     */
    public async resetConfig(): Promise<APIResponse> {
        return this.executeRequest('reset_config', undefined);
    }

    /**
     * 执行命令
     * @param command - 命令名称
     * @param args - 命令参数
     * @returns Promise 对象，解析为命令执行结果
     */
    public async executeCommand(command: string, args?: unknown[]): Promise<APIResponse> {
        return this.executeRequest('execute_command', { command, args });
    }

    /**
     * 发送事件通知
     * @param event - 事件名称
     * @param data - 事件数据
     * @returns Promise 对象，解析为事件处理结果
     */
    public async notifyEvent(event: string, data?: unknown): Promise<APIResponse> {
        return this.executeRequest('notify_event', { event, data });
    }
}

/**
 * 创建 IPC API 实例
 * @returns IPC API 实例
 */
export function createIPCAPI(): IPCAPI {
    return new IPCAPI(IPCClient.getInstance());
} 