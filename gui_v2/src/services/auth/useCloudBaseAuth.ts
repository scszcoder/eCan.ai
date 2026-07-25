/**
 * CloudBase Authentication Hook
 * 腾讯云 CloudBase 认证集成 Hook
 *
 * 提供统一的认证接口，屏蔽 CloudBase/Cognito 的差异
 */

import { useState, useCallback, useEffect } from 'react';
import { cloudbaseAuth, type CloudBaseUserInfo } from './cloudbaseAuth';
import { userStorageManager, type LoginSession } from '../storage/UserStorageManager';
import { tokenRefreshService } from './tokenRefreshService';
import { pageRefreshManager } from '../events/PageRefreshManager';
import { logger } from '../../utils/logger';
import { useAppConfig } from '../../contexts/AppConfigContext';

/** 检查 CloudBase 是否可用 */
const isCloudBaseAvailable = (envId?: string): boolean => {
  return !!envId;
};

export interface UseCloudBaseAuthOptions {
  /** 登录成功回调 */
  onLoginSuccess?: (session: LoginSession) => void;
  /** 登录失败回调 */
  onLoginError?: (error: string) => void;
  /** 登出回调 */
  onLogout?: () => void;
}

export interface UseCloudBaseAuthReturn {
  /** 是否正在初始化 */
  isInitializing: boolean;
  /** 是否已登录 */
  isLoggedIn: boolean;
  /** CloudBase 是否可用 */
  isCloudBaseAvailable: boolean;
  /** 当前用户信息 */
  currentUser: CloudBaseUserInfo | null;
  /** 是否正在登录 */
  isLoggingIn: boolean;
  /** 登录进度状态 */
  loginProgress: 'idle' | 'authenticating' | 'success' | 'redirecting';
  /** 登录进度文本 */
  loginProgressText: string;

  // 登录方法
  /** 邮箱密码登录 */
  loginWithEmail: (email: string, password: string, role?: string) => Promise<boolean>;
  /** 手机号验证码登录 */
  loginWithPhone: (phone: string, code: string, role?: string) => Promise<boolean>;
  /** 发送手机验证码 */
  sendPhoneCode: (phone: string, purpose?: 'login' | 'register' | 'reset_password') => Promise<boolean>;
  /** 微信登录 */
  loginWithWechat: (code: string, role?: string) => Promise<boolean>;
  /** 邮箱注册 */
  signupWithEmail: (email: string, password: string) => Promise<boolean>;
  /** 登出 */
  logout: () => Promise<void>;
  /** 刷新 Token */
  refreshToken: () => Promise<boolean>;

  // 状态设置方法
  setLoginProgress: (progress: 'idle' | 'authenticating' | 'success' | 'redirecting') => void;
  setLoginProgressText: (text: string) => void;
  setIsLoggingIn: (value: boolean) => void;
}

/**
 * CloudBase 认证 Hook
 *
 * @param options - 配置选项
 * @returns 认证状态和方法
 */
export function useCloudBaseAuth(options: UseCloudBaseAuthOptions = {}): UseCloudBaseAuthReturn {
  const [isInitializing, setIsInitializing] = useState(true);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [currentUser, setCurrentUser] = useState<CloudBaseUserInfo | null>(null);
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [loginProgress, setLoginProgress] = useState<'idle' | 'authenticating' | 'success' | 'redirecting'>('idle');
  const [loginProgressText, setLoginProgressText] = useState('');

  // 公开配置从运行时 /api/config（后端 auth_config.yml）读取
  const { config: appConfig } = useAppConfig();
  const cloudBaseEnvId = appConfig?.auth?.cloudbase_env_id || '';

  // 检查 CloudBase 是否可用
  const cloudBaseAvailable = isCloudBaseAvailable(cloudBaseEnvId);

  // 初始化
  useEffect(() => {
    const init = async () => {
      if (!cloudBaseAvailable) {
        logger.info('[CloudBaseAuth] CloudBase not available');
        setIsInitializing(false);
        return;
      }

      try {
        // 初始化配置
        cloudbaseAuth.initialize({ envId: cloudBaseEnvId });

        // 检查配置
        const configResult = await cloudbaseAuth.checkConfig();
        if (!configResult.available) {
          logger.warn('[CloudBaseAuth] CloudBase not configured:', configResult.reason);
          setIsInitializing(false);
          return;
        }

        // 尝试恢复登录状态
        if (cloudbaseAuth.restoreAuthState()) {
          const userInfo = cloudbaseAuth.getUserInfo();
          setCurrentUser(userInfo);
          setIsLoggedIn(true);
          logger.info('[CloudBaseAuth] Restored login state');
        }

        logger.info('[CloudBaseAuth] CloudBase initialized successfully');
      } catch (error) {
        logger.error('[CloudBaseAuth] Init error:', error);
      } finally {
        setIsInitializing(false);
      }
    };

    init();
  }, [cloudBaseAvailable, cloudBaseEnvId]);

  /**
   * 保存登录会话
   */
  const saveLoginSession = useCallback((token: string, userInfo: CloudBaseUserInfo, role: string) => {
    const session: LoginSession = {
      token,
      userInfo: {
        username: userInfo.email || userInfo.phoneNumber || userInfo.customUserId || '',
        email: userInfo.email || '',
        role,
        name: userInfo.nickname || '',
        given_name: '',
        family_name: '',
        picture: userInfo.avatarUrl || '',
        login_type: 'password',
      },
      loginTime: Date.now(),
    };

    userStorageManager.saveLoginSession(session);
    pageRefreshManager.enable();

    // 启动 Token 刷新服务
    tokenRefreshService.start(token, {
      checkInterval: 30 * 60 * 1000,
      refreshThreshold: 60 * 60,
      onTokenRefreshed: (newToken: string) => {
        logger.info('[CloudBaseAuth] Token refreshed');
        userStorageManager.setToken(newToken);
      },
      onTokenExpired: () => {
        logger.warn('[CloudBaseAuth] Token expired');
        userStorageManager.logout();
        options.onLogout?.();
      },
    });

    options.onLoginSuccess?.(session);
  }, [options]);

  /**
   * 邮箱密码登录
   */
  const loginWithEmail = useCallback(async (email: string, password: string, role: string = 'Commander'): Promise<boolean> => {
    setIsLoggingIn(true);
    setLoginProgress('authenticating');

    try {
      const result = await cloudbaseAuth.loginWithEmail(email, password);

      if (result.success && result.data) {
        const { token, userInfo } = result.data;
        setCurrentUser(userInfo);
        setIsLoggedIn(true);
        setLoginProgress('success');
        saveLoginSession(token, userInfo, role);
        return true;
      }

      options.onLoginError?.(result.error || 'Login failed');
      return false;
    } catch (error) {
      logger.error('[CloudBaseAuth] Login error:', error);
      options.onLoginError?.(String(error));
      return false;
    } finally {
      setIsLoggingIn(false);
    }
  }, [saveLoginSession, options]);

  /**
   * 发送手机验证码
   */
  const sendPhoneCode = useCallback(async (
    phone: string,
    purpose: 'login' | 'register' | 'reset_password' = 'login'
  ): Promise<boolean> => {
    try {
      const result = await cloudbaseAuth.sendPhoneCode(phone, purpose);
      return result.success;
    } catch (error) {
      logger.error('[CloudBaseAuth] Send code error:', error);
      return false;
    }
  }, []);

  /**
   * 手机号验证码登录
   */
  const loginWithPhone = useCallback(async (phone: string, code: string, role: string = 'Commander'): Promise<boolean> => {
    setIsLoggingIn(true);
    setLoginProgress('authenticating');

    try {
      const result = await cloudbaseAuth.loginWithPhone(phone, code);

      if (result.success && result.data) {
        const { token, userInfo } = result.data;
        setCurrentUser(userInfo);
        setIsLoggedIn(true);
        setLoginProgress('success');
        saveLoginSession(token, userInfo, role);
        return true;
      }

      options.onLoginError?.(result.error || 'Phone login failed');
      return false;
    } catch (error) {
      logger.error('[CloudBaseAuth] Phone login error:', error);
      options.onLoginError?.(String(error));
      return false;
    } finally {
      setIsLoggingIn(false);
    }
  }, [saveLoginSession, options]);

  /**
   * 微信登录
   */
  const loginWithWechat = useCallback(async (code: string, role: string = 'Commander'): Promise<boolean> => {
    setIsLoggingIn(true);
    setLoginProgress('authenticating');

    try {
      const result = await cloudbaseAuth.loginWithWechat(code);

      if (result.success && result.data) {
        const { token, userInfo } = result.data;
        setCurrentUser(userInfo);
        setIsLoggedIn(true);
        setLoginProgress('success');
        saveLoginSession(token, userInfo, role);
        return true;
      }

      options.onLoginError?.(result.error || 'WeChat login failed');
      return false;
    } catch (error) {
      logger.error('[CloudBaseAuth] WeChat login error:', error);
      options.onLoginError?.(String(error));
      return false;
    } finally {
      setIsLoggingIn(false);
    }
  }, [saveLoginSession, options]);

  /**
   * 邮箱注册
   */
  const signupWithEmail = useCallback(async (email: string, password: string): Promise<boolean> => {
    setIsLoggingIn(true);

    try {
      const result = await cloudbaseAuth.signupWithEmail(email, password);
      return result.success;
    } catch (error) {
      logger.error('[CloudBaseAuth] Signup error:', error);
      return false;
    } finally {
      setIsLoggingIn(false);
    }
  }, []);

  /**
   * 登出
   */
  const logout = useCallback(async (): Promise<void> => {
    try {
      await cloudbaseAuth.logout();
      tokenRefreshService.stop();
      pageRefreshManager.disable();
      setCurrentUser(null);
      setIsLoggedIn(false);
      setLoginProgress('idle');
      options.onLogout?.();
    } catch (error) {
      logger.error('[CloudBaseAuth] Logout error:', error);
    }
  }, [options]);

  /**
   * 刷新 Token
   */
  const refreshToken = useCallback(async (): Promise<boolean> => {
    try {
      const result = await cloudbaseAuth.refreshToken();
      return result.success;
    } catch (error) {
      logger.error('[CloudBaseAuth] Refresh token error:', error);
      return false;
    }
  }, []);

  return {
    isInitializing,
    isLoggedIn,
    isCloudBaseAvailable: cloudBaseAvailable,
    currentUser,
    isLoggingIn,
    loginProgress,
    loginProgressText,
    loginWithEmail,
    loginWithPhone,
    sendPhoneCode,
    loginWithWechat,
    signupWithEmail,
    logout,
    refreshToken,
    setLoginProgress,
    setLoginProgressText,
    setIsLoggingIn,
  };
}

export default useCloudBaseAuth;
