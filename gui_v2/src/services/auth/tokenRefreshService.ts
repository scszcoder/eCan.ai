/**
 * Token Auto-Refresh Service
 * Automatically refreshes authentication tokens before they expire
 */

import { ipcClient } from '../ipc/ipcWCClient';
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

class TokenRefreshService {
  private refreshTimer: NodeJS.Timeout | null = null;
  private checkInterval = 30 * 60 * 1000; // Check every 30 minutes
  private refreshThreshold = 60 * 60; // Refresh when less than 1 hour remaining
  private currentToken: string | null = null;
  private onTokenRefreshed: ((newToken: string) => void) | null = null;
  private onTokenExpired: (() => void) | null = null;
  private consecutiveFailures = 0;
  private maxConsecutiveFailures = 3; // Allow 3 consecutive failures before triggering logout

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

    const checkTime = new Date().toISOString();
    logger.info('[TokenRefresh] Starting token check', {
      checkTime,
      tokenPrefix: this.currentToken.substring(0, 8)
    });

    try {
      // Get current token info
      const tokenInfo = await this.getTokenInfo(this.currentToken);

      if (!tokenInfo) {
        this.consecutiveFailures++;
        logger.error('[TokenRefresh] Failed to get token info', {
          consecutiveFailures: this.consecutiveFailures,
          maxAllowed: this.maxConsecutiveFailures,
          checkTime
        });
        
        // Only trigger logout after multiple consecutive failures
        if (this.consecutiveFailures >= this.maxConsecutiveFailures) {
          logger.error('[TokenRefresh] Max consecutive failures reached, triggering logout', {
            totalFailures: this.consecutiveFailures,
            checkTime
          });
          this.handleTokenExpired();
        }
        return;
      }
      
      // Reset failure counter on success
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

  /**
   * Get current token information
   */
  async getTokenInfo(token: string): Promise<TokenInfo | null> {
    try {
      logger.debug('[TokenRefresh] Requesting token info from backend', {
        tokenPrefix: token.substring(0, 8)
      });
      
      const response = await ipcClient.invoke('auth.getTokenInfo', { token });
      
      logger.debug('[TokenRefresh] Received response from backend', {
        status: response.status,
        hasData: !!response.data,
        hasError: !!response.error
      });
      
      if (response.status === 'success') {
        logger.debug('[TokenRefresh] Token info retrieved successfully', {
          username: response.data?.username,
          timeRemaining: response.data?.time_remaining_hours
        });
        return response.data as TokenInfo;
      } else {
        logger.error('[TokenRefresh] Backend returned error response', {
          status: response.status,
          message: response.message,
          error: response.error,
          errorCode: response.error?.code,
          fullResponse: JSON.stringify(response)
        });
        return null;
      }
    } catch (error) {
      logger.error('[TokenRefresh] Exception while getting token info', {
        error: error,
        errorMessage: error instanceof Error ? error.message : String(error),
        errorStack: error instanceof Error ? error.stack : undefined
      });
      return null;
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
      const response = await ipcClient.invoke('auth.refreshToken', { 
        token: this.currentToken 
      });
      
      logger.debug('[TokenRefresh] Refresh response received', {
        status: response.status,
        hasData: !!response.data
      });
      
      if (response.status === 'success') {
        const newToken = response.data.token;
        const oldTokenPrefix = this.currentToken.substring(0, 8);
        this.currentToken = newToken;
        
        logger.info('[TokenRefresh] Token refreshed successfully', {
          username: response.data.username,
          oldTokenPrefix,
          newTokenPrefix: newToken.substring(0, 8),
          expiresAt: response.data.expires_at ? new Date(response.data.expires_at * 1000).toISOString() : 'unknown'
        });

        // Notify callback
        if (this.onTokenRefreshed) {
          logger.debug('[TokenRefresh] Notifying token refresh callback');
          this.onTokenRefreshed(newToken);
        }

        return newToken;
      } else {
        logger.error('[TokenRefresh] Failed to refresh token', {
          status: response.status,
          message: response.message,
          error: response.error,
          fullResponse: JSON.stringify(response)
        });
        this.handleTokenExpired();
        return null;
      }
    } catch (error) {
      logger.error('[TokenRefresh] Exception while refreshing token', {
        error: error,
        errorMessage: error instanceof Error ? error.message : String(error),
        errorStack: error instanceof Error ? error.stack : undefined
      });
      this.handleTokenExpired();
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
      const response = await ipcClient.invoke('auth.extendToken', { 
        token: this.currentToken,
        seconds 
      });
      
      if (response.status === 'success') {
        logger.info('[TokenRefresh] Token extended successfully', {
          time_remaining_hours: response.data.time_remaining_hours
        });
        return true;
      } else {
        logger.error('[TokenRefresh] Failed to extend token:', response.message);
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
