/**
 * API Router - 智能路由层，根据 API 定义自动选择通信通道
 * 
 * 职责：
 * 1. 根据平台和 API 定义选择最佳通信通道
 * 2. 执行实际的网络请求（IPC/HTTP/GraphQL）
 * 3. 统一错误处理和响应格式转换
 */

import { APIDefinition, Channel } from './api-config';
import { ipcClient } from '../ipc/ipcClient';
import { appSyncRequest } from '../web/appSyncClient';
import { logger } from '../../utils/logger';
import type { APIResponse } from '../ipc/api';

const getEnv = () => {
  try {
    if (typeof import.meta !== 'undefined' && (import.meta as any).env) {
      return (import.meta as any).env as Record<string, any>;
    }
  } catch {}
  try {
    if (typeof process !== 'undefined' && (process as any).env) {
      return (process as any).env as Record<string, any>;
    }
  } catch {}
  return {} as Record<string, any>;
};

const isTruthyEnvValue = (value: unknown): boolean => {
  const normalized = String(value ?? '').trim().toLowerCase();
  return normalized === '1' || normalized === 'true' || normalized === 'yes' || normalized === 'on';
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
export class APIRouter {
  private static instance: APIRouter;
  private config: Required<APIRouterConfig>;

  private constructor(config: APIRouterConfig = {}) {
    this.config = {
      localServerBaseUrl: config.localServerBaseUrl || 'http://localhost:4668',
      enableLogging: config.enableLogging ?? true,
      defaultTimeout: config.defaultTimeout || 30000
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
        case Channel.IPC:
          response = await this.executeViaIPC<T>(method, params, options);
          break;
        
        case Channel.GRAPHQL:
          response = await this.executeViaGraphQL<T>(definition, params);
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
      
      return this.createErrorResponse(
        'EXECUTION_ERROR',
        error instanceof Error ? error.message : String(error),
        error
      );
    }
  }

  /**
   * 通过 IPC 执行请求
   * 复制自 ipcApi.executeRequest 的 IPC 执行逻辑
   */
  private async executeViaIPC<T>(
    method: string,
    params?: any,
    options?: { timeout?: number }
  ): Promise<APIResponse<T>> {
    const startTs = Date.now();
    const timeout = options?.timeout || this.config.defaultTimeout;
    
    try {
      // 确保 IPC 客户端已初始化
      if (!ipcClient.isInitialized()) {
        await ipcClient.initialize();
      }

      // 调用 IPC
      const response = await ipcClient.invoke(method, params, { timeout });

      if (this.config.enableLogging) {
        logger.debug(`[APIRouter] IPC response for ${method}`, { 
          response, 
          durationMs: Date.now() - startTs 
        });
      }

      if (response.status === 'success') {
        return {
          success: true,
          data: response.result as T
        };
      } else {
        const errorCode = String(response.error?.code || 'UNKNOWN_ERROR');
        
        // Handle INVALID_TOKEN error by clearing stored token and redirecting to login
        if (errorCode === 'INVALID_TOKEN' || errorCode === 'TOKEN_REQUIRED') {
          logger.warn(`[APIRouter] Authentication failed for ${method}: ${errorCode}`);
          
          // Clear the invalid token from storage
          try {
            const { userStorageManager } = await import('../storage/UserStorageManager');
            userStorageManager.removeToken();
            logger.info('[APIRouter] Cleared invalid token from storage');
            
            // Show user notification (only once)
            if (!sessionStorage.getItem('token_expired_notification_shown')) {
              sessionStorage.setItem('token_expired_notification_shown', 'true');
              
              // Try to show Ant Design message if available
              try {
                const { message } = await import('antd');
                message.warning('Your session has expired. Please log in again.');
              } catch {
                // Fallback to console if Ant Design not available
                console.warn('Session expired. Please log in again.');
              }
            }
            
            // Redirect to login page if not already there
            if (window.location.hash !== '#/login') {
              logger.info('[APIRouter] Redirecting to login due to invalid token');
              // Small delay to allow notification to show
              setTimeout(() => {
                window.location.hash = '#/login';
              }, 500);
            }
          } catch (error) {
            logger.error('[APIRouter] Error clearing invalid token:', error);
          }
        }
        
        return {
          success: false,
          error: {
            code: errorCode,
            message: response.error?.message || 'Unknown error occurred',
            details: response.error?.details
          }
        };
      }
    } catch (error) {
      if (this.config.enableLogging) {
        logger.error(`[APIRouter] IPC error for ${method}`, { 
          error, 
          durationMs: Date.now() - startTs 
        });
      }
      
      return this.createErrorResponse(
        'IPC_ERROR',
        error instanceof Error ? error.message : 'IPC request failed',
        error
      );
    }
  }

  /**
   * 通过 GraphQL 执行请求
   */
  private async executeViaGraphQL<T>(
    definition: APIDefinition,
    params?: any
  ): Promise<APIResponse<T>> {
    const query = definition.graphql?.query;
    const mutation = definition.graphql?.mutation;
    const resultPath = definition.graphql?.resultPath;
    const gqlString = (query || mutation || '').trim();

    console.log(`[APIRouter] executeViaGraphQL: method=${definition.method}, resultPath=${resultPath}`);
    console.log(`[APIRouter] executeViaGraphQL params:`, JSON.stringify(params, null, 2));

    try {
      const normalizedParams = (() => {
        if (!params || typeof params !== 'object') return params;
        if (!gqlString.includes('getAllMine')) return params;
        if (!('username' in params)) return params;
        if ('owner' in params || 'userId' in params) return params;

        return {
          ...params,
          owner: (params as any).username,
          userId: (params as any).username,
        };
      })();

      // IMPORTANT: LocalServer GraphQL handler requires extensions.method for routing.
      // Pass definition.method to appSyncRequest so appSyncClient can include it in body.extensions.
      const data = await appSyncRequest<any>(gqlString, normalizedParams, undefined, definition.method);
      
      console.log(`[APIRouter] executeViaGraphQL raw response:`, JSON.stringify(data, null, 2));

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

      console.log(`[APIRouter] executeViaGraphQL final result:`, JSON.stringify(result, null, 2));

      return {
        success: true,
        data: result as T
      };
    } catch (error) {
      console.error(`[APIRouter] executeViaGraphQL error:`, error);
      return this.createErrorResponse(
        'GRAPHQL_ERROR',
        error instanceof Error ? error.message : 'GraphQL request failed',
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
   * 选择通信通道
   * 根据 VITE_IPC_MODE 环境变量和 GraphQL 配置自动判断
   */
  private selectChannel(_definition: APIDefinition): Channel {
    const env = getEnv();
    
    // 如果 VITE_IPC_MODE 为 true，使用 IPC
    if (isTruthyEnvValue(env.VITE_IPC_MODE)) {
      return Channel.IPC;
    }

    // 否则默认使用 GraphQL/AppSync
    return Channel.GRAPHQL;
  }

  /**
   * 获取当前配置
   */
  public getConfig(): Readonly<Required<APIRouterConfig>> {
    return { ...this.config };
  }
}

/**
 * 导出默认实例
 */
export const apiRouter = APIRouter.getInstance();
