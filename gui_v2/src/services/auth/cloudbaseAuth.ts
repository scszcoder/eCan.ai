/**
 * CloudBase Authentication Service
 * 腾讯云 CloudBase 认证服务前端 SDK
 *
 * 支持的登录方式：
 * 1. 邮箱密码登录
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
      const resp = await apiRouter.execute<any>(
        { method: 'cloudbase_login' },
        { email, password, role: 'Commander' },
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
      const resp = await apiRouter.execute<any>(
        { method: 'cloudbase_phone_login' },
        { phone, code, verification_id: verificationId, role: 'Commander' },
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

      return { success: false, error: _formatError(resp, 'Phone login failed') };
    } catch (error) {
      logger.error('[CloudBaseAuth] Phone login error:', error);
      return { success: false, error: String(error) };
    }
  }

  /**
   * 发送手机验证码
   */
  async sendPhoneCode(phone: string, purpose: 'login' | 'register' | 'reset_password' = 'login'): Promise<{ success: boolean; error?: string; devCode?: string; verificationId?: string }> {
    if (!this.isInitialized()) {
      return { success: false, error: 'CloudBase not initialized' };
    }

    try {
      const resp = await apiRouter.execute<any>(
        { method: 'cloudbase_send_code' },
        { phone, purpose },
      );

      const data = (resp && (resp as any).data) || (resp && (resp as any).result?.data);
      if (resp?.success && data) {
        return {
          success: true,
          devCode: data.dev_code,  // 仅开发模式返回
          verificationId: data.verification_id,
        };
      }

      return { success: false, error: _formatError(resp, 'Failed to send code') };
    } catch (error) {
      logger.error('[CloudBaseAuth] Send code error:', error);
      return { success: false, error: String(error) };
    }
  }


  /**
   * 使用 CloudBase 托管登录页进行微信登录（推荐，无需备案域名）
   *
   * 流程：
   * 1. 调用 CloudBase 提供的链接（CloudBase 已自动管理回调域名）
   * 2. 用户扫码授权后 CloudBase 处理回调
   * 3. 通过 URL 参数把 token 返回到前端
   */
  async loginWithCloudBaseWechat(redirectUri: string): Promise<CloudBaseAuthResult> {
    if (!this.isInitialized()) {
      return { success: false, error: 'CloudBase not initialized' };
    }

    try {
      // 保存跳转前的路径，登录成功后跳回来
      sessionStorage.setItem('wechat_login_redirect', redirectUri || window.location.origin);

      // 用 CSRF token 作为 state
      const state = Math.random().toString(36).slice(2);
      sessionStorage.setItem('wx_state', state);

      // 调后端获取微信授权 URI（必须传 redirect_uri，否则 CloudBase 返回的 URI 缺少回调地址，
      // 会导致微信回调时报 "redirect_uri 参数错误"）
      const resp = await apiRouter.execute<any>(
        { method: 'cloudbase_wechat_h5_login' },
        { state, redirect_uri: redirectUri || window.location.origin },
      );

      if (resp?.success && resp?.data?.url) {
        logger.info('[CloudBaseAuth] Redirecting to CloudBase WeChat login');
        window.location.href = resp.data.url;
        return { success: true };
      }

      return { success: false, error: _formatError(resp, 'Failed to get login URL') };
    } catch (error) {
      logger.error('[CloudBaseAuth] CloudBase WeChat login error:', error);
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
      const resp = await apiRouter.execute<any>(
        { method: 'cloudbase_signup' },
        { email, password },
      );

      const data = (resp && (resp as any).data) || (resp && (resp as any).result?.data);
      if (resp?.success) {
        return {
          success: true,
          verificationId: data?.verification_id,
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
      const resp = await apiRouter.execute<any>(
        { method: 'cloudbase_signup_confirm' },
        { email, code, verification_id: verificationId, password },
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
        return {
          success: true,
          devCode: data?.dev_code,
          verificationId: data?.verification_id,
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
      const resp = await apiRouter.execute<any>(
        { method: 'cloudbase_reset_password' },
        { phone, code, new_password: newPassword, verification_id: verificationId },
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
   * 检查 CloudBase 配置
   */
  async checkConfig(): Promise<{
    available: boolean;
    wechatAvailable: boolean;
    reason?: string;
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
      return {
        available: data?.available || false,
        wechatAvailable: data?.wechat_available || configData.wechat_configured || false,
        reason: data?.reason,
        config: {
          hasEnvId: configData.configured || false,
          hasCredentials: configData.configured || false,
          region: configData.region || 'ap-guangzhou',
          wechatEnabled: configData.wechat_login_enabled || false,
        },
      };
    } catch (error) {
      logger.error('[CloudBaseAuth] Check config error:', error);
      return { available: false, wechatAvailable: false, reason: String(error) };
    }
  }
}

// 导出单例
export const cloudbaseAuth = new CloudBaseAuthService();
export default cloudbaseAuth;
