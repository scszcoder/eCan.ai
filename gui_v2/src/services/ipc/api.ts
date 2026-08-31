/**
 * IPC API
 * 提供与 Python Backend通信的Advanced API
 */
import { logger } from '../../utils/logger';
import { createChatApi } from './chatApi';
import { createLightRAGApi } from './lightragApi';
import { logoutManager } from '../LogoutManager';
import { ipcClient } from './ipcClient';
import { apiRouter } from '../api/api-router';
import { GRAPHQL_QUERIES, GRAPHQL_MUTATIONS } from '../api/api-config';
import { useUserStore } from '../../stores/userStore';
import { detectPlatform } from '../../config/platform';
import { getCachedAppConfig } from '../../contexts/AppConfigContext';

const getLoginRedirectUrl = (): string => {
    if (window.location.protocol === 'file:') {
        return `${window.location.href.split('#')[0]}#/login`;
    }
    return `${window.location.origin}/#/login`;
};

const shouldHandleDesktopAuthLossSilently = (errorCode: string, storageManager: any): boolean => {
    try {
        if (detectPlatform() !== 'desktop') return false;
        if (errorCode === 'TOKEN_REQUIRED') return true;
        if (storageManager?.wasDesktopColdStartTokenCleared?.()) return true;
        return !storageManager?.getToken?.();
    } catch {
        return false;
    }
};

const isConfirmedSessionReplacement = (details?: unknown): boolean => {
    try {
        const value = details && typeof details === 'object' && 'details' in details
            ? (details as any).details
            : details;
        return !!(
            value &&
            typeof value === 'object' &&
            ((value as any).reason === 'session_replaced' || (value as any).session_replaced === true)
        );
    } catch {
        return false;
    }
};

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

export interface DeleteAgentSkillResult {
    message?: string;
    skill_id?: string;
    db_deleted?: boolean;
    mem_deleted?: boolean;
    file_deleted?: boolean;
    cloud_deleted?: boolean;
    cloud_cached?: boolean;
    cloud_error?: string | null;
    cloud_task_id?: string | null;
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

    // Cached settings data from getSettings (includes providers)
    private _settingsData: any = null;
    private _settingsUsername: string | null = null;
    private _settingsPromise: Promise<any> | null = null;

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
        return apiRouter.windowToggleFullscreen();
    }

    /**
     * Get window fullscreen state
     */
    public async windowGetFullscreenState(): Promise<boolean> {
        await this.ensureInitialized();
        return apiRouter.windowGetFullscreenState();
    }

    private async ensureInitialized(): Promise<void> {
        // ipcClient 现在只是兼容层，已经在构造函数中初始化
        // 所有请求都通过 apiRouter 处理，无需额外初始化检查
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
        try {
            // All requests now use HTTP GraphQL via apiRouter
            await this.ensureInitialized();

            // Use apiRouter.execute() for all requests
            const response = await apiRouter.execute<T>(
                { method },
                params,
                { timeout }
            );

            console.log('[IPCAPI] executeRequest:response', method, { response, durationMs: Date.now() - startTs });
            
            // apiRouter.execute already returns APIResponse<T> format
            // Handle error cases for token validation
            if (!response.success && response.error) {
                const errorCode = String(response.error.code || 'UNKNOWN_ERROR');
                
                // Handle INVALID_TOKEN error by clearing stored token and redirecting to login
                if (errorCode === 'INVALID_TOKEN' || errorCode === 'TOKEN_REQUIRED') {
                    logger.warn(`[IPCAPI] Authentication failed for ${method}: ${errorCode}`);
                    
                    // During the post-login grace period the backend (MainWindow) may still
                    // be initializing.  Suppress the aggressive token-clear + redirect so the
                    // IPC retry loop can handle transient failures instead of bouncing the
                    // user back to the login page (the "double login" bug).
                    try {
                        const { userStorageManager } = await import('../storage/UserStorageManager');
                        
                        if (userStorageManager.isInPostLoginGracePeriod()) {
                            logger.info(`[IPCAPI] Within post-login grace period, suppressing redirect for ${method}: ${errorCode}`);
                            // Fall through — return the error to the caller without clearing
                            // the token or redirecting.  The caller / retry loop will handle it.
                        } else if (shouldHandleDesktopAuthLossSilently(errorCode, userStorageManager)) {
                            userStorageManager.removeToken();
                            sessionStorage.removeItem('token_expired_notification_shown');
                            logger.info(`[IPCAPI] Silently handling desktop auth bootstrap loss for ${method}: ${errorCode}`);
                            if (window.location.hash !== '#/login') {
                                setTimeout(() => {
                                    window.location.replace(getLoginRedirectUrl());
                                }, 100);
                            }
                            return {
                                success: true,
                                data: null as any
                            };
                        } else {
                            userStorageManager.removeToken();
                            logger.info('[IPCAPI] Cleared invalid token from storage');
                            const tokenDetails = response.error?.details;
                            const messageKey = isConfirmedSessionReplacement(tokenDetails)
                                ? 'auth.sessionInvalidated'
                                : 'auth.sessionExpired';

                            // Reset InitializationProgressManager singleton state so the login page
                            // does not inherit a stale fully_ready=true from the previous session
                            try {
                                const { forceCleanupInitializationProgress } = await import('../../hooks/useInitializationProgress');
                                forceCleanupInitializationProgress();
                                logger.info('[IPCAPI] Cleared stale initialization progress state due to invalid token');
                            } catch { /* ignore */ }
                            
                            // Show user notification (only once)
                            if (!sessionStorage.getItem('token_expired_notification_shown')) {
                                sessionStorage.setItem('token_expired_notification_shown', 'true');
                                
                                // Try to show Ant Design message if available
                                try {
                                    const { message } = await import('antd');
                                    // Get i18n translation
                                    const i18nModule = await import('@/i18n');
                                    const i18n = i18nModule.default;
                                    const messageText = i18n.t(messageKey);
                                    
                                    message.warning({
                                        content: messageText,
                                        duration: 5,
                                        key: 'session-invalidated'
                                    });
                                } catch (error) {
                                    // Fallback to console if Ant Design or i18n not available
                                    console.warn(isConfirmedSessionReplacement(tokenDetails)
                                        ? 'Session invalidated. You may have logged in from another device. Please log in again.'
                                        : 'Session expired. Please log in again.');
                                }
                            }
                            
                            // Redirect to login page if not already there
                            if (window.location.hash !== '#/login') {
                                logger.info('[IPCAPI] Redirecting to login due to invalid token');
                                // Force full page reload to login to ensure React Router responds
                                setTimeout(() => {
                                    window.location.replace(getLoginRedirectUrl());
                                }, 500);
                            }
                            
                            // Return empty success response to prevent error display in UI
                            return {
                                success: true,
                                data: null as any
                            };
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
            
            // Return the response (success case)
            return response;
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

    // ==================== CloudBase (CN) ====================
    // Frontend HTTP /api/cloudbase/login has never been registered; route every
    // CloudBase call through IPC to the cloudbase_handler module so it talks
    // to Tencent Cloud and not AWS Cognito.
    public async cloudbaseLogin<T>(email: string, password: string, role?: string, lang?: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'cloudbase_login' }, { email, password, role: role || 'Commander', lang });
    }

    public async cloudbasePhoneLogin<T>(phone: string, code: string, role?: string, lang?: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'cloudbase_phone_login' }, { phone, code, role: role || 'Commander', lang });
    }

    public async cloudbaseSendCode<T>(phone: string, purpose: string = 'login'): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'cloudbase_send_code' }, { phone, purpose });
    }

    public async cloudbaseSignup<T>(email: string, password: string, lang?: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'cloudbase_signup' }, { email, password, lang });
    }

    public async cloudbaseSignupConfirm<T>(email: string, code: string, verificationId: string, password: string, lang?: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'cloudbase_signup_confirm' }, { email, code, verification_id: verificationId, password, lang });
    }

    public async cloudbaseGetUserInfo<T>(refreshToken: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'cloudbase_get_user_info' }, { refresh_token: refreshToken });
    }

    public async cloudbaseLogout<T>(token: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'cloudbase_logout' }, { token });
    }

    public async cloudbaseRefreshToken<T>(refreshToken: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'cloudbase_refresh_token' }, { refresh_token: refreshToken });
    }

    public async cloudbaseFinalizeSession<T>(params: {
        access_token: string;
        refresh_token?: string;
        expires_in?: number;
        user_identifier: string;
        user_info?: Record<string, any>;
        role?: string;
        lang?: string;
    }): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'cloudbase_finalize_session' }, params);
    }

    public async cloudbaseCheckConfig<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'cloudbase_check_config' }, {});
    }

    public async getLastLoginInfo<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_last_login' });
    }

    public async saveLoginInfo<T>(username: string, password: string, role: string, language?: string, loginType?: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'save_login_info' }, { username, password, role, language, login_type: loginType });
    }

    public async clearLoginInfo<T>(username: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'clear_login_info' }, { username });
    }

    public async getHostname<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_hostname' });
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

    /**
     * Force-terminate the process holding the Google OAuth callback port
     * (default 9382). Backend only kills processes whose executable name
     * matches our own (eCan.exe) — refuses otherwise. Used by the Login
     * page's recovery flow when google_login returns
     * ``error_kind=port_occupied``.
     */
    public async forceCloseOauthPortBlocker<T = any>(port?: number): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'force_close_oauth_port_blocker' },
            port ? { port } : {},
        );
    }

    public async loginWithApple<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'login_with_apple' });
    }

    public async clearAuthCache<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'clear_auth_cache' });
    }

    /**
     * Get token information
     * @param token - JWT token
     * @returns Token information including expiration, username, etc.
     */
    public async getTokenInfo(token: string): Promise<APIResponse<any>> {
        return apiRouter.execute({ method: 'auth.getTokenInfo' }, { token });
    }

    /**
     * Refresh authentication token
     * @param token - Current JWT token
     * @returns New token information
     */
    public async refreshToken(token: string): Promise<APIResponse<{ token: string }>> {
        return apiRouter.execute({ method: 'auth.refreshToken' }, { token });
    }

    /**
     * Extend token validity period
     * @param token - Current JWT token
     * @param seconds - Number of seconds to extend (optional)
     * @returns Extended token information
     */
    public async extendToken(token: string, seconds?: number): Promise<APIResponse<any>> {
        return apiRouter.execute({ method: 'auth.extendToken' }, { token, seconds });
    }

    /**
     * Get current authentication token
     * @returns Current authentication token
     */
    public async getAuthToken(): Promise<APIResponse<string>> {
        return apiRouter.execute({ method: 'get_auth_token' }, {});
    }

    public async getAll<T>(username: string): Promise<APIResponse<T>> {
        const response = await apiRouter.execute<T>(
      {
        method: 'get_all',
        graphql: {
          query: GRAPHQL_QUERIES.GET_ALL_MINE,
          resultPath: 'getAllMine'
        }
      },
      { owner: username, userId: username }
    );

        // Cache settings from getAllMine response so provider methods work
        // without requiring a separate getSettings call
        if (response.success && response.data) {
            const data = response.data as any;
            if (data.settings && !this._settingsData) {
                // settings from getAllMine may be a JSON string
                let parsed = data.settings;
                if (typeof parsed === 'string') {
                    try { parsed = JSON.parse(parsed); } catch (_e) { /* keep as-is */ }
                }
                this._settingsData = parsed;
                this._settingsUsername = username;
                console.log('[IPCAPI] _settingsData cached from getAllMine, keys:', Object.keys(parsed));
            }
        }
        return response;
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

        const isCloudBase = getCachedAppConfig()?.auth_type === 'cloudbase';
        const params = isCloudBase
            ? {}
            : company ? { username, company } : { username };
        const response = await apiRouter.execute<any>(
      {
        method: 'get_all_org_agents',
        graphql: {
          query: isCloudBase
              ? GRAPHQL_QUERIES.GET_ORG_AGENT_TREE_CLOUDBASE
              : GRAPHQL_QUERIES.GET_ORG_AGENT_TREE,
          resultPath: 'getOrgAgentTree'
        }
      },
      params
    );
        
        // Wrap the tree response in {orgs: ...} format expected by the store.
        // CloudBase returns null when a new account has not created an organization yet.
        if (response.success) {
          // If data is already wrapped with orgs, use as-is; otherwise wrap it.
          const wrappedData = response.data?.orgs ? response.data : { orgs: response.data ?? null };
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
      // For local IPC: pass agent_id so backend can query specific agents with relations (skills/tasks)
      // For GraphQL: GET_ALL_MINE only declares $owner and $userId, agent_id is ignored by AppSync
      { username, agent_id }
    );
    }

    public async getAgentSkills<T>(username: string,skill_ids: string[]): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'get_agent_skills',
        graphql: {
          query: GRAPHQL_QUERIES.GET_AGENT_SKILLS,
          resultPath: 'queryAgentSkills'
        }
      },
      // CloudBase derives ownership from the authenticated bearer. `skill_ids`
      // is retained for the desktop IPC signature but is not a GraphQL filter.
      { input: {} }
    );
    }

    public async getPublicSkills<T>(username: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'get_public_skills',
        graphql: {
          query: GRAPHQL_QUERIES.GET_PUBLIC_SKILLS,
          resultPath: 'queryAgentSkills'
        }
      },
      { input: { isPublic: true } }
    );
    }

    public async getSubscribedSkillIds<T>(username: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'get_subscribed_skill_ids',
        graphql: {
          query: GRAPHQL_QUERIES.GET_SUBSCRIBED_SKILL_IDS,
          resultPath: 'getSubscribedSkillIds'
        }
      },
      { owner: username }
    );
    }

    public async getSkillVersions<T>(skillId: string, limit = 10): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'get_skill_versions' },
            { skillId, limit }
        );
    }

    public async restoreSkillVersion<T>(skillId: string, versionId: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'restore_skill_version' },
            { skillId, versionId }
        );
    }

    public async upsertSkillReview<T>(skillId: string, reviewerId: string, rating: number, reviewText?: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'upsert_skill_review' },
            { skillId, reviewerId, rating, reviewText: reviewText || '' }
        );
    }

    public async getSkillReviews<T>(skillId: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'get_skill_reviews' },
            { skillId }
        );
    }

    public async deleteSkillReview<T>(reviewId: string, reviewerId: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'delete_skill_review' },
            { reviewId, reviewerId }
        );
    }

    public async getSkillAnalytics<T>(username: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'get_skill_analytics' },
            { username }
        );
    }

    public async subscribeToSkill<T>(username: string, skillId: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'subscribe_to_skill',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.SUBSCRIBE_TO_SKILL,
          resultPath: 'subscribeToSkill'
        }
      },
      { skillId, owner: username }
    );
    }

    public async unsubscribeFromSkill<T>(username: string, skillId: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'unsubscribe_from_skill',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.UNSUBSCRIBE_FROM_SKILL,
          resultPath: 'unsubscribeFromSkill'
        }
      },
      { skillId, owner: username }
    );
    }

    public async incrementSkillDownload<T>(skillId: string, delta: number = 1): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'increment_skill_download' },
            { skillId, delta }
        );
    }

    public async getSkillMarketplaceStats<T>(skillId: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'get_skill_marketplace_stats' },
            { skillId }
        );
    }

    public async getSkillChangelog<T>(skillId: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'get_skill_changelog' },
            { skillId }
        );
    }

    public async appendSkillChangelog<T>(skillId: string, version: string, notes: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'append_skill_changelog' },
            { skillId, version, notes }
        );
    }

    public async recordSkillUsage<T>(skillId: string, userId: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'record_skill_usage' },
            { skillId, userId }
        );
    }

    public async getUserSkillProficiency<T>(userId: string, skillId: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'get_user_skill_proficiency' },
            { userId, skillId }
        );
    }

    public async updateUserSkillProficiency<T>(userId: string, skillId: string, score: number, level: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'update_user_skill_proficiency' },
            { userId, skillId, score, level }
        );
    }

    public async toggleSkillFavorite<T>(userId: string, skillId: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'toggle_skill_favorite' },
            { userId, skillId }
        );
    }

    public async listFavoriteSkills<T>(userId: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'list_favorite_skills' },
            { userId }
        );
    }

    public async reportSkill<T>(skillId: string, reporterId: string, reason: string, note: string = ''): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'report_skill' },
            { skillId, reporterId, reason, note }
        );
    }

    public async listSimilarSkills<T>(skillId: string, limit: number = 6): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'list_similar_skills' },
            { skillId, limit }
        );
    }

    public async listSkillsByOwner<T>(owner: string, excludeId: string = '', limit: number = 8): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'list_skills_by_owner' },
            { owner, excludeId, limit }
        );
    }

    public async incrementReviewHelpful<T>(reviewId: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'increment_review_helpful' },
            { reviewId }
        );
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
      // Pass username so the local IPC handler can resolve the owner.
      // The GraphQL query declares no variables, but AppSync ignores extra
      // variables and the local server reads them from the request params.
      { owner: username, userId: username }
    );
    }

    public async getPrompts<T>(username: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
      {
        method: 'get_prompts',
        graphql: {
          query: GRAPHQL_QUERIES.GET_PROMPTS,
          resultPath: 'getPrompts'
        }
      },
      { owner: username }
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

    /**
     * Send one turn to the prompt-editor chat agent.
     *
     * The backend runs a small LangGraph (single LLM node, gpt-5.5 by
     * default, otherwise the user's configured default LLM) and returns:
     *   - `assistant_message`: short reply to show in the chat thread
     *   - `proposed_md_content`: revised prompt body for the diff/Apply card
     *   - `raw_llm_output`: verbatim model output, for debugging
     *   - `model`: { provider_id, model_name } actually used
     *
     * History is the recent conversation (caller decides cap; backend also
     * caps to 30 turns).  current_md_content is the prompt body the
     * editor currently shows so the agent can propose a focused diff.
     */
    public async promptAgentChat<T = any>(params: {
      prompt_id: string;
      user_message: string;
      current_md_content: string;
      history?: Array<{ role: 'user' | 'assistant'; content: string }>;
      provider_id?: string;
      model_name?: string;
    }): Promise<APIResponse<T>> {
        // Reasoning models (gpt-5.5 etc.) routinely take 30-90s for a single
        // turn. The default 30s timeout aborts the fetch even though the
        // backend completes successfully — surfaced as
        // "signal is aborted without reason". 3 minutes gives comfortable
        // headroom; the backend has no upper bound on its end.
        return apiRouter.execute(
          { method: 'prompt_agent_chat' },
          params,
          { timeout: 180_000 }
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
      // IMPORTANT: GRAPHQL_QUERIES.GET_ALL_MINE only declares $owner and $userId.
      // Do not pass extra variables like tool_ids, otherwise AppSync will reject the request.
      { owner: username, userId: username }
    );
    }

    // Avatar API methods (web: GraphQL → queryAvatarResources / addAvatarResources / removeAvatarResources)
    public async getSystemAvatars<T>(username: string): Promise<APIResponse<T>> {
        const response = await apiRouter.execute<any>(
          {
            method: 'avatar.get_system_avatars',
            graphql: {
              query: GRAPHQL_QUERIES.QUERY_AVATAR_RESOURCES,
              resultPath: 'queryAvatars'
            }
          },
          { username }
        );
        return this._transformAvatarResponse<T>(response, 'system');
    }

    public async getUploadedAvatars<T>(username: string): Promise<APIResponse<T>> {
        const response = await apiRouter.execute<any>(
          {
            method: 'avatar.get_uploaded_avatars',
            graphql: {
              query: GRAPHQL_QUERIES.QUERY_AVATAR_RESOURCES,
              resultPath: 'queryAvatars'
            }
          },
          { username }
        );
        return this._transformAvatarResponse<T>(response, 'uploaded');
    }

    public async uploadAvatar<T>(username: string, fileData: string, filename: string): Promise<APIResponse<T>> {
        const response = await apiRouter.execute<any>(
          {
            method: 'avatar.upload_avatar',
            graphql: {
              mutation: GRAPHQL_MUTATIONS.ADD_AVATAR_RESOURCES,
              resultPath: 'addAvatars'
            }
          },
          { username, fileData, filename }
        );
        // After creating the DB record, upload the actual file to S3 via presigned URL
        if (response.success && response.data) {
            const results = typeof response.data === 'string' ? JSON.parse(response.data) : response.data;
            const created = Array.isArray(results) ? results[0] : results;
            if (created?.image_upload_url) {
                try {
                    // Decode base64 to binary and upload via presigned URL
                    const binaryData = Uint8Array.from(atob(fileData), c => c.charCodeAt(0));
                    const ext = filename.split('.').pop()?.toLowerCase() || 'png';
                    const mimeTypes: Record<string, string> = {
                        png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg',
                        gif: 'image/gif', webp: 'image/webp', webm: 'video/webm',
                        mp4: 'video/mp4', mov: 'video/quicktime'
                    };
                    await fetch(created.image_upload_url, {
                        method: 'PUT',
                        body: binaryData,
                        headers: { 'Content-Type': mimeTypes[ext] || 'application/octet-stream' }
                    });
                    console.log('[IPCAPI] Avatar file uploaded to S3 via presigned URL');
                } catch (uploadErr) {
                    console.error('[IPCAPI] Failed to upload avatar file to S3:', uploadErr);
                }
            }
            return { success: true, data: created as T };
        }
        return response as APIResponse<T>;
    }

    public async deleteUploadedAvatar<T>(username: string, avatarId: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
          {
            method: 'avatar.delete_uploaded_avatar',
            graphql: {
              mutation: GRAPHQL_MUTATIONS.REMOVE_AVATAR_RESOURCES,
              resultPath: 'removeAvatars'
            }
          },
          { username, avatarId }
        );
    }

    /**
     * Transform raw DB avatar records to frontend AvatarData format.
     * Handles AWSJSON (may be string) and maps DB fields → AvatarData.
     * Uses presigned_image_url / presigned_video_url generated server-side.
     */
    private _transformAvatarResponse<T>(response: APIResponse<any>, type: 'system' | 'uploaded'): APIResponse<T> {
        if (!response.success) return response as APIResponse<T>;
        let rows = response.data;
        if (typeof rows === 'string') {
            try { rows = JSON.parse(rows); } catch { return { success: true, data: [] as any }; }
        }
        if (!Array.isArray(rows)) return { success: true, data: [] as any };
        
        console.log('[IPCAPI] _transformAvatarResponse raw data:', rows);
        
        const avatars = rows.map((r: any) => {
            // Use presigned URLs from lambda (private bucket); fall back to cloud_*_url or local paths
            const imageUrl = r.presigned_image_url || r.cloud_image_url || r.imageUrl || r.image_url || '';
            const videoUrl = r.presigned_video_url || r.cloud_video_url || r.videoUrl || r.video_url || '';
            
            return {
                type: r.is_public ? 'system' : type,
                id: r.id,
                name: r.name || undefined,
                hash: r.image_hash || undefined,
                imageUrl,
                videoUrl: videoUrl || undefined,
                thumbnailUrl: imageUrl || undefined,
                imageExists: !!imageUrl,
                videoExists: !!videoUrl,
            };
        });
        return { success: true, data: avatars as T };
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
        this._settingsUsername = username;

        const doFetch = async (): Promise<APIResponse<T>> => {
            const response = await apiRouter.execute<T>({
                method: 'get_settings',
                graphql: {
                    query: GRAPHQL_QUERIES.GET_SETTINGS,
                    resultPath: 'getSettings'
                }
            }, { username });

            // AWSJSON comes back as a JSON string — parse it into an object
            if (response.success && typeof response.data === 'string') {
                try {
                    response.data = JSON.parse(response.data) as T;
                } catch (_e) {
                    // already parsed or not JSON
                }
            }

            // Cache the full settings response (includes providers)
            if (response.success && response.data) {
                this._settingsData = response.data;
                console.log('[IPCAPI] _settingsData cached, keys:', Object.keys(response.data));
                console.log('[IPCAPI] _settingsData.llm_providers?', typeof (response.data as any)?.llm_providers, !!(response.data as any)?.llm_providers);
            }
            return response;
        };

        // Deduplicate concurrent calls
        if (!this._settingsPromise) {
            this._settingsPromise = doFetch().finally(() => { this._settingsPromise = null; });
        }
        return this._settingsPromise;
    }

    /**
     * Ensure settings are loaded (for provider methods that depend on cache)
     */
    private async _ensureSettingsLoaded(): Promise<void> {
        if (this._settingsData) return;
        if (this._settingsPromise) {
            await this._settingsPromise;
            return;
        }
        // Try to get username from user store if not already set
        if (!this._settingsUsername) {
            const storeUsername = useUserStore.getState().username;
            if (storeUsername) {
                this._settingsUsername = storeUsername;
                console.log('[IPCAPI] _ensureSettingsLoaded: got username from userStore:', storeUsername);
            }
        }
        // Fetch settings if we have a username
        if (this._settingsUsername) {
            await this.getSettings(this._settingsUsername);
        }
    }

    /**
     * Extract provider array from cached settings data
     */
    private _extractProviders(key: string): any[] | null {
        const raw = this._settingsData?.[key];
        if (!raw) return null;
        const providersDict = raw.providers || raw;
        let arr: any[];
        if (typeof providersDict === 'object' && !Array.isArray(providersDict)) {
            arr = Object.values(providersDict);
        } else if (Array.isArray(providersDict)) {
            arr = providersDict;
        } else {
            return null;
        }
        // Derive api_key_configured from api_key presence (cloud/DynamoDB mode
        // doesn't store this flag — compute it on the fly)
        return arr.map((p: any) => ({
            ...p,
            api_key_configured: p.api_key_configured ?? (!!p.api_key && p.api_key.length > 0),
        }));
    }

    public async updateUserPreferences<T>(language?: string, theme?: string): Promise<APIResponse<T>> {
        const params: any = {};
        if (language) params.language = language;
        if (theme) params.theme = theme;
        return apiRouter.execute({ method: 'update_user_preferences' }, params);
    }

    // LLM Management APIs
    public async getLLMProviders<T>(username?: string): Promise<APIResponse<T>> {
        // Ensure settings are loaded (providers come from DynamoDB settings)
        await this._ensureSettingsLoaded();
        console.log('[IPCAPI] getLLMProviders: _settingsData keys=', this._settingsData ? Object.keys(this._settingsData) : 'NULL');
        console.log('[IPCAPI] getLLMProviders: _settingsUsername=', this._settingsUsername);
        const providers = this._extractProviders('llm_providers');
        console.log('[IPCAPI] getLLMProviders: extracted providers=', providers);
        if (providers) {
            return { success: true, data: { providers } as T };
        }
        // In desktop mode, _settingsData doesn't contain llm_providers (they come from Python backend)
        // This is expected behavior, not an error condition
        if (this._settingsUsername) {
            console.debug('[IPCAPI] getLLMProviders: cache miss, using IPC for desktop mode');
        }
        // Pass username so the backend reads ryoais_models.json / ollama_models.json from the
        // same path that fetchRyoAISModels / fetchOllamaModels wrote to.
        const params: any = {};
        if (username) params.username = username;
        return apiRouter.execute({ method: 'get_llm_providers' }, params);
    }

    public async setDefaultLLM<T>(name: string, username: string, model?: string): Promise<APIResponse<T>> {
        // Persist default LLM to DynamoDB settings
        await this._ensureSettingsLoaded();
        if (this._settingsData && this._settingsUsername) {
            const settings = this._settingsData.settings
                ? JSON.parse(JSON.stringify(this._settingsData.settings))
                : {};
            settings.default_llm = name;
            if (model) settings.default_llm_model = model;
            const savePayload = {
                username: this._settingsUsername,
                settings,
                llm_providers: this._settingsData.llm_providers || {},
                embedding_providers: this._settingsData.embedding_providers || {},
                rerank_providers: this._settingsData.rerank_providers || {},
            };
            const saveResponse = await this.saveSettings(savePayload);
            if (saveResponse.success) {
                this._settingsData = null;
                return { success: true, data: { message: `Default LLM set to ${name}` } as unknown as T };
            }
            return { success: false, error: { message: 'Failed to save default LLM setting' } } as APIResponse<T>;
        }
        const params: any = { name, username };
        if (model) {
            params.model = model;
        }
        return apiRouter.execute({ method: 'set_default_llm' }, params);
    }

    public async updateLLMProvider<T>(name: string, apiKey: string, azureEndpoint?: string, awsAccessKeyId?: string, awsSecretAccessKey?: string, baseUrl?: string): Promise<APIResponse<T>> {
        // Try to persist via DynamoDB settings (needed in web/cloud mode where
        // 'update_llm_provider' has no GraphQL resolver and goes nowhere)
        await this._ensureSettingsLoaded();
        if (this._settingsData && this._settingsUsername) {
            const llmProviders = this._settingsData.llm_providers
                ? JSON.parse(JSON.stringify(this._settingsData.llm_providers))
                : {};
            const providersDict = llmProviders.providers || llmProviders;

            // Find and update the matching provider entry
            let found = false;
            for (const key of Object.keys(providersDict)) {
                const p = providersDict[key];
                if (p && (p.provider === name || p.name === name || key === name)) {
                    p.api_key = apiKey;
                    p.api_key_configured = !!apiKey && apiKey.length > 0;
                    if (azureEndpoint !== undefined) p.azure_endpoint = azureEndpoint;
                    if (awsAccessKeyId !== undefined) p.aws_access_key_id = awsAccessKeyId;
                    if (awsSecretAccessKey !== undefined) p.aws_secret_access_key = awsSecretAccessKey;
                    if (baseUrl !== undefined) p.base_url = baseUrl;
                    found = true;
                    break;
                }
            }

            if (found) {
                // Save full settings back to DynamoDB
                const savePayload = {
                    username: this._settingsUsername,
                    settings: this._settingsData.settings || {},
                    llm_providers: llmProviders,
                    embedding_providers: this._settingsData.embedding_providers || {},
                    rerank_providers: this._settingsData.rerank_providers || {},
                };

                const saveResponse = await this.saveSettings(savePayload);
                if (saveResponse.success) {
                    // Invalidate cache so next load picks up fresh data
                    this._settingsData = null;
                    return { success: true, data: { message: `Provider ${name} updated successfully` } as unknown as T };
                }
                return { success: false, error: { message: 'Failed to save provider settings' } } as APIResponse<T>;
            }
        }

        // Fallback to original IPC/local backend path
        const params: any = { name, api_key: apiKey };
        if (azureEndpoint !== undefined) {
            params.azure_endpoint = azureEndpoint;
        }
        if (awsAccessKeyId !== undefined) {
            params.aws_access_key_id = awsAccessKeyId;
        }
        if (awsSecretAccessKey !== undefined) {
            params.aws_secret_access_key = awsSecretAccessKey;
        }
        if (baseUrl !== undefined) {
            params.base_url = baseUrl;
        }
        return apiRouter.execute({ method: 'update_llm_provider' }, params);
    }

    public async setLLMProviderModel<T>(name: string, model: string): Promise<APIResponse<T>> {
        // Persist model selection to DynamoDB (web mode has no GraphQL resolver for this)
        await this._ensureSettingsLoaded();
        if (this._settingsData && this._settingsUsername) {
            const llmProviders = this._settingsData.llm_providers
                ? JSON.parse(JSON.stringify(this._settingsData.llm_providers))
                : {};
            const providersDict = llmProviders.providers || llmProviders;
            let found = false;
            for (const key of Object.keys(providersDict)) {
                const p = providersDict[key];
                if (p && (p.provider === name || p.name === name || key === name)) {
                    p.default_model = model;
                    p.preferred_model = model;
                    found = true;
                    break;
                }
            }
            if (found) {
                const savePayload = {
                    username: this._settingsUsername,
                    settings: this._settingsData.settings || {},
                    llm_providers: llmProviders,
                    embedding_providers: this._settingsData.embedding_providers || {},
                    rerank_providers: this._settingsData.rerank_providers || {},
                };
                const saveResponse = await this.saveSettings(savePayload);
                if (saveResponse.success) {
                    this._settingsData = null; // invalidate cache
                    return { success: true, data: { message: `Model for ${name} set to ${model}` } as unknown as T };
                }
                return { success: false, error: { message: 'Failed to save model selection' } } as APIResponse<T>;
            }
        }
        return apiRouter.execute({ method: 'set_llm_provider_model' }, { name, model });
    }

    public async setLLMProviderEnableThinking<T>(name: string, enableThinking: boolean): Promise<APIResponse<T>> {
        // Persist enable_thinking to DynamoDB
        await this._ensureSettingsLoaded();
        if (this._settingsData && this._settingsUsername) {
            const llmProviders = this._settingsData.llm_providers
                ? JSON.parse(JSON.stringify(this._settingsData.llm_providers))
                : {};
            const providersDict = llmProviders.providers || llmProviders;
            let found = false;
            for (const key of Object.keys(providersDict)) {
                const p = providersDict[key];
                if (p && (p.provider === name || p.name === name || key === name)) {
                    p.enable_thinking = enableThinking;
                    found = true;
                    break;
                }
            }
            if (found) {
                const savePayload = {
                    username: this._settingsUsername,
                    settings: this._settingsData.settings || {},
                    llm_providers: llmProviders,
                    embedding_providers: this._settingsData.embedding_providers || {},
                    rerank_providers: this._settingsData.rerank_providers || {},
                };
                const saveResponse = await this.saveSettings(savePayload);
                if (saveResponse.success) {
                    this._settingsData = null;
                    return { success: true, data: { message: `Thinking mode for ${name} set to ${enableThinking}` } as unknown as T };
                }
                return { success: false, error: { message: 'Failed to save thinking mode' } } as APIResponse<T>;
            }
        }
        return apiRouter.execute({ method: 'set_llm_provider_enable_thinking' }, { name, enable_thinking: enableThinking });
    }

    public async deleteLLMProviderConfig<T>(name: string, username: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'delete_llm_provider_config' }, { name, username });
    }

    public async getLLMProviderApiKey<T>(name: string, showFull: boolean = false): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_llm_provider_api_key' }, { name, show_full: showFull });
    }

    public async getConfiguredLLMProviders<T>(): Promise<APIResponse<T>> {
        // In cloud mode, return providers from settings cache that have api_key configured
        await this._ensureSettingsLoaded();
        const providers = this._extractProviders('llm_providers');
        if (providers) {
            const configured = providers.filter((p: any) => p.api_key_configured);
            return { success: true, data: { providers: configured } as T };
        }
        return apiRouter.execute({ method: 'get_configured_llm_providers' });
    }

    public async getLLMProvidersWithCredentials<T>(): Promise<APIResponse<T>> {
        // In cloud mode, return all providers from settings cache (they already include api_key)
        await this._ensureSettingsLoaded();
        const providers = this._extractProviders('llm_providers');
        if (providers) {
            return { success: true, data: { providers } as T };
        }
        return apiRouter.execute({ method: 'get_llm_providers_with_credentials' });
    }

    // Embedding Management APIs
    public async getEmbeddingProviders<T>(username?: string): Promise<APIResponse<T>> {
        await this._ensureSettingsLoaded();
        const providers = this._extractProviders('embedding_providers');
        if (providers) {
            return { success: true, data: { providers } as T };
        }
        // In desktop mode, providers come from Python backend via IPC
        if (this._settingsUsername) {
            console.debug('[IPCAPI] getEmbeddingProviders: cache miss, using IPC for desktop mode');
        }
        const params: any = {};
        if (username) params.username = username;
        return apiRouter.execute({ method: 'get_embedding_providers' }, params);
    }

    public async setDefaultEmbedding<T>(name: string, username: string, model?: string): Promise<APIResponse<T>> {
        // Persist default embedding to DynamoDB settings
        await this._ensureSettingsLoaded();
        if (this._settingsData && this._settingsUsername) {
            const settings = this._settingsData.settings
                ? JSON.parse(JSON.stringify(this._settingsData.settings))
                : {};
            settings.default_embedding = name;
            if (model) settings.default_embedding_model = model;
            const savePayload = {
                username: this._settingsUsername,
                settings,
                llm_providers: this._settingsData.llm_providers || {},
                embedding_providers: this._settingsData.embedding_providers || {},
                rerank_providers: this._settingsData.rerank_providers || {},
            };
            const saveResponse = await this.saveSettings(savePayload);
            if (saveResponse.success) {
                this._settingsData = null;
                return { success: true, data: { message: `Default embedding set to ${name}` } as unknown as T };
            }
        }
        const params: any = { name, username };
        if (model) {
            params.model = model;
        }
        return apiRouter.execute({ method: 'set_default_embedding' }, params);
    }

    public async updateEmbeddingProvider<T>(name: string, apiKey: string, azureEndpoint?: string, baseUrl?: string): Promise<APIResponse<T>> {
        // Persist embedding provider API key to DynamoDB
        await this._ensureSettingsLoaded();
        if (this._settingsData && this._settingsUsername) {
            const embeddingProviders = this._settingsData.embedding_providers
                ? JSON.parse(JSON.stringify(this._settingsData.embedding_providers))
                : {};
            const providersDict = embeddingProviders.providers || embeddingProviders;
            let found = false;
            for (const key of Object.keys(providersDict)) {
                const p = providersDict[key];
                if (p && (p.provider === name || p.name === name || key === name)) {
                    p.api_key = apiKey;
                    p.api_key_configured = !!apiKey && apiKey.length > 0;
                    if (azureEndpoint !== undefined) p.azure_endpoint = azureEndpoint;
                    if (baseUrl !== undefined) p.base_url = baseUrl;
                    found = true;
                    break;
                }
            }
            if (found) {
                const savePayload = {
                    username: this._settingsUsername,
                    settings: this._settingsData.settings || {},
                    llm_providers: this._settingsData.llm_providers || {},
                    embedding_providers: embeddingProviders,
                    rerank_providers: this._settingsData.rerank_providers || {},
                };
                const saveResponse = await this.saveSettings(savePayload);
                if (saveResponse.success) {
                    this._settingsData = null;
                    return { success: true, data: { message: `Embedding provider ${name} updated` } as unknown as T };
                }
            }
        }
        const params: any = { name, api_key: apiKey };
        if (azureEndpoint !== undefined) {
            params.azure_endpoint = azureEndpoint;
        }
        if (baseUrl !== undefined) {
            params.base_url = baseUrl;
        }
        return apiRouter.execute({ method: 'update_embedding_provider' }, params);
    }

    public async setEmbeddingProviderModel<T>(name: string, model: string): Promise<APIResponse<T>> {
        await this._ensureSettingsLoaded();
        if (this._settingsData && this._settingsUsername) {
            const embeddingProviders = this._settingsData.embedding_providers
                ? JSON.parse(JSON.stringify(this._settingsData.embedding_providers))
                : {};
            const providersDict = embeddingProviders.providers || embeddingProviders;
            let found = false;
            for (const key of Object.keys(providersDict)) {
                const p = providersDict[key];
                if (p && (p.provider === name || p.name === name || key === name)) {
                    p.default_model = model;
                    p.preferred_model = model;
                    found = true;
                    break;
                }
            }
            if (found) {
                const savePayload = {
                    username: this._settingsUsername,
                    settings: this._settingsData.settings || {},
                    llm_providers: this._settingsData.llm_providers || {},
                    embedding_providers: embeddingProviders,
                    rerank_providers: this._settingsData.rerank_providers || {},
                };
                const saveResponse = await this.saveSettings(savePayload);
                if (saveResponse.success) {
                    this._settingsData = null;
                    return { success: true, data: { message: `Embedding model for ${name} set to ${model}` } as unknown as T };
                }
            }
        }
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
    public async getRerankProviders<T>(username?: string): Promise<APIResponse<T>> {
        await this._ensureSettingsLoaded();
        const providers = this._extractProviders('rerank_providers');
        if (providers) {
            return { success: true, data: { providers } as T };
        }
        // In desktop mode, providers come from Python backend via IPC
        if (this._settingsUsername) {
            console.debug('[IPCAPI] getRerankProviders: cache miss, using IPC for desktop mode');
        }
        const params: any = {};
        if (username) params.username = username;
        return apiRouter.execute({ method: 'get_rerank_providers' }, params);
    }

    public async setDefaultRerank<T>(name: string, username: string, model?: string): Promise<APIResponse<T>> {
        await this._ensureSettingsLoaded();
        if (this._settingsData && this._settingsUsername) {
            const settings = this._settingsData.settings
                ? JSON.parse(JSON.stringify(this._settingsData.settings))
                : {};
            settings.default_rerank = name;
            if (model) settings.default_rerank_model = model;
            const savePayload = {
                username: this._settingsUsername,
                settings,
                llm_providers: this._settingsData.llm_providers || {},
                embedding_providers: this._settingsData.embedding_providers || {},
                rerank_providers: this._settingsData.rerank_providers || {},
            };
            const saveResponse = await this.saveSettings(savePayload);
            if (saveResponse.success) {
                this._settingsData = null;
                return { success: true, data: { message: `Default rerank set to ${name}` } as unknown as T };
            }
        }
        const params: any = { name, username };
        if (model) {
            params.model = model;
        }
        return apiRouter.execute({ method: 'set_default_rerank' }, params);
    }

    public async updateRerankProvider<T>(name: string, apiKey: string, azureEndpoint?: string, baseUrl?: string): Promise<APIResponse<T>> {
        await this._ensureSettingsLoaded();
        if (this._settingsData && this._settingsUsername) {
            const rerankProviders = this._settingsData.rerank_providers
                ? JSON.parse(JSON.stringify(this._settingsData.rerank_providers))
                : {};
            const providersDict = rerankProviders.providers || rerankProviders;
            let found = false;
            for (const key of Object.keys(providersDict)) {
                const p = providersDict[key];
                if (p && (p.provider === name || p.name === name || key === name)) {
                    p.api_key = apiKey;
                    p.api_key_configured = !!apiKey && apiKey.length > 0;
                    if (azureEndpoint !== undefined) p.azure_endpoint = azureEndpoint;
                    if (baseUrl !== undefined) p.base_url = baseUrl;
                    found = true;
                    break;
                }
            }
            if (found) {
                const savePayload = {
                    username: this._settingsUsername,
                    settings: this._settingsData.settings || {},
                    llm_providers: this._settingsData.llm_providers || {},
                    embedding_providers: this._settingsData.embedding_providers || {},
                    rerank_providers: rerankProviders,
                };
                const saveResponse = await this.saveSettings(savePayload);
                if (saveResponse.success) {
                    this._settingsData = null;
                    return { success: true, data: { message: `Rerank provider ${name} updated` } as unknown as T };
                }
            }
        }
        const params: any = { name, api_key: apiKey };
        if (azureEndpoint !== undefined) {
            params.azure_endpoint = azureEndpoint;
        }
        if (baseUrl !== undefined) {
            params.base_url = baseUrl;
        }
        return apiRouter.execute({ method: 'update_rerank_provider' }, params);
    }

    public async setRerankProviderModel<T>(name: string, model: string): Promise<APIResponse<T>> {
        await this._ensureSettingsLoaded();
        if (this._settingsData && this._settingsUsername) {
            const rerankProviders = this._settingsData.rerank_providers
                ? JSON.parse(JSON.stringify(this._settingsData.rerank_providers))
                : {};
            const providersDict = rerankProviders.providers || rerankProviders;
            let found = false;
            for (const key of Object.keys(providersDict)) {
                const p = providersDict[key];
                if (p && (p.provider === name || p.name === name || key === name)) {
                    p.default_model = model;
                    p.preferred_model = model;
                    found = true;
                    break;
                }
            }
            if (found) {
                const savePayload = {
                    username: this._settingsUsername,
                    settings: this._settingsData.settings || {},
                    llm_providers: this._settingsData.llm_providers || {},
                    embedding_providers: this._settingsData.embedding_providers || {},
                    rerank_providers: rerankProviders,
                };
                const saveResponse = await this.saveSettings(savePayload);
                if (saveResponse.success) {
                    this._settingsData = null;
                    return { success: true, data: { message: `Rerank model for ${name} set to ${model}` } as unknown as T };
                }
            }
        }
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

    public async getProviderModels<T>(host: string, apiKey?: string, modelType?: string, provider?: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'settings.getProviderModels' }, { host, api_key: apiKey, model_type: modelType, provider });
    }

    public async getRyoAISModels<T>(host: string, username?: string, verifySsl: boolean = false): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'settings.getRyoAISModels' }, { host, username, verify_ssl: verifySsl });
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

    public async testTask<T>(skillName?: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'test_task' }, { skill_name: skillName || 'my_test_bu_tools' });
    }

    // --- Feige Multi-Tab Diagnostic (2026-05-20) ---
    // Enumerates Chrome's Feige tabs via CDP, runs read-only JS snapshots
    // (inventory mode) or simultaneous sends from 2 tabs (concurrent_send).
    // Used to validate the multi-tab refactor design.
    public async testFeigeTabs<T>(params?: {
        mode?: 'inventory' | 'concurrent_send';
        cdp_port?: number;
        customer_a?: string;
        customer_b?: string;
        message_text?: string;
    }): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'test_feige_tabs' }, params || {});
    }

    // --- Lambda LLM Proxy Tests ---

    public async testLambdaProxyPing<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'test_lambda_proxy_ping' }, {});
    }

    public async testLlmProxyModels<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'test_llm_proxy_models' }, {});
    }

    public async testLambdaProxyLlm<T>(params?: { prompt?: string; provider?: string; model?: string }): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'test_lambda_proxy_llm' }, params || {});
    }

    public async testLambdaProxyBrowserUse<T>(params?: { prompt?: string; provider?: string; model?: string }): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'test_lambda_proxy_browser_use' }, params || {});
    }

    public async testLambdaProxyEmbedding<T>(params?: { text?: string; model?: string }): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'test_lambda_proxy_embedding' }, params || {});
    }

    public async testLambdaProxyHealthCheck<T>(params?: { providers?: string[] }): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'test_lambda_proxy_health_check' }, params || {});
    }

    public async testReqCreateScene<T>(params?: { description?: string; output_format?: string; style?: string }): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'test_req_create_scene' }, params || {});
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
      { username, agent_id }
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
      { username, agent }
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
        const taskInput: Record<string, any> = {
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
        // Pass skills/skill_ids for the local IPC handler (not part of GraphQL schema)
        if (agent_task_info.skills) taskInput.skills = agent_task_info.skills;
        if (agent_task_info.skill_ids) taskInput.skill_ids = agent_task_info.skill_ids;
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
        const taskInput: Record<string, any> = {
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
        // Pass skills/skill_ids for the local IPC handler (not part of GraphQL schema)
        if (agent_task_info.skills) taskInput.skills = agent_task_info.skills;
        if (agent_task_info.skill_ids) taskInput.skill_ids = agent_task_info.skill_ids;
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

    /**
     * Refresh agent task status
     */
    public async refreshAgentTaskStatus(username: string, taskId: string): Promise<APIResponse<any>> {
        return this.executeRequest('refresh_agent_task_status', { username, task_id: taskId });
    }

    /**
     * Run agent task
     */
    public async runAgentTask(username: string, params: {
        task_id: string;
        task_type?: string;
        cloud_based?: boolean;
        skill_id?: string;
        skill?: string;
    }): Promise<APIResponse<any>> {
        return this.executeRequest('run_agent_task', { username, ...params });
    }

    // ==================== Relation Tables (RDS) - Web GraphQL Only ====================
    private toAwsJson(value: any) {
      if (value === undefined) return undefined;
      if (value === null) return null;
      return typeof value === 'string' ? value : JSON.stringify(value);
    }

    private parseAwsJsonMaybe<T = any>(value: any): T {
      if (value === null || value === undefined) return value as T;
      if (typeof value !== 'string') return value as T;
      const s = value.trim();
      if (!s) return value as T;
      try {
        return JSON.parse(s) as T;
      } catch {
        return value as T;
      }
    }

    public async queryAgentOrgRels(input?: Record<string, any>): Promise<APIResponse<any[]>> {
      const resp = await apiRouter.execute(
        {
          method: 'query_agent_org_rels',
          graphql: {
            query: GRAPHQL_QUERIES.QUERY_AGENT_ORG_RELS,
            resultPath: 'queryAgentOrgRels'
          }
        },
        { input: this.toAwsJson(input || {}) }
      );
      if (!resp.success) return resp as any;
      return { success: true, data: this.parseAwsJsonMaybe<any[]>(resp.data) };
    }

    public async addAgentOrgRels(input: any[]): Promise<APIResponse<any>> {
      return apiRouter.execute(
        {
          method: 'add_agent_org_rels',
          graphql: {
            mutation: GRAPHQL_MUTATIONS.ADD_AGENT_ORG_RELS,
            resultPath: 'addAgentOrgRels'
          }
        },
        { input }
      );
    }

    public async removeAgentOrgRels(input: { id: string }[]): Promise<APIResponse<any>> {
      return apiRouter.execute(
        {
          method: 'remove_agent_org_rels',
          graphql: {
            mutation: GRAPHQL_MUTATIONS.REMOVE_AGENT_ORG_RELS,
            resultPath: 'removeAgentOrgRels'
          }
        },
        { input }
      );
    }

    public async queryAgentSkillRels(input?: Record<string, any>): Promise<APIResponse<any[]>> {
      const resp = await apiRouter.execute(
        {
          method: 'query_agent_skill_rels',
          graphql: {
            query: GRAPHQL_QUERIES.QUERY_AGENT_SKILL_RELS,
            resultPath: 'queryAgentSkillRels'
          }
        },
        { input: this.toAwsJson(input || {}) }
      );
      if (!resp.success) return resp as any;
      return { success: true, data: this.parseAwsJsonMaybe<any[]>(resp.data) };
    }

    public async addAgentSkillRels(input: any[]): Promise<APIResponse<any>> {
      return apiRouter.execute(
        {
          method: 'add_agent_skill_rels',
          graphql: {
            mutation: GRAPHQL_MUTATIONS.ADD_AGENT_SKILL_RELS,
            resultPath: 'addAgentSkillRels'
          }
        },
        { input }
      );
    }

    public async removeAgentSkillRels(input: { id: string }[]): Promise<APIResponse<any>> {
      return apiRouter.execute(
        {
          method: 'remove_agent_skill_rels',
          graphql: {
            mutation: GRAPHQL_MUTATIONS.REMOVE_AGENT_SKILL_RELS,
            resultPath: 'removeAgentSkillRels'
          }
        },
        { input }
      );
    }

    public async queryAgentTaskRels(input?: Record<string, any>): Promise<APIResponse<any[]>> {
      const resp = await apiRouter.execute(
        {
          method: 'query_agent_task_rels',
          graphql: {
            query: GRAPHQL_QUERIES.QUERY_AGENT_TASK_RELS,
            resultPath: 'queryAgentTaskRels'
          }
        },
        { input: this.toAwsJson(input || {}) }
      );
      if (!resp.success) return resp as any;
      return { success: true, data: this.parseAwsJsonMaybe<any[]>(resp.data) };
    }

    public async addAgentTaskRels(input: any[]): Promise<APIResponse<any>> {
      return apiRouter.execute(
        {
          method: 'add_agent_task_rels',
          graphql: {
            mutation: GRAPHQL_MUTATIONS.ADD_AGENT_TASK_RELS,
            resultPath: 'addAgentTaskRels'
          }
        },
        { input }
      );
    }

    public async removeAgentTaskRels(input: { id: string }[]): Promise<APIResponse<any>> {
      return apiRouter.execute(
        {
          method: 'remove_agent_task_rels',
          graphql: {
            mutation: GRAPHQL_MUTATIONS.REMOVE_AGENT_TASK_RELS,
            resultPath: 'removeAgentTaskRels'
          }
        },
        { input }
      );
    }

    public async queryAgentTaskSkillRels(input?: Record<string, any>): Promise<APIResponse<any[]>> {
      const resp = await apiRouter.execute(
        {
          method: 'query_agent_task_skill_rels',
          graphql: {
            query: GRAPHQL_QUERIES.QUERY_AGENT_TASK_SKILL_RELS,
            resultPath: 'queryAgentTaskSkillRels'
          }
        },
        { input: this.toAwsJson(input || {}) }
      );
      if (!resp.success) return resp as any;
      return { success: true, data: this.parseAwsJsonMaybe<any[]>(resp.data) };
    }

    public async addAgentTaskSkillRels(input: any[]): Promise<APIResponse<any>> {
      return apiRouter.execute(
        {
          method: 'add_agent_task_skill_rels',
          graphql: {
            mutation: GRAPHQL_MUTATIONS.ADD_AGENT_TASK_SKILL_RELS,
            resultPath: 'addAgentTaskSkillRels'
          }
        },
        { input }
      );
    }

    public async removeAgentTaskSkillRels(input: ({ id: string } | { task_id: string; skill_id: string })[]): Promise<APIResponse<any>> {
      return apiRouter.execute(
        {
          method: 'remove_agent_task_skill_rels',
          graphql: {
            mutation: GRAPHQL_MUTATIONS.REMOVE_AGENT_TASK_SKILL_RELS,
            resultPath: 'removeAgentTaskSkillRels'
          }
        },
        { input }
      );
    }

    // Placeholders (not currently used by web UI)
    public async queryAgentSkillToolRels(input?: Record<string, any>): Promise<APIResponse<any[]>> {
      const resp = await apiRouter.execute(
        {
          method: 'query_agent_skill_tool_rels',
          graphql: {
            query: GRAPHQL_QUERIES.QUERY_AGENT_SKILL_TOOL_RELS,
            resultPath: 'queryAgentSkillToolRels'
          }
        },
        { input: this.toAwsJson(input || {}) }
      );
      if (!resp.success) return resp as any;
      return { success: true, data: this.parseAwsJsonMaybe<any[]>(resp.data) };
    }

    public async addAgentSkillToolRels(input: any[]): Promise<APIResponse<any>> {
      return apiRouter.execute(
        {
          method: 'add_agent_skill_tool_rels',
          graphql: {
            mutation: GRAPHQL_MUTATIONS.ADD_AGENT_SKILL_TOOL_RELS,
            resultPath: 'addAgentSkillToolRels'
          }
        },
        { input }
      );
    }

    public async removeAgentSkillToolRels(input: { id: string }[]): Promise<APIResponse<any>> {
      return apiRouter.execute(
        {
          method: 'remove_agent_skill_tool_rels',
          graphql: {
            mutation: GRAPHQL_MUTATIONS.REMOVE_AGENT_SKILL_TOOL_RELS,
            resultPath: 'removeAgentSkillToolRels'
          }
        },
        { input }
      );
    }

    public async queryAgentSkillKnowledgeRels(input?: Record<string, any>): Promise<APIResponse<any[]>> {
      const resp = await apiRouter.execute(
        {
          method: 'query_agent_skill_knowledge_rels',
          graphql: {
            query: GRAPHQL_QUERIES.QUERY_AGENT_SKILL_KNOWLEDGE_RELS,
            resultPath: 'queryAgentSkillKnowledgeRels'
          }
        },
        { input: this.toAwsJson(input || {}) }
      );
      if (!resp.success) return resp as any;
      return { success: true, data: this.parseAwsJsonMaybe<any[]>(resp.data) };
    }

    public async addAgentSkillKnowledgeRels(input: any[]): Promise<APIResponse<any>> {
      return apiRouter.execute(
        {
          method: 'add_agent_skill_knowledge_rels',
          graphql: {
            mutation: GRAPHQL_MUTATIONS.ADD_AGENT_SKILL_KNOWLEDGE_RELS,
            resultPath: 'addAgentSkillKnowledgeRels'
          }
        },
        { input }
      );
    }

    public async removeAgentSkillKnowledgeRels(input: { id: string }[]): Promise<APIResponse<any>> {
      return apiRouter.execute(
        {
          method: 'remove_agent_skill_knowledge_rels',
          graphql: {
            mutation: GRAPHQL_MUTATIONS.REMOVE_AGENT_SKILL_KNOWLEDGE_RELS,
            resultPath: 'removeAgentSkillKnowledgeRels'
          }
        },
        { input }
      );
    }

    public async queryCloudTaskRunId(taskId: string, hostName?: string, metaData: Record<string, any> = {}): Promise<APIResponse<{ id: string; runID: string; runner: string; status: string; success: boolean; error: string; timestamp: string }>> {
        const toAwsJson = (value: any) => {
          if (value === undefined) return undefined;
          if (value === null) return null;
          return typeof value === 'string' ? value : JSON.stringify(value);
        };
        return apiRouter.execute(
      {
        method: 'query_cloud_task_run_id',
        graphql: {
          query: GRAPHQL_QUERIES.QUERY_CLOUD_TASK_RUN_ID,
          resultPath: 'queryCloudTaskRunId'
        }
      },
      { input: { task_id: taskId, host_name: hostName || null, meta_data: toAwsJson(metaData) } }
    );
    }

    public async saveAgentSkill<T>(username: string, skill_info: T): Promise<APIResponse<void>> {
        // GraphQL mutation expects input: [SkillUpdateInput!]!
        // NOTE: AWSJSON fields must be JSON strings for AppSync.
        const toAwsJson = (value: any) => {
          if (value === undefined) return undefined;
          if (value === null) return null;
          return typeof value === 'string' ? value : JSON.stringify(value);
        };
        const normalizeSkillUpdateInput = (skill: any) => {
          if (!skill || typeof skill !== 'object') return skill;
          const out: Record<string, any> = {};
          const allowed = [
            'id',
            'name',
            'description',
            'version',
            'path',
            'level',
            'source',
            'public',
            'rentable',
            'price',
            'price_model',
            'askid',
            // AWSJSON
            'config',
            'diagram',
            'tags',
            'apps',
            'examples',
            'inputModes',
            'outputModes',
            'limitations',
          ];
          const awsJsonFields = new Set([
            'config',
            'diagram',
            'tags',
            'apps',
            'examples',
            'inputModes',
            'outputModes',
            'limitations',
          ]);

          for (const key of allowed) {
            if (!(key in skill)) continue;
            const v = (skill as any)[key];
            if (v === undefined) continue;
            out[key] = awsJsonFields.has(key) ? toAwsJson(v) : v;
          }
          return out;
        };

        const normalizedSkill = normalizeSkillUpdateInput(skill_info as any);

        // Note: owner is NOT in SkillUpdateInput schema - backend gets it from identity claims
        return apiRouter.execute(
      {
        method: 'save_agent_skill',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.UPDATE_AGENT_SKILLS,
          resultPath: 'updateAgentSkills'
        }
      },
      { username, skill_info: normalizedSkill }
    );
    }

    /**
     * Rename skill - uses ID-based approach for reliable DB update
     * @param oldName - Old skill name (without _skill suffix) - used for file system rename
     * @param newName - New skill name (without _skill suffix) - used for file system rename
     * @param currentFilePath - (Optional) Current skill JSON file path for external directories
     * @param skillId - (Required) The unique skill ID - used to locate DB record for update
     * @returns API response with skillRoot path
     */
    public async renameSkill(oldName: string, newName: string, currentFilePath?: string, skillId?: string): Promise<APIResponse<{ skillRoot: string; skillId: string }>> {
        const params: any = { oldName, newName };
        if (currentFilePath) {
            params.currentFilePath = currentFilePath;
        }
        if (skillId) {
            params.skillId = skillId;
        }
        return apiRouter.execute<{ skillRoot: string; skillId: string }>(
            { method: 'skills.rename' },
            params
        );
    }

    /**
     * Run skill via IPC (simplified version without username)
     * Used by canvas-controller for local skill execution
     */
    public async runSkillViaIPC(skillData: any): Promise<APIResponse<any>> {
        return apiRouter.execute({ method: 'run_skill' }, { skill: skillData });
    }

    /**
     * Step run skill via IPC
     */
    public async stepRunSkillViaIPC(): Promise<APIResponse<any>> {
        return apiRouter.execute({ method: 'step_run_skill' }, {});
    }

    /**
     * Pause running skill via IPC
     */
    public async pauseRunSkillViaIPC(): Promise<APIResponse<any>> {
        return apiRouter.execute({ method: 'pause_run_skill' }, {});
    }

    /**
     * Resume running skill via IPC
     */
    public async resumeRunSkillViaIPC(): Promise<APIResponse<any>> {
        return apiRouter.execute({ method: 'resume_run_skill' }, {});
    }

    /**
     * Cancel running skill via IPC
     */
    public async cancelRunSkillViaIPC(): Promise<APIResponse<any>> {
        return apiRouter.execute({ method: 'cancel_run_skill' }, {});
    }

    public async newAgentSkill<T>(username: string, skill_info: T): Promise<APIResponse<void>> {
        // GraphQL mutation expects input: [SkillInput!]!
        // NOTE: AWSJSON fields must be JSON strings for AppSync.
        const toAwsJson = (value: any) => {
          if (value === undefined) return undefined;
          if (value === null) return null;
          return typeof value === 'string' ? value : JSON.stringify(value);
        };
        const normalizeSkillInput = (skill: any) => {
          if (!skill || typeof skill !== 'object') return skill;
          const out: Record<string, any> = {};
          const allowed = [
            'id',
            'name',
            'description',
            'version',
            'path',
            'level',
            'source',
            'public',
            'rentable',
            'price',
            'price_model',
            'askid',
            // AWSJSON
            'config',
            'diagram',
            'tags',
            'apps',
            'examples',
            'inputModes',
            'outputModes',
            'limitations',
          ];
          const awsJsonFields = new Set([
            'config',
            'diagram',
            'tags',
            'apps',
            'examples',
            'inputModes',
            'outputModes',
            'limitations',
          ]);

          for (const key of allowed) {
            if (!(key in skill)) continue;
            const v = (skill as any)[key];
            if (v === undefined) continue;
            out[key] = awsJsonFields.has(key) ? toAwsJson(v) : v;
          }
          return out;
        };

        const normalizedSkill = normalizeSkillInput(skill_info as any);

        // Note: owner is NOT in SkillInput schema - backend gets it from identity claims
        return apiRouter.execute(
      {
        method: 'new_agent_skill',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.ADD_AGENT_SKILLS,
          resultPath: 'addAgentSkills'
        }
      },
      { username, skill_info: normalizedSkill }
    );
    }

    public async deleteAgentSkill(username: string, skill_id: string): Promise<APIResponse<DeleteAgentSkillResult>> {
        // GraphQL mutation expects input: [ID!]!
        return apiRouter.execute(
      {
        method: 'delete_agent_skill',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.REMOVE_AGENT_SKILLS,
          resultPath: 'removeAgentSkills'
        }
      },
      { username, skill_id, input: [skill_id] }
    );
    }

    public async runSkill<T>(username: string, skill: T, meta_data?: any): Promise<APIResponse<void>> {
        // skill must be JSON-stringified for AWSJSON type in GraphQL schema
        const skillJson = typeof skill === 'string' ? skill : JSON.stringify(skill);
        const metaJson = meta_data == null ? '{}' : (typeof meta_data === 'string' ? meta_data : JSON.stringify(meta_data));
        return apiRouter.execute(
      {
        method: 'run_skill',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.RUN_SKILL,
          resultPath: 'runSkill'
        }
      },
      { username, skill: skillJson, meta_data: metaJson }
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
      { username, skill: skillJson }
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
      { username, skill: skillJson }
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
      { username, skill: skillJson }
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
      { username, skill: skillJson }
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
        // skill must be JSON-stringified for AWSJSON type in GraphQL schema
        const skillJson = typeof skill === 'string' ? skill : JSON.stringify(skill);
        return apiRouter.execute(
      {
        method: 'request_skill_state',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.REQUEST_SKILL_STATE,
          resultPath: 'requestSkillState'
        }
      },
      {username, skill: skillJson}
    );
    }

    public async injectSkillState<T>(username: string, skill: T): Promise<APIResponse<void>> {
        // skill must be JSON-stringified for AWSJSON type in GraphQL schema
        const skillJson = typeof skill === 'string' ? skill : JSON.stringify(skill);
        return apiRouter.execute(
      {
        method: 'inject_skill_state',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.INJECT_SKILL_STATE,
          resultPath: 'injectSkillState'
        }
      },
      {username, skill: skillJson}
    );
    }

    public async loadSkillSchemas<T>(username: string, skill: T): Promise<APIResponse<void>> {
        // skill must be JSON-stringified for AWSJSON type in GraphQL schema
        const skillJson = typeof skill === 'string' ? skill : JSON.stringify(skill);
        return apiRouter.execute(
      {
        method: 'load_skill_schemas',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.LOAD_SKILL_SCHEMAS,
          resultPath: 'loadSkillSchemas'
        }
      },
      {username, skill: skillJson}
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
     * Get system initialization status
     * @returns Promise with simple ready status and i18n key
     */
    public async getInitializationProgress(): Promise<APIResponse<{
        ready: boolean;
        status: string;  // i18n key like 'system.ready' or 'system.initializing'
    }>> {
        const response = await apiRouter.execute<{ready: boolean; status: string}>(
            { method: 'get_initialization_progress' }
        );

        if (response.success && response.data) {
            return {
                success: true,
                data: {
                    ready: response.data.ready ?? false,
                    status: response.data.status ?? 'system.initializing'
                }
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

    // LLM Token Usage APIs
    public async getMonthlyTokenUsage<T>(month?: number, year?: number): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'llm.getMonthlyTokenUsage' }, { month, year });
    }

    public async getTokenUsageTimeSeries<T>(period?: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'llm.getTokenUsageTimeSeries' }, { period: period || '1m' });
    }

    public async getTokenUsageBreakdown<T>(start?: string, end?: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'llm.getTokenUsageBreakdown' }, { start, end });
    }

    public async getTokenUsageAlarms<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'llm.getTokenUsageAlarms' });
    }

    public async setTokenAlarmLevels<T>(daily_token_limit: number, monthly_token_limit: number): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'llm.setTokenAlarmLevels' }, { daily_token_limit, monthly_token_limit });
    }

    // Agent Runtime Status APIs
    public async getAgentRuntimeStatus<T>(agent_id: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_agent_runtime_status' }, { agent_id });
    }

    public async getAllAgentsRuntimeStatus<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_all_agents_runtime_status' }, {});
    }

    public async toggleAgentEnabled<T>(agent_id: string, enable: boolean): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'toggle_agent_enabled' }, { agent_id, enable });
    }

    public async setAgentEnabled<T>(agent_id: string, enabled: boolean): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'set_agent_enabled' }, { agent_id, enabled });
    }

    // ── Channel Management APIs ────────────────────────────────────────────────

    public async getChannels<T>(): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_channels' }, {});
    }

    public async saveChannelConfig<T>(channel_id: string, config: Record<string, any>): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'save_channel_config' }, { channel_id, config });
    }

    public async startChannel<T>(channel_id: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'start_channel' }, { channel_id });
    }

    public async stopChannel<T>(channel_id: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'stop_channel' }, { channel_id });
    }

    public async getWhatsappQR<T>(channel_id?: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_whatsapp_qr' }, { channel_id: channel_id || 'whatsapp_baileys' });
    }

    public async sendChannelMessage<T>(channel_id: string, chat_id: string, text: string): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'send_channel_message' }, { channel_id, chat_id, text });
    }

    public async getChannelTestMessages<T>(channel_id?: string, since_ts?: number): Promise<APIResponse<T>> {
        return apiRouter.execute({ method: 'get_channel_test_messages' }, { channel_id: channel_id || '', since_ts: since_ts || 0 });
    }

    // ── Skill History APIs ─────────────────────────────────────────────────────

    /**
     * Get history list for a skill
     * @param skillId - The skill ID
     * @param limit - Maximum number of records to return (default 100)
     * @param offset - Number of records to skip (default 0)
     */
    public async getSkillHistoryList<T>(skillId: string, limit?: number, offset?: number): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'get_skill_history_list' },
            { skill_id: skillId, limit: limit || 100, offset: offset || 0 }
        );
    }

    /**
     * Get a specific history record
     * @param historyId - The history record ID
     */
    public async getSkillHistory<T>(historyId: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'get_skill_history' },
            { history_id: historyId }
        );
    }

    /**
     * Restore skill from a history record
     * @param historyId - The history record ID to restore from
     * @param skipBackup - Whether to skip creating backup of current state
     */
    public async restoreSkillFromHistory<T>(historyId: string, skipBackup?: boolean): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'restore_skill_from_history' },
            { history_id: historyId, skip_backup: skipBackup || false }
        );
    }

    /**
     * Delete a specific history record
     * @param historyId - The history record ID to delete
     */
    public async deleteSkillHistory<T>(historyId: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'delete_skill_history' },
            { history_id: historyId }
        );
    }

    /**
     * Delete all history records for a skill
     * @param skillId - The skill ID
     */
    public async deleteAllSkillHistory<T>(skillId: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'delete_all_skill_history' },
            { skill_id: skillId }
        );
    }

    /**
     * Get history count for a skill
     * @param skillId - The skill ID
     */
    public async getSkillHistoryCount<T>(skillId: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'get_skill_history_count' },
            { skill_id: skillId }
        );
    }

    /**
     * Compare two history versions
     * @param historyId1 - First history record ID
     * @param historyId2 - Second history record ID
     */
    public async compareSkillVersions<T>(historyId1: string, historyId2: string): Promise<APIResponse<T>> {
        return apiRouter.execute(
            { method: 'compare_skill_versions' },
            { history_id1: historyId1, history_id2: historyId2 }
        );
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
