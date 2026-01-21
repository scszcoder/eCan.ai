import { logger } from '../../utils/logger';

export interface WebAuthUserInfo {
  username: string;
  email?: string;
  name?: string;
  given_name?: string;
  family_name?: string;
  picture?: string;
  email_verified?: boolean;
  sub?: string;
}

export interface WebAuthSession {
  accessToken: string;
  idToken?: string;
  refreshToken?: string;
  tokenType?: string;
  expiresAt?: number;
  userInfo: WebAuthUserInfo;
}

const STORAGE_KEYS = {
  ACCESS_TOKEN: 'web_auth_access_token',
  ID_TOKEN: 'web_auth_id_token',
  REFRESH_TOKEN: 'web_auth_refresh_token',
  EXPIRES_AT: 'web_auth_expires_at',
  TOKEN_TYPE: 'web_auth_token_type',
  USER_INFO: 'web_auth_user_info',
} as const;

let memorySession: WebAuthSession | null = null;

const readFromStorage = (): WebAuthSession | null => {
  try {
    const accessToken = sessionStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
    const userInfoRaw = sessionStorage.getItem(STORAGE_KEYS.USER_INFO);
    if (!accessToken || !userInfoRaw) return null;

    const expiresAtRaw = sessionStorage.getItem(STORAGE_KEYS.EXPIRES_AT);
    const expiresAt = expiresAtRaw ? Number(expiresAtRaw) : undefined;

    return {
      accessToken,
      idToken: sessionStorage.getItem(STORAGE_KEYS.ID_TOKEN) || undefined,
      refreshToken: sessionStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN) || undefined,
      tokenType: sessionStorage.getItem(STORAGE_KEYS.TOKEN_TYPE) || undefined,
      expiresAt,
      userInfo: JSON.parse(userInfoRaw) as WebAuthUserInfo,
    };
  } catch (error) {
    logger.warn('[WebAuthSession] Failed to read session storage', error);
    return null;
  }
};

const writeToStorage = (session: WebAuthSession): void => {
  try {
    sessionStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, session.accessToken);
    sessionStorage.setItem(STORAGE_KEYS.USER_INFO, JSON.stringify(session.userInfo));

    if (session.idToken) {
      sessionStorage.setItem(STORAGE_KEYS.ID_TOKEN, session.idToken);
    } else {
      sessionStorage.removeItem(STORAGE_KEYS.ID_TOKEN);
    }

    if (session.refreshToken) {
      sessionStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, session.refreshToken);
    } else {
      sessionStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN);
    }

    if (session.tokenType) {
      sessionStorage.setItem(STORAGE_KEYS.TOKEN_TYPE, session.tokenType);
    } else {
      sessionStorage.removeItem(STORAGE_KEYS.TOKEN_TYPE);
    }

    if (typeof session.expiresAt === 'number') {
      sessionStorage.setItem(STORAGE_KEYS.EXPIRES_AT, String(session.expiresAt));
    } else {
      sessionStorage.removeItem(STORAGE_KEYS.EXPIRES_AT);
    }
  } catch (error) {
    logger.warn('[WebAuthSession] Failed to write session storage', error);
  }
};

const clearStorage = (): void => {
  Object.values(STORAGE_KEYS).forEach((key) => sessionStorage.removeItem(key));
};

export const webAuthSession = {
  setSession(session: WebAuthSession): void {
    memorySession = session;
    writeToStorage(session);
  },

  getSession(): WebAuthSession | null {
    if (memorySession) return memorySession;
    const stored = readFromStorage();
    if (stored) memorySession = stored;
    return stored;
  },

  getAccessToken(): string | null {
    return this.getSession()?.accessToken || null;
  },

  getRefreshToken(): string | null {
    return this.getSession()?.refreshToken || null;
  },

  getUserInfo(): WebAuthUserInfo | null {
    return this.getSession()?.userInfo || null;
  },

  isAuthenticated(): boolean {
    const session = this.getSession();
    if (!session?.accessToken) return false;
    if (!session.expiresAt) return true;
    return Date.now() < session.expiresAt;
  },

  updateAccessToken(accessToken: string, expiresAt?: number): void {
    const session = this.getSession();
    if (!session) return;
    const updated: WebAuthSession = {
      ...session,
      accessToken,
      expiresAt: expiresAt ?? session.expiresAt,
    };
    memorySession = updated;
    writeToStorage(updated);
  },

  updateTokens(update: {
    accessToken?: string;
    idToken?: string;
    refreshToken?: string;
    tokenType?: string;
    expiresAt?: number;
  }): void {
    const session = this.getSession();
    if (!session) return;
    const updated: WebAuthSession = {
      ...session,
      accessToken: update.accessToken ?? session.accessToken,
      idToken: update.idToken ?? session.idToken,
      refreshToken: update.refreshToken ?? session.refreshToken,
      tokenType: update.tokenType ?? session.tokenType,
      expiresAt: update.expiresAt ?? session.expiresAt,
    };
    memorySession = updated;
    writeToStorage(updated);
  },

  clear(): void {
    memorySession = null;
    clearStorage();
  },
};
