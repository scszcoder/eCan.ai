import { webAuthSession } from '../auth/webAuthSession';

interface GraphQLError {
  message: string;
  [key: string]: any;
}

interface GraphQLResponse<T> {
  data?: T;
  errors?: GraphQLError[];
}

const getAppSyncEndpoint = (): string => {
  const env = (typeof import.meta !== 'undefined' && import.meta.env) ? import.meta.env : {};
  return (env.VITE_APPSYNC_ENDPOINT as string) || '';
};

export const appSyncRequest = async <T>(query: string, variables?: Record<string, any>): Promise<T> => {
  const endpoint = getAppSyncEndpoint();
  if (!endpoint) {
    throw new Error('AppSync endpoint missing. Set VITE_APPSYNC_ENDPOINT.');
  }

  const accessToken = webAuthSession.getAccessToken();
  if (!accessToken) {
    throw new Error('Missing access token for AppSync request.');
  }

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
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
