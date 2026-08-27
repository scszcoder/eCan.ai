/**
 * CloudBase Authentication Service
 * 2. 手机号 + 验证码登录
 * 3. 微信登录
 * 4. 自定义登录 Ticket
 */

import { logger } from '../../utils/logger';
import { apiRouter } from '../api/api-router';

export interface CloudBaseConfig {
  /** CloudBase 环境 ID */
  envId: string;
  /** CloudBase 访问端点 */
  endpoint?: string;
}

export interface CloudBaseUserInfo {
  /** 用户唯一标识 */
  uuid: string;
  /** 微信 OpenID */
  wxOpenId?: string;
  /** 手机号 */
  phoneNumber?: string;
  /** 邮箱 */
  email?: string;
  /** 昵称 */
  nickname?: string;
  /** 用户名 */
  username?: string;
  /** 头像 URL */
  avatarUrl?: string;
  /** 自定义用户 ID */
  customUserId?: string;
  /** 登录类型 */
  loginType: 'email' | 'phone' | 'wechat' | 'custom';
}

export interface CloudBaseAuthResult {
  /** 是否成功 */
  success: boolean;
  /** 认证数据 */
  data?: {
    /** JWT Token */
    token: string;
    /** 刷新令牌 */
    refreshToken: string;
    /** 用户信息 */
    userInfo: CloudBaseUserInfo;
  };
  /** 错误信息 */
  error?: string;
  /** 错误码 */
  errorCode?: string;
}

export interface LoginSession {
  /** JWT Token */
  token: string;
  /** 用户信息 */
  userInfo: {
    /** 用户名 */
    username: string;
    /** 邮箱 */
    email: string;
    /** 角色 */
    role: string;
    /** 昵称 */
    name: string;
    /** 名 */
    given_name: string;
    /** 姓 */
    family_name: string;
    /** 头像 */
    picture: string;
    /** 登录类型 */
    login_type: string;
  };
  /** 登录时间 */
  loginTime: number;
  /** 会话 ID */
  sessionId?: string;
}

const STORAGE_KEYS = {
  CLOUDBASE_TOKEN: 'cloudbase_token',
  CLOUDBASE_REFRESH_TOKEN: 'cloudbase_refresh_token',
  CLOUDBASE_USER_INFO: 'cloudbase_user_info',
} as const;

export function getWechatOAuthRedirectUri(): string {
  return `${window.location.origin}${window.location.pathname}#/login`;
}

/**
 * Extract a user-facing error message from a GraphQL response, logging the raw
 * CloudBase `original_error` to the console so developers can inspect it without
 * polluting the localized UI text. The original message is also preserved in
 * `result.originalError` (via the caller) for callers that want it.
 *
 * Returns the localized message unchanged so it can be shown to end users.
 */
function _formatError(resp: any, fallback: string): string {
  const err = resp?.error;
  const localized = err?.message || fallback;
  const details = err?.details;
  const originalError =
    (details && typeof details === 'object' && (details as any).original_error) ||
    (details && typeof details === 'object' && (details as any).details?.original_error);
  const originalCode =
    (details && typeof details === 'object' && (details as any).original_error_code) ||
    (details && typeof details === 'object' && (details as any).details?.original_error_code);
  if (typeof originalError === 'string' && originalError) {
    logger.error('[CloudBaseAuth] Upstream error:', {
      code: err?.code,
      originalCode,
      originalError,
      localized,
    });
  }
  return localized;
}

class CloudBaseAuthService {
  private config: CloudBaseConfig | null = null;
  private token: string | null = null;
  private _refreshToken: string | null = null;
  private userInfo: CloudBaseUserInfo | null = null;

  /**
   * 初始化 CloudBase 配置
   */
  initialize(config: CloudBaseConfig): void {
    this.config = config;
    logger.info('[CloudBaseAuth] Initialized with envId:', config.envId);
  }

  /**
   * 检查是否已初始化
   */
  isInitialized(): boolean {
    return this.config !== null && !!this.config.envId;
  }

  /**
   * 检查是否已登录
   */
  isLoggedIn(): boolean {
    return !!this.token && !!this.userInfo;
  }

  /**
   * 获取当前配置
   */
  getConfig(): CloudBaseConfig | null {
    return this.config;
  }

  /**
   * 获取当前用户信息
   */
  getUserInfo(): CloudBaseUserInfo | null {
    return this.userInfo;
  }

  /**
   * 获取当前 Token
   */
  getToken(): string | null {
    return this.token;
  }

  /**
   * 获取刷新令牌
   */
  getRefreshToken(): string | null {
    return this._refreshToken;
  }

  /**
   * 保存认证结果
   */
  private saveAuthResult(result: CloudBaseAuthResult): boolean {
    if (!result.success || !result.data) {
      return false;
    }

    this.token = result.data.token;
    this._refreshToken = result.data.refreshToken;
    this.userInfo = result.data.userInfo;

    // 持久化到 localStorage
    try {
      localStorage.setItem(STORAGE_KEYS.CLOUDBASE_TOKEN, this.token);
      localStorage.setItem(STORAGE_KEYS.CLOUDBASE_REFRESH_TOKEN, this._refreshToken);
      localStorage.setItem(STORAGE_KEYS.CLOUDBASE_USER_INFO, JSON.stringify(this.userInfo));
    } catch (e) {
      logger.warn('[CloudBaseAuth] Failed to persist auth data:', e);
    }

    return true;
  }

  /**
   * 从本地存储恢复认证状态
   */
  restoreAuthState(): boolean {
    try {
      const token = localStorage.getItem(STORAGE_KEYS.CLOUDBASE_TOKEN);
      const refreshToken = localStorage.getItem(STORAGE_KEYS.CLOUDBASE_REFRESH_TOKEN);
      const userInfoStr = localStorage.getItem(STORAGE_KEYS.CLOUDBASE_USER_INFO);

      if (token && refreshToken && userInfoStr) {
        this.token = token;
        this._refreshToken = refreshToken;
        this.userInfo = JSON.parse(userInfoStr);
        logger.info('[CloudBaseAuth] Auth state restored from localStorage');
        return true;
      }
    } catch (e) {
      logger.warn('[CloudBaseAuth] Failed to restore auth state:', e);
    }
    return false;
  }

  /**
   * 清除认证状态
   */
  clearAuthState(): void {
    this.token = null;
    this._refreshToken = null;
    this.userInfo = null;

    try {
      localStorage.removeItem(STORAGE_KEYS.CLOUDBASE_TOKEN);
      localStorage.removeItem(STORAGE_KEYS.CLOUDBASE_REFRESH_TOKEN);
      localStorage.removeItem(STORAGE_KEYS.CLOUDBASE_USER_INFO);
    } catch (e) {
      logger.warn('[CloudBaseAuth] Failed to clear auth state:', e);
    }
  }

  // ==================== 登录方法 ====================

  /**
   * 邮箱密码登录
   */
  async loginWithEmail(email: string, password: string): Promise<CloudBaseAuthResult> {
    if (!this.isInitialized()) {
      return { success: false, error: 'CloudBase not initialized' };
    }

    try {
      // Trim email and password before sending — values copied from
      // password managers / browser autofill frequently have
      // leading/trailing whitespace which CloudBase's SDK treats as a
      // credential mismatch (INVALID_CREDENTIALS) even when the user
      // typed them correctly.  See terminals/7.txt:41 where ``password``
      // arrived at the backend as ``' Ecan249511118!'`` (note leading
      // space) and CloudBase rejected it as INVALID_CREDENTIALS.
      const resp = await apiRouter.execute<any>(
        { method: 'cloudbase_login' },
        { email: email.trim(), password: password.trim(), role: 'Commander' },
      );

      const data = (resp && (resp as any).data) || (resp && (resp as any).result?.data);
      if (resp?.success && data) {
        const result: CloudBaseAuthResult = {
          success: true,
          data: {
            token: data.token,
            refreshToken: data.refresh_token || data.token,
            userInfo: {
              uuid: data.user_info?.uuid || '',
              email: data.user_info?.email || email,
              username: data.user_info?.username,
              nickname: data.user_info?.nickname,
              loginType: 'email',
            },
          },
        };
        this.saveAuthResult(result);
        return result;
      }

      return { success: false, error: _formatError(resp, 'Login failed') };
    } catch (error) {
      logger.error('[CloudBaseAuth] Login error:', error);
      return { success: false, error: String(error) };
    }
  }

  /**
   * 手机号验证码登录
   * @param phone 手机号
   * @param code 验证码
   * @param verificationId 验证码发送时返回的 verification_id（必须）
   */
  async loginWithPhone(phone: string, code: string, verificationId?: string): Promise<CloudBaseAuthResult> {
    if (!this.isInitialized()) {
      return { success: false, error: 'CloudBase not initialized' };
    }

    try {
      // Trim phone and code before sending — autofill / paste
      // frequently introduces whitespace.  Code in particular is
      // easy to mistype with an accidental trailing space.
      const resp = await apiRouter.execute<any>(
        { method: 'cloudbase_phone_login' },
        { phone: phone.trim(), code: code.trim(), verification_id: verificationId, role: 'Commander' },
      );

      const data = (resp && (resp as any).data) || (resp && (resp as any).result?.data);
      if (resp?.success && data) {
        const result: CloudBaseAuthResult = {
          success: true,
          data: {
            token: data.token,
            refreshToken: data.refresh_token || data.token,
            userInfo: {
              uuid: data.user_info?.uuid || '',
              // Keep a canonical username for all downstream stores.  The
              // previous phone path only populated phoneNumber, while the
              // org/agent sync service keys every request by username.
              username: data.user_info?.username || data.user_info?.phone || phone,
              phoneNumber: data.user_info?.phone || phone,
              loginType: 'phone',
            },
          },
        };
        this.saveAuthResult(result);
        return result;
      }

      return { success: false, error: _formatError(resp, 'Phone login failed') };
    } catch (error) {
      logger.error('[CloudBaseAuth] Phone login error:', error);
      return { success: false, error: String(error) };
    }
  }

  /**
   * 发送手机验证码
   * 返回 isUser: true 表示号码已注册(走 sign_in)，false 表示未注册(后端会自动 sign_up)
   */
  async sendPhoneCode(phone: string, purpose: 'login' | 'register' | 'reset_password' = 'login'): Promise<{ success: boolean; error?: string; devCode?: string; verificationId?: string; isUser?: boolean }> {
    if (!this.isInitialized()) {
      return { success: false, error: 'CloudBase not initialized' };
    }

    try {
      // Trim phone before sending — autofill / paste frequently
      // introduces spaces, dashes, or country-code prefixes that
      // CloudBase's SMS provider rejects as INVALID_PARAMS.
      const resp = await apiRouter.execute<any>(
        { method: 'cloudbase_send_code' },
        { phone: phone.trim(), purpose },
      );

      const data = (resp && (resp as any).data) || (resp && (resp as any).result?.data);
      if (resp?.success && data) {
        // 兼容 CloudBase 两种字段命名（snake_case vs camelCase）
        const verificationId = data.verification_id || data.verificationId;
        return {
          success: true,
          devCode: data.dev_code,  // 仅开发模式返回
          verificationId,
          isUser: typeof data.is_user === 'boolean' ? data.is_user : undefined,
        };
      }

      return { success: false, error: _formatError(resp, 'Failed to send code') };
    } catch (error) {
      logger.error('[CloudBaseAuth] Send code error:', error);
      return { success: false, error: String(error) };
    }
  }


  /**
   * Start the server-owned WeChat OAuth flow.
   *
   * The callback exchanges the authorization code with WeChat and receives
   * the provider's raw OpenID. Keeping this exchange server-side protects
   * the app secret and gives web and desktop the same account identity.
   */
  async loginWithCloudBaseWechat(wechatAppId?: string): Promise<CloudBaseAuthResult> {
    if (!this.isInitialized()) {
      return { success: false, error: 'CloudBase not initialized' };
    }

    if (!(wechatAppId || import.meta.env.VITE_WECHAT_APP_ID || '').trim()) {
      return { success: false, error: 'WeChat login is not configured' };
    }

    try {
      logger.info('[CloudBaseAuth] Redirecting to the server-owned WeChat OAuth flow');
      window.location.assign('/cn/login_callback/wechat_login.php');
      return { success: true };
    } catch (error) {
      logger.error('[CloudBaseAuth] CloudBase WeChat login error:', error);
      return { success: false, error: String(error) };
    }
  }

  async registerWechatSession(accessToken: string): Promise<{
    success: boolean;
    sessionToken?: string;
    expiresIn?: number;
    error?: string;
  }> {
    try {
      const resp = await apiRouter.execute<any>(
        {
          method: 'registerWeChatSession',
          graphql: {
            mutation: `
              mutation RegisterWeChatSession($input: RegisterWeChatSessionInput!) {
                registerWeChatSession(input: $input) {
                  sessionToken
                  expiresIn
                }
              }
            `,
            resultPath: 'registerWeChatSession',
          },
        },
        { input: { wxAccessToken: accessToken } },
      );
      const data = (resp as any)?.data;
      if (resp?.success && data?.sessionToken) {
        return {
          success: true,
          sessionToken: data.sessionToken,
          expiresIn: data.expiresIn,
        };
      }
      return { success: false, error: _formatError(resp, 'Failed to create WeChat session') };
    } catch (error) {
      logger.error('[CloudBaseAuth] WeChat session registration error:', error);
      return { success: false, error: String(error) };
    }
  }

  /**
   * 桌面 App 微信扫码登录（内嵌浏览器弹窗）。
   *
   * 后端在内嵌浏览器弹窗打开已备案域名上的 wechat_login.php，用户扫码后
   * 后端读取页面 localStorage 中的 token/username，并走与邮箱登录相同的
   * finalize 链路（安装 token、生成 IPC 会话、拉起 MainWindow）。返回
   * 与 finalizeSession 一致的 shape，前端据此保存会话。
   *
   * 仅桌面模式可用；Web 模式请用 loginWithCloudBaseWechat。
   */
  async loginWithWechatQR(role: string = 'Commander', lang?: string): Promise<CloudBaseAuthResult & { session_id?: string; ipc_token?: string }> {
    if (!this.isInitialized()) {
      return { success: false, error: 'CloudBase not initialized' };
    }

    try {
      // The backend opens an in-app QR dialog and blocks until the user
      // finishes scanning (backend hard-caps at 310s). Override the default
      // 30s IPC timeout so the request outlives the scan — 330s matches the
      // CIAM wechatLogin precedent and stays above the backend cap.
      const resp = await apiRouter.execute<any>(
        { method: 'cloudbase_wechat_qr_login' },
        { role, lang },
        { timeout: 330_000 },
      );

      const data = (resp && (resp as any).data) || (resp && (resp as any).result?.data);
      if (resp?.success && data) {
        return {
          success: true,
          data: {
            token: data.token,
            refreshToken: data.refresh_token || data.token,
            userInfo: {
              uuid: data.user_info?.uuid || '',
              email: data.user_info?.email || '',
              username: data.user_info?.username,
              nickname: data.user_info?.name,
              loginType: 'wechat',
            },
          },
          session_id: data.session_id,
          ipc_token: data.token,
        };
      }

      return { success: false, error: _formatError(resp, 'WeChat login failed') };
    } catch (error) {
      logger.error('[CloudBaseAuth] WeChat QR login error:', error);
      return { success: false, error: String(error) };
    }
  }

  /**
   * 邮箱注册（第一步：发验证码，返回 verification_id）
   */
  async signupWithEmail(email: string, password: string): Promise<{ success: boolean; error?: string; verificationId?: string }> {
    if (!this.isInitialized()) {
      return { success: false, error: 'CloudBase not initialized' };
    }

    try {
      // Trim email/password before sending — see the rationale in
      // loginWithEmail.  Autofill / password managers frequently
      // introduce leading/trailing whitespace.
      const resp = await apiRouter.execute<any>(
        { method: 'cloudbase_signup' },
        { email: email.trim(), password: password.trim() },
      );

      const data = (resp && (resp as any).data) || (resp && (resp as any).result?.data);
      if (resp?.success) {
        // 兼容 CloudBase 两种字段命名（snake_case vs camelCase）
        const verificationId = data?.verification_id || data?.verificationId;
        return {
          success: true,
          verificationId,
        };
      }

      return { success: false, error: _formatError(resp, 'Signup failed') };
    } catch (error) {
      logger.error('[CloudBaseAuth] Signup error:', error);
      return { success: false, error: String(error) };
    }
  }

  /**
   * 邮箱注册（第二步：输入验证码完成注册）
   * @param verificationId signupWithEmail 返回的 verification_id
   */
  async confirmSignupWithEmail(email: string, code: string, password: string, verificationId: string): Promise<CloudBaseAuthResult> {
    if (!this.isInitialized()) {
      return { success: false, error: 'CloudBase not initialized' };
    }

    try {
      // Trim email / code / password — see loginWithEmail for
      // rationale.  The verification code is short and easy to
      // mistype with trailing whitespace when copy-pasting from an
      // SMS; trimming prevents INVALID_PARAMS.
      const resp = await apiRouter.execute<any>(
        { method: 'cloudbase_signup_confirm' },
        {
          email: email.trim(),
          code: code.trim(),
          verification_id: verificationId,
          password: password.trim(),
        },
      );

      const data = (resp && (resp as any).data) || (resp && (resp as any).result?.data);
      if (resp?.success && data) {
        const result: CloudBaseAuthResult = {
          success: true,
          data: {
            token: data.token,
            refreshToken: data.refresh_token || data.token,
            userInfo: {
              uuid: data.user_info?.uuid || '',
              email: data.user_info?.email || email,
              username: data.user_info?.username,
              nickname: data.user_info?.nickname,
              loginType: 'email',
            },
          },
        };
        this.saveAuthResult(result);
        return result;
      }

      return { success: false, error: _formatError(resp, 'Signup confirm failed') };
    } catch (error) {
      logger.error('[CloudBaseAuth] Signup confirm error:', error);
      return { success: false, error: String(error) };
    }
  }

  /**
   * 手机号注册
   * @param verificationId 验证码发送时返回的 verification_id（必须）
   */
  async signupWithPhone(phone: string, code: string, password?: string, verificationId?: string): Promise<CloudBaseAuthResult> {
    if (!this.isInitialized()) {
      return { success: false, error: 'CloudBase not initialized' };
    }

    try {
      const resp = await apiRouter.execute<any>(
        { method: 'cloudbase_phone_signup' },
        { phone, code, password, verification_id: verificationId, role: 'Commander' },
      );

      const data = (resp && (resp as any).data) || (resp && (resp as any).result?.data);
      if (resp?.success && data) {
        const result: CloudBaseAuthResult = {
          success: true,
          data: {
            token: data.token,
            refreshToken: data.refresh_token || data.token,
            userInfo: {
              uuid: data.user_info?.uuid || '',
              phoneNumber: phone,
              loginType: 'phone',
            },
          },
        };
        this.saveAuthResult(result);
        return result;
      }

      return { success: false, error: _formatError(resp, 'Phone signup failed') };
    } catch (error) {
      logger.error('[CloudBaseAuth] Phone signup error:', error);
      return { success: false, error: String(error) };
    }
  }

  /**
   * 发送密码重置验证码
   */
  async sendPasswordResetCode(phone: string): Promise<{ success: boolean; error?: string; devCode?: string; verificationId?: string }> {
    if (!this.isInitialized()) {
      return { success: false, error: 'CloudBase not initialized' };
    }

    try {
      const resp = await apiRouter.execute<any>(
        { method: 'cloudbase_forgot_password' },
        { phone },
      );

      const data = (resp && (resp as any).data) || (resp && (resp as any).result?.data);
      if (resp?.success) {
        // 兼容 CloudBase 两种字段命名（snake_case vs camelCase）
        const verificationId = data?.verification_id || data?.verificationId;
        return {
          success: true,
          devCode: data?.dev_code,
          verificationId,
        };
      }

      return { success: false, error: _formatError(resp, 'Failed to send code') };
    } catch (error) {
      logger.error('[CloudBaseAuth] Send reset code error:', error);
      return { success: false, error: String(error) };
    }
  }

  /**
   * 通过手机验证码重置密码
   * @param verificationId 验证码发送时返回的 verification_id（必须）
   */
  async resetPasswordWithPhone(phone: string, code: string, newPassword: string, verificationId?: string): Promise<{ success: boolean; error?: string }> {
    if (!this.isInitialized()) {
      return { success: false, error: 'CloudBase not initialized' };
    }

    try {
      // Trim phone / code / new_password before sending — autofill
      // / paste / password-manager fields frequently carry leading
      // or trailing whitespace.  Trim everything we send so a stray
      // space can't cause a downstream INVALID_PARAMS / INVALID_CREDENTIALS.
      const resp = await apiRouter.execute<any>(
        { method: 'cloudbase_reset_password' },
        {
          phone: phone.trim(),
          code: code.trim(),
          new_password: newPassword.trim(),
          verification_id: verificationId,
        },
      );

      if (resp?.success) {
        return { success: true };
      }

      return { success: false, error: _formatError(resp, 'Password reset failed') };
    } catch (error) {
      logger.error('[CloudBaseAuth] Reset password error:', error);
      return { success: false, error: String(error) };
    }
  }

  /**
   * 刷新 Token
   */
  async refreshToken(): Promise<{ success: boolean; error?: string }> {
    if (!this._refreshToken) {
      return { success: false, error: 'No refresh token' };
    }

    try {
      const resp = await apiRouter.execute<any>(
        { method: 'cloudbase_refresh_token' },
        { refresh_token: this._refreshToken },
      );

      const data = (resp && (resp as any).data) || (resp && (resp as any).result?.data);
      if (resp?.success && data) {
        this.token = data.token;
        this._refreshToken = data.refresh_token || this._refreshToken;
        localStorage.setItem(STORAGE_KEYS.CLOUDBASE_TOKEN, this.token!);
        localStorage.setItem(STORAGE_KEYS.CLOUDBASE_REFRESH_TOKEN, this._refreshToken!);
        return { success: true };
      }

      return { success: false, error: _formatError(resp, 'Token refresh failed') };
    } catch (error) {
      logger.error('[CloudBaseAuth] Token refresh error:', error);
      return { success: false, error: String(error) };
    }
  }

  /**
   * 登出
   */
  async logout(): Promise<{ success: boolean; error?: string }> {
    if (this.token) {
      try {
        await apiRouter.execute(
          { method: 'cloudbase_logout' },
          { token: this.token },
        );
      } catch (e) {
        logger.warn('[CloudBaseAuth] Logout API call failed:', e);
      }
    }

    this.clearAuthState();
    return { success: true };
  }

  /**
   * Hand a CloudBase access_token (obtained from a hosted login page /
   * OAuth callback) to the backend so it can finalize the session and run
   * the same post-login chain as password login on Intl.
   *
   * The backend takes care of:
   *   - installing tokens into ``AuthManager``
   *   - launching ``MainWindow`` / token_manager / onboarding
   *   - minting an IPC session token
   *   - creating a web session (in web mode)
   *
   * Response shape mirrors ``loginWithEmail`` so the frontend can stay
   * response-shape-identical.
   */
  async finalizeSession(params: {
    access_token: string;
    refresh_token?: string;
    expires_in?: number;
    user_identifier: string;
    user_info?: Record<string, any>;
    role?: string;
    lang?: string;
  }): Promise<CloudBaseAuthResult & { session_id?: string; ipc_token?: string }> {
    if (!this.isInitialized()) {
      return { success: false, error: 'CloudBase not initialized' };
    }

    try {
      const resp = await apiRouter.execute<any>(
        { method: 'cloudbase_finalize_session' },
        {
          access_token: params.access_token,
          refresh_token: params.refresh_token,
          expires_in: params.expires_in ?? 7200,
          user_identifier: params.user_identifier,
          user_info: params.user_info ?? {},
          role: params.role ?? 'Commander',
          lang: params.lang,
        },
      );

      const data = (resp && (resp as any).data) || (resp && (resp as any).result?.data);
      if (resp?.success && data) {
        return {
          success: true,
          data: {
            token: data.token,
            refreshToken: data.refresh_token || data.token,
            userInfo: {
              uuid: data.user_info?.uuid || '',
              email: data.user_info?.email || '',
              username: data.user_info?.username,
              nickname: data.user_info?.name,
              loginType: 'wechat',
            },
          },
          session_id: data.session_id,
          ipc_token: data.token,
        };
      }

      return { success: false, error: _formatError(resp, 'Session finalize failed') };
    } catch (error) {
      logger.error('[CloudBaseAuth] Finalize session error:', error);
      return { success: false, error: String(error) };
    }
  }

  /**
   * 检查 CloudBase 配置
   *
   * Returns ``null`` (instead of ``false``) for ``wechatAvailable`` when the
   * IPC call fails (backend unreachable / handler error).  The caller can
   * then distinguish:
   *
   *   - ``false`` → backend explicitly reports WeChat as not configured.
   *     UI must hide the WeChat tab.
   *   - ``null``  → backend is unreachable (e.g. just after logout, when the
   *     LOCAL GraphQL server is in the middle of restarting).  UI should
   *     keep whatever optimistic state it has and not flicker.
   *
   * ``available`` keeps boolean semantics because the only caller already
   * treats it as a fallback (LoginCN's ``ensureCloudbase`` reads
   * ``appConfig.auth.cloudbase_env_id`` directly, not this flag).
   */
  async checkConfig(): Promise<{
    available: boolean;
    wechatAvailable: boolean | null;
    reason?: string;
    success: boolean;
    config?: {
      hasEnvId: boolean;
      hasCredentials: boolean;
      region: string;
      wechatEnabled: boolean;
    };
  }> {
    try {
      const resp = await apiRouter.execute<any>(
        { method: 'cloudbase_check_config' },
        {},
      );

      const data = (resp && (resp as any).data) || (resp && (resp as any).result?.data);
      const configData = data?.config || {};

      // Treat {success: false} from apiRouter (e.g. HTTP 500 from a
      // server that is mid-shutdown) as "unknown" instead of "off".
      // Returning ``false`` here would let the LoginCN tab flicker off
      // during the post-logout server restart window (regression reported
      // 2026-08-24, see terminals/7.txt:895-985).
      if (!resp || resp.success !== true || !data) {
        return {
          available: false,
          wechatAvailable: null,
          success: false,
          reason: data?.reason || resp?.error?.message || 'IPC unreachable',
          config: {
            hasEnvId: false,
            hasCredentials: false,
            region: configData.region || 'ap-shanghai',
            wechatEnabled: false,
          },
        };
      }

      return {
        available: data.available || false,
        wechatAvailable:
          data.wechat_available ?? configData.wechat_configured ?? false,
        success: true,
        reason: data.reason,
        config: {
          hasEnvId: configData.configured || false,
          hasCredentials: configData.configured || false,
          region: configData.region || 'ap-shanghai',
          wechatEnabled: configData.wechat_login_enabled || false,
        },
      };
    } catch (error) {
      logger.error('[CloudBaseAuth] Check config error:', error);
      return {
        available: false,
        wechatAvailable: null,
        success: false,
        reason: String(error),
        config: {
          hasEnvId: false,
          hasCredentials: false,
          region: 'ap-shanghai',
          wechatEnabled: false,
        },
      };
    }
  }
}

// 导出单例
export const cloudbaseAuth = new CloudBaseAuthService();
export default cloudbaseAuth;
