import { logger } from '../../utils/logger';

/**
 * Web Tencent CIAM client — China-region counterpart of `cognitoAuth`.
 *
 * Mirrors cognitoAuth's browser PKCE redirect flow and return shapes so
 * AuthCallback can dispatch to either, but CIAM is OIDC-standard so this client
 * is discovery-driven: it derives the authorize/token/userinfo/logout endpoints
 * from `${issuer}/.well-known/openid-configuration` instead of hardcoding paths
 * (consistent with the Python CIAMService). Inert until VITE_CIAM_ISSUER +
 * VITE_CIAM_CLIENT_ID are set — `isConfigured()` is false and nothing runs.
 *
 * NOTE: the CIAM discovery endpoint must allow CORS from the web origin, and
 * WeChat-federated claims may lack `email` (openid/unionid/nickname) — revisit
 * the AuthCallback userInfo mapping once a live CIAM token is available (Layer 0).
 */

export interface CIAMConfig {
  issuer: string;
  clientId: string;
  redirectUri: string;
  postLogoutUri: string;
  scopes: string;
  wechatIdp?: string;
}

export interface CIAMTokens {
  access_token: string;
  id_token?: string;
  refresh_token?: string;
  token_type?: string;
  expires_in?: number;
}

interface OidcDiscovery {
  issuer?: string;
  authorization_endpoint: string;
  token_endpoint: string;
  userinfo_endpoint?: string;
  end_session_endpoint?: string;
  jwks_uri?: string;
}

const STORAGE_KEYS = {
  CODE_VERIFIER: 'ciam_pkce_verifier',
  STATE: 'ciam_pkce_state',
} as const;

const getDefaultRedirectUri = (): string => {
  if (typeof window === 'undefined') return '';
  if (window.location.protocol === 'file:') {
    return `${window.location.href.split('#')[0]}#/auth/callback`;
  }
  return `${window.location.origin}/#/auth/callback`;
};

const getDefaultLogoutUri = (): string => {
  if (typeof window === 'undefined') return '';
  if (window.location.protocol === 'file:') {
    return `${window.location.href.split('#')[0]}#/login`;
  }
  return `${window.location.origin}/#/login`;
};

export const getCIAMConfig = (): CIAMConfig | null => {
  const env = (typeof import.meta !== 'undefined' && import.meta.env) ? import.meta.env : {};

  const issuer = env.VITE_CIAM_ISSUER as string | undefined;
  const clientId = env.VITE_CIAM_CLIENT_ID as string | undefined;

  if (!issuer || !clientId) {
    return null;
  }

  return {
    issuer: issuer.replace(/\/$/, ''),
    clientId,
    redirectUri: (env.VITE_CIAM_REDIRECT_URI as string | undefined) || getDefaultRedirectUri(),
    postLogoutUri: (env.VITE_CIAM_LOGOUT_URI as string | undefined) || getDefaultLogoutUri(),
    scopes: (env.VITE_CIAM_SCOPES as string | undefined) || 'openid profile',
    wechatIdp: env.VITE_CIAM_WECHAT_IDP as string | undefined,
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

const storePkce = (verifier: string, state: string) => {
  sessionStorage.setItem(STORAGE_KEYS.CODE_VERIFIER, verifier);
  sessionStorage.setItem(STORAGE_KEYS.STATE, state);
};

const loadPkce = () => {
  const verifier = sessionStorage.getItem(STORAGE_KEYS.CODE_VERIFIER);
  const state = sessionStorage.getItem(STORAGE_KEYS.STATE);
  return { verifier, state };
};

const clearPkce = () => {
  sessionStorage.removeItem(STORAGE_KEYS.CODE_VERIFIER);
  sessionStorage.removeItem(STORAGE_KEYS.STATE);
};

const decodeJwtPayload = (token: string): Record<string, any> => {
  const payload = token.split('.')[1];
  if (!payload) return {};
  const base64 = payload.replace(/-/g, '+').replace(/_/g, '/');
  const padded = base64.padEnd(base64.length + (4 - (base64.length % 4)) % 4, '=');
  const json = atob(padded);
  return JSON.parse(json);
};

// Cached per page-load; re-fetched on the callback page after the redirect.
let discoveryCache: OidcDiscovery | null = null;

const getDiscovery = async (issuer: string): Promise<OidcDiscovery> => {
  if (discoveryCache) return discoveryCache;
  const url = `${issuer}/.well-known/openid-configuration`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`CIAM OIDC discovery failed (${response.status}) at ${url}`);
  }
  discoveryCache = (await response.json()) as OidcDiscovery;
  return discoveryCache;
};

export const ciamAuth = {
  isConfigured(): boolean {
    return !!getCIAMConfig();
  },

  async startWechatLogin(): Promise<void> {
    const config = getCIAMConfig();
    if (!config) {
      throw new Error('CIAM config missing. Set VITE_CIAM_ISSUER and VITE_CIAM_CLIENT_ID.');
    }

    const discovery = await getDiscovery(config.issuer);

    const state = randomString(16);
    const verifier = randomString(64);
    const challenge = base64UrlEncode(await sha256(verifier));
    storePkce(verifier, state);

    const params = new URLSearchParams({
      client_id: config.clientId,
      response_type: 'code',
      redirect_uri: config.redirectUri,
      scope: config.scopes,
      state,
      code_challenge: challenge,
      code_challenge_method: 'S256',
    });
    if (config.wechatIdp) {
      params.set('identity_provider', config.wechatIdp);
    }

    window.location.assign(`${discovery.authorization_endpoint}?${params.toString()}`);
  },

  async exchangeCodeForTokens(code: string, state?: string): Promise<CIAMTokens> {
    const config = getCIAMConfig();
    if (!config) {
      throw new Error('CIAM config missing.');
    }

    const { verifier, state: storedState } = loadPkce();
    if (!verifier) {
      throw new Error('Missing PKCE verifier. Please restart login.');
    }
    if (storedState && state && storedState !== state) {
      throw new Error('Invalid login state. Please restart login.');
    }

    const discovery = await getDiscovery(config.issuer);

    const body = new URLSearchParams({
      grant_type: 'authorization_code',
      client_id: config.clientId,
      code,
      redirect_uri: config.redirectUri,
      code_verifier: verifier,
    });

    const response = await fetch(discovery.token_endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
    });

    if (!response.ok) {
      const text = await response.text();
      logger.error('[CIAMAuth] Token exchange failed', text);
      throw new Error('Token exchange failed.');
    }

    const data = (await response.json()) as CIAMTokens;
    clearPkce();
    return data;
  },

  async refreshTokens(refreshToken: string): Promise<CIAMTokens> {
    const config = getCIAMConfig();
    if (!config) {
      throw new Error('CIAM config missing.');
    }

    const discovery = await getDiscovery(config.issuer);

    const body = new URLSearchParams({
      grant_type: 'refresh_token',
      client_id: config.clientId,
      refresh_token: refreshToken,
    });

    const response = await fetch(discovery.token_endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
    });

    if (!response.ok) {
      const text = await response.text();
      logger.error('[CIAMAuth] Refresh failed', text);
      throw new Error('Token refresh failed.');
    }

    return (await response.json()) as CIAMTokens;
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
      logger.warn('[CIAMAuth] Failed to decode id token', error);
      return {};
    }
  },
};
