/**
 * Token Auto-Refresh Service
 * Automatically refreshes authentication tokens before they expire
 */

import { IPCAPI } from '../ipc/api';
import { isWebPlatform } from '../../config/platform';
import { webAuthSession } from './webAuthSession';
import { cognitoAuth } from './cognitoAuth';
import { logger } from '../../utils/logger';

interface TokenInfo {
  username: string;
  role: string;
  created_at: number;
  expires_at: number;
  last_used: number;
  time_remaining_seconds: number;
  time_remaining_hours: number;
  is_expiring_soon: boolean;
}

// Error codes that mean the token is truly invalid/expired at the backend.
// When the backend explicitly returns one of these, we should logout — there
// is no point in retrying because the token will not magically come back.
const TOKEN_INVALID_ERROR_CODES = new Set([
  'INVALID_TOKEN',
  'TOKEN_REQUIRED',
  'MISSING_TOKEN',
  'TOKEN_INFO_ERROR',
  'UNAUTHENTICATED',
  'SESSION_EXPIRED',
]);

// Error codes that mean the failure was NOT about token validity — typically
// the backend is down, the network is unreachable, or some transient infra
// problem. We must not interpret these as "token expired" and must not logout.
const INFRA_ERROR_CODES = new Set([
  'LOCAL_GRAPHQL_ERROR',
  'EXECUTION_ERROR',
  'NETWORK_OFFLINE',
  'TIMEOUT',
  'ECONNREFUSED',
  'ECONNRESET',
  'ENOTFOUND',
  'EAI_AGAIN',
  'ETIMEDOUT',
  'HTTP_500',
  'HTTP_502',
  'HTTP_503',
  'HTTP_504',
]);

function classifyErrorCode(code: string | undefined): 'invalid_token' | 'infra' | 'unknown' {
  if (!code) return 'unknown';
  if (TOKEN_INVALID_ERROR_CODES.has(code)) return 'invalid_token';
  if (INFRA_ERROR_CODES.has(code)) return 'infra';
  return 'unknown';
}

class TokenRefreshService {
  private refreshTimer: NodeJS.Timeout | null = null;
  private checkInterval = 30 * 60 * 1000; // Check every 30 minutes
  private refreshThreshold = 60 * 60; // Refresh when less than 1 hour remaining
  private currentToken: string | null = null;
  private onTokenRefreshed: ((newToken: string) => void) | null = null;
  private onTokenExpired: (() => void) | null = null;
  private consecutiveFailures = 0;
  // Ambiguous/unknown-error threshold. Infra failures don't count.
  // Auth failures (backend confirms token invalid) logout immediately on the first hit —
  // no need to count; if the backend really says INVALID_TOKEN, no amount of retries help.
  private maxConsecutiveFailures = 3;

  /**
   * Start automatic token refresh service
   */
  start(token: string, options?: {
    checkInterval?: number;
    refreshThreshold?: number;
    onTokenRefreshed?: (newToken: string) => void;
    onTokenExpired?: () => void;
  }) {
    this.currentToken = token;
    
    if (options?.checkInterval) {
      this.checkInterval = options.checkInterval;
    }
    if (options?.refreshThreshold) {
      this.refreshThreshold = options.refreshThreshold;
    }
    if (options?.onTokenRefreshed) {
      this.onTokenRefreshed = options.onTokenRefreshed;
    }
    if (options?.onTokenExpired) {
      this.onTokenExpired = options.onTokenExpired;
    }

    // Stop existing timer if any
    this.stop();

    // Start periodic check
    this.refreshTimer = setInterval(() => {
      this.checkAndRefreshToken();
    }, this.checkInterval);

    // Don't do immediate check - wait for first interval
    // This prevents premature logout if token check fails right after login
    logger.info('[TokenRefresh] Service started', {
      checkIntervalMinutes: this.checkInterval / 1000 / 60,
      refreshThresholdMinutes: this.refreshThreshold / 60,
      maxConsecutiveFailures: this.maxConsecutiveFailures,
      note: 'First check will occur after first interval'
    });
  }

  /**
   * Stop automatic token refresh service
   */
  stop() {
    if (this.refreshTimer) {
      clearInterval(this.refreshTimer);
      this.refreshTimer = null;
      logger.info('[TokenRefresh] Service stopped');
    }
  }

  /**
   * Check token status and refresh if needed
   */
  private async checkAndRefreshToken() {
    if (!this.currentToken) {
      logger.warn('[TokenRefresh] No token available');
      return;
    }

    if (isWebPlatform()) {
      await this.checkAndRefreshWebToken();
      return;
    }

    const checkTime = new Date().toISOString();
    logger.info('[TokenRefresh] Starting token check', {
      checkTime,
      tokenPrefix: this.currentToken.substring(0, 8)
    });

    try {
      // Get current token info
      const result = await this.getTokenInfo(this.currentToken);

      if (!result.ok) {
        // INFRA failures must NEVER escalate to logout. The backend is down,
        // the user's token is still good — losing the session because the
        // server briefly went away is a real UX bug we hit on Aug 25 2026.
        if (result.reason === 'infra') {
          logger.warn('[TokenRefresh] Backend unreachable, keeping session', {
            errorCode: result.errorCode,
            checkTime,
            note: 'Not treating as token expiration'
          });
          // Do not increment consecutiveFailures — the token is fine.
          return;
        }

        if (result.reason === 'invalid_token') {
          logger.error('[TokenRefresh] Backend reported token invalid, triggering logout', {
            errorCode: result.errorCode,
            checkTime
          });
          this.handleTokenExpired();
          return;
        }

        // Unknown / unrecognized error code — fall back to legacy behavior
        // of counting toward a higher threshold. This preserves safety for
        // future backend error codes we haven't classified yet.
        this.consecutiveFailures++;
        logger.error('[TokenRefresh] Unknown error getting token info', {
          consecutiveFailures: this.consecutiveFailures,
          maxAllowed: this.maxConsecutiveFailures,
          errorCode: result.errorCode,
          checkTime
        });

        if (this.consecutiveFailures >= this.maxConsecutiveFailures) {
          logger.error('[TokenRefresh] Max consecutive failures reached, triggering logout', {
            totalFailures: this.consecutiveFailures,
            checkTime
          });
          this.handleTokenExpired();
        }
        return;
      }

      const tokenInfo = result.info;
      // result.info is non-null when result.ok is true (we just checked above),
      // but TS can't narrow it across the closure of getTokenInfo. Use a local
      // assertion here that is sound given the contract.
      if (!tokenInfo) {
        // Defensive — should never happen because result.ok implies result.info.
        this.consecutiveFailures++;
        return;
      }
      // Reset failure counter on any success — including after a successful
      // response that followed infra failures. This means a single infra blip
      // does not poison the counter for legitimate token-expired errors later.
      this.consecutiveFailures = 0;

      logger.info('[TokenRefresh] Token check successful', {
        username: tokenInfo.username,
        timeRemainingHours: tokenInfo.time_remaining_hours,
        timeRemainingSeconds: tokenInfo.time_remaining_seconds,
        isExpiringSoon: tokenInfo.is_expiring_soon,
        expiresAt: new Date(tokenInfo.expires_at * 1000).toISOString(),
        checkTime
      });

      // Refresh if expiring soon
      if (tokenInfo.time_remaining_seconds < this.refreshThreshold) {
        logger.info('[TokenRefresh] Token expiring soon, refreshing...', {
          time_remaining_hours: tokenInfo.time_remaining_hours
        });
        
        await this.refreshToken();
      }
    } catch (error) {
      logger.error('[TokenRefresh] Error checking token:', error);
    }
  }

  private async checkAndRefreshWebToken() {
    const session = webAuthSession.getSession();
    if (!session?.accessToken) {
      logger.warn('[TokenRefresh] No web session available');
      return;
    }

    if (!session.expiresAt) {
      logger.info('[TokenRefresh] Web session has no expiry, skipping refresh');
      return;
    }

    const msRemaining = session.expiresAt - Date.now();
    const secondsRemaining = Math.floor(msRemaining / 1000);

    if (secondsRemaining < this.refreshThreshold) {
      logger.info('[TokenRefresh] Web token expiring soon, refreshing...', {
        secondsRemaining
      });

      const refreshToken = session.refreshToken;
      if (!refreshToken) {
        logger.warn('[TokenRefresh] No refresh token available for web session');
        this.handleTokenExpired();
        return;
      }

      try {
        const refreshed = await cognitoAuth.refreshTokens(refreshToken);
        const newExpiresAt = refreshed.expires_in
          ? Date.now() + refreshed.expires_in * 1000
          : session.expiresAt;

        webAuthSession.updateTokens({
          accessToken: refreshed.access_token,
          idToken: refreshed.id_token ?? session.idToken,
          tokenType: refreshed.token_type ?? session.tokenType,
          expiresAt: newExpiresAt,
        });

        this.currentToken = refreshed.access_token;
        if (this.onTokenRefreshed) {
          this.onTokenRefreshed(refreshed.access_token);
        }
      } catch (error) {
        logger.error('[TokenRefresh] Failed to refresh web token', error);
        this.handleTokenExpired();
      }
    }
  }

  /**
   * Get current token information.
   *
   * Returns a `TokenCheckResult` that distinguishes between:
   *   - `ok: true` — backend returned token info, all good
   *   - `ok: false, reason: 'invalid_token'` — backend explicitly said token is invalid/expired
   *   - `ok: false, reason: 'infra'` — network/server problem, NOT a token issue
   *   - `ok: false, reason: 'unknown'` — unrecognized error code; treat as ambiguous
   *
   * Callers MUST NOT interpret `reason === 'infra'` as a token problem.
   */
  async getTokenInfo(token: string): Promise<{
    ok: boolean;
    reason?: 'invalid_token' | 'infra' | 'unknown';
    errorCode?: string;
    info?: TokenInfo;
  }> {
    try {
      logger.debug('[TokenRefresh] Requesting token info from backend', {
        tokenPrefix: token.substring(0, 8)
      });

      const api = IPCAPI.getInstance();
      const response = await api.getTokenInfo(token);

      logger.debug('[TokenRefresh] Received response from backend', {
        success: response.success,
        hasData: !!response.data,
        hasError: !!response.error,
        errorCode: response.error?.code
      });

      if (response.success) {
        logger.debug('[TokenRefresh] Token info retrieved successfully', {
          username: response.data?.username,
          timeRemaining: response.data?.time_remaining_hours
        });
        return { ok: true, info: response.data as TokenInfo };
      }

      const errorCode = response.error?.code;
      const reason = classifyErrorCode(errorCode);
      logger.error('[TokenRefresh] Backend returned error response', {
        errorCode,
        reason,
        message: response.error?.message,
        fullResponse: JSON.stringify(response)
      });
      return { ok: false, reason, errorCode };
    } catch (error) {
      // Network/transport exceptions (fetch failures, AbortError, etc.) reach here.
      // These are infra errors — never treat as token invalid.
      logger.error('[TokenRefresh] Exception while getting token info', {
        error,
        errorMessage: error instanceof Error ? error.message : String(error),
        errorStack: error instanceof Error ? error.stack : undefined
      });
      return { ok: false, reason: 'infra', errorCode: 'EXCEPTION' };
    }
  }

  /**
   * Refresh current token
   */
  async refreshToken(): Promise<string | null> {
    if (!this.currentToken) {
      logger.error('[TokenRefresh] No token to refresh');
      return null;
    }

    logger.info('[TokenRefresh] Attempting to refresh token', {
      tokenPrefix: this.currentToken.substring(0, 8)
    });

    try {
      const api = IPCAPI.getInstance();
      const response = await api.refreshToken(this.currentToken);

      logger.debug('[TokenRefresh] Refresh response received', {
        success: response.success,
        hasData: !!response.data,
        errorCode: response.error?.code
      });

      if (response.success && response.data?.token) {
        const newToken = response.data.token;
        const oldTokenPrefix = this.currentToken.substring(0, 8);
        this.currentToken = newToken;

        logger.info('[TokenRefresh] Token refreshed successfully', {
          username: (response.data as any).username,
          oldTokenPrefix,
          newTokenPrefix: newToken.substring(0, 8),
          expiresAt: (response.data as any).expires_at ? new Date((response.data as any).expires_at * 1000).toISOString() : 'unknown'
        });

        // Notify callback
        if (this.onTokenRefreshed) {
          logger.debug('[TokenRefresh] Notifying token refresh callback');
          this.onTokenRefreshed(newToken);
        }

        return newToken;
      }

      // Refresh failed — distinguish infra from invalid_token.
      const refreshErrorCode = response.error?.code;
      const reason = classifyErrorCode(refreshErrorCode);

      if (reason === 'infra') {
        // Backend was unreachable / had a transient error. Do NOT logout.
        // The existing token is still good; we'll retry on the next interval.
        logger.warn('[TokenRefresh] Refresh failed due to infra, keeping current token', {
          errorCode: refreshErrorCode,
          message: response.error?.message
        });
        return null;
      }

      logger.error('[TokenRefresh] Failed to refresh token', {
        errorCode: refreshErrorCode,
        reason,
        fullResponse: JSON.stringify(response)
      });
      this.handleTokenExpired();
      return null;
    } catch (error) {
      // Network/transport exception during refresh — also infra, not auth.
      logger.warn('[TokenRefresh] Refresh exception (infra), keeping current token', {
        errorMessage: error instanceof Error ? error.message : String(error)
      });
      return null;
    }
  }

  /**
   * Extend current token validity
   */
  async extendToken(seconds?: number): Promise<boolean> {
    if (!this.currentToken) {
      logger.error('[TokenRefresh] No token to extend');
      return false;
    }

    try {
      const api = IPCAPI.getInstance();
      const response = await api.extendToken(this.currentToken, seconds);
      
      if (response.success) {
        logger.info('[TokenRefresh] Token extended successfully', {
          time_remaining_hours: response.data?.time_remaining_hours
        });
        return true;
      } else {
        logger.error('[TokenRefresh] Failed to extend token:', response.error?.message);
        return false;
      }
    } catch (error) {
      logger.error('[TokenRefresh] Error extending token:', error);
      return false;
    }
  }

  /**
   * Handle token expiration
   */
  private handleTokenExpired() {
    logger.warn('[TokenRefresh] Handling token expiration', {
      consecutiveFailures: this.consecutiveFailures,
      hasExpiredCallback: !!this.onTokenExpired
    });
    
    this.stop();
    
    if (this.onTokenExpired) {
      logger.info('[TokenRefresh] Triggering token expired callback');
      this.onTokenExpired();
    } else {
      logger.warn('[TokenRefresh] No token expired callback registered');
    }
  }

  /**
   * Update current token
   */
  updateToken(token: string) {
    this.currentToken = token;
    logger.debug('[TokenRefresh] Token updated');
  }

  /**
   * Get current token
   */
  getCurrentToken(): string | null {
    return this.currentToken;
  }
}

// Export singleton instance
export const tokenRefreshService = new TokenRefreshService();
