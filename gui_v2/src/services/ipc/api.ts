/**
 * IPC API
 * 提供与 Python 后端通信的高级 API
 */
import { IPCWCClient } from './ipcWCClient';
import { IPCResponse } from './types';
import { logger } from '../../utils/logger';
import { createChatApi } from './chatApi';
import { logoutManager } from '../LogoutManager';

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
    private ipcWCClient: IPCWCClient;

    // 新增 chat 字段
    public chatApi: ReturnType<typeof createChatApi>;

    private constructor() {
        this.ipcWCClient = IPCWCClient.getInstance();
        // 初始化 chat api
        this.chatApi = createChatApi(this);
        // 注册logout清理函数
        this.registerLogoutCleanup();
    }

    /**
     * 清理IPC请求队列
     */
    public clearQueue(): void {
        this.ipcWCClient.clearQueue();
    }

    /**
     * 注册logout清理函数
     */
    private registerLogoutCleanup(): void {
        logoutManager.registerCleanup({
            name: 'IPCAPI',
            cleanup: () => {
                logger.info('[IPCAPI] Cleaning up for logout...');
                this.clearQueue(); // 清理IPC请求队列
                // 可以在这里添加其他IPC相关的清理逻辑
                logger.info('[IPCAPI] Cleanup completed');
            },
            priority: 5 // 最高优先级，最先清理IPC
        });
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
     * 执行 IPC 请求 - 使用队列机制以避免并发问题
     * @param method - 请求方法名
     * @param params - 请求参数
     * @returns Promise 对象，解析为 API 响应
     */
    private async executeRequest<T>(method: string, params?: unknown): Promise<APIResponse<T>> {
        const startTs = Date.now();
        console.log('[IPCAPI] executeRequest:start', method, { params });
        try {
            // 对于 get_initialization_progress，使用 invoke 方法以利用队列和并发控制
            let response: IPCResponse;
            if (method === 'get_initialization_progress') {
                response = await this.ipcWCClient.invoke(method, params) as IPCResponse;
            } else {
                response = await this.ipcWCClient.sendRequest(method, params) as IPCResponse;
            }

            console.log('[IPCAPI] executeRequest:response', method, { response, durationMs: Date.now() - startTs });
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
            console.log('[IPCAPI] executeRequest:error', method, { error, durationMs: Date.now() - startTs });
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
    public async login<T>(username: string, password: string, machine_role: string, lang?: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('login', { username, password, machine_role, lang });
    }

    public async getLastLoginInfo<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_last_login', {});
    }

    public async logout<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('logout', {});
    }

    public async signup<T>(username: string, password: string, lang?: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('signup', { username, password, lang });
    }

    public async forgotPassword<T>(username: string, lang?: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('forgot_password', { username, lang });
    }

    public async confirmForgotPassword<T>(username: string, confirmCode: string, newPassword: string, lang?: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('confirm_forgot_password', { username, confirmCode, newPassword, lang});
    }

    public async googleLogin<T>(lang?: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('google_login', { lang });
    }

    public async loginWithApple<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('login_with_apple', {});
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

    public async getVehicles<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_vehicles', { });
    }

    public async getSchedules<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_schedules', { });
    }

    public async getTools<T>(username: string, tool_ids: string[]): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_tools', {username, tool_ids });
    }

    /**
     * Refresh MCP tool schemas on the backend and return refreshed list
     */
    public async refreshToolsSchemas<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('refresh_tools_schemas', {});
    }

    // public async getKnowledges<T>(username: string, knowledge_ids: string[]): Promise<APIResponse<T>> {
    //     return this.executeRequest<T>('get_knowledges', {username, knowledge_ids });
    // }

    public async getSettings<T>(username: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_settings', {username});
    }

    // LLM Management APIs
    public async getLLMProviders<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_llm_providers', {});
    }

    public async setDefaultLLM<T>(name: string, username: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('set_default_llm', { name, username });
    }

    public async updateLLMProvider<T>(name: string, apiKey: string, azureEndpoint?: string, awsAccessKeyId?: string, awsSecretAccessKey?: string): Promise<APIResponse<T>> {
        const params: any = { name, api_key: apiKey };
        if (azureEndpoint) {
            params.azure_endpoint = azureEndpoint;
        }
        if (awsAccessKeyId) {
            params.aws_access_key_id = awsAccessKeyId;
        }
        if (awsSecretAccessKey) {
            params.aws_secret_access_key = awsSecretAccessKey;
        }
        return this.executeRequest<T>('update_llm_provider', params);
    }

    public async deleteLLMProviderConfig<T>(name: string, username: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('delete_llm_provider_config', { name, username });
    }

    public async getLLMProviderApiKey<T>(name: string, showFull: boolean = false): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_llm_provider_api_key', { name, show_full: showFull });
    }

    public async runTest<T>(username: string, tests: TestConfig[]): Promise<APIResponse<T>> {
        return this.executeRequest<T>('run_tests', { tests });
    }

    // Some backends expect a single test payload instead of an array under {tests}
    public async runSingleTest<T>(test: { test_id: string; args?: Record<string, any> }): Promise<APIResponse<T>> {
        return this.executeRequest<T>('run_tests', test);
    }

    public async stopTest<T>(test_ids: string[]): Promise<APIResponse<T>> {
        return this.executeRequest<T>('stop_tests', { test_ids });
    }

    public async saveAgents<T>(username: string, agents: T[]): Promise<APIResponse<void>> {
        return this.executeRequest<void>('save_agents', {username, agents});
    }

    public async deleteAgents<T>(username: string, agent_ids: (string|number)[]): Promise<APIResponse<void>> {
        // Delete multiple agents by id
        return this.executeRequest<void>('delete_agents', { username, agent_ids });
    }

    public async deleteAgent<T>(username: string, agent_id: string|number): Promise<APIResponse<void>> {
        // Convenience wrapper to delete a single agent
        return this.deleteAgents<T>(username, [agent_id]);
    }

    public async newAgents<T>(username: string, agents: T[]): Promise<APIResponse<void>> {
        // Create multiple agents
        return this.executeRequest<void>('new_agents', { username, agents });
    }

    public async newTools<T>(username: string, tools: T[]): Promise<APIResponse<void>> {
        return this.executeRequest<void>('new_tools', {username, tools});
    }

    public async deleteTools<T>(username: string, tools: T[]): Promise<APIResponse<void>> {
        return this.executeRequest<void>('delete_tools', {username, tools});
    }

    public async saveTools<T>(username: string, tools: T[]): Promise<APIResponse<void>> {
        return this.executeRequest<void>('save_tools', {username, tools});
    }

    public async saveTasks<T>(username: string, tasks: T[]): Promise<APIResponse<void>> {
        return this.executeRequest<void>('save_tasks', {username, tasks});
    }

    public async newTasks<T>(username: string, tasks: T[]): Promise<APIResponse<void>> {
        return this.executeRequest<void>('new_tasks', {username, tasks});
    }

    public async deleteTasks<T>(username: string, tasks: T[]): Promise<APIResponse<void>> {
        return this.executeRequest<void>('delete_tasks', {username, tasks});
    }

    public async saveSkills<T>(username: string, skills: T[]): Promise<APIResponse<void>> {
        return this.executeRequest<void>('save_skills', {username, skills});
    }

    public async saveSkill<T>(username: string, skill_info: T): Promise<APIResponse<void>> {
        return this.executeRequest<void>('save_skill', {username, skill_info});
    }

    public async newSkill<T>(username: string, skill_info: T): Promise<APIResponse<void>> {
        return this.executeRequest<void>('new_skill', {username, skill_info});
    }

    public async deleteSkills<T>(username: string, skills: T[]): Promise<APIResponse<void>> {
        return this.executeRequest<void>('delete_skills', {username, skills});
    }

    public async runSkill<T>(username: string, skill: T): Promise<APIResponse<void>> {
        return this.executeRequest<void>('run_skill', {username, skill});
    }

    public async cancelRunSkill<T>(username: string, skill: T): Promise<APIResponse<void>> {
        return this.executeRequest<void>('cancel_run_skill', {username, skill});
    }

    public async pauseRunSkill<T>(username: string, skill: T): Promise<APIResponse<void>> {
        return this.executeRequest<void>('pause_run_skill', {username, skill});
    }

    public async resumeRunSkill<T>(username: string, skill: T): Promise<APIResponse<void>> {
        return this.executeRequest<void>('resume_run_skill', {username, skill});
    }

    public async stepRunSkill<T>(username: string, skill: T): Promise<APIResponse<void>> {
        return this.executeRequest<void>('step_run_skill', {username, skill});
    }

    public async setSkillBreakpoints<T>(username: string, node_name: string): Promise<APIResponse<void>> {
        return this.executeRequest<void>('set_skill_breakpoints', {username, node_name});
    }

    public async clearSkillBreakpoints<T>(username: string, node_name: string): Promise<APIResponse<void>> {
        return this.executeRequest<void>('clear_skill_breakpoints', {username, node_name});
    }

    public async requestSkillState<T>(username: string, skill: T): Promise<APIResponse<void>> {
        return this.executeRequest<void>('request_skill_state', {username, skill});
    }

    public async injectSkillState<T>(username: string, skill: T): Promise<APIResponse<void>> {
        return this.executeRequest<void>('inject_skill_state', {username, skill});
    }

    public async loadSkillSchemas<T>(username: string, skill: T): Promise<APIResponse<void>> {
        return this.executeRequest<void>('load_skill_schemas', {username, skill});
    }

    public async saveSettings<T>(value: T): Promise<APIResponse<void>> {
        return this.executeRequest<void>('save_settings', value);
    }

    public async newKnowledges<T>(values: T[]): Promise<APIResponse<void>> {
        return this.executeRequest<void>('new_knowledges', values);
    }

    public async saveKnowledges<T>(values: T[]): Promise<APIResponse<void>> {
        return this.executeRequest<void>('save_knowledges', values);
    }

    public async deleteKnowledges<T>(values: T[]): Promise<APIResponse<void>> {
        return this.executeRequest<void>('delete_knowledges', values);
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
     * Editor support: fetch agents for chat_node party selector
     */
    public async getEditorAgents<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_editor_agents', {});
    }

    /**
     * Editor support: fetch queues/events for pend_input_node
     */
    public async getEditorPendingSources<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_editor_pending_sources', {});
    }

    /**
     * Editor support: fetch NodeState JSON Schema for NodeStatePanel and forms
     */
    public async getNodeStateSchema<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('skill_editor.get_node_state_schema', {});
    }

    /**
     * 获取初始化进度
     * @returns Promise 对象，解析为初始化进度信息
     */
    public async getInitializationProgress(): Promise<APIResponse<{
        ui_ready: boolean;
        critical_services_ready: boolean;
        async_init_complete: boolean;
        fully_ready: boolean;
        sync_init_complete: boolean;
        message: string;
    }>> {
        return this.executeRequest('get_initialization_progress');
    }

    // Org Management APIs - New simplified names
    public async getOrgs<T>(username: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_orgs', { username });
    }

    public async createOrg<T>(username: string, name: string, description?: string, parent_id?: string, org_type?: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('create_org', { username, name, description, parent_id, organization_type: org_type });
    }

    public async updateOrg<T>(username: string, org_id: string, name?: string, description?: string, parent_id?: string | null): Promise<APIResponse<T>> {
        return this.executeRequest<T>('update_org', { username, organization_id: org_id, name, description, parent_id });
    }

    public async deleteOrg<T>(username: string, org_id: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('delete_org', { username, organization_id: org_id });
    }

    public async getOrgAgents<T>(username: string, org_id: string, include_descendants?: boolean): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_org_agents', { username, organization_id: org_id, include_descendants });
    }

    public async bindAgentToOrg<T>(username: string, agent_id: string, org_id: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('bind_agent_to_org', { username, agent_id, organization_id: org_id });
    }

    public async unbindAgentFromOrg<T>(username: string, agent_id: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('unbind_agent_from_org', { username, agent_id });
    }

    public async getAvailableAgentsForBinding<T>(username: string, org_id: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_available_agents_for_binding', { username, organization_id: org_id });
    }


}

/**
 * 创建 IPC API 实例
 * @returns IPC API 实例
 */
export function createIPCAPI(): IPCAPI {
    return IPCAPI.getInstance();
} 