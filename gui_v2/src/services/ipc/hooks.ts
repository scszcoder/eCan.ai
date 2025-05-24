import { useCallback, useEffect, useState } from 'react';
import { IPCClient } from './client';
import { IPCResponse, IPCRequestHandler, IPCErrorHandler } from './types';

/**
 * IPC Hook 返回值类型
 */
interface UseIPCResult {
    /** IPC 客户端是否就绪 */
    isReady: boolean;
    /** 发送请求到 Python 后端 */
    sendRequest: (method: string, params?: unknown) => Promise<IPCResponse>;
    /** 注册请求处理器 */
    registerRequestHandler: (method: string, handler: IPCRequestHandler) => void;
    /** 设置错误处理器 */
    setErrorHandler: (handler: IPCErrorHandler) => void;
}

/**
 * IPC Hook
 * 提供在 React 组件中使用 IPC 客户端的功能
 */
export function useIPC(): UseIPCResult {
    const [client] = useState(() => IPCClient.getInstance());
    const [isReady, setIsReady] = useState(false);

    useEffect(() => {
        // 检查 IPC 是否已初始化
        const checkIPC = () => {
            if (client['ipc']) {
                setIsReady(true);
            } else {
                setTimeout(checkIPC, 100);
            }
        };
        checkIPC();

        // 组件卸载时清理
        return () => {
            // 可以在这里添加清理逻辑
        };
    }, [client]);

    /**
     * 发送请求到 Python 后端
     */
    const sendRequest = useCallback(async (
        method: string,
        params?: unknown
    ): Promise<IPCResponse> => {
        if (!isReady) {
            throw new Error('IPC client is not ready');
        }
        return client.sendRequest(method, params);
    }, [client, isReady]);

    /**
     * 注册请求处理器
     */
    const registerRequestHandler = useCallback((
        method: string,
        handler: IPCRequestHandler
    ): void => {
        if (!isReady) {
            throw new Error('IPC client is not ready');
        }
        client.registerRequestHandler(method, handler);
    }, [client, isReady]);

    /**
     * 设置错误处理器
     */
    const setErrorHandler = useCallback((
        handler: IPCErrorHandler
    ): void => {
        if (!isReady) {
            throw new Error('IPC client is not ready');
        }
        client.setErrorHandler(handler);
    }, [client, isReady]);

    return {
        isReady,
        sendRequest,
        registerRequestHandler,
        setErrorHandler
    };
} 