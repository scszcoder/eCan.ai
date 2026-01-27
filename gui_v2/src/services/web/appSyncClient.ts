import { webAuthSession } from '../auth/webAuthSession';
import { getSettings } from '../../stores/settingsStore';
import { userStorageManager } from '../storage/UserStorageManager';
import { detectPlatform } from '../../config/platform';

interface GraphQLError {
  message: string;
  [key: string]: any;
}

interface GraphQLResponse<T> {
  data?: T;
  errors?: GraphQLError[];
}

export type AppSyncAuthMode = 'auto' | 'bearer' | 'apiKey' | 'none';

export interface AppSyncRequestOptions {
  authMode?: AppSyncAuthMode;
  apiKey?: string;
  /** GraphQL 操作名称 */
  operationName?: string;
  /** 自定义扩展字段 */
  extensions?: Record<string, any>;
}

const getEnv = () => {
  try {
    if (typeof import.meta !== 'undefined' && (import.meta as any).env) {
      return (import.meta as any).env as Record<string, any>;
    }
  } catch {}
  return {} as Record<string, any>;
};

const isTruthyEnvValue = (value: unknown): boolean => {
  const normalized = String(value ?? '').trim().toLowerCase();
  return normalized === '1' || normalized === 'true' || normalized === 'yes' || normalized === 'on';
};

// Check if we should use local server (desktop + VITE_IPC_MODE OFF)
const shouldUseLocalServer = (): boolean => {
  const platform = detectPlatform();
  if (platform !== 'desktop') return false;
  
  const env = getEnv();
  const ipcModeOn = isTruthyEnvValue(env.VITE_IPC_MODE);
  // Use local server when on desktop AND IPC mode is OFF
  return !ipcModeOn;
};

const getLocalServerEndpoint = (): string => {
  // In dev mode, prefer same-origin path so Vite proxy can handle forwarding.
  try {
    if (typeof import.meta !== 'undefined' && (import.meta as any).env?.DEV) {
      return '/graphql';
    }
  } catch {}
  const settings = getSettings();
  const port = settings?.local_server_port || '4668';
  return `http://localhost:${port}/graphql`;
};

const getAppSyncEndpoint = (): string => {
  const env = getEnv();
  // Try env var first, then fall back to settings
  const fromEnv = (env.VITE_APPSYNC_ENDPOINT as string) || '';
  if (fromEnv) return fromEnv;
  
  const settings = getSettings();
  return (settings?.wan_api_endpoint || '').trim();
};

const getAppSyncApiKey = (overrideKey?: string): string => {
  if (overrideKey) return overrideKey;
  const env = (typeof import.meta !== 'undefined' && import.meta.env) ? import.meta.env : {};
  const settings = getSettings();
  const fromSettings = settings?.wan_api_key || settings?.api_key;
  return (fromSettings || env.VITE_APPSYNC_API_KEY || '').trim();
};

export const appSyncRequest = async <T>(
  query: string,
  variables?: Record<string, any>,
  options?: AppSyncRequestOptions,
  method?: string
): Promise<T> => {
  // Determine endpoint: local server (desktop + IPC mode OFF) or AppSync (web / desktop + IPC mode ON)
  const useLocalServer = shouldUseLocalServer();
  const endpoint = useLocalServer ? getLocalServerEndpoint() : getAppSyncEndpoint();
  
  if (!endpoint) {
    console.error('[AppSyncClient] No endpoint available. Check VITE_APPSYNC_ENDPOINT or settings.wan_api_endpoint');
    throw new Error('AppSync endpoint missing. Set VITE_APPSYNC_ENDPOINT or configure wan_api_endpoint in settings.');
  }

  const headers: Record<string, string> = {
    'Content-Type': 'application/json'
  };

  // Local server doesn't need authentication
  if (useLocalServer) {
    console.log('[AppSyncClient] Using local server (no auth):', endpoint);
    const token = userStorageManager.getToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
  } else {
    // AppSync needs authentication
    const accessToken = userStorageManager.getToken();
    const apiKey = getAppSyncApiKey(options?.apiKey);
    const authMode = options?.authMode ?? 'auto';

    if (authMode === 'apiKey') {
      if (!apiKey) {
        throw new Error('Missing API key for AppSync request.');
      }
      headers['x-api-key'] = apiKey;
    } else if (authMode === 'bearer') {
      if (!accessToken) {
        throw new Error('Missing access token for AppSync request.');
      }
      headers.Authorization = `Bearer ${accessToken}`;
    } else if (accessToken) {
      headers.Authorization = `Bearer ${accessToken}`;
    } else if (apiKey) {
      headers['x-api-key'] = apiKey;
    } else {
      throw new Error('Missing AppSync credentials (access token or API key).');
    }
  }

  const finalVariables: Record<string, any> = (variables && typeof variables === 'object') ? { ...variables } : {};

  const normalizedQuery = (query ?? '').trim();
  const isPlaceholderQuery = !normalizedQuery;
  const optionOperationName = (options?.operationName ?? '').trim();

  // Only use `method` as operationName when we had to synthesize a placeholder query.
  // When the caller provides a real GraphQL document, do NOT override operationName;
  // otherwise LocalServer will use that name as response field and break resultPath extraction.
  const normalizedOperationName = (
    optionOperationName || (isPlaceholderQuery ? (method ?? '') : '')
  ).trim();

  const effectiveQuery = normalizedQuery
    ? normalizedQuery
    : `query ${normalizedOperationName || 'Anonymous'} { __typename }`;

  // 构建请求 body
  const body: Record<string, any> = { query: effectiveQuery, variables: finalVariables };
  
  // 添加可选字段
  if (normalizedOperationName) {
    body.operationName = normalizedOperationName;
  }
  
  // 构建 extensions
  const extensions: Record<string, any> = {};
  
  // 添加 method 到 extensions
  if (method) {
    extensions.method = method;
  }
  
  // 合并用户提供的 extensions
  if (options?.extensions) {
    Object.assign(extensions, options.extensions);
  }
  
  // 如果有 extensions，添加到 body
  if (Object.keys(extensions).length > 0) {
    body.extensions = extensions;
  }

  const response = await fetch(endpoint, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });

  const payload = (await response.json()) as GraphQLResponse<T>;

  if (payload.errors && payload.errors.length > 0) {
    const message = payload.errors[0]?.message || 'AppSync request failed';
    throw new Error(message);
  }

  if (!payload.data) {
    throw new Error('AppSync response missing data');
  }

  return payload.data;
};
