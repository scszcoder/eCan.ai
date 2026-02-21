import { getSettings } from '../../stores/settingsStore';
import { userStorageManager } from '../storage/UserStorageManager';
import { detectPlatform } from '../../config/platform';
import { webAuthSession } from '../auth/webAuthSession';

interface GraphQLError {
  message: string;
  [key: string]: any;
}

interface GraphQLResponse<T> {
  data?: T;
  errors?: GraphQLError[];
}

export type AppSyncAuthMode = 'auto' | 'bearer' | 'apiKey' | 'lambda' | 'none';

export interface AppSyncRequestOptions {
  authMode?: AppSyncAuthMode;
  apiKey?: string;
  /** Additional HTTP headers to send (merged after auth headers). */
  headers?: Record<string, string>;
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

  const runtimePlatform = (() => {
    try {
      return detectPlatform();
    } catch {
      return 'web' as const;
    }
  })();
  
  // Desktop mode: use local server endpoint
  // Check both isWebPlatform() and isLocalhost() because platform detection
  // may incorrectly report 'web' when running desktop app via Vite dev server
  if (runtimePlatform === 'desktop' || isLocalhost()) {
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

const stripBearerPrefix = (token: string): string => {
  const t = (token || '').trim();
  if (!t) return t;
  return t.toLowerCase().startsWith('bearer ') ? t.slice(7).trim() : t;
};

const ensureBearerPrefix = (token: string): string => {
  const t = (token || '').trim();
  if (!t) return t;
  return t.toLowerCase().startsWith('bearer ') ? t : `Bearer ${t}`;
};

const isNotAuthorizedError = (err: unknown): boolean => {
  const msg = err instanceof Error ? err.message : String(err ?? '');
  return /not authorized/i.test(msg) || /unauthorized/i.test(msg);
};

const getUserPoolsJwt = (accessToken: string | null): string => {
  // AppSync User Pools expects a raw JWT (no Bearer prefix).
  // Prefer idToken when available.
  const idToken = webAuthSession.getSession?.()?.idToken;
  const raw = (idToken || accessToken || '').trim();
  return stripBearerPrefix(raw);
};

export const appSyncRequest = async <T>(
  query: string,
  variables?: Record<string, any>,
  options?: AppSyncRequestOptions,
  method?: string
): Promise<T> => {
  // Debug: log incoming parameters
  console.log('[AppSyncClient] appSyncRequest called with method:', method);
  console.log('[AppSyncClient] appSyncRequest variables:', JSON.stringify(variables, null, 2));
  
  // Get GraphQL endpoint (AWS AppSync or local server)
  const endpoint = getGraphQLEndpoint();
  
  if (!endpoint) {
    console.error('[AppSyncClient] No GraphQL endpoint available');
    throw new Error('GraphQL endpoint missing. Configure VITE_APPSYNC_ENDPOINT or wan_api_endpoint in settings.');
  }

  const baseHeaders: Record<string, string> = { 'Content-Type': 'application/json' };

  // Determine if using local server or AWS AppSync
  const isLocalServer = endpoint.includes('localhost') || endpoint.startsWith('/graphql');

  // Authentication sources
  const accessToken = userStorageManager.getToken();
  const apiKey = getAppSyncApiKey(options?.apiKey);
  const authMode = options?.authMode ?? 'auto';

  // Skill editor queries are typically protected by Cognito User Pools;
  // when we run with API key auth, AppSync will return Not Authorized.
  const preferUserPools = !isLocalServer && typeof method === 'string' && method.startsWith('skill_editor.');

  const buildHeaders = (mode: AppSyncAuthMode): Record<string, string> => {
    const headers: Record<string, string> = { ...baseHeaders };

    if (mode === 'none') {
      return headers;
    }

    // AWS_LAMBDA authorizer mode: AppSync routes requests to the Lambda authorizer
    // when the Authorization header is present but not a valid JWT.
    if (mode === 'lambda') {
      headers.Authorization = 'lambda-auth';
      return headers;
    }

    if (mode === 'apiKey') {
      if (!apiKey) throw new Error('Missing API key for AppSync request.');
      headers['x-api-key'] = apiKey;
      return headers;
    }

    if (mode === 'bearer') {
      if (!accessToken) throw new Error('Missing access token for AppSync request.');
      headers.Authorization = isLocalServer
        ? ensureBearerPrefix(accessToken)
        : getUserPoolsJwt(accessToken);
      return headers;
    }

    // auto
    if (isLocalServer) {
      if (accessToken) headers.Authorization = ensureBearerPrefix(accessToken);
      return headers;
    }

    // AWS AppSync
    const jwt = getUserPoolsJwt(accessToken);
    // Default auth for this API is Cognito User Pools.
    // Prefer JWT when available to avoid 401s from stale/invalid API keys.
    if (jwt) {
      headers.Authorization = jwt;
      return headers;
    }
    if (apiKey) {
      headers['x-api-key'] = apiKey;
      return headers;
    }
    return headers;
  };

  const mergeExtraHeaders = (headers: Record<string, string>): Record<string, string> => {
    const extra = options?.headers;
    if (!extra) return headers;
    return { ...headers, ...extra };
  };

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

  const initialMode = authMode;
  const initialHeaders = mergeExtraHeaders(buildHeaders(initialMode));

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: initialHeaders,
    body: JSON.stringify(body),
  });

  const tryReadJson = async () => {
    try {
      return (await response.json()) as GraphQLResponse<T>;
    } catch {
      return {} as GraphQLResponse<T>;
    }
  };

  let payload = await tryReadJson();

  // Retry on HTTP auth failures (AppSync can return 401/403 before a GraphQL payload is produced).
  if (!response.ok && (response.status === 401 || response.status === 403) && !isLocalServer) {
    const canTryJwt = !!getUserPoolsJwt(accessToken);
    const canTryApiKey = !!apiKey;

    const usedApiKey = !!initialHeaders['x-api-key'];
    const usedAuth = !!initialHeaders.Authorization;

    const retryOrder: AppSyncAuthMode[] = preferUserPools
      ? ['bearer', 'apiKey']
      : ['bearer', 'apiKey'];

    for (const m of retryOrder) {
      if (m === 'bearer' && (!canTryJwt || usedAuth)) continue;
      if (m === 'apiKey' && (!canTryApiKey || usedApiKey)) continue;

      const retryResp = await fetch(endpoint, {
        method: 'POST',
        headers: mergeExtraHeaders(buildHeaders(m)),
        body: JSON.stringify(body),
      });

      if (!retryResp.ok && (retryResp.status === 401 || retryResp.status === 403)) {
        continue;
      }

      try {
        payload = (await retryResp.json()) as GraphQLResponse<T>;
      } catch {
        payload = {} as GraphQLResponse<T>;
      }
      break;
    }
  }

  // One-time retry: swap auth modes on Not Authorized.
  if (payload.errors && payload.errors.length > 0) {
    const message = payload.errors[0]?.message || 'AppSync request failed';

    const canTryJwt = !isLocalServer && !!getUserPoolsJwt(accessToken);
    const canTryApiKey = !isLocalServer && !!apiKey;

    const usedApiKey = !!(buildHeaders(authMode)['x-api-key']);
    const usedAuth = !!(buildHeaders(authMode).Authorization);

    if (isNotAuthorizedError(new Error(message))) {
      // Prefer retrying with JWT for skill_editor.* calls.
      const retryOrder: AppSyncAuthMode[] = preferUserPools
        ? ['bearer', 'apiKey']
        : ['apiKey', 'bearer'];

      for (const m of retryOrder) {
        if (m === 'bearer' && (!canTryJwt || usedAuth)) continue;
        if (m === 'apiKey' && (!canTryApiKey || usedApiKey)) continue;

        const retryResp = await fetch(endpoint, {
          method: 'POST',
          headers: buildHeaders(m),
          body: JSON.stringify(body),
        });
        const retryPayload = (await retryResp.json()) as GraphQLResponse<T>;
        if (!retryPayload.errors || retryPayload.errors.length === 0) {
          payload = retryPayload;
          break;
        }
      }
    }

    if (payload.errors && payload.errors.length > 0) {
      throw new Error(payload.errors[0]?.message || message);
    }
  }

  if (!payload.data) throw new Error('AppSync response missing data');
  return payload.data;
};
