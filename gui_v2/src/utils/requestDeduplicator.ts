/**
 * 请求去重管理器
 * 防止相同的API请求在短时间内重复发送
 */

interface PendingRequest {
  promise: Promise<any>;
  timestamp: number;
}

class RequestDeduplicator {
  private pendingRequests: Map<string, PendingRequest> = new Map();
  private readonly CACHE_DURATION = 1000; // 1秒内的重复请求将被去重

  /**
   * 生成请求的唯一键
   */
  private generateKey(method: string, params: any): string {
    return `${method}:${JSON.stringify(params)}`;
  }

  /**
   * 清理过期的请求缓存
   */
  private cleanup(): void {
    const now = Date.now();
    for (const [key, request] of this.pendingRequests.entries()) {
      if (now - request.timestamp > this.CACHE_DURATION) {
        this.pendingRequests.delete(key);
      }
    }
  }

  /**
   * 执行去重的请求
   * @param method 方法名
   * @param params 参数
   * @param requestFn 实际的请求函数
   * @returns Promise
   */
  async deduplicate<T>(
    method: string,
    params: any,
    requestFn: () => Promise<T>
  ): Promise<T> {
    const key = this.generateKey(method, params);
    
    // 清理过期缓存
    this.cleanup();

    // 检查是否有相同的请求正在进行
    const existingRequest = this.pendingRequests.get(key);
    if (existingRequest) {
      console.log(`[RequestDeduplicator] 去重请求: ${method}`, params);
      return existingRequest.promise;
    }

    // 创建新的请求
    const promise = requestFn().finally(() => {
      // 请求完成后清理缓存
      this.pendingRequests.delete(key);
    });

    // 缓存请求
    this.pendingRequests.set(key, {
      promise,
      timestamp: Date.now()
    });

    return promise;
  }

  /**
   * 清除所有缓存的请求
   */
  clear(): void {
    this.pendingRequests.clear();
  }

  /**
   * 获取当前缓存的请求数量
   */
  size(): number {
    return this.pendingRequests.size;
  }
}

// 导出单例实例
export const requestDeduplicator = new RequestDeduplicator();
export default RequestDeduplicator;
