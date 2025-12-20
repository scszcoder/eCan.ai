/**
 * Unified User Storage Manager
 * Centralized management for all user-related data storage operations
 * Handles localStorage, sessionStorage, and Zustand store synchronization
 */

import { logger } from '../../utils/logger';
import { useUserStore } from '../../stores/userStore';
import { logoutManager } from '../LogoutManager';

// User data interfaces
export interface UserInfo {
  username: string;
  role: string;
  email?: string;
  name?: string;           // Display name (from Google profile)
  given_name?: string;     // First name
  family_name?: string;    // Last name
  picture?: string;        // Avatar URL (from Google)
  email_verified?: boolean;
  login_type?: 'password' | 'google';  // Login method
}

export interface LoginSession {
  token: string;
  userInfo: UserInfo;
  loginTime: number;
  expiresAt?: number;
}

export interface UserPreferences {
  language: string;
  theme?: string;
  [key: string]: any;
}

// Storage keys constants
const STORAGE_KEYS = {
  // Authentication
  TOKEN: 'ipc_auth_token',
  TOKEN_LEGACY: 'token', // For backward compatibility
  IS_AUTHENTICATED: 'isAuthenticated',
  
  // User info
  USERNAME: 'username',
  USER_INFO: 'user_info',
  USER_ROLE: 'userRole',
  
  // Session
  LOGIN_TIME: 'loginTime',
  LAST_LOGIN: 'lastLogin',
  
  // Preferences
  LANGUAGE: 'language',
  THEME: 'theme',
} as const;

export class UserStorageManager {
  private static instance: UserStorageManager;
  
  private constructor() {}
  
  public static getInstance(): UserStorageManager {
    if (!UserStorageManager.instance) {
      UserStorageManager.instance = new UserStorageManager();
      // RegisterlogoutCleanupFunction
      UserStorageManager.instance.registerLogoutCleanup();
    }
    return UserStorageManager.instance;
  }

  // ===== Token Management =====
  
  /**
   * Set authentication token
   */
  setToken(token: string): void {
    try {
      localStorage.setItem(STORAGE_KEYS.TOKEN, token);
      localStorage.setItem(STORAGE_KEYS.TOKEN_LEGACY, token); // Backward compatibility
      logger.debug('Token stored successfully');
    } catch (error) {
      logger.error('Failed to store token:', error);
      throw new Error('Failed to store authentication token');
    }
  }
  
  /**
   * Get authentication token
   */
  getToken(): string | null {
    try {
      // Try new key first, fallback to legacy key
      return localStorage.getItem(STORAGE_KEYS.TOKEN) || 
             localStorage.getItem(STORAGE_KEYS.TOKEN_LEGACY);
    } catch (error) {
      logger.error('Failed to get token:', error);
      return null;
    }
  }
  
  /**
   * Remove authentication token
   */
  removeToken(): void {
    try {
      localStorage.removeItem(STORAGE_KEYS.TOKEN);
      localStorage.removeItem(STORAGE_KEYS.TOKEN_LEGACY);
      logger.debug('Token removed successfully');
    } catch (error) {
      logger.error('Failed to remove token:', error);
    }
  }
  
  /**
   * Check if user has valid token
   */
  hasValidToken(): boolean {
    const token = this.getToken();
    return !!token && token.length > 0;
  }

  // ===== User Info Management =====
  
  /**
   * Set user information
   */
  setUserInfo(userInfo: UserInfo): void {
    try {
      // Store complete user info
      localStorage.setItem(STORAGE_KEYS.USER_INFO, JSON.stringify(userInfo));
      
      // Store individual fields for backward compatibility
      localStorage.setItem(STORAGE_KEYS.USERNAME, userInfo.username);
      localStorage.setItem(STORAGE_KEYS.USER_ROLE, userInfo.role);
      
      // Update Zustand store
      useUserStore.getState().setUsername(userInfo.username);
      
      logger.debug('User info stored successfully:', userInfo.username);
    } catch (error) {
      logger.error('Failed to store user info:', error);
      throw new Error('Failed to store user information');
    }
  }
  
  /**
   * Get user information
   */
  getUserInfo(): UserInfo | null {
    try {
      const userInfoStr = localStorage.getItem(STORAGE_KEYS.USER_INFO);
      if (userInfoStr) {
        return JSON.parse(userInfoStr);
      }
      
      // Fallback to individual fields
      const username = localStorage.getItem(STORAGE_KEYS.USERNAME);
      const role = localStorage.getItem(STORAGE_KEYS.USER_ROLE);
      
      if (username && role) {
        return { username, role };
      }
      
      return null;
    } catch (error) {
      logger.error('Failed to get user info:', error);
      return null;
    }
  }
  
  /**
   * Get username only
   */
  getUsername(): string | null {
    const userInfo = this.getUserInfo();
    return userInfo?.username || null;
  }
  
  /**
   * Get user role only
   */
  getUserRole(): string | null {
    const userInfo = this.getUserInfo();
    return userInfo?.role || null;
  }

  // ===== Authentication State Management =====
  
  /**
   * Set authentication state
   */
  setAuthenticationState(isAuthenticated: boolean): void {
    try {
      localStorage.setItem(STORAGE_KEYS.IS_AUTHENTICATED, isAuthenticated.toString());
      if (isAuthenticated) {
        localStorage.setItem(STORAGE_KEYS.LOGIN_TIME, Date.now().toString());
      }
      logger.debug('Authentication state set:', isAuthenticated);
    } catch (error) {
      logger.error('Failed to set authentication state:', error);
    }
  }
  
  /**
   * Check if user is authenticated
   */
  isAuthenticated(): boolean {
    try {
      const isAuth = localStorage.getItem(STORAGE_KEYS.IS_AUTHENTICATED) === 'true';
      const hasToken = this.hasValidToken();
      const hasUserInfo = !!this.getUserInfo();
      
      return isAuth && hasToken && hasUserInfo;
    } catch (error) {
      logger.error('Failed to check authentication state:', error);
      return false;
    }
  }

  // ===== Session Management =====
  
  /**
   * Save complete login session
   */
  saveLoginSession(session: LoginSession): void {
    try {
      this.setToken(session.token);
      this.setUserInfo(session.userInfo);
      this.setAuthenticationState(true);
      
      // Store session metadata
      localStorage.setItem(STORAGE_KEYS.LOGIN_TIME, session.loginTime.toString());
      if (session.expiresAt) {
        localStorage.setItem('sessionExpiresAt', session.expiresAt.toString());
      }
      
      logger.info('Login session saved successfully for user:', session.userInfo.username);
    } catch (error) {
      logger.error('Failed to save login session:', error);
      throw new Error('Failed to save login session');
    }
  }
  
  /**
   * Get current login session
   */
  getLoginSession(): LoginSession | null {
    try {
      const token = this.getToken();
      const userInfo = this.getUserInfo();
      const loginTimeStr = localStorage.getItem(STORAGE_KEYS.LOGIN_TIME);
      
      if (!token || !userInfo || !loginTimeStr) {
        return null;
      }
      
      const session: LoginSession = {
        token,
        userInfo,
        loginTime: parseInt(loginTimeStr, 10)
      };
      
      const expiresAtStr = localStorage.getItem('sessionExpiresAt');
      if (expiresAtStr) {
        session.expiresAt = parseInt(expiresAtStr, 10);
      }
      
      return session;
    } catch (error) {
      logger.error('Failed to get login session:', error);
      return null;
    }
  }
  
  /**
   * Check if session is valid (not expired)
   */
  isSessionValid(): boolean {
    const session = this.getLoginSession();
    if (!session) return false;
    
    if (session.expiresAt && Date.now() > session.expiresAt) {
      logger.warn('Session expired');
      return false;
    }
    
    return true;
  }

  // ===== User Preferences =====
  
  /**
   * Set user preferences
   */
  setUserPreferences(preferences: UserPreferences): void {
    try {
      Object.entries(preferences).forEach(([key, value]) => {
        if (key in STORAGE_KEYS) {
          localStorage.setItem(STORAGE_KEYS[key as keyof typeof STORAGE_KEYS], value);
        } else {
          localStorage.setItem(`pref_${key}`, JSON.stringify(value));
        }
      });
      logger.debug('User preferences saved');
    } catch (error) {
      logger.error('Failed to save user preferences:', error);
    }
  }
  
  /**
   * Get user preferences
   */
  getUserPreferences(): UserPreferences {
    try {
      const preferences: UserPreferences = {
        language: localStorage.getItem(STORAGE_KEYS.LANGUAGE) || 'en-US'
      };
      
      const theme = localStorage.getItem(STORAGE_KEYS.THEME);
      if (theme) preferences.theme = theme;
      
      return preferences;
    } catch (error) {
      logger.error('Failed to get user preferences:', error);
      return { language: 'en-US' };
    }
  }

  // ===== Cleanup Operations =====

  /**
   * Complete logout process with comprehensive cleanup
   */
  logout(): void {
    try {
      logger.info('Starting logout process...');

      // Clear all user data
      this.clearAllUserData();

      // Additional logout-specific cleanup
      // Clear any cached API responses
      sessionStorage.clear();

      // Clear any temporary data
      const tempKeys = Object.keys(localStorage).filter(key =>
        key.includes('temp_') ||
        key.includes('cache_') ||
        key.includes('draft_')
      );
      tempKeys.forEach(key => localStorage.removeItem(key));

      logger.info('Logout process completed successfully');
    } catch (error) {
      logger.error('Error during logout process:', error);
      throw new Error('Logout process failed');
    }
  }

  /**
   * Clear all user data (logout)
   */
  clearAllUserData(): void {
    try {
      // Remove all user-related data from STORAGE_KEYS
      Object.values(STORAGE_KEYS).forEach(key => {
        localStorage.removeItem(key);
      });

      // Remove additional session and app data
      const additionalKeys = [
        'sessionExpiresAt',
        'lastActivity',
        'appData',
        'userPreferences',
        // Add any other user-specific keys that might exist
      ];

      additionalKeys.forEach(key => {
        localStorage.removeItem(key);
      });

      // Clear any keys that start with 'pref_' (user preferences)
      const allKeys = Object.keys(localStorage);
      allKeys.forEach(key => {
        if (key.startsWith('pref_') || key.startsWith('user_') || key.startsWith('session_')) {
          localStorage.removeItem(key);
        }
      });

      // Clear Zustand store
      useUserStore.getState().setUsername(null);

      logger.info('All user data cleared successfully');
    } catch (error) {
      logger.error('Failed to clear user data:', error);
      throw new Error('Failed to clear user data during logout');
    }
  }
  
  /**
   * Restore user state from storage (for page refresh)
   */
  restoreUserState(): boolean {
    try {
      if (!this.isAuthenticated() || !this.isSessionValid()) {
        logger.info('No valid user session found');
        return false;
      }
      
      const userInfo = this.getUserInfo();
      if (userInfo) {
        // Restore Zustand store
        useUserStore.getState().setUsername(userInfo.username);
        logger.info('User state restored for:', userInfo.username);
        return true;
      }
      
      return false;
    } catch (error) {
      logger.error('Failed to restore user state:', error);
      return false;
    }
  }

  // ===== Debug and Maintenance =====
  
  /**
   * Get all user storage data (for debugging)
   */
  getAllUserData(): Record<string, any> {
    const data: Record<string, any> = {};
    
    Object.entries(STORAGE_KEYS).forEach(([name, key]) => {
      const value = localStorage.getItem(key);
      if (value) {
        data[name] = value;
      }
    });
    
    return data;
  }
  
  /**
   * Validate storage integrity
   */
  validateStorageIntegrity(): boolean {
    try {
      const hasToken = this.hasValidToken();
      const hasUserInfo = !!this.getUserInfo();
      const isAuth = localStorage.getItem(STORAGE_KEYS.IS_AUTHENTICATED) === 'true';
      
      const isValid = hasToken === hasUserInfo && hasUserInfo === isAuth;
      
      if (!isValid) {
        logger.warn('Storage integrity check failed', {
          hasToken,
          hasUserInfo,
          isAuth
        });
      }
      
      return isValid;
    } catch (error) {
      logger.error('Storage integrity validation failed:', error);
      return false;
    }
  }

  /**
   * RegisterlogoutCleanupFunction
   */
  private registerLogoutCleanup(): void {
    logoutManager.registerCleanup({
      name: 'UserStorageManager',
      cleanup: () => {
        logger.info('[UserStorageManager] Cleaning up for logout...');
        this.logout(); // 使用现有的logoutMethod
        logger.info('[UserStorageManager] Cleanup completed');
      },
      priority: 25 // 中等Priority
    });
  }
}

// Export singleton instance
export const userStorageManager = UserStorageManager.getInstance();

// Export for backward compatibility
export const tokenStorage = {
  getToken: () => userStorageManager.getToken(),
  setToken: (token: string) => userStorageManager.setToken(token),
  removeToken: () => userStorageManager.removeToken()
};
