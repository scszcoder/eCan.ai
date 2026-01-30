import { getSettings } from '../../stores/settingsStore';
import { userStorageManager } from '../storage/UserStorageManager';
import { isWebPlatform } from '../../config/platform';

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

/**
 * Check if running on localhost (desktop app via Vite dev server or production)
 */
const isLocalhost = (): boolean => {
  try {
    const hostname = window?.location?.hostname || '';
    return hostname === 'localhost' || hostname === '127.0.0.1' || hostname.startsWith('192.168.');
  } catch {
    return false;
  }
};

/**
 * Get GraphQL endpoint
 * - Desktop/localhost: always use local server GraphQL endpoint (Python backend)
 * - Web (non-localhost): use AWS AppSync endpoint from env or settings
 */
const getGraphQLEndpoint = (): string => {
  const env = getEnv();
  const settings = getSettings();
  
  // Desktop mode: use local server endpoint
  // Check both isWebPlatform() and isLocalhost() because platform detection
  // may incorrectly report 'web' when running desktop app via Vite dev server
  if (!isWebPlatform() || isLocalhost()) {
    // In dev mode, use same-origin path for Vite proxy
    try {
      if (typeof import.meta !== 'undefined' && (import.meta as any).env?.DEV) {
        console.log('[AppSyncClient] Using local GraphQL endpoint: /graphql');
        return '/graphql';
      }
    } catch {}
    
    const port = settings?.local_server_port || '4668';
    console.log(`[AppSyncClient] Using local GraphQL endpoint: http://localhost:${port}/graphql`);
    return `http://localhost:${port}/graphql`;
  }
  
  // Web mode: use AWS AppSync endpoint
  const appSyncEndpoint = (env.VITE_APPSYNC_ENDPOINT as string) || settings?.wan_api_endpoint || '';
  if (appSyncEndpoint.trim()) {
    console.log(`[AppSyncClient] Using AppSync endpoint: ${appSyncEndpoint.trim()}`);
    return appSyncEndpoint.trim();
  }
  
  // Fallback for web mode without AppSync configured
  throw new Error('Web mode requires VITE_APPSYNC_ENDPOINT or wan_api_endpoint in settings.');
};

const getAppSyncApiKey = (overrideKey?: string): string => {
  if (overrideKey) return overrideKey;
  const env = getEnv();
  const settings = getSettings();
  const fromSettings = settings?.wan_api_key;
  return (fromSettings || (env as any).VITE_APPSYNC_API_KEY || '').trim();
};

export const appSyncRequest = async <T>(
  query: string,
  variables?: Record<string, any>,
  options?: AppSyncRequestOptions,
  method?: string
): Promise<T> => {
  // Get GraphQL endpoint (AWS AppSync or local server)
  const endpoint = getGraphQLEndpoint();
  
  if (!endpoint) {
    console.error('[AppSyncClient] No GraphQL endpoint available');
    throw new Error('GraphQL endpoint missing. Configure VITE_APPSYNC_ENDPOINT or wan_api_endpoint in settings.');
  }

  const headers: Record<string, string> = {
    'Content-Type': 'application/json'
  };

  // Determine if using local server or AWS AppSync
  const isLocalServer = endpoint.includes('localhost') || endpoint.startsWith('/graphql');
  
  // Authentication
  const accessToken = userStorageManager.getToken();
  const apiKey = getAppSyncApiKey(options?.apiKey);
  const authMode = options?.authMode ?? 'auto';

  if (authMode === 'none') {
    // No authentication
  } else if (authMode === 'apiKey') {
    if (!apiKey) {
      throw new Error('Missing API key for AppSync request.');
    }
    headers['x-api-key'] = apiKey;
  } else if (authMode === 'bearer') {
    if (!accessToken) {
      throw new Error('Missing access token for AppSync request.');
    }
    headers.Authorization = `Bearer ${accessToken}`;
  } else {
    // Auto mode: prefer token, fallback to API key
    if (accessToken) {
      headers.Authorization = `Bearer ${accessToken}`;
    } else if (apiKey && !isLocalServer) {
      headers['x-api-key'] = apiKey;
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
