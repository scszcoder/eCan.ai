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

class CloudBaseAuthService {
  private config: CloudBaseConfig | null = null;
  private token: string | null = null;
  private refreshToken: string | null = null;
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
    return this.refreshToken;
  }

  /**
   * 保存认证结果
   */
  private saveAuthResult(result: CloudBaseAuthResult): boolean {
    if (!result.success || !result.data) {
      return false;
    }

    this.token = result.data.token;
    this.refreshToken = result.data.refreshToken;
    this.userInfo = result.data.userInfo;

    // 持久化到 localStorage
    try {
      localStorage.setItem(STORAGE_KEYS.CLOUDBASE_TOKEN, this.token);
      localStorage.setItem(STORAGE_KEYS.CLOUDBASE_REFRESH_TOKEN, this.refreshToken);
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
        this.refreshToken = refreshToken;
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
    this.refreshToken = null;
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
      const response = await fetch(`${this.config!.endpoint || ''}/api/cloudbase/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, password }),
      });

      const data = await response.json();

      if (data.success && data.data) {
        const result: CloudBaseAuthResult = {
          success: true,
          data: {
            token: data.data.token,
            refreshToken: data.data.token,
            userInfo: {
              uuid: data.data.user_info?.uuid || '',
              email: data.data.user_info?.email || email,
              loginType: 'email',
            },
          },
        };
        this.saveAuthResult(result);
        return result;
      }

      return { success: false, error: data.error?.message || 'Login failed' };
    } catch (error) {
      logger.error('[CloudBaseAuth] Login error:', error);
      return { success: false, error: String(error) };
    }
  }

  /**
   * 手机号验证码登录
   */
  async loginWithPhone(phone: string, code: string): Promise<CloudBaseAuthResult> {
    if (!this.isInitialized()) {
      return { success: false, error: 'CloudBase not initialized' };
    }

    try {
      const response = await fetch(`${this.config!.endpoint || ''}/api/cloudbase/phone-login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ phone, code }),
      });

      const data = await response.json();

      if (data.success && data.data) {
        const result: CloudBaseAuthResult = {
          success: true,
          data: {
            token: data.data.token,
            refreshToken: data.data.token,
            userInfo: {
              uuid: data.data.user_info?.uuid || '',
              phoneNumber: phone,
              loginType: 'phone',
            },
          },
        };
        this.saveAuthResult(result);
        return result;
      }

      return { success: false, error: data.error?.message || 'Phone login failed' };
    } catch (error) {
      logger.error('[CloudBaseAuth] Phone login error:', error);
      return { success: false, error: String(error) };
    }
  }

  /**
   * 发送手机验证码
   */
  async sendPhoneCode(phone: string, purpose: 'login' | 'register' | 'reset_password' = 'login'): Promise<{ success: boolean; error?: string }> {
    if (!this.isInitialized()) {
      return { success: false, error: 'CloudBase not initialized' };
    }

    try {
      const response = await fetch(`${this.config!.endpoint || ''}/api/cloudbase/send-code`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ phone, purpose }),
      });

      const data = await response.json();
      return { success: data.success, error: data.error?.message };
    } catch (error) {
      logger.error('[CloudBaseAuth] Send code error:', error);
      return { success: false, error: String(error) };
    }
  }

  /**
   * 微信登录
   */
  async loginWithWechat(code: string): Promise<CloudBaseAuthResult> {
    if (!this.isInitialized()) {
      return { success: false, error: 'CloudBase not initialized' };
    }

    try {
      const response = await fetch(`${this.config!.endpoint || ''}/api/cloudbase/wechat-login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ code }),
      });

      const data = await response.json();

      if (data.success && data.data) {
        const result: CloudBaseAuthResult = {
          success: true,
          data: {
            token: data.data.token,
            refreshToken: data.data.token,
            userInfo: {
              uuid: data.data.user_info?.uuid || '',
              wxOpenId: data.data.user_info?.openid,
              nickname: data.data.user_info?.name,
              avatarUrl: data.data.user_info?.avatar_url,
              loginType: 'wechat',
            },
          },
        };
        this.saveAuthResult(result);
        return result;
      }

      return { success: false, error: data.error?.message || 'WeChat login failed' };
    } catch (error) {
      logger.error('[CloudBaseAuth] WeChat login error:', error);
      return { success: false, error: String(error) };
    }
  }

  /**
   * 邮箱注册
   */
  async signupWithEmail(email: string, password: string): Promise<{ success: boolean; error?: string }> {
    if (!this.isInitialized()) {
      return { success: false, error: 'CloudBase not initialized' };
    }

    try {
      const response = await fetch(`${this.config!.endpoint || ''}/api/cloudbase/signup`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, password }),
      });

      const data = await response.json();
      return { success: data.success, error: data.error?.message };
    } catch (error) {
      logger.error('[CloudBaseAuth] Signup error:', error);
      return { success: false, error: String(error) };
    }
  }

  /**
   * 刷新 Token
   */
  async refreshToken(): Promise<{ success: boolean; error?: string }> {
    if (!this.refreshToken) {
      return { success: false, error: 'No refresh token' };
    }

    try {
      const response = await fetch(`${this.config?.endpoint || ''}/api/cloudbase/refresh-token`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ refresh_token: this.refreshToken }),
      });

      const data = await response.json();

      if (data.success && data.data) {
        this.token = data.data.token;
        this.refreshToken = data.data.refresh_token || this.refreshToken;
        localStorage.setItem(STORAGE_KEYS.CLOUDBASE_TOKEN, this.token!);
        localStorage.setItem(STORAGE_KEYS.CLOUDBASE_REFRESH_TOKEN, this.refreshToken!);
        return { success: true };
      }

      return { success: false, error: data.error?.message || 'Token refresh failed' };
    } catch (error) {
      logger.error('[CloudBaseAuth] Token refresh error:', error);
      return { success: false, error: String(error) };
    }
  }

  /**
   * 登出
   */
  async logout(): Promise<{ success: boolean; error?: string }> {
    if (!this.token) {
      this.clearAuthState();
      return { success: true };
    }

    try {
      await fetch(`${this.config?.endpoint || ''}/api/cloudbase/logout`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ token: this.token }),
      });
    } catch (e) {
      logger.warn('[CloudBaseAuth] Logout API call failed:', e);
    }

    this.clearAuthState();
    return { success: true };
  }

  /**
   * 检查 CloudBase 配置
   */
  async checkConfig(): Promise<{
    available: boolean;
    reason?: string;
    config?: {
      hasEnvId: boolean;
      hasCredentials: boolean;
      region: string;
      wechatEnabled: boolean;
    };
  }> {
    try {
      const response = await fetch(`${this.config?.endpoint || ''}/api/cloudbase/check-config`);
      const data = await response.json();
      return {
        available: data.data?.available || false,
        reason: data.data?.reason,
        config: {
          hasEnvId: data.data?.has_env_id || false,
          hasCredentials: data.data?.has_credentials || false,
          region: data.data?.region || 'ap-guangzhou',
          wechatEnabled: data.data?.wechat_enabled || false,
        },
      };
    } catch (error) {
      logger.error('[CloudBaseAuth] Check config error:', error);
      return { available: false, reason: String(error) };
    }
  }
}

// 导出单例
export const cloudbaseAuth = new CloudBaseAuthService();
export default cloudbaseAuth;
