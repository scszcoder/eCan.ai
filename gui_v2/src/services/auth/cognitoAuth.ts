import { logger } from '../../utils/logger';

export interface CognitoConfig {
  domain: string;
  clientId: string;
  redirectUri: string;
  logoutUri: string;
  scopes: string;
}

export interface CognitoTokens {
  access_token: string;
  id_token?: string;
  refresh_token?: string;
  token_type?: string;
  expires_in?: number;
}

const STORAGE_KEYS = {
  CODE_VERIFIER: 'cognito_pkce_verifier',
  STATE: 'cognito_pkce_state',
  SCREEN_HINT: 'cognito_screen_hint',
} as const;

const getDefaultRedirectUri = (): string => {
  if (typeof window === 'undefined') return '';
  return `${window.location.origin}/#/auth/callback`;
};

const getDefaultLogoutUri = (): string => {
  if (typeof window === 'undefined') return '';
  return `${window.location.origin}/#/login`;
};

export const getCognitoConfig = (): CognitoConfig | null => {
  const env = (typeof import.meta !== 'undefined' && import.meta.env) ? import.meta.env : {};

  const domain = env.VITE_COGNITO_DOMAIN as string | undefined;
  const clientId = env.VITE_COGNITO_CLIENT_ID as string | undefined;

  if (!domain || !clientId) {
    return null;
  }

  return {
    domain,
    clientId,
    redirectUri: (env.VITE_COGNITO_REDIRECT_URI as string | undefined) || getDefaultRedirectUri(),
    logoutUri: (env.VITE_COGNITO_LOGOUT_URI as string | undefined) || getDefaultLogoutUri(),
    scopes: (env.VITE_COGNITO_SCOPES as string | undefined) || 'openid email profile',
  };
};

const randomString = (length: number): string => {
  const values = new Uint8Array(length);
  crypto.getRandomValues(values);
  return Array.from(values).map((b) => ('0' + b.toString(16)).slice(-2)).join('');
};

const base64UrlEncode = (buffer: ArrayBuffer): string => {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  bytes.forEach((b) => {
    binary += String.fromCharCode(b);
  });
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
};

const sha256 = async (value: string): Promise<ArrayBuffer> => {
  const encoder = new TextEncoder();
  return crypto.subtle.digest('SHA-256', encoder.encode(value));
};

const storePkce = (verifier: string, state: string, screenHint?: string) => {
  sessionStorage.setItem(STORAGE_KEYS.CODE_VERIFIER, verifier);
  sessionStorage.setItem(STORAGE_KEYS.STATE, state);
  if (screenHint) {
    sessionStorage.setItem(STORAGE_KEYS.SCREEN_HINT, screenHint);
  } else {
    sessionStorage.removeItem(STORAGE_KEYS.SCREEN_HINT);
  }
};

const loadPkce = () => {
  const verifier = sessionStorage.getItem(STORAGE_KEYS.CODE_VERIFIER);
  const state = sessionStorage.getItem(STORAGE_KEYS.STATE);
  const screenHint = sessionStorage.getItem(STORAGE_KEYS.SCREEN_HINT);
  return { verifier, state, screenHint };
};

const clearPkce = () => {
  sessionStorage.removeItem(STORAGE_KEYS.CODE_VERIFIER);
  sessionStorage.removeItem(STORAGE_KEYS.STATE);
  sessionStorage.removeItem(STORAGE_KEYS.SCREEN_HINT);
};

const decodeJwtPayload = (token: string): Record<string, any> => {
  const payload = token.split('.')[1];
  if (!payload) return {};
  const base64 = payload.replace(/-/g, '+').replace(/_/g, '/');
  const padded = base64.padEnd(base64.length + (4 - (base64.length % 4)) % 4, '=');
  const json = atob(padded);
  return JSON.parse(json);
};

export const cognitoAuth = {
  isConfigured(): boolean {
    return !!getCognitoConfig();
  },

  async startHostedLogin(options?: { identityProvider?: string; screenHint?: 'signup' | 'login' }): Promise<void> {
    const config = getCognitoConfig();
    if (!config) {
      throw new Error('Cognito config missing. Set VITE_COGNITO_DOMAIN and VITE_COGNITO_CLIENT_ID.');
    }

    const state = randomString(16);
    const verifier = randomString(64);
    const challenge = base64UrlEncode(await sha256(verifier));

    storePkce(verifier, state, options?.screenHint);

    const params = new URLSearchParams({
      client_id: config.clientId,
      response_type: 'code',
      redirect_uri: config.redirectUri,
      scope: config.scopes,
      state,
      code_challenge: challenge,
      code_challenge_method: 'S256',
    });

    if (options?.identityProvider) {
      params.set('identity_provider', options.identityProvider);
    }
    if (options?.screenHint) {
      params.set('screen_hint', options.screenHint);
    }

    const url = `https://${config.domain}/oauth2/authorize?${params.toString()}`;
    window.location.assign(url);
  },

  async exchangeCodeForTokens(code: string, state?: string): Promise<CognitoTokens> {
    const config = getCognitoConfig();
    if (!config) {
      throw new Error('Cognito config missing.');
    }

    const { verifier, state: storedState } = loadPkce();
    if (!verifier) {
      throw new Error('Missing PKCE verifier. Please restart login.');
    }
    if (storedState && state && storedState !== state) {
      throw new Error('Invalid login state. Please restart login.');
    }

    const body = new URLSearchParams({
      grant_type: 'authorization_code',
      client_id: config.clientId,
      code,
      redirect_uri: config.redirectUri,
      code_verifier: verifier,
    });

    const response = await fetch(`https://${config.domain}/oauth2/token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: body.toString(),
    });

    if (!response.ok) {
      const text = await response.text();
      logger.error('[CognitoAuth] Token exchange failed', text);
      throw new Error('Token exchange failed.');
    }

    const data = (await response.json()) as CognitoTokens;
    clearPkce();
    return data;
  },

  async refreshTokens(refreshToken: string): Promise<CognitoTokens> {
    const config = getCognitoConfig();
    if (!config) {
      throw new Error('Cognito config missing.');
    }

    const body = new URLSearchParams({
      grant_type: 'refresh_token',
      client_id: config.clientId,
      refresh_token: refreshToken,
    });

    const response = await fetch(`https://${config.domain}/oauth2/token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: body.toString(),
    });

    if (!response.ok) {
      const text = await response.text();
      logger.error('[CognitoAuth] Refresh failed', text);
      throw new Error('Token refresh failed.');
    }

    return (await response.json()) as CognitoTokens;
  },

  parseCallbackParams(): { code?: string; state?: string; error?: string } {
    const hash = typeof window !== 'undefined' ? window.location.hash : '';
    const search = typeof window !== 'undefined' ? window.location.search : '';

    const queryFromHash = hash.includes('?') ? hash.substring(hash.indexOf('?') + 1) : '';
    const query = queryFromHash || (search.startsWith('?') ? search.substring(1) : '');
    const params = new URLSearchParams(query);

    return {
      code: params.get('code') || undefined,
      state: params.get('state') || undefined,
      error: params.get('error') || undefined,
    };
  },

  decodeIdToken(idToken?: string): Record<string, any> {
    if (!idToken) return {};
    try {
      return decodeJwtPayload(idToken);
    } catch (error) {
      logger.warn('[CognitoAuth] Failed to decode id token', error);
      return {};
    }
  },

  buildLogoutUrl(): string {
    const config = getCognitoConfig();
    if (!config) {
      return '/';
    }
    const params = new URLSearchParams({
      client_id: config.clientId,
      logout_uri: config.logoutUri,
    });
    return `https://${config.domain}/logout?${params.toString()}`;
  },

  startLogout(): void {
    window.location.assign(this.buildLogoutUrl());
  },
};
