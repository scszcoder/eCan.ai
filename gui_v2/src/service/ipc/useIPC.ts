import { useEffect, useState } from 'react';
import { IPCService } from './ipcService';
import type { BaseResponse } from './types';

/**
 * IPC Hook
 * 用于在 React 组件中使用 IPC 服务
 */
export function useIPC() {
    const [isReady, setIsReady] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const ipcService = IPCService.getInstance();

    useEffect(() => {
        const checkReady = async () => {
            try {
                // 等待 WebChannel 就绪
                await ipcService.waitForReady();
                // 检查 window.ipc 是否存在
                if (!window.ipc) {
                    throw new Error('IPC object not found in window');
                }
                setIsReady(true);
                setError(null);
            } catch (err) {
                setError(err instanceof Error ? err.message : 'Failed to initialize IPC');
            }
        };

        // 如果页面已经加载完成，立即检查
        if (document.readyState === 'complete') {
            checkReady();
        } else {
            // 否则等待页面加载完成
            window.addEventListener('load', checkReady);
            return () => {
                window.removeEventListener('load', checkReady);
            };
        }
    }, []);

    const sendMessage = async (content: string): Promise<BaseResponse> => {
        try {
            return await ipcService.sendTextMessage(content);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to send message');
            return {
                success: false,
                error: err instanceof Error ? err.message : 'Failed to send message'
            };
        }
    };

    const sendConfig = async (action: 'get' | 'set', key: string, value?: unknown): Promise<BaseResponse> => {
        try {
            return await ipcService.sendConfigMessage(action, key, value);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to send config');
            return {
                success: false,
                error: err instanceof Error ? err.message : 'Failed to send config'
            };
        }
    };

    const sendCommand = async (command: string, args?: unknown[]): Promise<BaseResponse> => {
        try {
            return await ipcService.sendCommandMessage(command, args);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to send command');
            return {
                success: false,
                error: err instanceof Error ? err.message : 'Failed to send command'
            };
        }
    };

    const sendEvent = async (event: string, data?: unknown): Promise<BaseResponse> => {
        try {
            return await ipcService.sendEventMessage(event, data);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to send event');
            return {
                success: false,
                error: err instanceof Error ? err.message : 'Failed to send event'
            };
        }
    };

    return {
        isReady,
        error,
        sendMessage,
        sendConfig,
        sendCommand,
        sendEvent
    };
} 