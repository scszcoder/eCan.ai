import { useEffect, useState } from 'react';
import { IPCService } from './ipcService';
import type { BaseResponse } from './types';

/**
 * IPC Hook
 * 用于在 React 组件中使用 IPC 服务
 */
export function useIPC() {
    const [isReady, setIsReady] = useState(false);
    const ipcService = IPCService.getInstance();

    useEffect(() => {
        const init = async () => {
            try {
                await ipcService.waitForReady();
                setIsReady(true);
            } catch (error) {
                console.error('Failed to initialize IPC:', error);
            }
        };

        init();
    }, []);

    return {
        isReady,
        sendMessage: (content: string): Promise<BaseResponse> => 
            ipcService.sendTextMessage(content),
        sendConfig: (action: 'get' | 'set', key: string, value?: string): Promise<BaseResponse> => 
            ipcService.sendConfigMessage(action, key, value),
        sendCommand: (command: string, args?: unknown[]): Promise<BaseResponse> => 
            ipcService.sendCommandMessage(command, args),
        sendEvent: (event: string, data?: unknown): Promise<BaseResponse> => 
            ipcService.sendEventMessage(event, data)
    };
} 