import { ipcClient } from './ipcClient';
import { logger } from '@/utils/logger';

/**
 * IPC API 响应包装类
 */
export class APIResponse<T = unknown> {
    constructor(
        public success: boolean,
        public data?: T,
        public error?: {
            code: string;
            message: string;
        }
    ) {}

    static success<T>(data: T): APIResponse<T> {
        return new APIResponse<T>(true, data);
    }

    static error<T>(code: string, message: string): APIResponse<T> {
        return new APIResponse<T>(false, undefined, { code, message });
    }
}

/**
 * IPC API 类
 * 提供统一的接口来调用 Python 后端服务
 */
export class IPCAPI {
    private static instance: IPCAPI;

    private constructor() {}

    public static getInstance(): IPCAPI {
        if (!IPCAPI.instance) {
            IPCAPI.instance = new IPCAPI();
        }
        return IPCAPI.instance;
    }

    /**
     * 发送请求到 Python
     */
    private async sendRequest<T = unknown>(
        method: string,
        params?: unknown,
        meta?: Record<string, unknown>,
        callback?: (response: APIResponse<T>) => void
    ): Promise<APIResponse<T>> {
        try {
            const result = await ipcClient.sendRequest<T>(method, params, meta);
            const response = APIResponse.success<T>(result);
            if (callback) {
                callback(response);
            }
            return response;
        } catch (error) {
            logger.error(`Error in ${method}:`, error);
            const response = APIResponse.error<T>(
                'REQUEST_ERROR',
                error instanceof Error ? error.message : String(error)
            );
            if (callback) {
                callback(response);
            }
            return response;
        }
    }

    /**
     * 配置相关接口
     */
    public async getConfig<T = unknown>(
        key: string,
        callback?: (response: APIResponse<T>) => void
    ): Promise<APIResponse<T>> {
        return this.sendRequest<T>('get_config', { key }, undefined, callback);
    }

    public async setConfig<T = unknown>(
        key: string,
        value: T,
        callback?: (response: APIResponse<void>) => void
    ): Promise<APIResponse<void>> {
        return this.sendRequest<void>('set_config', { key, value }, undefined, callback);
    }
    
    /**
     * 系统相关接口
     */
    public async getSystemInfo(
        callback?: (response: APIResponse<{
            version: string;
            platform: string;
            arch: string;
        }>) => void
    ): Promise<APIResponse<{
        version: string;
        platform: string;
        arch: string;
    }>> {
        return this.sendRequest<{
            version: string;
            platform: string;
            arch: string;
        }>('get_system_info', undefined, undefined, callback);
    }
}

// 导出单例实例
export const ipcApi = IPCAPI.getInstance(); 