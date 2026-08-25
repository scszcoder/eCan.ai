/**
 * 应用配置上下文
 *
 * 运行时从后端拉取所有配置。前端只关心：
 *   app_id / is_cn / auth_type + auth{cloudbase,wechat,cognito}
 *
 * 真值源：
 * - desktop 模式（file:// 或 localhost）：IPC handler `getAppConfig`
 *   （gui/ipc/w2p_handlers/app_config_handler.py），通过 apiRouter.execute 调用。
 * - web 部署：web_server.py 的 GET /api/config（同源 fetch），由 ECAN_APP_ID 派生。
 *
 * 双路径原因：web 部署下前端没有"后端进程"的 IPC 通道（没有 Qt WebChannel，
 * 走 web_server 的 WebSocket 是异步通道），用同源 fetch 拿一次性配置最简单。
 */

import React, { createContext, useContext, useEffect, useState } from 'react';
import { detectPlatform } from '../config/platform';
import { setCachedRegion, setCachedAuthConfig } from '../services/auth/AuthProvider';

export interface AuthConfig {
  // CloudBase (CN)
  cloudbase_env_id: string;
  wechat_app_id: string;
  // Cognito (Intl)
  cognito_domain: string;
  cognito_client_id: string;
}

export interface AppConfig {
  // Identity
  app_id: string;
  is_cn: boolean;
  auth_type: 'cloudbase' | 'cognito';

  // Auth
  auth: AuthConfig;
}

interface AppConfigContextValue {
  config: AppConfig | null;
  loading: boolean;
  error: Error | null;
  refetch: () => void;
}

const AppConfigContext = createContext<AppConfigContextValue | null>(null);

/**
 * Module-level cache of the latest config snapshot. Components use
 * useAppConfig() for the live value; non-React code (e.g. early
 * bootstrap, WebSocket subscription managers) reads this synchronously.
 * Populated by AppConfigProvider on every config update.
 */
let _cachedConfig: AppConfig | null = null;
export function getCachedAppConfig(): AppConfig | null {
  return _cachedConfig;
}

/**
 * Normalize payload from either source (IPC handler `getAppConfig` or
 * web_server `/api/config`) into the AppConfig shape the frontend uses.
 * Both sources return auth/cloudbase_wechat/cognito fields; web_server
 * additionally returns legacy platform/api_base/ws_url/cognito_*_uri
 * fields which we ignore (frontend doesn't consume them).
 */
function normalize(raw: any): AppConfig {
  const auth = (raw && raw.auth) || {};
  return {
    app_id: raw?.app_id ?? 'intl',
    is_cn: !!raw?.is_cn,
    auth_type: raw?.auth_type === 'cloudbase' ? 'cloudbase' : 'cognito',
    auth: {
      cloudbase_env_id: auth.cloudbase_env_id || '',
      wechat_app_id: auth.wechat_app_id || '',
      cognito_domain: auth.cognito_domain || '',
      cognito_client_id: auth.cognito_client_id || '',
    },
  };
}

/**
 * Pull runtime AppConfig:
 * - desktop: apiRouter.execute({method: 'getAppConfig'}) → IPC handler
 * - web: fetch('/api/config') → web_server.py (same-origin)
 */
async function fetchConfig(): Promise<AppConfig> {
  const platform = (() => {
    try { return detectPlatform(); } catch { return 'web' as const; }
  })();

  if (platform === 'web') {
    const resp = await fetch('/api/config', { credentials: 'same-origin' });
    if (!resp.ok) {
      throw new Error(`/api/config HTTP ${resp.status}`);
    }
    return normalize(await resp.json());
  }

  const { apiRouter } = await import('../services/api/api-router');
  const out = await apiRouter.execute<any>(
    { method: 'getAppConfig' },
    {},
  );
  if (!out.success || !out.data) {
    throw new Error(
      `getAppConfig failed: ${out.error?.code ?? 'UNKNOWN'} ${out.error?.message ?? ''}`,
    );
  }
  return normalize(out.data);
}

/**
 * 应用配置 Provider
 */
export function AppConfigProvider({ children }: { children: React.ReactNode }) {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  // Tunables for the "backend not ready yet" retry.  When the user
  // refreshes the page mid-startup, the very first ``getAppConfig`` call
  // hits the LOCAL GraphQL server while uvicorn is still binding the
  // port, so it fails.  Without retry we'd fall back to the
  // intl/cognito empty config and the login route would render LoginIntl
  // forever — even once the backend wakes up.  See terminals/1.txt
  // (`ECONNREFUSED` from Vite proxy) for the failure mode.
  //
  // Total wait: 1.5s + 3s + 6s + 12s ≈ 22.5s, which covers the worst
  // observed backend startup.  After that we give up and use the
  // fallback so the user at least sees SOMETHING (better than a stuck
  // spinner); the AppConfigProvider exposes ``refetch`` so the LoginCN
  // mount can kick another fetch once backend is reachable.
  const RETRY_DELAYS_MS = [1500, 3000, 6000, 12000];

  const loadConfig = async () => {
    setLoading(true);
    setError(null);
    try {
      let lastErr: unknown = null;
      for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt++) {
        try {
          const data = await fetchConfig();
          setConfig(data);
          _cachedConfig = data;
          setError(null);
          return;
        } catch (err) {
          lastErr = err;
          const isLastAttempt = attempt === RETRY_DELAYS_MS.length;
          if (isLastAttempt) {
            throw err;
          }
          const delay = RETRY_DELAYS_MS[attempt];
          console.warn(
            `[AppConfig] fetchConfig attempt ${attempt + 1} failed ` +
              `(retrying in ${delay}ms):`,
            err,
          );
          await new Promise((resolve) => setTimeout(resolve, delay));
        }
      }
      // Unreachable — the loop either returns or throws on the last
      // attempt.  Keep TS happy.
      throw lastErr;
    } catch (err) {
      console.error('[AppConfig] Failed to load config:', err);
      setError(err instanceof Error ? err : new Error(String(err)));
      // 兜底：后端不可达时用 intl/cognito。后端真值源恢复后即被覆盖。
      //
      // IMPORTANT: this fallback is what previously caused
      // "刷新页面显示 LoginIntl 但后端是 CN" — once we wrote the
      // fallback, ``useLoginComponent`` saw ``auth_type === 'cognito'``
      // and rendered LoginIntl forever, even after the backend woke up.
      //
      // The route fix in ``routes/index.tsx`` (``useLoginComponent``
      // returns null while loading) means the spinner keeps showing
      // during the retry loop above.  If we reach this catch block
      // (all retries exhausted) the spinner finally gives way to the
      // fallback config — and ``refetch`` is wired so the user can
      // retry by reloading or by code paths that detect backend ready.
      const fallback: AppConfig = {
        app_id: 'intl',
        is_cn: false,
        auth_type: 'cognito',
        auth: {
          cloudbase_env_id: '',
          wechat_app_id: '',
          cognito_domain: '',
          cognito_client_id: '',
        },
      };
      setConfig(fallback);
      _cachedConfig = fallback;
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
      auth_type: config.auth_type,
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
 * 便捷钩子：获取认证类型
 */
export function useAuthType(): 'cloudbase' | 'cognito' {
  const { config } = useAppConfig();
  return config?.auth_type || 'cognito';
}

/**
 * 便捷钩子：是否 CN 版本
 * 
 * 注意：config 加载前返回 false，应用应处理 loading 状态。
 * 如需在加载期间阻止渲染，请使用 useConfigLoading()。
 */
export function useIsCN(): boolean {
  const { config } = useAppConfig();
  return config?.is_cn || false;
}

/**
 * 便捷钩子：获取当前区域
 * 返回 'cn' | 'intl'，config 加载前返回 'intl' 作为默认值。
 */
export function useRegion(): 'cn' | 'intl' {
  const { config } = useAppConfig();
  return config?.is_cn ? 'cn' : 'intl';
}

/**
 * 便捷钩子：配置是否正在加载
 */
export function useConfigLoading(): boolean {
  const { loading } = useAppConfig();
  return loading;
}

/**
 * 同步获取当前区域（从模块级缓存）
 * 适用于非 React 上下文（如 WebSocket 订阅管理器）
 */
export function getRegionSync(): 'cn' | 'intl' {
  const cached = getCachedAppConfig();
  return cached?.is_cn ? 'cn' : 'intl';
}