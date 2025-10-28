import { useState, useEffect, useCallback } from 'react';
import { loadNodeStateSchema } from '../stores/nodeStateSchemaStore';
import { get_ipc_api } from '../services/ipc_api';
import { logger } from '../utils/logger';
import { logoutManager } from '../services/LogoutManager';

// Global singleton to prevent multiple polling instances
class InitializationProgressManager {
  private static instance: InitializationProgressManager;
  private subscribers: Set<(progress: InitializationProgress | null) => void> = new Set();
  private currentProgress: InitializationProgress | null = null;
  private isPolling = false;
  private intervalId: NodeJS.Timeout | null = null;
  private pollInterval = 1000; // Default 1 second
  private maxPollingDuration = 60000; // 60 seconds timeout
  private pollingStartTime: number | null = null;

  static getInstance(): InitializationProgressManager {
    if (!InitializationProgressManager.instance) {
      logger.debug('[InitProgressManager] Creating singleton instance');
      InitializationProgressManager.instance = new InitializationProgressManager();
      // RegisterCleanupFunction到logout管理器
      InitializationProgressManager.instance.registerLogoutCleanup();
    } else {
      logger.debug('[InitProgressManager] Returning existing singleton instance');
    }
    return InitializationProgressManager.instance;
  }

  subscribe(callback: (progress: InitializationProgress | null) => void): () => void {
    logger.debug(`[InitProgressManager] New subscriber added. Total: ${this.subscribers.size + 1}`);
    this.subscribers.add(callback);

    // Send current progress immediately
    if (this.currentProgress) {
      callback(this.currentProgress);
    }

    // Start polling if not already started
    this.startPolling();

    // Return unsubscribe function
    return () => {
      this.subscribers.delete(callback);
      logger.debug(`[InitProgressManager] Subscriber removed. Remaining: ${this.subscribers.size}`);
      if (this.subscribers.size === 0) {
        logger.debug('[InitProgressManager] No more subscribers, stopping polling');
        this.stopPolling();
      }
    };
  }

  private isFetching = false; // Add fetch guard

  private async fetchProgress(): Promise<boolean> {
    // Prevent concurrent fetches
    if (this.isFetching) {
      logger.debug('[InitProgressManager] Fetch already in progress, skipping...');
      return false;
    }

    this.isFetching = true;

    try {
      const ipcApi = get_ipc_api();
      if (!ipcApi) {
        throw new Error('IPC API not available');
      }

      const requestId = Math.random().toString(36).substring(2, 11);
      logger.debug(`[InitProgressManager] Sending getInitializationProgress request [${requestId}]...`);
      const response = await ipcApi.getInitializationProgress();

      if (response.success && response.data) {
        this.currentProgress = response.data;

        // Notify all subscribers
        this.subscribers.forEach(callback => callback(this.currentProgress));

        // Stop polling if fully ready
        if (response.data.fully_ready) {
          this.stopPolling();
          return true; // Signal to stop polling
        }
      } else {
        logger.error('Failed to get initialization progress:', response.error?.message);
      }
    } catch (err) {
      logger.error('Failed to fetch initialization progress:', err);
    } finally {
      this.isFetching = false;
    }

    return false; // Continue polling
  }

  private startPolling(): void {
    if (this.isPolling) {
      logger.debug(`[InitProgressManager] Already polling, skipping start (subscribers: ${this.subscribers.size})`);
      return; // Already polling
    }

    this.isPolling = true;
    this.pollingStartTime = Date.now(); // 记录开始Time
    logger.debug(`[InitProgressManager] Starting polling... (subscribers: ${this.subscribers.size})`);

    // Initial fetch
    this.fetchProgress().then(shouldStop => {
      if (shouldStop) {
        return;
      }

      // Start interval polling with timeout protection
      this.intervalId = setInterval(async () => {
        // Check是否Timeout
        if (this.pollingStartTime && Date.now() - this.pollingStartTime > this.maxPollingDuration) {
          logger.warn('[InitProgressManager] ⚠️ Polling timeout after 60s, stopping...');
          this.stopPolling();
          
          // Notification订阅者TimeoutStatus
          const timeoutProgress: InitializationProgress = {
            ui_ready: false,
            critical_services_ready: false,
            async_init_complete: false,
            fully_ready: false,
            sync_init_complete: false,
            message: 'Initialization timeout - please refresh the page'
          };
          this.currentProgress = timeoutProgress;
          this.subscribers.forEach(callback => callback(timeoutProgress));
          return;
        }
        
        logger.debug(`[InitProgressManager] Interval fetch (subscribers: ${this.subscribers.size})`);
        const shouldStop = await this.fetchProgress();
        if (shouldStop) {
          this.stopPolling();
        }
      }, this.pollInterval);
    });
  }

  private stopPolling(): void {
    if (!this.isPolling) {
      return;
    }

    this.isPolling = false;
    this.pollingStartTime = null; // Reset开始Time

    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
    logger.debug('[InitProgressManager] Polling stopped');
  }

  /**
   * RegisterlogoutCleanupFunction
   */
  private registerLogoutCleanup(): void {
    logoutManager.registerCleanup({
      name: 'InitializationProgressManager',
      cleanup: () => {
        logger.info('[InitProgressManager] Cleaning up for logout...');
        this.stopPolling();
        this.subscribers.clear();
        this.currentProgress = null;
        this.isFetching = false;
        logger.info('[InitProgressManager] Cleanup completed');
      },
      priority: 10 // 高Priority，尽早Cleanup
    });
  }

  /**
   * 强制CleanupAllStatus（Used forlogout）
   */
  public forceCleanup(): void {
    logger.info('[InitProgressManager] Force cleanup initiated');
    this.stopPolling();
    this.subscribers.clear();
    this.currentProgress = null;
    this.isFetching = false;
  }

  // Method to manually refetch (for external use)
  async refetch(): Promise<void> {
    await this.fetchProgress();
  }
}

export interface InitializationProgress {
  ui_ready: boolean;
  critical_services_ready: boolean;
  async_init_complete: boolean;
  fully_ready: boolean;
  sync_init_complete: boolean;
  message: string;
}

export interface UseInitializationProgressReturn {
  progress: InitializationProgress | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

/**
 * Hook to monitor MainWindow initialization progress using singleton manager
 * Note: pollInterval is now managed globally by the singleton
 */
export function useInitializationProgress(
  enabled: boolean = true
): UseInitializationProgressReturn {
  const [progress, setProgress] = useState<InitializationProgress | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      await InitializationProgressManager.getInstance().refetch();
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      logger.error('Failed to refetch initialization progress:', err);
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const manager = InitializationProgressManager.getInstance();

    // Subscribe to progress updates
    const unsubscribe = manager.subscribe((newProgress) => {
      setProgress(newProgress);
      setError(null);

      // Stop loading if fully ready
      if (newProgress?.fully_ready) {
        setIsLoading(false);
        // Prefetch NodeState schema so node editors don't wait later
        loadNodeStateSchema().catch(() => {/* ignore errors; panel will fallback */});
      }
    });

    return unsubscribe;
  }, [enabled]);

  return {
    progress,
    isLoading,
    error,
    refetch
  };
}
