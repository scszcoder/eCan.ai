/**
 * IPC API
 * 提供与 Python 后端通信的高级 API
 */
import { IPCClient } from './client';
import { IPCResponse } from './types';
import { logger } from '../../utils/logger';
import { createChatApi } from './chatApi';

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

export interface TestConfig {
    test_id: string;  // or test_name, depending on your needs
    args?: Record<string, any>;  // Optional arguments for the test
    // Add other test properties as needed
}
/**
 * IPC API 类
 * 提供与 Python 后端通信的高级 API 接口
 */
export class IPCAPI {
    private static instance: IPCAPI;
    private client: IPCClient;

    // 新增 chat 字段
    public chat: ReturnType<typeof createChatApi>;

    private constructor() {
        this.client = IPCClient.getInstance();
        // 初始化 chat api
        this.chat = createChatApi(this);
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
            logger.debug(`Executing ${method}`, params ? `with params: ${JSON.stringify(params)}` : '');
            const response = await this.client.sendRequest(method, params) as IPCResponse;

            if (response.status === 'success') {
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
            logger.error(`Failed to execute ${method}:`, error);
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
    public async login<T>(username: string, password: string, machine_role: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('login', { username, password, machine_role });
    }

    public async getLastLoginInfo<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_last_login', {});
    }

    public async getAll<T>(username: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_all', { username });
    }

    public async getAgents<T>(username: string, skill_ids: string[]): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_agents', { username, skill_ids });
    }

    public async getSkills<T>(username: string,skill_ids: string[]): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_skills', { username, skill_ids });
    }

    public async getTasks<T>(username: string, task_ids: string[]): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_tasks', {username, task_ids });
    }

    public async getVehicles<T>(username: string, v_ids: string[]): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_vehicles', {username, v_ids });
    }

    public async getTools<T>(username: string, tool_ids: string[]): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_tools', {username, tool_ids });
    }

    public async getKnowledges<T>(username: string, knowledge_ids: string[]): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_knowledges', {username, knowledge_ids });
    }

    public async getSettings<T>(username: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_settings', {username});
    }

    public async runTest<T>(tests: TestConfig[]): Promise<APIResponse<T>> {
        return this.executeRequest<T>('run_tests', { tests });
    }

    public async stopTest<T>(test_ids: string[]): Promise<APIResponse<T>> {
        return this.executeRequest<T>('stop_tests', { test_ids });
    }

    public async saveAgents<T>(username: string, agents: T[]): Promise<APIResponse<void>> {
        return this.executeRequest<void>('save_agents', {username, agents});
    }

    public async saveTools<T>(username: string, tools: T[]): Promise<APIResponse<void>> {
        return this.executeRequest<void>('save_tools', {username, tools});
    }

    public async saveTasks<T>(username: string, tasks: T[]): Promise<APIResponse<void>> {
        return this.executeRequest<void>('save_tasks', {username, tasks});
    }

    public async saveSkills<T>(username: string, skills: T[]): Promise<APIResponse<void>> {
        return this.executeRequest<void>('save_skills', {username, skills});
    }

    public async saveSkill<T>(username: string, skill_info: T): Promise<APIResponse<void>> {
        return this.executeRequest<void>('save_skill', {username, skill_info});
    }


    public async runSkill<T>(username: string, skill: T): Promise<APIResponse<void>> {
        return this.executeRequest<void>('run_skill', {username, skill});
    }


    public async saveSettings<T>(value: T): Promise<APIResponse<void>> {
        return this.executeRequest<void>('save_settings', value);
    }

    public async saveKnowledges<T>(values: T[]): Promise<APIResponse<void>> {
        return this.executeRequest<void>('save_knowledges', values);
    }

    public async getAvailableTests<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_available_tests', {});
    }

    /**
     * 获取可调用函数列表
     * @param filter - 过滤条件，可选包含：
     *   - text: 文本过滤条件，会搜索函数名、描述和参数
     *   - type: 类型过滤条件（'system' 或 'custom'）
     * @returns Promise 对象，解析为可调用函数列表
     */
    public async getCallables<T>(filter?: { text?: string; type?: 'system' | 'custom' }): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_callables', filter);
    }

    /**
     * Manage callable function (add/update/delete)
     * @param params - Raw parameters to be sent to IPC
     * @returns Promise<APIResponse<T>> - Standard API response with typed data
     */
    public async manageCallable<T>(params: any): Promise<APIResponse<T>> {
        return this.executeRequest<T>('manage_callable', params);
    }

    /**
     * 获取设置
     * @param keys - 要获取的设置键名数组，如果为空则获取所有设置
     * @returns Promise 对象，解析为设置值
     */
    /*
    public async getSettings<T>(keys: string[] = []): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_settings', { keys });
    }
    */

    /**
     * 保存设置
     * @param settings - 要保存的设置对象
     * @returns Promise 对象，解析为操作结果
     */
    /*
    public async saveSettings<T>(settings: T): Promise<APIResponse<void>> {
        return this.executeRequest<void>('save_settings', settings);
    }
    */

    public async getChatMessages<T>(params: {
        chatId: string;
        limit?: number;
        offset?: number;
        reverse?: boolean;
    }): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_chat_messages', params);
    }

    public async deleteChat<T>(chatId: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('delete_chat', { chatId });
    }

    public async markMessageAsRead<T>(messageIds: string[], userId: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('mark_message_as_read', { messageIds, userId });
    }
}

/**
 * 创建 IPC API 实例
 * @returns IPC API 实例
 */
export function createIPCAPI(): IPCAPI {
    return IPCAPI.getInstance();
} 