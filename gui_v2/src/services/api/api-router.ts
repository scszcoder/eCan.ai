/**
 * API Router - 智能路由层，根据 API 定义自动选择通信通道
 * 
 * 职责：
 * 1. 根据平台和 API 定义选择最佳通信通道
 * 2. 执行实际的网络请求（IPC/HTTP/GraphQL）
 * 3. 统一错误处理和响应格式转换
 */

import { APIDefinition, Channel } from './api-config';
import { appSyncRequest } from '../web/appSyncClient';
import { logger } from '../../utils/logger';
import type { APIResponse } from '../ipc/api';
import { detectPlatform } from '@/config/platform';
import { userStorageManager } from '../storage/UserStorageManager';
import { networkHealthChecker } from './network-health';

const getLoginRedirectUrl = (): string => {
  if (window.location.protocol === 'file:') {
    return `${window.location.href.split('#')[0]}#/login`;
  }
  return `${window.location.origin}/#/login`;
};

const shouldHandleDesktopAuthLossSilently = (errorCode?: string): boolean => {
  try {
    if (detectPlatform() !== 'desktop') return false;
    if (errorCode === 'TOKEN_REQUIRED') return true;
    if (userStorageManager.wasDesktopColdStartTokenCleared()) return true;
    return !userStorageManager.getToken();
  } catch {
    return false;
  }
};

const isConfirmedSessionReplacement = (details?: unknown): boolean => {
  try {
    const value = details && typeof details === 'object' && 'details' in details
      ? (details as any).details
      : details;
    return !!(
      value &&
      typeof value === 'object' &&
      ((value as any).reason === 'session_replaced' || (value as any).session_replaced === true)
    );
  } catch {
    return false;
  }
};

/**
 * API 路由器配置
 */
export interface APIRouterConfig {
  /** Local Server 基础 URL */
  localServerBaseUrl?: string;
  /** 是否启用请求日志 */
  enableLogging?: boolean;
  /** 默认超时时间（毫秒） */
  defaultTimeout?: number;
}

/**
 * API 路由器
 * 
 * 负责根据 API 定义和运行环境，自动选择合适的通信通道执行请求
 */
/**
 * 请求队列项
 */
interface QueuedRequest<T> {
  execute: () => Promise<APIResponse<T>>;
  resolve: (value: APIResponse<T>) => void;
  reject: (error: any) => void;
}

export class APIRouter {
  private static instance: APIRouter;
  private config: Required<APIRouterConfig>;
  
  // 请求队列相关
  private requestQueue: QueuedRequest<any>[] = [];
  private isProcessingQueue = false;

  private constructor(config: APIRouterConfig = {}) {
    this.config = {
      localServerBaseUrl: config.localServerBaseUrl ?? '',
      enableLogging: config.enableLogging ?? true,
      defaultTimeout: config.defaultTimeout || 30000  // 30 秒，后端串行处理请求时排队可能超过 10 秒
    };
  }

  /**
   * 获取 API 路由器单例
   */
  public static getInstance(config?: APIRouterConfig): APIRouter {
    if (!APIRouter.instance) {
      APIRouter.instance = new APIRouter(config);
    }
    return APIRouter.instance;
  }

  /**
   * 更新配置
   */
  public updateConfig(config: Partial<APIRouterConfig>): void {
    this.config = { ...this.config, ...config };
  }

  /**
   * 获取认证 token
   */
  private getAuthToken(): string | null {
    const token = userStorageManager.getToken();
    console.log('[APIRouter] getAuthToken:', token ? `${token.substring(0, 20)}...` : 'null');
    return token;
  }

  /**
   * 执行 API 请求
   * 
   * @param definition - API 定义
   * @param params - 请求参数
   * @param options - 请求选项
   * @returns API 响应
   */
  public async execute<T = any>(
    definition: APIDefinition,
    params?: any,
    options?: { timeout?: number }
  ): Promise<APIResponse<T>> {
    const startTime = Date.now();
    const method = definition.method;
    
    // if (this.config.enableLogging) {
    //   logger.debug(`[APIRouter] Executing: ${method}`, { params });
    // }

    try {
      // 选择通信通道
      const channel = this.selectChannel(definition);
      
      if (this.config.enableLogging) {
        logger.debug(`[APIRouter] Selected channel: ${channel} for ${method}`);
      }

      // 根据通道执行请求
      let response: APIResponse<T>;
      
      switch (channel) {
        case Channel.LOCAL:
          response = await this.executeViaLocalGraphQL<T>(method, params, options);
          break;
        
        case Channel.CLOUD:
          response = await this.executeViaCloudGraphQL<T>(definition, params);
          break;
        
        default:
          return this.createErrorResponse(
            'UNSUPPORTED_CHANNEL',
            `Channel '${channel}' is not supported`
          );
      }

      if (this.config.enableLogging) {
        const duration = Date.now() - startTime;
        logger.debug(`[APIRouter] Completed: ${method} in ${duration}ms`, {
          success: response.success,
          channel
        });
      }

      return response;

    } catch (error) {
      const duration = Date.now() - startTime;
      logger.error(`[APIRouter] Failed: ${method} after ${duration}ms`, error);
      
      // 检查是否是 token 错误
      const errorMessage = error instanceof Error ? error.message : String(error);
      if (this.isTokenError(errorMessage)) {
        await this.handleTokenExpired();
      }
      
      return this.createErrorResponse(
        'EXECUTION_ERROR',
        errorMessage,
        error
      );
    }
  }

  /**
   * 通过本地 GraphQL 执行请求
   * 使用本地 /graphql 端点与 Python 后端通信
   */
  private async executeViaLocalGraphQL<T>(
    method: string,
    params?: any,
    options?: { timeout?: number }
  ): Promise<APIResponse<T>> {
    const startTs = Date.now();
    const timeout = options?.timeout || this.config.defaultTimeout;
    
    try {
      // 快速检测网络连接状态
      if (!networkHealthChecker.isNetworkAvailable()) {
        logger.warn(`[APIRouter] Network offline, skipping ${method}`);
        return this.createErrorResponse(
          'NETWORK_OFFLINE',
          'Network is offline. Please check your internet connection.'
        );
      }
      
      // 动态获取本地服务器地址
      const baseUrl = this.getLocalServerUrl();
      const url = `${baseUrl}/graphql`;
      
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), timeout);
      
      // 获取 token 并添加到 headers
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      
      const token = this.getAuthToken();
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      
      const response = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          query: `query ${method} { ${method} }`,
          operationName: method,
          variables: params || {},  // 使用标准 GraphQL variables 字段
          extensions: {
            method  // 保留 method 用于后端路由
          }
        }),
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const result = await response.json();

      if (this.config.enableLogging) {
        console.log(`[APIRouter] Local GraphQL response for ${method} (${Date.now() - startTs}ms):`, result);
      }

      // 处理 GraphQL 响应格式
      if (result.errors && result.errors.length > 0) {
        const error = result.errors[0];
        const errorCode = String(error.extensions?.code || 'GRAPHQL_ERROR');
        
        // Handle SYSTEM_NOT_READY: Check if user has valid token, if not redirect to login
        if (errorCode === 'SYSTEM_NOT_READY' || errorCode === 'MAIN_WINDOW_NOT_AVAILABLE') {
          logger.warn(`[APIRouter] System not ready for ${method}: ${errorCode}`);
          
          // Check if user has a valid token
          const token = this.getAuthToken();
          if (!token) {
            // No token - user should be on login page
            logger.info('[APIRouter] System not ready and no token found, redirecting to login');
            
            // Clear any stale data
            try {
              const { userStorageManager } = await import('../storage/UserStorageManager');
              userStorageManager.removeToken();
            } catch (error) {
              logger.error('[APIRouter] Error clearing token:', error);
            }
            
            // Redirect to login if not already there
            if (window.location.hash !== '#/login') {
              setTimeout(() => {
                window.location.replace(getLoginRedirectUrl());
              }, 100);
            }
            
            return {
              success: true,
              data: null as any
            };
          }
          
          // Has token but system not ready - this is normal during initialization
          // Return error to let UI handle it (e.g., show loading state)
          logger.debug('[APIRouter] System not ready but token exists, waiting for initialization');
          return {
            success: false,
            error: {
              code: errorCode,
              message: 'System is initializing, please wait...',
              details: error.extensions
            }
          };
        }
        
        // Handle INVALID_TOKEN error by clearing stored token and redirecting to login
        if (errorCode === 'INVALID_TOKEN' || errorCode === 'TOKEN_REQUIRED') {
          logger.warn(`[APIRouter] Authentication failed for ${method}: ${errorCode}`);

          if (shouldHandleDesktopAuthLossSilently(errorCode)) {
            try {
              userStorageManager.removeToken();
              sessionStorage.removeItem('token_expired_notification_shown');
              logger.info(`[APIRouter] Silently handling desktop auth bootstrap loss for ${method}: ${errorCode}`);
              if (window.location.hash !== '#/login') {
                setTimeout(() => {
                  window.location.replace(getLoginRedirectUrl());
                }, 100);
              }
            } catch (error) {
              logger.error('[APIRouter] Error silently handling desktop auth loss:', error);
            }
            return {
              success: true,
              data: null as any
            };
          }
          
          // IMPORTANT: INVALID_TOKEN means the token is truly invalid (e.g., session replaced by new login)
          // This is different from SYSTEM_NOT_READY which is a transient initialization issue.
          // We should ALWAYS handle INVALID_TOKEN immediately, regardless of grace period.
          try {
            const { userStorageManager } = await import('../storage/UserStorageManager');
            
            // Clear the invalid token from storage
            userStorageManager.removeToken();
            logger.info('[APIRouter] Cleared invalid token from storage');
            
            const tokenDetails = error.extensions?.details ?? error.extensions;
            const messageKey = isConfirmedSessionReplacement(tokenDetails)
              ? 'auth.sessionInvalidated'
              : 'auth.sessionExpired';

            // Show user notification (only once)
            if (!sessionStorage.getItem('token_expired_notification_shown')) {
              sessionStorage.setItem('token_expired_notification_shown', 'true');
              
              // Try to show Ant Design message if available
              try {
                const { message } = await import('antd');
                // Get i18n translation
                const i18nModule = await import('@/i18n');
                const i18n = i18nModule.default;
                const messageText = i18n.t(messageKey);
                
                message.warning({
                  content: messageText,
                  duration: 5,
                  key: 'session-invalidated'
                });
              } catch (error) {
                // Fallback to console if Ant Design or i18n not available
                console.warn(isConfirmedSessionReplacement(tokenDetails)
                  ? 'Session invalidated. You may have logged in from another device. Please log in again.'
                  : 'Session expired. Please log in again.');
              }
            }
            
            // Redirect to login page if not already there
            if (window.location.hash !== '#/login') {
              logger.info('[APIRouter] Redirecting to login due to invalid token');
              // Force full page reload to login to ensure React Router responds
              setTimeout(() => {
                window.location.replace(getLoginRedirectUrl());
              }, 500);
            }
          } catch (error) {
            logger.error('[APIRouter] Error clearing invalid token:', error);
          }
          
          // Return empty success response to prevent error display in UI
          // The redirect will happen shortly, so we don't want to show error messages
          // This prevents the error from being displayed while the redirect is in progress
          return {
            success: true,
            data: null as any  // Empty data to prevent UI errors
          };
        }
        
        console.error(`[APIRouter] GraphQL error for ${method}: code=${errorCode}, message=${error.message}, extensions=`, error.extensions);
        
        return {
          success: false,
          error: {
            code: errorCode,
            message: error.message || 'GraphQL error occurred',
            details: error.extensions
          }
        };
      }
      
      // 成功响应 - 自动解包 GraphQL 包装
      // GraphQL 响应格式: { data: { method_name: actual_data } }
      // 我们需要提取 actual_data
      let responseData = result.data;
      
      // 如果 data 是对象且只有一个键（method name），自动解包
      if (responseData && typeof responseData === 'object' && !Array.isArray(responseData)) {
        const keys = Object.keys(responseData);
        if (keys.length === 1) {
          const methodKey = keys[0];
          // 解包：data.method_name -> data
          responseData = responseData[methodKey];
          if (this.config.enableLogging) {
            console.log(`[APIRouter] Auto-unwrapped GraphQL response from '${methodKey}'`);
          }
        }
      }
      
      return {
        success: true,
        data: responseData as T
      };
    } catch (error) {
      if (this.config.enableLogging) {
        logger.error(`[APIRouter] Local GraphQL error for ${method}`, { 
          error, 
          durationMs: Date.now() - startTs 
        });
      }
      
      return this.createErrorResponse(
        'LOCAL_GRAPHQL_ERROR',
        error instanceof Error ? error.message : 'Local GraphQL request failed',
        error
      );
    }
  }

  /**
   * 通过云端 GraphQL 执行请求
   * 使用 AppSync 与 AWS 云端通信
   */
  private async executeViaCloudGraphQL<T>(
    definition: APIDefinition,
    params?: any
  ): Promise<APIResponse<T>> {
    const query = definition.graphql?.query;
    const mutation = definition.graphql?.mutation;
    const resultPath = definition.graphql?.resultPath;
    const gqlString = (query || mutation || '').trim();

    // Only log in development mode or when explicitly enabled
    const isDev = import.meta.env.DEV;
    const enableVerboseLogging = import.meta.env.VITE_VERBOSE_GRAPHQL === 'true';
    
    if (isDev || enableVerboseLogging) {
      console.log(`[APIRouter] GraphQL: ${definition.method}`);
    }

    try {
      const normalizedParams = (() => {
        if (!params || typeof params !== 'object') return params;

        // For getAllMine queries: map username → owner/userId
        if (gqlString.includes('getAllMine')) {
          if ('username' in params && !('owner' in params) && !('userId' in params)) {
            return {
              ...params,
              owner: (params as any).username,
              userId: (params as any).username,
            };
          }
          return params;
        }

        // For mutations with input objects: inject owner into each input item
        // so the Lambda can resolve user identity even when JWT expires and
        // AppSync falls back to API-key auth (no identity claims available).
        if (
          mutation
          && 'input' in params
          && !definition.method.startsWith('skill_editor.')
          && definition.method !== 'rag_register_documents'
        ) {
          const username = (params as any).username
            || userStorageManager.getUsername()
            || userStorageManager.getUserInfo()?.email
            || undefined;
          if (username) {
            const rawInput = (params as any).input;
            const injectOwner = (item: any) => {
              if (item && typeof item === 'object' && !item.owner) {
                return { ...item, owner: username };
              }
              return item;
            };
            return {
              ...params,
              input: Array.isArray(rawInput)
                ? rawInput.map(injectOwner)
                : injectOwner(rawInput),
            };
          }
        }

        return params;
      })();

      // IMPORTANT: LocalServer GraphQL handler requires extensions.method for routing.
      // Pass definition.method to appSyncRequest so appSyncClient can include it in body.extensions.
      const data = await appSyncRequest<any>(gqlString, normalizedParams, undefined, definition.method);
      
      // 根据 resultPath 提取数据
      let result = data;
      if (resultPath) {
        const paths = resultPath.split('.');
        for (const p of paths) {
          result = result?.[p];
          if (result === undefined) {
            console.error(`[APIRouter] Result path '${resultPath}' not found. Available keys:`, Object.keys(data || {}));
            return this.createErrorResponse(
              'GRAPHQL_RESULT_PATH_ERROR',
              `Result path '${resultPath}' not found in GraphQL response`
            );
          }
        }
      } else if (definition.method && result && typeof result === 'object' && definition.method in result) {
        // LocalServer GraphQL wraps response as { data: { <response_field_name>: result } }.
        // When no resultPath is specified, prefer returning payload under the method key.
        result = (result as any)[definition.method];
      }

      return {
        success: true,
        data: result as T
      };
    } catch (error) {
      console.error(`[APIRouter] GraphQL error (${definition.method}):`, error);
      
      // 检查是否是 token 错误
      const errorMessage = error instanceof Error ? error.message : 'GraphQL request failed';
      if (this.isTokenError(errorMessage)) {
        await this.handleTokenExpired();
      }
      
      return this.createErrorResponse(
        'GRAPHQL_ERROR',
        errorMessage,
        error
      );
    }
  }


  /**
   * 创建错误响应
   */
  private createErrorResponse<T>(
    code: string,
    message: string,
    details?: any
  ): APIResponse<T> {
    return {
      success: false,
      error: {
        code,
        message,
        details
      }
    };
  }

  /**
   * 获取本地服务器 URL
   *
   * production 下 WebEngineView 从 file:// 加载，但仍需要访问本地后端
   * LocalServer。直接用 `window.location.origin` 在 file:// 下会是
   * `null`/空串，所以这里固定返回 LocalServer 的 localhost URL（端口
   * 来自 VITE_LOCAL_SERVER_PORT，默认 4668，与 vite.config.ts proxy 一致）。
   * dev 下用 origin 即可：页面从 http://localhost:3000/ 加载，
   * /graphql 等由 vite proxy 转发给 LocalServer。
   */
  private getLocalServerUrl(): string {
    if (this.config.localServerBaseUrl) {
      return this.config.localServerBaseUrl;
    }
    if (typeof window !== 'undefined' && window.location?.origin?.startsWith('http')) {
      return window.location.origin;
    }
    // file:// 或 SSR: 退回 LocalServer 默认地址
    const port = import.meta.env.VITE_LOCAL_SERVER_PORT || '4668';
    return `http://localhost:${port}`;
  }

  /**
   * 选择通信通道
   * Desktop 平台使用本地 GraphQL (/graphql)
   * Web 平台使用云端 GraphQL (AppSync)
   */
  private selectChannel(_definition: APIDefinition): Channel {
    try {
      const platform = detectPlatform();
      if (platform === 'desktop') {
        return Channel.LOCAL;
      }
    } catch {
      // 如果检测失败，默认使用云端
    }

    // Web 平台使用云端 GraphQL/AppSync
    return Channel.CLOUD;
  }

  /**
   * 获取当前配置
   */
  public getConfig(): Readonly<Required<APIRouterConfig>> {
    return { ...this.config };
  }

  /**
   * 处理请求队列
   * 从队列中取出请求并顺序执行
   */
  private async processQueue(): Promise<void> {
    if (this.isProcessingQueue || this.requestQueue.length === 0) {
      return;
    }

    this.isProcessingQueue = true;

    while (this.requestQueue.length > 0) {
      const item = this.requestQueue.shift();
      if (!item) break;

      try {
        const result = await item.execute();
        item.resolve(result);
      } catch (error) {
        item.reject(error);
      }
    }

    this.isProcessingQueue = false;
  }

  /**
   * 顺序执行 API 请求（加入队列）
   * 适用于需要严格顺序执行的场景，如有状态的操作或有依赖关系的请求
   * 
   * @param definition - API 定义
   * @param params - 请求参数
   * @param options - 请求选项
   * @returns API 响应
   */
  public async executeSequential<T = any>(
    definition: APIDefinition,
    params?: any,
    options?: { timeout?: number }
  ): Promise<APIResponse<T>> {
    return new Promise((resolve, reject) => {
      this.requestQueue.push({
        execute: () => this.execute<T>(definition, params, options),
        resolve,
        reject
      });

      // 触发队列处理
      this.processQueue();
    });
  }

  /**
   * 清空请求队列
   * 用于取消所有待处理的顺序请求
   */
  public clearQueue(): void {
    // 拒绝所有待处理的请求
    this.requestQueue.forEach(item => {
      item.reject(new Error('Request queue cleared'));
    });
    this.requestQueue = [];
  }

  /**
   * Toggle window fullscreen state
   * 这是一个便捷方法，不需要 GraphQL 定义
   */
  public async windowToggleFullscreen(): Promise<boolean> {
    const response = await this.execute<{ is_fullscreen: boolean }>(
      { method: 'window_toggle_fullscreen' },
      {}
    );
    return response?.data?.is_fullscreen ?? false;
  }

  /**
   * Get window fullscreen state
   * 这是一个便捷方法，不需要 GraphQL 定义
   */
  public async windowGetFullscreenState(): Promise<boolean> {
    const response = await this.execute<{ is_fullscreen: boolean }>(
      { method: 'window_get_fullscreen_state' },
      {}
    );
    return response?.data?.is_fullscreen ?? false;
  }

  /**
   * 检查是否是 token 相关错误
   */
  private isTokenError(errorMessage: string): boolean {
    const tokenErrorPatterns = [
      'Token validation failed',
      'Token is invalid',
      'Token expired',
      'INVALID_TOKEN',
      'TOKEN_REQUIRED',
      'TOKEN_VALIDATION_ERROR',
      'Authentication failed',
      'Unauthorized'
    ];
    
    return tokenErrorPatterns.some(pattern => 
      errorMessage.includes(pattern)
    );
  }

  /**
   * 处理 token 过期/失效
   * 清除 token 并跳转到登录页面
   */
  private async handleTokenExpired(): Promise<void> {
    // 避免重复触发
    if ((window as any).__tokenExpiredHandling) {
      return;
    }
    (window as any).__tokenExpiredHandling = true;
    
    try {
      const { userStorageManager } = await import('../storage/UserStorageManager');

      if (shouldHandleDesktopAuthLossSilently()) {
        userStorageManager.removeToken();
        sessionStorage.removeItem('token_expired_notification_shown');
        logger.info('[APIRouter] Silently handling desktop token loss');
        if (window.location.hash !== '#/login') {
          setTimeout(() => {
            window.location.replace(getLoginRedirectUrl());
            (window as any).__tokenExpiredHandling = false;
          }, 100);
        } else {
          (window as any).__tokenExpiredHandling = false;
        }
        return;
      }
      
      // 检查是否在登录后宽限期内
      if (userStorageManager.isInPostLoginGracePeriod()) {
        logger.info('[APIRouter] Within post-login grace period, suppressing token expired handling');
        (window as any).__tokenExpiredHandling = false;
        return;
      }
      
      // 清除无效的 token
      userStorageManager.removeToken();
      logger.info('[APIRouter] Cleared invalid token from storage');
      
      // 显示用户通知（只显示一次）
      if (!sessionStorage.getItem('token_expired_notification_shown')) {
        sessionStorage.setItem('token_expired_notification_shown', 'true');
        
        try {
          const { message } = await import('antd');
          message.warning('您的登录已过期，请重新登录', 3);
        } catch {
          console.warn('Session expired. Please log in again.');
        }
      }
      
      // 跳转到登录页面（如果不在登录页面）
      if (window.location.hash !== '#/login') {
        logger.info('[APIRouter] Redirecting to login due to token expired');
        setTimeout(() => {
          window.location.hash = '#/login';
          // 重置标志，允许下次再次处理
          (window as any).__tokenExpiredHandling = false;
        }, 500);
      } else {
        (window as any).__tokenExpiredHandling = false;
      }
    } catch (error) {
      logger.error('[APIRouter] Error handling token expired:', error);
      (window as any).__tokenExpiredHandling = false;
    }
  }
}

/**
 * 导出默认实例
 */
export const apiRouter = APIRouter.getInstance();
