/**
 * 应用配置上下文
 *
 * 运行时从后端 /api/config 获取所有配置
 * 前端不再需要 .env 文件
 */

import React, { createContext, useContext, useEffect, useState } from 'react';
import { setCachedRegion, setCachedAuthConfig } from '../services/auth/AuthProvider';

export interface AuthConfig {
  // CloudBase (CN)
  cloudbase_env_id: string;
  wechat_app_id: string;
  // Cognito (Intl)
  cognito_domain: string;
  cognito_client_id: string;
  cognito_redirect_uri: string;
  cognito_logout_uri: string;
  cognito_scopes: string;
}

export interface PlatformInfo {
  is_desktop: boolean;
  system: string;
  hostname: string;
}

export interface AppConfig {
  // Identity
  app_id: string;
  is_cn: boolean;
  auth_type: 'cloudbase' | 'cognito';

  // Cloud endpoints (from auth_config.yml APPSYNC.*, no hardcoded)
  graphql_endpoint: string;
  ws_endpoint: string;
  ws_host: string;

  // Legacy endpoint fields
  api_base: string;
  ws_url: string;

  // Auth
  auth: AuthConfig;

  // Platform
  platform: PlatformInfo;
}

interface AppConfigContextValue {
  config: AppConfig | null;
  loading: boolean;
  error: Error | null;
  refetch: () => void;
}

const AppConfigContext = createContext<AppConfigContextValue | null>(null);

/**
 * 获取配置接口地址
 */
function getConfigEndpoint(): string {
  // 桌面应用：前端在 localhost:3000，后端在 localhost:4668
  // Web 部署：前端和后端在同一域名
  if (typeof window !== 'undefined') {
    const isDesktop = window.location.port === '3000' ||
                       window.location.protocol === 'file:';

    if (isDesktop) {
      // 桌面应用：直接请求后端 API
      const apiBase = import.meta.env.VITE_API_BASE || 'http://localhost:4668';
      return `${apiBase}/api/config`;
    }

    // Web 部署：使用当前域名
    const protocol = window.location.protocol;
    const host = window.location.host;
    return `${protocol}//${host}/api/config`;
  }

  // Node 环境
  return import.meta.env.VITE_API_BASE
    ? `${import.meta.env.VITE_API_BASE}/api/config`
    : '/api/config';
}

/**
 * 获取 API 和 WS 地址
 */
function getEndpoints(config: AppConfig): { apiBase: string; wsUrl: string } {
  if (config.platform.is_desktop) {
    // 桌面版：使用后端返回的本地地址
    return {
      apiBase: config.api_base,
      wsUrl: config.ws_url,
    };
  }
  // Web 版：使用当前域名
  const protocol = window.location.protocol;
  const host = window.location.host;
  return {
    apiBase: `${protocol}//${host}`,
    wsUrl: config.ws_url,
  };
}

async function fetchConfig(): Promise<AppConfig> {
  const endpoint = getConfigEndpoint();
  const response = await fetch(endpoint);
  if (!response.ok) {
    throw new Error(`Failed to fetch config: ${response.status}`);
  }
  return response.json();
}

/**
 * 应用配置 Provider
 */
export function AppConfigProvider({ children }: { children: React.ReactNode }) {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const loadConfig = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchConfig();
      setConfig(data);
    } catch (err) {
      console.error('[AppConfig] Failed to load config:', err);
      setError(err instanceof Error ? err : new Error(String(err)));
      // 使用默认配置（intl/cognito）
      setConfig({
        app_id: 'intl',
        is_cn: false,
        auth_type: 'cognito',
        api_base: import.meta.env.VITE_API_BASE || 'http://localhost:4668',
        ws_url: import.meta.env.VITE_WS_URL || 'ws://localhost:8765',
        auth: {
          cloudbase_env_id: import.meta.env.VITE_CLOUDBASE_ENV_ID || '',
          wechat_app_id: import.meta.env.VITE_WECHAT_APP_ID || '',
          cognito_domain: import.meta.env.VITE_COGNITO_DOMAIN || '',
          cognito_client_id: import.meta.env.VITE_COGNITO_CLIENT_ID || '',
          cognito_redirect_uri: import.meta.env.VITE_COGNITO_REDIRECT_URI || 'http://localhost:3000/auth/callback',
          cognito_logout_uri: import.meta.env.VITE_COGNITO_LOGOUT_URI || 'http://localhost:3000/login',
          cognito_scopes: import.meta.env.VITE_COGNITO_SCOPES || 'openid email profile',
        },
        platform: {
          is_desktop: false,
          system: 'unknown',
          hostname: 'unknown',
        },
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadConfig();
  }, []);

  // 把运行时配置注入到 AuthProvider 模块级缓存，
  // 让 getAuthAdapter() 这类同步 API 也能拿到正确的区域 / 认证配置。
  useEffect(() => {
    if (!config) return;
    const region = config.is_cn ? 'cn' : 'intl';
    setCachedRegion(region);
    setCachedAuthConfig({
      cloudbase_env_id: config.auth.cloudbase_env_id,
      cognito_domain: config.auth.cognito_domain,
      cognito_client_id: config.auth.cognito_client_id,
    });
  }, [config]);

  return (
    <AppConfigContext.Provider value={{ config, loading, error, refetch: loadConfig }}>
      {children}
    </AppConfigContext.Provider>
  );
}

/**
 * 使用应用配置
 */
export function useAppConfig(): AppConfigContextValue {
  const context = useContext(AppConfigContext);
  if (!context) {
    throw new Error('useAppConfig must be used within AppConfigProvider');
  }
  return context;
}

/**
 * 便捷钩子：获取 API 端点
 */
export function useEndpoints() {
  const { config } = useAppConfig();
  if (!config) return { apiBase: '', wsUrl: '' };
  return getEndpoints(config);
}

/**
 * 便捷钩子：获取认证类型
 */
export function useAuthType(): 'cloudbase' | 'cognito' {
  const { config } = useAppConfig();
  return config?.auth_type || 'cognito';
}

/**
 * 便捷钩子：是否 CN 版本
 */
export function useIsCN(): boolean {
  const { config } = useAppConfig();
  return config?.is_cn || false;
}
