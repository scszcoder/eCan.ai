/**
 * IPC API
 * 提供与 Python 后端通信的高级 API
 */
import { IPCClient } from './client';
import { IPCResponse } from './types';

/**
 * API 响应类型
 */
export interface APIResponse<T = unknown> {
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
 * 提供与 Python 后端通信的高级 API 接口
 */
export class IPCAPI {
    private static instance: IPCAPI;
    private client: IPCClient;
    private logger: Console;

    private constructor() {
        this.client = IPCClient.getInstance();
        this.logger = console;
    }

    /**
     * 获取 IPCAPI 单例
     */
    public static getInstance(): IPCAPI {
        if (!IPCAPI.instance) {
            IPCAPI.instance = new IPCAPI();
        }
        return IPCAPI.instance;
    }

    /**
     * 执行 IPC 请求
     * @param method - 请求方法名
     * @param params - 请求参数
     * @returns Promise 对象，解析为 API 响应
     */
    private async executeRequest<T>(method: string, params?: unknown): Promise<APIResponse<T>> {
        try {
            this.logger.debug(`Executing ${method}`, params ? `with params: ${JSON.stringify(params)}` : '');
            const response = await this.client.sendRequest(method, params) as IPCResponse;
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
                        message: response.error?.message || 'Unknown error occurred',
                        details: response.error?.details
                    }
                };
            }
        } catch (error) {
            this.logger.error(`Failed to execute ${method}:`, error);
            return {
                success: false,
                error: {
                    code: 'REQUEST_ERROR',
                    message: error instanceof Error ? error.message : 'Request failed',
                    details: error
                }
            };
        }
    }

    /**
     * 用户登录
     * @param username - 用户名
     * @param password - 密码
     * @returns Promise 对象，解析为登录响应
     */
    public async login<T>(username: string, password: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('login', { username, password });
    }

    /**
     * 获取配置
     * @param key - 配置键名
     * @returns Promise 对象，解析为配置值
     */
    public async getConfig<T>(key: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_config', { key });
    }

    /**
     * 设置配置
     * @param key - 配置键名
     * @param value - 配置值
     * @returns Promise 对象，解析为操作结果
     */
    public async setConfig<T>(key: string, value: T): Promise<APIResponse<void>> {
        return this.executeRequest<void>('set_config', { key, value });
    }

    /**
     * 获取所有配置
     * @returns Promise 对象，解析为所有配置
     */
    public async getAllConfig(): Promise<APIResponse<Record<string, unknown>>> {
        return this.executeRequest<Record<string, unknown>>('get_all_config', {});
    }

    /**
     * 重置配置
     * @returns Promise 对象，解析为操作结果
     */
    public async resetConfig(): Promise<APIResponse<void>> {
        return this.executeRequest<void>('reset_config', {});
    }

    /**
     * 执行命令
     * @param command - 命令名
     * @param params - 命令参数
     * @returns Promise 对象，解析为命令执行结果
     */
    public async executeCommand<T>(command: string, params?: unknown): Promise<APIResponse<T>> {
        return this.executeRequest<T>('execute_command', { command, params });
    }

    /**
     * 通知事件
     * @param event - 事件名
     * @param data - 事件数据
     * @returns Promise 对象，解析为操作结果
     */
    public async notifyEvent(event: string, data?: unknown): Promise<APIResponse<void>> {
        return this.executeRequest<void>('notify_event', { event, data });
    }
}

/**
 * 创建 IPC API 实例
 * @returns IPC API 实例
 */
export function createIPCAPI(): IPCAPI {
    return IPCAPI.getInstance();
} 