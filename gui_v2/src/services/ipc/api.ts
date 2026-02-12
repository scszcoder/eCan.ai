/**
 * IPC API
 * 提供与 Python Backend通信的Advanced API
 */
import { IPCResponse } from './types';
import { logger } from '../../utils/logger';
import { createChatApi } from './chatApi';
import { createLightRAGApi } from './lightragApi';
import { logoutManager } from '../LogoutManager';
import { ipcClient } from './ipcClient';
import { detectPlatform } from '../../config/platform';
import { apiRouter } from '../api/api-router';
import { GRAPHQL_QUERIES, GRAPHQL_MUTATIONS } from '../api/api-config';

// Web Bridge mechanism has been deprecated and removed.
// All requests now go directly through IPC for consistency and reliability.

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
    private clientInitPromise: Promise<void> | null = null;

    // 新增 chat Field
    public chatApi: ReturnType<typeof createChatApi>;
    // 新增 lightrag Field
    public lightragApi: ReturnType<typeof createLightRAGApi>;

    private constructor() {
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
        ipcClient.clearQueue();
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
        await this.ensureInitialized();
        const response = await ipcClient.invoke('window_toggle_fullscreen', {});
        return response?.result?.is_fullscreen ?? response?.data?.is_fullscreen ?? false;
    }

    /**
     * Get window fullscreen state
     */
    public async windowGetFullscreenState(): Promise<boolean> {
        await this.ensureInitialized();
        const response = await ipcClient.invoke('window_get_fullscreen_state', {});
        return response?.result?.is_fullscreen ?? response?.data?.is_fullscreen ?? false;
    }

    private async ensureInitialized(): Promise<void> {
        if (ipcClient.isInitialized()) {
            return;
        }

        if (!this.clientInitPromise) {
            this.clientInitPromise = ipcClient.initialize().catch((error) => {
                this.clientInitPromise = null;
                throw error;
            });
        }

        await this.clientInitPromise;
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
            // All requests now go directly through IPC (Web Bridge deprecated)
            await this.ensureInitialized();

            const currentMode = ipcClient.getMode?.() ?? detectPlatform();
            if (currentMode === 'web' && !ipcClient.isConnected()) {
                return {
                    success: false,
                    error: {
                        code: 'NOT_CONNECTED',
                        message: 'WebSocket not connected. Call connect() first.'
                    }
                };
            }

            // 对于 get_initialization_progress，使用 invoke Method以利用队列和并发控制
            let response: IPCResponse;
            if (method === 'get_initialization_progress') {
                response = await ipcClient.invoke(method, params, { timeout });
            } else {
                response = await ipcClient.invoke(method, params, { timeout });
            }

            console.log('[IPCAPI] executeRequest:response', method, { response, durationMs: Date.now() - startTs });
            if (response.status === 'success') {
                return {
                    success: true,
                    data: response.result as T
                };
            } else {
                const errorCode = String(response.error?.code || 'UNKNOWN_ERROR');
                
                // Handle INVALID_TOKEN error by clearing stored token and redirecting to login
                if (errorCode === 'INVALID_TOKEN' || errorCode === 'TOKEN_REQUIRED') {
                    logger.warn(`[IPCAPI] Authentication failed for ${method}: ${errorCode}`);
                    
                    // Clear the invalid token from storage
                    try {
                        const { userStorageManager } = await import('../storage/UserStorageManager');
                        userStorageManager.removeToken();
                        logger.info('[IPCAPI] Cleared invalid token from storage');
                        
                        // Show user notification (only once)
                        if (!sessionStorage.getItem('token_expired_notification_shown')) {
                            sessionStorage.setItem('token_expired_notification_shown', 'true');
                            
                            // Try to show Ant Design message if available
                            try {
                                const { message } = await import('antd');
                                message.warning('Your session has expired. Please log in again.');
                            } catch {
                                // Fallback to console if Ant Design not available
                                console.warn('Session expired. Please log in again.');
                            }
                        }
                        
                        // Redirect to login page if not already there
                        if (window.location.hash !== '#/login') {
                            logger.info('[IPCAPI] Redirecting to login due to invalid token');
                            // Small delay to allow notification to show
                            setTimeout(() => {
                                window.location.hash = '#/login';
                            }, 500);
                        }
                    } catch (error) {
                        logger.error('[IPCAPI] Error clearing invalid token:', error);
                    }
                }
                
                return {
                    success: false,
                    error: {
                        code: errorCode,
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
        return apiRouter.execute({ method: 'login' }, { username, password, machine_role, lang });
    }

    public async getLastLoginInfo<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_last_login' });
    }

    public async logout<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'logout' });
    }

    public async signup<T>(username: string, password: string, lang?: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'signup' }, { username, password, lang });
    }

    public async forgotPassword<T>(username: string, lang?: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'forgot_password' }, { username, lang });
    }

    public async confirmForgotPassword<T>(username: string, confirmCode: string, newPassword: string, lang?: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'confirm_forgot_password' }, { username, confirmCode, newPassword, lang});
    }

    public async googleLogin<T>(lang?: string, role?: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'google_login' }, { lang, role });
    }

    public async loginWithApple<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'login_with_apple' });
    }

    public async getAll<T>(username: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'get_all',
        graphql: {
          query: GRAPHQL_QUERIES.GET_ALL_MINE,
          resultPath: 'getAllMine'
        }
      },
      { username }
    );
    }

    public async getAllOrgAgents<T>(username: string, companyName?: string): Promise<APIResponse<T>> {
        let company = companyName;
        if (!company) {
            try {
                company = localStorage.getItem('org_company_filter') || undefined;
            } catch {
                company = undefined;
            }
        }

        const params = company ? { username, company } : { username };
        const response = await apiRouter.execute<any>(
      {
        method: 'get_all_org_agents',
        graphql: {
          query: GRAPHQL_QUERIES.GET_ORG_AGENT_TREE,
          resultPath: 'getOrgAgentTree'
        }
      },
      params
    );
        
        // Wrap the tree response in {orgs: ...} format expected by the store
        if (response.success && response.data) {
            // If data is already wrapped with orgs, use as-is; otherwise wrap it
            const wrappedData = response.data.orgs ? response.data : { orgs: response.data };
            return { ...response, data: wrappedData as T };
        }
        return response as APIResponse<T>;
    }
    
    public async getAgents<T>(username: string, agent_id: string[]): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'get_agents',
        graphql: {
          query: GRAPHQL_QUERIES.GET_ALL_MINE,
          resultPath: 'getAllMine.agents'
        }
      },
      { username, agent_id }
    );
    }

    public async getAgentSkills<T>(username: string,skill_ids: string[]): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'get_agent_skills',
        graphql: {
          query: GRAPHQL_QUERIES.GET_ALL_MINE,
          resultPath: 'getAllMine.skills'
        }
      },
      { username, skill_ids }
    );
    }

    public async getPublicSkills<T>(username: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_public_skills' }, { username });
    }

    public async getAgentTasks<T>(username: string, agent_task_ids: string[]): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'get_agent_tasks',
        graphql: {
          query: GRAPHQL_QUERIES.GET_AGENT_TASKS,
          resultPath: 'getAgentTasks'
        }
      },
      { username, task_ids: agent_task_ids }
    );
    }

    public async getPrompts<T>(username: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'get_prompts',
        graphql: {
          query: GRAPHQL_QUERIES.GET_ALL_MINE,
          resultPath: 'getAllMine.prompts'
        }
      },
      { username }
    );
    }

    public async savePrompt<T>(username: string, prompt: any): Promise<APIResponse<T>> {
        // Transform flat prompt to GraphQL format: { id, owner, prompt: AWSJSON, version }
        const { id, owner, title, topic, sections, userSections, humanInputs, usageCount, source, readOnly, lastModified, ...rest } = prompt;
        const promptInput = {
          id: id || `pr-${Math.floor(Math.random() * 1_000_000)}`,
          owner: owner || username,
          prompt: JSON.stringify({
            title: title || '',
            topic: topic || '',
            sections: sections || [],
            userSections: userSections || [],
            humanInputs: humanInputs || [],
            usageCount: usageCount || 0,
            source: source || 'my_prompts',
            readOnly: false,
            lastModified: lastModified || new Date().toISOString(),
            ...rest
          }),
          version: prompt.version || '0.1'
        };
        
        return apiRouter.execute(
          {
            method: 'save_prompt',
            graphql: {
              mutation: GRAPHQL_MUTATIONS.ADD_PROMPTS,
              resultPath: 'addPrompts'
            }
          },
          { username, input: [promptInput] }
        );
    }

    public async deletePrompt<T>(username: string, id: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
          {
            method: 'delete_prompt',
            graphql: {
              mutation: GRAPHQL_MUTATIONS.REMOVE_PROMPTS,
              resultPath: 'removePrompts'
            }
          },
          { username, input: [id] }
        );
    }

    public async getVehicles<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_vehicles' }, { });
    }

    public async updateVehicleStatus<T>(vehicle_id: number, status: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'update_vehicle_status' }, { vehicle_id, status });
    }

    public async addVehicle<T>(vehicle: any): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'add_vehicle' }, vehicle);
    }

    public async updateVehicle<T>(vehicle_id: number, updates: any): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'update_vehicle' }, { vehicle_id, ...updates });
    }

    public async deleteVehicle<T>(vehicle_id: number): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'delete_vehicle' }, { vehicle_id });
    }

    public async assignBotToVehicle<T>(bot_id: string, vehicle_id: number): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'assign_bot_to_vehicle' }, { bot_id, vehicle_id });
    }

    public async removeBotFromVehicle<T>(bot_id: string, vehicle_id: number): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'remove_bot_from_vehicle' }, { bot_id, vehicle_id });
    }

    public async getSchedules<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_schedules' }, { });
    }

    public async getTools<T>(username: string, tool_ids: string[]): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'get_tools',
        graphql: {
          query: GRAPHQL_QUERIES.GET_ALL_MINE,
          resultPath: 'getAllMine.tools'
        }
      },
      { username, tool_ids }
    );
    }

    // Avatar API methods
    public async getSystemAvatars<T>(username: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'avatar.get_system_avatars' }, { username });
    }

    public async getUploadedAvatars<T>(username: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'avatar.get_uploaded_avatars' }, { username });
    }

    public async uploadAvatar<T>(username: string, fileData: string, filename: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'avatar.upload_avatar' }, { username, fileData, filename });
    }

    public async deleteUploadedAvatar<T>(username: string, avatarId: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'avatar.delete_uploaded_avatar' }, { username, avatarId });
    }

    /**
     * Refresh MCP tool schemas on the backend and return refreshed list
     */
    public async refreshToolsSchemas<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'refresh_tools_schemas' });
    }

    // public async getKnowledges<T>(username: string, knowledge_ids: string[]): Promise<APIResponse<T>> {
    //     return apiRouter.execute({ method: 'get_knowledges' }, {username, knowledge_ids });
    // }

    public async getSettings<T>(username: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_settings' }, {username});
    }

    public async updateUserPreferences<T>(language?: string, theme?: string): Promise<APIResponse<T>> {
        const params: any = {};
        if (language) params.language = language;
        if (theme) params.theme = theme;
        return apiRouter.execute({ method: 'update_user_preferences' }, params);
    }

    // LLM Management APIs
    public async getLLMProviders<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_llm_providers' });
    }

    public async setDefaultLLM<T>(name: string, username: string, model?: string): Promise<APIResponse<T>> {
        const params: any = { name, username };
        if (model) {
            params.model = model;
        }
        return apiRouter.execute({ method: 'set_default_llm' }, params);
    }

    public async updateLLMProvider<T>(name: string, apiKey: string, azureEndpoint?: string, awsAccessKeyId?: string, awsSecretAccessKey?: string, baseUrl?: string): Promise<APIResponse<T>> {
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
        if (baseUrl) {
            params.base_url = baseUrl;
        }
        return apiRouter.execute({ method: 'update_llm_provider' }, params);
    }

    public async setLLMProviderModel<T>(name: string, model: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'set_llm_provider_model' }, { name, model });
    }

    public async setLLMProviderEnableThinking<T>(name: string, enableThinking: boolean): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'set_llm_provider_enable_thinking' }, { name, enable_thinking: enableThinking });
    }

    public async deleteLLMProviderConfig<T>(name: string, username: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'delete_llm_provider_config' }, { name, username });
    }

    public async getLLMProviderApiKey<T>(name: string, showFull: boolean = false): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_llm_provider_api_key' }, { name, show_full: showFull });
    }

    public async getConfiguredLLMProviders<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_configured_llm_providers' });
    }

    public async getLLMProvidersWithCredentials<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_llm_providers_with_credentials' });
    }

    // Embedding Management APIs
    public async getEmbeddingProviders<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_embedding_providers' });
    }

    public async setDefaultEmbedding<T>(name: string, username: string, model?: string): Promise<APIResponse<T>> {
        const params: any = { name, username };
        if (model) {
            params.model = model;
        }
        return apiRouter.execute({ method: 'set_default_embedding' }, params);
    }

    public async updateEmbeddingProvider<T>(name: string, apiKey: string, azureEndpoint?: string, baseUrl?: string): Promise<APIResponse<T>> {
        const params: any = { name, api_key: apiKey };
        if (azureEndpoint) {
            params.azure_endpoint = azureEndpoint;
        }
        if (baseUrl) {
            params.base_url = baseUrl;
        }
        return apiRouter.execute({ method: 'update_embedding_provider' }, params);
    }

    public async setEmbeddingProviderModel<T>(name: string, model: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'set_embedding_provider_model' }, { name, model });
    }

    public async deleteEmbeddingProviderConfig<T>(name: string, username: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'delete_embedding_provider_config' }, { name, username });
    }

    public async getEmbeddingProviderApiKey<T>(name: string, showFull: boolean = false): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_embedding_provider_api_key' }, { name, show_full: showFull });
    }

    public async getDefaultEmbedding<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_default_embedding' });
    }

    // Rerank Management APIs
    public async getRerankProviders<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_rerank_providers' });
    }

    public async setDefaultRerank<T>(name: string, username: string, model?: string): Promise<APIResponse<T>> {
        const params: any = { name, username };
        if (model) {
            params.model = model;
        }
        return apiRouter.execute({ method: 'set_default_rerank' }, params);
    }

    public async updateRerankProvider<T>(name: string, apiKey: string, azureEndpoint?: string, baseUrl?: string): Promise<APIResponse<T>> {
        const params: any = { name, api_key: apiKey };
        if (azureEndpoint) {
            params.azure_endpoint = azureEndpoint;
        }
        if (baseUrl) {
            params.base_url = baseUrl;
        }
        return apiRouter.execute({ method: 'update_rerank_provider' }, params);
    }

    public async setRerankProviderModel<T>(name: string, model: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'set_rerank_provider_model' }, { name, model });
    }

    public async deleteRerankProviderConfig<T>(name: string, username: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'delete_rerank_provider_config' }, { name, username });
    }

    public async getRerankProviderApiKey<T>(name: string, showFull: boolean = false): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_rerank_provider_api_key' }, { name, show_full: showFull });
    }

    public async getDefaultRerank<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_default_rerank' });
    }

    public async getOllamaModels<T>(host: string, username?: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'settings.getOllamaModels' }, { host, username });
    }

    public async getRyoAISModels<T>(host: string, username?: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'settings.getRyoAISModels' }, { host, username });
    }

    public async runTest<T>(tests: TestConfig[]): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'run_tests' }, { tests });
    }

    // Some backends expect a single test payload instead of an array under {tests}
    public async runSingleTest<T>(test: { test_id: string; args?: Record<string, any> }): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'run_tests' }, test);
    }

    public async stopTest<T>(test_ids: string[]): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'stop_tests' }, { test_ids });
    }

    public async saveAgent<T>(username: string, agent: T[]): Promise<APIResponse<void>> {
        return apiRouter.execute(
      {
        method: 'save_agent',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.UPDATE_AGENTS,
          resultPath: 'updateAgents'
        }
      },
      {username, agent}
    );
    }

    public async deleteAgent<T>(username: string, agent_id: (string|number)[]): Promise<APIResponse<T>> {
        // Delete agents by id
        return apiRouter.execute(
      {
        method: 'delete_agent',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.REMOVE_AGENTS,
          resultPath: 'removeAgents'
        }
      },
      { username, input: agent_id }
    );
    }

    public async newAgent<T>(username: string, agent: T[]): Promise<APIResponse<void>> {
        // Create agents
        return apiRouter.execute(
      {
        method: 'new_agent',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.ADD_AGENTS,
          resultPath: 'addAgents'
        }
      },
      { username, input: agent }
    );
    }

    public async newTools<T>(username: string, tools: T[]): Promise<APIResponse<void>> {
        return apiRouter.execute(
      {
        method: 'new_tools',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.ADD_AGENT_TOOLS,
          resultPath: 'addAgentTools'
        }
      },
      {username, tools}
    );
    }

    public async deleteTools<T>(username: string, tools: T[]): Promise<APIResponse<void>> {
        return apiRouter.execute(
      {
        method: 'delete_tools',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.REMOVE_AGENT_TOOLS,
          resultPath: 'removeAgentTools'
        }
      },
      {username, tools}
    );
    }

    public async saveTools<T>(username: string, tools: T[]): Promise<APIResponse<void>> {
        return apiRouter.execute(
      {
        method: 'save_tools',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.UPDATE_AGENT_TOOLS,
          resultPath: 'updateAgentTools'
        }
      },
      {username, tools}
    );
    }

    public async saveAgentTask<T extends Record<string, any>>(username: string, agent_task_info: T): Promise<APIResponse<void>> {
        // Transform task info to match TaskUpdateInput GraphQL schema
        const toAwsJson = (value: any) => {
          if (value === undefined) return undefined;
          if (value === null) return null;
          return typeof value === 'string' ? value : JSON.stringify(value);
        };
        const taskInput = {
          id: agent_task_info.id,
          name: agent_task_info.name,
          description: agent_task_info.description,
          status: agent_task_info.status ?? 'pending',
          priority: agent_task_info.priority,
          task_type: agent_task_info.task_type ?? 'general',
          trigger_type: agent_task_info.trigger_type ?? agent_task_info.trigger ?? 'manual',
          org_id: agent_task_info.org_id,
          objectives: toAwsJson(agent_task_info.objectives),
          schedule: toAwsJson(agent_task_info.schedule),
          metadata: toAwsJson(agent_task_info.metadata),
          result: toAwsJson(agent_task_info.result),
        };
        return apiRouter.execute(
      {
        method: 'save_agent_task',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.UPDATE_AGENT_TASKS,
          resultPath: 'updateAgentTasks'
        }
      },
      { username, input: [taskInput] }
    );
    }

    public async newAgentTask<T extends Record<string, any>>(username: string, agent_task_info: T): Promise<APIResponse<void>> {
        // Transform task info to match TaskInput GraphQL schema
        const toAwsJson = (value: any) => {
          if (value === undefined) return undefined;
          if (value === null) return null;
          return typeof value === 'string' ? value : JSON.stringify(value);
        };
        const taskInput = {
          id: agent_task_info.id,
          name: agent_task_info.name,
          description: agent_task_info.description,
          status: agent_task_info.status ?? 'pending',
          priority: agent_task_info.priority,
          task_type: agent_task_info.task_type ?? 'general',
          trigger_type: agent_task_info.trigger_type ?? agent_task_info.trigger ?? 'manual',
          org_id: agent_task_info.org_id,
          objectives: toAwsJson(agent_task_info.objectives),
          schedule: toAwsJson(agent_task_info.schedule),
          metadata: toAwsJson(agent_task_info.metadata),
        };
        return apiRouter.execute(
      {
        method: 'new_agent_task',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.ADD_AGENT_TASKS,
          resultPath: 'addAgentTasks'
        }
      },
      { username, input: [taskInput] }
    );
    }

    public async deleteAgentTask(username: string, agent_task_id: string): Promise<APIResponse<void>> {
        return apiRouter.execute(
      {
        method: 'delete_agent_task',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.REMOVE_AGENT_TASKS,
          resultPath: 'removeAgentTasks'
        }
      },
      { username, input: [agent_task_id] }
    );
    }

    public async saveAgentSkill<T>(username: string, skill_info: T): Promise<APIResponse<void>> {
        // GraphQL mutation expects input: [SkillUpdateInput!]!
        // Note: owner is NOT in SkillUpdateInput schema - backend gets it from identity claims
        return apiRouter.execute(
      {
        method: 'save_agent_skill',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.UPDATE_AGENT_SKILLS,
          resultPath: 'updateAgentSkills'
        }
      },
      { input: [skill_info] }
    );
    }

    public async newAgentSkill<T>(username: string, skill_info: T): Promise<APIResponse<void>> {
        // GraphQL mutation expects input: [SkillInput!]!
        // Note: owner is NOT in SkillInput schema - backend gets it from identity claims
        return apiRouter.execute(
      {
        method: 'new_agent_skill',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.ADD_AGENT_SKILLS,
          resultPath: 'addAgentSkills'
        }
      },
      { input: [skill_info] }
    );
    }

    public async deleteAgentSkill(username: string, skill_id: string): Promise<APIResponse<void>> {
        // GraphQL mutation expects input: [ID!]!
        return apiRouter.execute(
      {
        method: 'delete_agent_skill',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.REMOVE_AGENT_SKILLS,
          resultPath: 'removeAgentSkills'
        }
      },
      { input: [skill_id] }
    );
    }

    public async runSkill<T>(username: string, skill: T): Promise<APIResponse<void>> {
        // skill must be JSON-stringified for AWSJSON type in GraphQL schema
        const skillJson = typeof skill === 'string' ? skill : JSON.stringify(skill);
        return apiRouter.execute(
      {
        method: 'run_skill',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.RUN_SKILL,
          resultPath: 'runSkill'
        }
      },
      { input: { username, skill: skillJson } }
    );
    }

    public async cancelRunSkill<T>(username: string, skill: T): Promise<APIResponse<void>> {
        const skillJson = typeof skill === 'string' ? skill : JSON.stringify(skill);
        return apiRouter.execute(
      {
        method: 'cancel_run_skill',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.CANCEL_RUN_SKILL,
          resultPath: 'cancelRunSkill'
        }
      },
      { input: { username, skill: skillJson } }
    );
    }

    public async pauseRunSkill<T>(username: string, skill: T): Promise<APIResponse<void>> {
        const skillJson = typeof skill === 'string' ? skill : JSON.stringify(skill);
        return apiRouter.execute(
      {
        method: 'pause_run_skill',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.PAUSE_RUN_SKILL,
          resultPath: 'pauseRunSkill'
        }
      },
      { input: { username, skill: skillJson } }
    );
    }

    public async resumeRunSkill<T>(username: string, skill: T): Promise<APIResponse<void>> {
        const skillJson = typeof skill === 'string' ? skill : JSON.stringify(skill);
        return apiRouter.execute(
      {
        method: 'resume_run_skill',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.RESUME_RUN_SKILL,
          resultPath: 'resumeRunSkill'
        }
      },
      { input: { username, skill: skillJson } }
    );
    }

    public async stepRunSkill<T>(username: string, skill: T): Promise<APIResponse<void>> {
        const skillJson = typeof skill === 'string' ? skill : JSON.stringify(skill);
        return apiRouter.execute(
      {
        method: 'step_run_skill',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.STEP_RUN_SKILL,
          resultPath: 'stepRunSkill'
        }
      },
      { input: { username, skill: skillJson } }
    );
    }

    public async setSkillBreakpoints<T>(username: string, node_name: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'set_skill_breakpoints',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.SET_SKILL_BREAKPOINTS,
          resultPath: 'setSkillBreakpoints'
        }
      },
      {username, node_name}
    );
    }

    public async clearSkillBreakpoints<T>(username: string, node_name: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'clear_skill_breakpoints',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.CLEAR_SKILL_BREAKPOINTS,
          resultPath: 'clearSkillBreakpoints'
        }
      },
      {username, node_name}
    );
    }

    public async requestSkillState<T>(username: string, skill: T): Promise<APIResponse<void>> {
        return apiRouter.execute(
      {
        method: 'request_skill_state',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.REQUEST_SKILL_STATE,
          resultPath: 'requestSkillState'
        }
      },
      {username, skill}
    );
    }

    public async injectSkillState<T>(username: string, skill: T): Promise<APIResponse<void>> {
        return apiRouter.execute(
      {
        method: 'inject_skill_state',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.INJECT_SKILL_STATE,
          resultPath: 'injectSkillState'
        }
      },
      {username, skill}
    );
    }

    public async loadSkillSchemas<T>(username: string, skill: T): Promise<APIResponse<void>> {
        return apiRouter.execute(
      {
        method: 'load_skill_schemas',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.LOAD_SKILL_SCHEMAS,
          resultPath: 'loadSkillSchemas'
        }
      },
      {username, skill}
    );
    }

    public async saveSettings<T>(value: T): Promise<APIResponse<void>> {
        return apiRouter.execute(
      {
        method: 'save_settings',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.UPDATE_AGENTS,
          resultPath: 'updateAgents'
        }
      },
      value
    );
    }

    public async newKnowledges<T>(values: T[]): Promise<APIResponse<void>> {
        return apiRouter.execute({ method: 'new_knowledges' }, values);
    }

    public async saveKnowledges<T>(values: T[]): Promise<APIResponse<void>> {
        return apiRouter.execute(
      {
        method: 'save_knowledges',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.UPDATE_AGENT_KNOWLEDGES,
          resultPath: 'updateAgentKnowledges'
        }
      },
      values
    );
    }

    public async deleteKnowledges<T>(values: T[]): Promise<APIResponse<void>> {
        return apiRouter.execute({ method: 'delete_knowledges' }, values);
    }

    public async getAvailableTests<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_available_tests' });
    }

    /**
     * Step-sim debug: cache sheets bundle and move to Start node on backend
     */
    public async setupSimStep<T>(bundle: any): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'setup_sim_step',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.SETUP_SIM_STEP,
          resultPath: 'setupSimStep'
        }
      },
      { bundle }
    );
    }

    /**
     * Step-sim debug: advance one node on backend
     */
    public async stepSim<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'step_sim',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.STEP_SIM,
          resultPath: 'stepSim'
        }
      }
    );
    }

    /**
     * Dev: trigger backend to run a small langgraph2flowgram export test
     */
    public async testLanggraph2Flowgram<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'test_langgraph2flowgram',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.TEST_LANGGRAPH2_FLOWGRAM,
          resultPath: 'testLanggraph2Flowgram'
        }
      }
    );
    }

    /**
     * Sim: trigger backend timer event
     */
    public async simTimerEvent<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'sim_timer_event',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.SIM_TIMER_EVENT,
          resultPath: 'simTimerEvent'
        }
      }
    );
    }

    /**
     * Sim: trigger backend websocket event
     */
    public async simWebsocketEvent<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'sim_websocket_event',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.SIM_WEBSOCKET_EVENT,
          resultPath: 'simWebsocketEvent'
        }
      }
    );
    }

    /**
     * Sim: trigger backend sse event
     */
    public async simSseEvent<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'sim_sse_event',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.SIM_SSE_EVENT,
          resultPath: 'simSseEvent'
        }
      }
    );
    }

    /**
     * Sim: trigger backend webhook event
     */
    public async simWebhookEvent<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'sim_webhook_event',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.SIM_WEBHOOK_EVENT,
          resultPath: 'simWebhookEvent'
        }
      }
    );
    }

    /**
     * Get可调用FunctionList
     * @param filter - Filter条件，OptionalInclude：
     *   - text: 文本Filter条件，会SearchFunction名、Description和Parameter
     *   - type: TypeFilter条件（'system' 或 'custom'）
     * @returns Promise 对象，Parse为可调用FunctionList
     */
    public async getCallables<T>(filter?: { text?: string; type?: 'system' | 'custom' }): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_callables' }, filter);
    }

    /**
     * Manage callable function (add/update/delete)
     * @param params - Raw parameters to be sent to IPC
     * @returns Promise<APIResponse<T>> - Standard API response with typed data
     */
    public async manageCallable<T>(params: any): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'manage_callable' }, params);
    }

    /**
     * Editor support: fetch agents for chat_node party selector
     */
    public async getEditorAgents<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_editor_agents' });
    }

    /**
     * Editor support: fetch queues/events for pend_input_node
     */
    public async getEditorPendingSources<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_editor_pending_sources' });
    }

    /**
     * Editor support: fetch NodeState JSON Schema for NodeStatePanel and forms
     */
    public async getNodeStateSchema<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'skill_editor.get_node_state_schema',
        graphql: {
          query: GRAPHQL_QUERIES.GET_NODE_STATE_SCHEMA,
          resultPath: 'getNodeStateSchema'
        }
      }
    );
    }

    /**
     * GetInitialize进度
     * @returns Promise 对象，Parse为Initialize进度Information
     */
    public async getInitializationProgress<T = {
        ui_ready: boolean;
        critical_services_ready: boolean;
        async_init_complete: boolean;
        fully_ready: boolean;
        sync_init_complete: boolean;
        message: string;
    }>(): Promise<APIResponse<T & {
        sync_init_complete: boolean;
        message: string;
    }>> {
        // Get username from localStorage for owner/userId
        const username = localStorage.getItem('username');
        const response = await apiRouter.execute<any>(
      {
        method: 'get_initialization_progress',
        graphql: {
          query: GRAPHQL_QUERIES.GET_ALL_MINE,
          resultPath: 'getAllMine'
        }
      },
      { owner: username, userId: username }
    );

        // Transform getAllMine response to initialization progress format
        // Respect the backend's actual progress values — do NOT override ui_ready/fully_ready.
        // The backend returns accurate progress (e.g., ui_ready: false when MainWindow isn't created).
        // Only set defaults for fields that are missing from the response.
        if (response.success && response.data) {
            const data = response.data;
            const initProgress = {
                ui_ready: data.ui_ready ?? false,
                critical_services_ready: data.critical_services_ready ?? false,
                async_init_complete: data.async_init_complete ?? false,
                fully_ready: data.fully_ready ?? false,
                sync_init_complete: data.sync_init_complete ?? false,
                message: data.message ?? 'Checking initialization...',
                ...data,  // Preserve any extra fields from backend
            };
            return {
                success: true,
                data: initProgress as any
            };
        }

        return response;
    }

    /**
     * Save skill editor cache to Python backend
     * @param cacheData - Cache data to save
     * @returns Promise with save result
     */
    public async saveEditorCache<T>(cacheData: any): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'save_editor_cache',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.SAVE_EDITOR_CACHE,
          resultPath: 'saveEditorCache'
        }
      },
      { cacheData }
    );
    }

    /**
     * Load skill editor cache from Python backend
     * @returns Promise with cache data
     */
    public async loadEditorCache<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'load_editor_cache',
        graphql: {
          query: GRAPHQL_QUERIES.GET_EDITOR_CACHE,
          resultPath: 'getEditorCache'
        }
      }
    );
    }

    /**
     * Clear skill editor cache from Python backend
     * @returns Promise with clear result
     */
    public async clearEditorCache<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'clear_editor_cache',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.CLEAR_EDITOR_CACHE,
          resultPath: 'clearEditorCache'
        }
      }
    );
    }

    // Org Management APIs - New simplified names
    public async getOrgs<T>(username: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'get_orgs',
        graphql: {
          query: GRAPHQL_QUERIES.QUERY_ORGS,
          resultPath: 'queryOrgs'
        }
      },
      { username }
    );
    }

    public async createOrg<T>(username: string, name: string, description?: string, parent_id?: string, org_type?: string): Promise<APIResponse<T>> {
        const input = [{
            name,
            description,
            parent_id,
            org_type: org_type || 'department'
        }];
        return apiRouter.execute(
            {
                method: 'create_org',
                graphql: {
                    mutation: GRAPHQL_MUTATIONS.ADD_ORGS,
                    resultPath: 'addOrgs'
                }
            },
            { input }
        );
    }

    public async updateOrg<T>(username: string, org_id: string, name?: string, description?: string, parent_id?: string | null): Promise<APIResponse<T>> {
        const input = [{
            id: org_id,
            name,
            description,
            parent_id
        }];
        return apiRouter.execute(
            {
                method: 'update_org',
                graphql: {
                    mutation: GRAPHQL_MUTATIONS.UPDATE_ORGS,
                    resultPath: 'updateOrgs'
                }
            },
            { input }
        );
    }

    public async deleteOrg<T>(username: string, org_id: string, force: boolean = false): Promise<APIResponse<T>> {
        return apiRouter.execute(
            {
                method: 'delete_org',
                graphql: {
                    mutation: GRAPHQL_MUTATIONS.REMOVE_ORGS,
                    resultPath: 'removeOrgs'
                }
            },
            { input: [org_id] }
        );
    }

    public async getOrgAgents<T>(username: string, org_id: string, include_descendants?: boolean): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_org_agents' }, { username, organization_id: org_id, include_descendants });
    }

    public async bindAgentToOrg<T>(username: string, agent_id: string, org_id: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'bind_agent_to_org' }, { username, agent_id, organization_id: org_id });
    }

    public async unbindAgentFromOrg<T>(username: string, agent_id: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'unbind_agent_from_org' }, { username, agent_id });
    }

    public async getAvailableAgentsForBinding<T>(username: string, org_id: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_available_agents_for_binding' }, { username, organization_id: org_id });
    }

    // Browser Use Settings APIs
    public async getBrowserUseSettings<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_browser_use_settings' });
    }

    public async saveBrowserUseSettings<T>(settings: any): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'save_browser_use_settings' }, { settings });
    }

}

/**
 * Create IPC API 实例
 * @returns IPC API 实例
 */
export function createIPCAPI(): IPCAPI {
    return IPCAPI.getInstance();
} 
/**
 * Singleton IPC API instance for convenient imports
 */
export const ipcApi = IPCAPI.getInstance();
