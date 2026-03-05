/**
 * 网络健康检查服务
 * 提供快速网络状态检测，避免长时间等待超时
 */

import { logger } from '../../utils/logger';

export class NetworkHealthChecker {
  private static instance: NetworkHealthChecker;
  private isOnline: boolean = true;
  private lastCheckTime: number = 0;
  private checkInterval: number = 5000; // 5秒缓存

  private constructor() {
    // 监听浏览器在线/离线事件
    if (typeof window !== 'undefined') {
      window.addEventListener('online', () => {
        this.isOnline = true;
        logger.info('[NetworkHealth] Network is online');
      });
      
      window.addEventListener('offline', () => {
        this.isOnline = false;
        logger.warn('[NetworkHealth] Network is offline');
      });
      
      this.isOnline = navigator.onLine;
    }
  }

  public static getInstance(): NetworkHealthChecker {
    if (!NetworkHealthChecker.instance) {
      NetworkHealthChecker.instance = new NetworkHealthChecker();
    }
    return NetworkHealthChecker.instance;
  }

  /**
   * 快速检查网络是否可用
   * 使用缓存避免频繁检查
   */
  public isNetworkAvailable(): boolean {
    const now = Date.now();
    
    // 如果浏览器报告离线，直接返回
    if (!navigator.onLine) {
      return false;
    }
    
    // 使用缓存结果
    if (now - this.lastCheckTime < this.checkInterval) {
      return this.isOnline;
    }
    
    this.lastCheckTime = now;
    return this.isOnline;
  }

  /**
   * 主动检测本地服务器连通性
   * 使用快速超时（2秒）
   */
  public async checkLocalServer(baseUrl: string): Promise<boolean> {
    if (!navigator.onLine) {
      return false;
    }

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 2000); // 2秒快速超时
      
      const response = await fetch(`${baseUrl}/health`, {
        method: 'GET',
        signal: controller.signal,
        cache: 'no-cache'
      });
      
      clearTimeout(timeoutId);
      
      const isHealthy = response.ok;
      this.isOnline = isHealthy;
      return isHealthy;
    } catch (error) {
      logger.debug('[NetworkHealth] Local server check failed:', error);
      this.isOnline = false;
      return false;
    }
  }

  /**
   * 重置网络状态
   */
  public reset(): void {
    this.isOnline = navigator.onLine;
    this.lastCheckTime = 0;
  }
}

export const networkHealthChecker = NetworkHealthChecker.getInstance();
