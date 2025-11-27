/**
 * IPC API
 * 提供与 Python Backend通信的Advanced API
 */
import { IPCWCClient } from './ipcWCClient';
import { IPCResponse } from './types';
import { logger } from '../../utils/logger';
import { createChatApi } from './chatApi';
import { createLightRAGApi } from './lightragApi';
import { logoutManager } from '../LogoutManager';

/**
 * API ResponseType
 */
export interface APIResponse<T = unknown> {
    /** ResponseStatus */
    success: boolean;
    /** ResponseData */
    data?: T;
    /** ErrorInformation */
    error?: {
        /** Error码 */
        code: string;
        /** ErrorDescription */
        message: string;
        /** 额外ErrorInformation */
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
 * 提供与 Python Backend通信的Advanced API Interface
 */
export class IPCAPI {
    private static instance: IPCAPI;
    private ipcWCClient: IPCWCClient;

    // 新增 chat Field
    public chatApi: ReturnType<typeof createChatApi>;
    // 新增 lightrag Field
    public lightragApi: ReturnType<typeof createLightRAGApi>;

    private constructor() {
        this.ipcWCClient = IPCWCClient.getInstance();
        // Initialize chat api
        this.chatApi = createChatApi(this);
        this.lightragApi = createLightRAGApi(this);
        // RegisterlogoutCleanupFunction
        this.registerLogoutCleanup();
    }

    /**
     * CleanupIPCRequest队列
     */
    public clearQueue(): void {
        this.ipcWCClient.clearQueue();
    }

    /**
     * RegisterlogoutCleanupFunction
     */
    private registerLogoutCleanup(): void {
        logoutManager.registerCleanup({
            name: 'IPCAPI',
            cleanup: () => {
                logger.info('[IPCAPI] Cleaning up for logout...');
                this.clearQueue(); // CleanupIPCRequest队列
                // Can在这里Add其他IPCRelated toCleanup逻辑
                logger.info('[IPCAPI] Cleanup completed');
            },
            priority: 5 // 最高Priority，最先CleanupIPC
        });
    }

    /**
     * Get IPCAPI 单例
     */
    public static getInstance(): IPCAPI {
        if (!IPCAPI.instance) {
            IPCAPI.instance = new IPCAPI();
        }
        return IPCAPI.instance;
    }

    /**
     * Toggle window fullscreen state
     */
    public async windowToggleFullscreen(): Promise<boolean> {
        const response = await this.ipcWCClient.invoke('window_toggle_fullscreen', {});
        return response?.result?.is_fullscreen ?? response?.data?.is_fullscreen ?? false;
    }

    /**
     * Get window fullscreen state
     */
    public async windowGetFullscreenState(): Promise<boolean> {
        const response = await this.ipcWCClient.invoke('window_get_fullscreen_state', {});
        return response?.result?.is_fullscreen ?? response?.data?.is_fullscreen ?? false;
    }

    /**
     * Execute IPC Request - 使用队列机制以避免并发问题
     * @param method - RequestMethod名
     * @param params - RequestParameter
     * @param timeout - Optional timeout in milliseconds
     * @returns Promise 对象，Parse为 API Response
     */
    public async executeRequest<T>(method: string, params?: unknown, timeout?: number): Promise<APIResponse<T>> {
        const startTs = Date.now();
        console.log('[IPCAPI] executeRequest:start', method, { params, timeout });
        try {
            // 对于 get_initialization_progress，使用 invoke Method以利用队列和并发控制
            let response: IPCResponse;
            if (method === 'get_initialization_progress') {
                response = await this.ipcWCClient.invoke(method, params, { timeout }) as IPCResponse;
            } else {
                response = await this.ipcWCClient.sendRequest(method, params, timeout) as IPCResponse;
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
     * UserLogin
     * @param username - User名
     * @param password - Password
     * @returns Promise 对象，Parse为LoginResponse
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

    public async googleLogin<T>(lang?: string, role?: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('google_login', { lang, role });
    }

    public async loginWithApple<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('login_with_apple', {});
    }

    public async getAll<T>(username: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_all', { username });
    }

    public async getAllOrgAgents<T>(username: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_all_org_agents', { username });
    }
    
    public async getAgents<T>(username: string, agent_id: string[]): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_agents', { username, agent_id });
    }

    public async getAgentSkills<T>(username: string,skill_ids: string[]): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_agent_skills', { username, skill_ids });
    }

    public async getAgentTasks<T>(username: string, agent_task_ids: string[]): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_agent_tasks', {username, task_ids: agent_task_ids });
    }

    public async getVehicles<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_vehicles', { });
    }

    public async updateVehicleStatus<T>(vehicle_id: number, status: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('update_vehicle_status', { vehicle_id, status });
    }

    public async addVehicle<T>(vehicle: any): Promise<APIResponse<T>> {
        return this.executeRequest<T>('add_vehicle', vehicle);
    }

    public async updateVehicle<T>(vehicle_id: number, updates: any): Promise<APIResponse<T>> {
        return this.executeRequest<T>('update_vehicle', { vehicle_id, ...updates });
    }

    public async deleteVehicle<T>(vehicle_id: number): Promise<APIResponse<T>> {
        return this.executeRequest<T>('delete_vehicle', { vehicle_id });
    }

    public async assignBotToVehicle<T>(bot_id: string, vehicle_id: number): Promise<APIResponse<T>> {
        return this.executeRequest<T>('assign_bot_to_vehicle', { bot_id, vehicle_id });
    }

    public async removeBotFromVehicle<T>(bot_id: string, vehicle_id: number): Promise<APIResponse<T>> {
        return this.executeRequest<T>('remove_bot_from_vehicle', { bot_id, vehicle_id });
    }

    public async getSchedules<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_schedules', { });
    }

    public async getTools<T>(username: string, tool_ids: string[]): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_tools', {username, tool_ids });
    }

    // Avatar API methods
    public async getSystemAvatars<T>(username: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('avatar.get_system_avatars', { username });
    }

    public async getUploadedAvatars<T>(username: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('avatar.get_uploaded_avatars', { username });
    }

    public async uploadAvatar<T>(username: string, fileData: string, filename: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('avatar.upload_avatar', { username, fileData, filename });
    }

    public async deleteUploadedAvatar<T>(username: string, avatarId: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('avatar.delete_uploaded_avatar', { username, avatarId });
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

    public async updateUserPreferences<T>(language?: string, theme?: string): Promise<APIResponse<T>> {
        const params: any = {};
        if (language) params.language = language;
        if (theme) params.theme = theme;
        return this.executeRequest<T>('update_user_preferences', params);
    }

    // LLM Management APIs
    public async getLLMProviders<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_llm_providers', {});
    }

    public async setDefaultLLM<T>(name: string, username: string, model?: string): Promise<APIResponse<T>> {
        const params: any = { name, username };
        if (model) {
            params.model = model;
        }
        return this.executeRequest<T>('set_default_llm', params);
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

    public async setLLMProviderModel<T>(name: string, model: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('set_llm_provider_model', { name, model });
    }

    public async deleteLLMProviderConfig<T>(name: string, username: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('delete_llm_provider_config', { name, username });
    }

    public async getLLMProviderApiKey<T>(name: string, showFull: boolean = false): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_llm_provider_api_key', { name, show_full: showFull });
    }

    public async getConfiguredLLMProviders<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_configured_llm_providers', {});
    }

    public async getLLMProvidersWithCredentials<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_llm_providers_with_credentials', {});
    }

    // Embedding Management APIs
    public async getEmbeddingProviders<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_embedding_providers', {});
    }

    public async setDefaultEmbedding<T>(name: string, username: string, model?: string): Promise<APIResponse<T>> {
        const params: any = { name, username };
        if (model) {
            params.model = model;
        }
        return this.executeRequest<T>('set_default_embedding', params);
    }

    public async updateEmbeddingProvider<T>(name: string, apiKey: string, azureEndpoint?: string): Promise<APIResponse<T>> {
        const params: any = { name, api_key: apiKey };
        if (azureEndpoint) {
            params.azure_endpoint = azureEndpoint;
        }
        return this.executeRequest<T>('update_embedding_provider', params);
    }

    public async setEmbeddingProviderModel<T>(name: string, model: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('set_embedding_provider_model', { name, model });
    }

    public async deleteEmbeddingProviderConfig<T>(name: string, username: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('delete_embedding_provider_config', { name, username });
    }

    public async getEmbeddingProviderApiKey<T>(name: string, showFull: boolean = false): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_embedding_provider_api_key', { name, show_full: showFull });
    }

    public async getDefaultEmbedding<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_default_embedding', {});
    }

    // Rerank Management APIs
    public async getRerankProviders<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_rerank_providers', {});
    }

    public async setDefaultRerank<T>(name: string, username: string, model?: string): Promise<APIResponse<T>> {
        const params: any = { name, username };
        if (model) {
            params.model = model;
        }
        return this.executeRequest<T>('set_default_rerank', params);
    }

    public async updateRerankProvider<T>(name: string, apiKey: string, azureEndpoint?: string): Promise<APIResponse<T>> {
        const params: any = { name, api_key: apiKey };
        if (azureEndpoint) {
            params.azure_endpoint = azureEndpoint;
        }
        return this.executeRequest<T>('update_rerank_provider', params);
    }

    public async setRerankProviderModel<T>(name: string, model: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('set_rerank_provider_model', { name, model });
    }

    public async deleteRerankProviderConfig<T>(name: string, username: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('delete_rerank_provider_config', { name, username });
    }

    public async getRerankProviderApiKey<T>(name: string, showFull: boolean = false): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_rerank_provider_api_key', { name, show_full: showFull });
    }

    public async getDefaultRerank<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('get_default_rerank', {});
    }

    public async runTest<T>(tests: TestConfig[]): Promise<APIResponse<T>> {
        return this.executeRequest<T>('run_tests', { tests });
    }

    // Some backends expect a single test payload instead of an array under {tests}
    public async runSingleTest<T>(test: { test_id: string; args?: Record<string, any> }): Promise<APIResponse<T>> {
        return this.executeRequest<T>('run_tests', test);
    }

    public async stopTest<T>(test_ids: string[]): Promise<APIResponse<T>> {
        return this.executeRequest<T>('stop_tests', { test_ids });
    }

    public async saveAgent<T>(username: string, agent: T[]): Promise<APIResponse<void>> {
        return this.executeRequest<void>('save_agent', {username, agent});
    }

    public async deleteAgent<T>(username: string, agent_id: (string|number)[]): Promise<APIResponse<T>> {
        // Delete agents by id
        return this.executeRequest<T>('delete_agent', { username, agent_id });
    }

    public async newAgent<T>(username: string, agent: T[]): Promise<APIResponse<void>> {
        // Create agents
        return this.executeRequest<void>('new_agent', { username, agent });
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

    public async saveAgentTask<T>(username: string, agent_task_info: T): Promise<APIResponse<void>> {
        return this.executeRequest<void>('save_agent_task', {username, task_info: agent_task_info});
    }

    public async newAgentTask<T>(username: string, agent_task_info: T): Promise<APIResponse<void>> {
        return this.executeRequest<void>('new_agent_task', {username, task_info: agent_task_info});
    }

    public async deleteAgentTask(username: string, agent_task_id: string): Promise<APIResponse<void>> {
        return this.executeRequest<void>('delete_agent_task', {username, task_id: agent_task_id});
    }

    public async saveAgentSkill<T>(username: string, skill_info: T): Promise<APIResponse<void>> {
        return this.executeRequest<void>('save_agent_skill', {username, skill_info});
    }

    public async newAgentSkill<T>(username: string, skill_info: T): Promise<APIResponse<void>> {
        return this.executeRequest<void>('new_agent_skill', {username, skill_info});
    }

    public async deleteAgentSkill(username: string, skill_id: string): Promise<APIResponse<void>> {
        return this.executeRequest<void>('delete_agent_skill', {username, skill_id});
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

    public async setSkillBreakpoints<T>(username: string, node_name: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('set_skill_breakpoints', {username, node_name});
    }

    public async clearSkillBreakpoints<T>(username: string, node_name: string): Promise<APIResponse<T>> {
        return this.executeRequest<T>('clear_skill_breakpoints', {username, node_name});
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
     * Step-sim debug: cache sheets bundle and move to Start node on backend
     */
    public async setupSimStep<T>(bundle: any): Promise<APIResponse<T>> {
        return this.executeRequest<T>('setup_sim_step', { bundle });
    }

    /**
     * Step-sim debug: advance one node on backend
     */
    public async stepSim<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('step_sim', {});
    }

    /**
     * Dev: trigger backend to run a small langgraph2flowgram export test
     */
    public async testLanggraph2Flowgram<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('test_langgraph2flowgram', {});
    }

    /**
     * Get可调用FunctionList
     * @param filter - Filter条件，OptionalInclude：
     *   - text: 文本Filter条件，会SearchFunction名、Description和Parameter
     *   - type: TypeFilter条件（'system' 或 'custom'）
     * @returns Promise 对象，Parse为可调用FunctionList
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
     * GetInitialize进度
     * @returns Promise 对象，Parse为Initialize进度Information
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

    /**
     * Save skill editor cache to Python backend
     * @param cacheData - Cache data to save
     * @returns Promise with save result
     */
    public async saveEditorCache<T>(cacheData: any): Promise<APIResponse<T>> {
        return this.executeRequest<T>('save_editor_cache', { cacheData });
    }

    /**
     * Load skill editor cache from Python backend
     * @returns Promise with cache data
     */
    public async loadEditorCache<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('load_editor_cache', {});
    }

    /**
     * Clear skill editor cache from Python backend
     * @returns Promise with clear result
     */
    public async clearEditorCache<T>(): Promise<APIResponse<T>> {
        return this.executeRequest<T>('clear_editor_cache', {});
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

    public async deleteOrg<T>(username: string, org_id: string, force: boolean = false): Promise<APIResponse<T>> {
        return this.executeRequest<T>('delete_org', { username, organization_id: org_id, force });
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
 * Create IPC API 实例
 * @returns IPC API 实例
 */
export function createIPCAPI(): IPCAPI {
    return IPCAPI.getInstance();
} 