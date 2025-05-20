import { useEffect, useCallback } from 'react';
import { ipcService, IPCResponse, LogEntry, NetworkRequest, ElementLog } from '../services/ipc';
import { logger } from '../utils/logger';

interface UseIPCOptions {
  onEvent?: (eventType: string, data: unknown) => void;
  onResponse?: (responseType: string, data: unknown) => void;
}

export function useIPC(options: UseIPCOptions = {}) {
  const { onEvent, onResponse } = options;

  // 注册全局事件处理器
  useEffect(() => {
    if (onEvent) {
      const handler = (data: unknown) => {
        try {
          // 假设事件数据包含 eventType 和 data
          const eventData = data as { eventType: string; data: unknown };
          onEvent(eventData.eventType, eventData.data);
        } catch (e) {
          logger.error('Error in event handler:', e);
        }
      };

      ipcService.registerEventHandler('*', handler);
      return () => {
        ipcService.unregisterEventHandler('*', handler);
      };
    }
  }, [onEvent]);

  // 注册全局响应处理器
  useEffect(() => {
    if (onResponse) {
      const handler = (response: IPCResponse) => {
        try {
          onResponse(response.responseType, response.result);
        } catch (e) {
          logger.error('Error in response handler:', e);
        }
      };

      ipcService.registerResponseHandler('*', handler);
      return () => {
        ipcService.unregisterResponseHandler('*', handler);
      };
    }
  }, [onResponse]);

  // 发送命令
  const sendCommand = useCallback((command: string, data?: Record<string, unknown>) => {
    ipcService.sendCommand(command, data);
  }, []);

  // 发送请求
  const sendRequest = useCallback(<T>(requestType: string, data?: Record<string, unknown>): Promise<T> => {
    return ipcService.sendRequest<T>(requestType, data);
  }, []);

  // 预定义的命令方法
  const reload = useCallback(() => {
    ipcService.reload();
  }, []);

  const toggleDevTools = useCallback(() => {
    ipcService.toggleDevTools();
  }, []);

  const clearLogs = useCallback(() => {
    ipcService.clearLogs();
  }, []);

  const executeScript = useCallback((script: string) => {
    ipcService.executeScript(script);
  }, []);

  // 新增的命令方法
  const showNotification = useCallback((title: string, message: string) => {
    sendCommand('show_notification', { title, message });
  }, [sendCommand]);

  const updateProgress = useCallback((progress: number, message: string) => {
    sendCommand('update_progress', { progress, message });
  }, [sendCommand]);

  // 预定义的请求方法
  const getPageInfo = useCallback(() => {
    return ipcService.getPageInfo();
  }, []);

  const getConsoleLogs = useCallback(() => {
    return ipcService.getConsoleLogs();
  }, []);

  const getNetworkLogs = useCallback(() => {
    return ipcService.getNetworkLogs();
  }, []);

  const getElementLogs = useCallback(() => {
    return ipcService.getElementLogs();
  }, []);

  return {
    sendCommand,
    sendRequest,
    reload,
    toggleDevTools,
    clearLogs,
    executeScript,
    showNotification,
    updateProgress,
    getPageInfo,
    getConsoleLogs,
    getNetworkLogs,
    getElementLogs
  };
} 