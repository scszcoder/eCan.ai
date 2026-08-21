import { useState, useEffect, useCallback, useRef } from 'react';
import { get_ipc_api } from '../services/ipc_api';
import { logger } from '../utils/logger';
import i18n from '../i18n';

export interface SystemStatus {
  ready: boolean;
  status: string;  // i18n key like 'system.ready' or 'system.initializing'
}

/**
 * Simple hook to check system initialization status.
 * Polls backend every 2 seconds until ready.
 */
export function useSystemStatus(enabled: boolean = true) {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [isChecking, setIsChecking] = useState(true);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const checkStatus = useCallback(async () => {
    try {
      const ipcApi = get_ipc_api();
      if (!ipcApi) return;

      const response = await ipcApi.getInitializationProgress();
      if (response.success && response.data) {
        const data = response.data as SystemStatus;
        setStatus(data);
        setIsChecking(false);

        // Stop polling when ready
        if (data.ready && intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      }
    } catch (err) {
      logger.debug('[useSystemStatus] Check failed:', err);
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;

    // Initial check
    checkStatus();

    // Poll every 2 seconds until ready
    intervalRef.current = setInterval(checkStatus, 2000);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [enabled, checkStatus]);

  // Get localized message based on status i18n key
  const message = status?.status ? i18n.t(status.status) : i18n.t('system.initializing', '加载中...');

  return {
    status,
    isReady: status?.ready ?? false,
    isChecking,
    message,
    refetch: checkStatus
  };
}

// Backward compatibility alias
export const useInitializationProgress = useSystemStatus;
export const forceCleanupInitializationProgress = () => {};
export interface InitializationProgress extends SystemStatus {}
