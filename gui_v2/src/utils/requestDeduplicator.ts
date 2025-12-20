/**
 * Request去重管理器
 * 防止相同的APIRequest在短Time内重复Send
 */

interface PendingRequest {
  promise: Promise<any>;
  timestamp: number;
}

class RequestDeduplicator {
  private pendingRequests: Map<string, PendingRequest> = new Map();
  private readonly CACHE_DURATION = 1000; // 1秒内的重复Request将被去重

  /**
   * 生成Request的唯一键
   */
  private generateKey(method: string, params: any): string {
    return `${method}:${JSON.stringify(params)}`;
  }

  /**
   * Cleanup过期的RequestCache
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
   * Execute去重的Request
   * @param method Method名
   * @param params Parameter
   * @param requestFn 实际的RequestFunction
   * @returns Promise
   */
  async deduplicate<T>(
    method: string,
    params: any,
    requestFn: () => Promise<T>
  ): Promise<T> {
    const key = this.generateKey(method, params);
    
    // Cleanup过期Cache
    this.cleanup();

    // Check是否有相同的Request正在进行
    const existingRequest = this.pendingRequests.get(key);
    if (existingRequest) {
      console.log(`[RequestDeduplicator] 去重Request: ${method}`, params);
      return existingRequest.promise;
    }

    // Create新的Request
    const promise = requestFn().finally(() => {
      // RequestCompleted后CleanupCache
      this.pendingRequests.delete(key);
    });

    // CacheRequest
    this.pendingRequests.set(key, {
      promise,
      timestamp: Date.now()
    });

    return promise;
  }

  /**
   * 清除AllCache的Request
   */
  clear(): void {
    this.pendingRequests.clear();
  }

  /**
   * GetWhen前Cache的RequestCount
   */
  size(): number {
    return this.pendingRequests.size;
  }
}

// Export单例实例
export const requestDeduplicator = new RequestDeduplicator();
export default RequestDeduplicator;
