import { webAuthSession } from '../auth/webAuthSession';
import { getSettings } from '../../stores/settingsStore';

interface GraphQLError {
  message: string;
  [key: string]: any;
}

interface GraphQLResponse<T> {
  data?: T;
  errors?: GraphQLError[];
}

export type AppSyncAuthMode = 'auto' | 'bearer' | 'apiKey';

export interface AppSyncRequestOptions {
  authMode?: AppSyncAuthMode;
  apiKey?: string;
}

const getAppSyncEndpoint = (): string => {
  const env = (typeof import.meta !== 'undefined' && import.meta.env) ? import.meta.env : {};
  return (env.VITE_APPSYNC_ENDPOINT as string) || '';
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
  options?: AppSyncRequestOptions
): Promise<T> => {
  const endpoint = getAppSyncEndpoint();
  if (!endpoint) {
    throw new Error('AppSync endpoint missing. Set VITE_APPSYNC_ENDPOINT.');
  }

  const accessToken = webAuthSession.getAccessToken();
  const apiKey = getAppSyncApiKey(options?.apiKey);
  const authMode = options?.authMode ?? 'auto';

  const headers: Record<string, string> = {
    'Content-Type': 'application/json'
  };

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

  const response = await fetch(endpoint, {
    method: 'POST',
    headers,
    body: JSON.stringify({ query, variables }),
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
