/**
 * 统一认证提供者 (Auth Provider)
 *
 * 设计原则：
 * 1. 业务代码不直接调用 Cognito/CloudBase SDK
 * 2. 运行时从 AppConfigContext 获取认证类型
 * 3. 前端构建不区分 cn/intl，统一构建
 * 4. 同一套代码，根据后端配置自动选择认证方式
 */

import { logger } from '../../utils/logger';
import { cognitoAuth } from './cognitoAuth';
import { cloudbaseAuth } from './cloudbaseAuth';

/**
 * 统一的用户信息
 */
export interface UnifiedUserInfo {
  uid: string;
  email?: string;
  phone?: string;
  nickname?: string;
  avatar?: string;
  loginType: 'cognito' | 'tcb' | 'anonymous';
}

export interface UnifiedTokens {
  token: string;
  refreshToken?: string;
  idToken?: string;
  expiresAt?: number;
}

export interface UnifiedSession {
  user: UnifiedUserInfo;
  tokens: UnifiedTokens;
}

export type Region = 'cn' | 'intl';

/**
 * 获取当前区域 (基于运行时配置)
 *
 * 同步读取 AppConfig 缓存值；AppConfig 还没加载完时，
 * 根据构建期是否有 VITE_CLOUDBASE_ENV_ID 兜底。
 * 业务侧应通过 useAppConfig() 获取运行时区域。
 */
export function getCurrentRegion(): Region {
  // 1. 运行时配置（来自后端 IPC handler getAppConfig, 由 AppConfigProvider 注入）
  const cached = cachedRegion();
  if (cached) return cached;

  // 2. 构建期兜底：仅在开发期 npm run dev / Web 部署且后端尚未加载时生效。
  //    VITE_APP_ID 是过时的构建期区分方式，构建系统从未设置过它，已不再使用。
  if (import.meta.env.VITE_CLOUDBASE_ENV_ID) {
    return 'cn';
  }
  return 'intl';
}

/**
 * 缓存区域（由 AppConfigContext 注入）
 */
let _cachedRegion: Region | null = null;
function cachedRegion(): Region | null {
  return _cachedRegion;
}
export function setCachedRegion(region: Region | null): void {
  _cachedRegion = region;
}

/**
 * 判断是否已配置认证（运行时配置优先）
 */
export function isAuthConfigured(): boolean {
  const cached = cachedConfig();
  if (cached) {
    if (cached.auth_type === 'cloudbase') return !!cached.cloudbase_env_id;
    if (cached.auth_type === 'cognito') return !!(cached.cognito_domain && cached.cognito_client_id);
  }
  if (import.meta.env.VITE_CLOUDBASE_ENV_ID) return true;
  return !!(import.meta.env.VITE_COGNITO_DOMAIN && import.meta.env.VITE_COGNITO_CLIENT_ID);
}

let _cachedAuthSnapshot: {
  auth_type: 'cloudbase' | 'cognito';
  cloudbase_env_id: string;
  cognito_domain: string;
  cognito_client_id: string;
} | null = null;
function cachedConfig(): typeof _cachedAuthSnapshot {
  return _cachedAuthSnapshot;
}
export function setCachedAuthConfig(snapshot: typeof _cachedAuthSnapshot): void {
  _cachedAuthSnapshot = snapshot;
}

/**
 * 统一认证适配器接口
 */
export interface IAuthAdapter {
  readonly region: Region;
  isConfigured(): boolean;
  initialize(): Promise<void>;
  signInWithEmail(email: string, password: string): Promise<UnifiedSession>;
  signInWithPhone(phone: string, code: string): Promise<UnifiedSession>;
  signUpWithEmail?(email: string, password: string): Promise<void>;
  signUpWithPhone?(phone: string, code: string, password?: string): Promise<UnifiedSession>;
  forgotPassword?(phone: string): Promise<{ devCode?: string }>;
  resetPassword?(phone: string, code: string, newPassword: string): Promise<void>;
  signInWithWechat?(): Promise<UnifiedSession>;
  signOut(): Promise<void>;
  getSession(): Promise<UnifiedSession | null>;
  getAccessToken(): Promise<string | null>;
  refreshSession?(): Promise<UnifiedSession>;
  onAuthStateChanged(callback: (session: UnifiedSession | null) => void): () => void;
}

let currentSession: UnifiedSession | null = null;
const authListeners = new Set<(session: UnifiedSession | null) => void>();

function notifyAuthStateChanged(session: UnifiedSession | null) {
  currentSession = session;
  authListeners.forEach((cb) => cb(session));
}

/**
 * CloudBase 适配器 (CN)
 */
class CloudBaseAuthAdapter implements IAuthAdapter {
  readonly region: Region = 'cn';

  isConfigured(): boolean {
    const cached = cachedConfig();
    if (cached) return !!cached.cloudbase_env_id;
    return !!import.meta.env.VITE_CLOUDBASE_ENV_ID;
  }

  async initialize(): Promise<void> {
    const cached = cachedConfig();
    const envId = cached?.cloudbase_env_id || import.meta.env.VITE_CLOUDBASE_ENV_ID;
    if (!envId) {
      logger.warn('[CloudBaseAuthAdapter] No CloudBase envId configured');
      return;
    }
    await cloudbaseAuth.initialize({ envId });
  }

  async signInWithEmail(email: string, password: string): Promise<UnifiedSession> {
    const result = await cloudbaseAuth.loginWithEmail(email, password);
    if (!result.success || !result.data) {
      throw new Error(result.error || 'CloudBase email login failed');
    }
    const session: UnifiedSession = {
      user: {
        uid: result.data.userInfo.uuid,
        email: result.data.userInfo.email,
        phone: result.data.userInfo.phoneNumber,
        nickname: result.data.userInfo.nickname,
        avatar: result.data.userInfo.avatarUrl,
        loginType: 'tcb',
      },
      tokens: {
        token: result.data.token,
        refreshToken: result.data.refreshToken,
      },
    };
    notifyAuthStateChanged(session);
    return session;
  }

  async signInWithPhone(phone: string, code: string): Promise<UnifiedSession> {
    const result = await cloudbaseAuth.loginWithPhone(phone, code);
    if (!result.success || !result.data) {
      throw new Error(result.error || 'CloudBase phone login failed');
    }
    const session: UnifiedSession = {
      user: {
        uid: result.data.userInfo.uuid,
        email: result.data.userInfo.email,
        phone: result.data.userInfo.phoneNumber,
        nickname: result.data.userInfo.nickname,
        avatar: result.data.userInfo.avatarUrl,
        loginType: 'tcb',
      },
      tokens: {
        token: result.data.token,
        refreshToken: result.data.refreshToken,
      },
    };
    notifyAuthStateChanged(session);
    return session;
  }

  async signUpWithEmail(email: string, password: string): Promise<void> {
    const result = await cloudbaseAuth.signupWithEmail(email, password);
    if (!result.success) {
      throw new Error(result.error || 'CloudBase signup failed');
    }
  }

  async signUpWithPhone(phone: string, code: string, password?: string): Promise<UnifiedSession> {
    const result = await cloudbaseAuth.signupWithPhone(phone, code, password);
    if (!result.success || !result.data) {
      throw new Error(result.error || 'CloudBase phone signup failed');
    }
    const session: UnifiedSession = {
      user: {
        uid: result.data.userInfo.uuid,
        email: result.data.userInfo.email,
        phone: result.data.userInfo.phoneNumber,
        nickname: result.data.userInfo.nickname,
        avatar: result.data.userInfo.avatarUrl,
        loginType: 'tcb',
      },
      tokens: {
        token: result.data.token,
        refreshToken: result.data.refreshToken,
      },
    };
    notifyAuthStateChanged(session);
    return session;
  }

  async forgotPassword(phone: string): Promise<{ devCode?: string }> {
    const result = await cloudbaseAuth.sendPasswordResetCode(phone);
    if (!result.success) {
      throw new Error(result.error || 'Failed to send reset code');
    }
    return { devCode: result.devCode };
  }

  async resetPassword(phone: string, code: string, newPassword: string): Promise<void> {
    const result = await cloudbaseAuth.resetPasswordWithPhone(phone, code, newPassword);
    if (!result.success) {
      throw new Error(result.error || 'Password reset failed');
    }
  }

  async signOut(): Promise<void> {
    await cloudbaseAuth.logout();
    notifyAuthStateChanged(null);
  }

  async getSession(): Promise<UnifiedSession | null> {
    if (currentSession) return currentSession;
    const userInfo = cloudbaseAuth.getUserInfo();
    const token = cloudbaseAuth.getToken();
    if (!userInfo || !token) return null;
    currentSession = {
      user: {
        uid: userInfo.uuid,
        email: userInfo.email,
        phone: userInfo.phoneNumber,
        nickname: userInfo.nickname,
        avatar: userInfo.avatarUrl,
        loginType: 'tcb',
      },
      tokens: { token },
    };
    return currentSession;
  }

  async getAccessToken(): Promise<string | null> {
    return cloudbaseAuth.getToken();
  }

  async refreshSession(): Promise<UnifiedSession> {
    const session = await this.getSession();
    if (!session) throw new Error('No active session');
    const refreshResult = await cloudbaseAuth.refreshToken();
    if (!refreshResult.success) {
      throw new Error(refreshResult.error || 'Failed to refresh token');
    }
    const token = cloudbaseAuth.getToken();
    if (!token) throw new Error('Failed to refresh token');
    session.tokens.token = token;
    notifyAuthStateChanged(session);
    return session;
  }

  onAuthStateChanged(callback: (session: UnifiedSession | null) => void): () => void {
    authListeners.add(callback);
    if (currentSession) callback(currentSession);
    return () => {
      authListeners.delete(callback);
    };
  }
}

/**
 * Cognito 适配器 (Intl)
 */
class CognitoAuthAdapter implements IAuthAdapter {
  readonly region: Region = 'intl';

  isConfigured(): boolean {
    const cached = cachedConfig();
    if (cached) return !!(cached.cognito_domain && cached.cognito_client_id);
    return !!import.meta.env.VITE_COGNITO_DOMAIN && !!import.meta.env.VITE_COGNITO_CLIENT_ID;
  }

  async initialize(): Promise<void> {
    logger.info('[CognitoAuthAdapter] Initialized');
  }

  async signInWithEmail(_email: string, _password: string): Promise<UnifiedSession> {
    throw new Error('Cognito uses Hosted UI. Call startHostedLogin() instead.');
  }

  async signInWithPhone(_phone: string, _code: string): Promise<UnifiedSession> {
    throw new Error('Cognito phone login not directly supported. Use Cognito hosted UI.');
  }

  async signOut(): Promise<void> {
    cognitoAuth.startLogout();
  }

  async getSession(): Promise<UnifiedSession | null> {
    if (currentSession) return currentSession;
    const idToken = localStorage.getItem('cognito_id_token');
    const accessToken = localStorage.getItem('cognito_access_token');
    if (!idToken && !accessToken) return null;

    const payload = cognitoAuth.decodeIdToken(idToken || '');
    currentSession = {
      user: {
        uid: payload.sub || '',
        email: payload.email,
        nickname: payload.name || payload.nickname,
        avatar: payload.picture,
        loginType: 'cognito',
      },
      tokens: {
        token: accessToken || '',
        idToken: idToken || undefined,
        expiresAt: payload.exp ? payload.exp * 1000 : undefined,
      },
    };
    return currentSession;
  }

  async getAccessToken(): Promise<string | null> {
    return localStorage.getItem('cognito_access_token');
  }

  async refreshSession(): Promise<UnifiedSession> {
    const refreshToken = localStorage.getItem('cognito_refresh_token');
    if (!refreshToken) throw new Error('No refresh token available');
    const tokens = await cognitoAuth.refreshTokens(refreshToken);
    if (tokens.access_token) {
      localStorage.setItem('cognito_access_token', tokens.access_token);
    }
    if (tokens.id_token) {
      localStorage.setItem('cognito_id_token', tokens.id_token);
    }
    const session = await this.getSession();
    if (!session) throw new Error('Failed to refresh session');
    notifyAuthStateChanged(session);
    return session;
  }

  onAuthStateChanged(callback: (session: UnifiedSession | null) => void): () => void {
    authListeners.add(callback);
    if (currentSession) callback(currentSession);
    return () => {
      authListeners.delete(callback);
    };
  }
}

let cachedAdapter: IAuthAdapter | null = null;

/**
 * 获取当前区域的认证适配器 (单例)
 *
 * 区域检测顺序：
 *   1. 运行时缓存（由 AppConfigProvider 调用 setCachedRegion 注入）
 *   2. 构建期兜底：是否有 VITE_CLOUDBASE_ENV_ID
 */
export function getAuthAdapter(): IAuthAdapter {
  if (cachedAdapter) return cachedAdapter;

  let region: Region;
  const runtimeRegion = cachedRegion();
  if (runtimeRegion) {
    region = runtimeRegion;
  } else if (import.meta.env.VITE_CLOUDBASE_ENV_ID) {
    region = 'cn';
  } else {
    region = 'intl';
  }

  cachedAdapter = region === 'cn'
    ? new CloudBaseAuthAdapter()
    : new CognitoAuthAdapter();
  logger.info(`[AuthProvider] Using ${region} adapter`);
  return cachedAdapter;
}

/**
 * 获取适配器（异步版本，用于需要等待的场景）
 */
export async function getAuthAdapterAsync(): Promise<IAuthAdapter> {
  return getAuthAdapter();
}

/**
 * 重置缓存 (用于测试或配置变更)
 */
export function resetAuthAdapter(): void {
  cachedAdapter = null;
  currentSession = null;
}
