import { useEffect, useState } from 'react';
import { ipcClient } from './ipcClient';
import { BaseResponse } from './types';

export function useIPC() {
    const [isReady, setIsReady] = useState(false);

    useEffect(() => {
        const checkReady = async () => {
            try {
                await ipcClient.waitForReady();
                setIsReady(true);
            } catch (error) {
                console.error('Failed to wait for IPC ready:', error);
                setIsReady(false);
            }
        };

        checkReady();
    }, []);

    const sendMessage = async (message: string): Promise<BaseResponse> => {
        return ipcClient.sendTextMessage(message);
    };

    const sendConfig = async (action: 'get' | 'set', key: string, value?: string): Promise<BaseResponse> => {
        return ipcClient.sendConfigMessage(action, key, value);
    };

    const sendCommand = async (command: string, args?: unknown[]): Promise<BaseResponse> => {
        return ipcClient.sendCommandMessage(command, args);
    };

    const sendEvent = async (event: string, data?: unknown): Promise<BaseResponse> => {
        return ipcClient.sendEventMessage(event, data);
    };

    return {
        isReady,
        sendMessage,
        sendConfig,
        sendCommand,
        sendEvent
    };
} 