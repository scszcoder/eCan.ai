import { useEffect, useCallback } from 'react';
import { pageRefreshManager, PageRefreshAction } from '../services/events/PageRefreshManager';
import { logger } from '../utils/logger';

/**
 * PageRefresh管理器Hook
 * Used for在PageRefresh后Execute指定的Operation
 */
export const usePageRefreshManager = (
    action: PageRefreshAction,
    actionName: string = 'default'
) => {
    // RegisterPageRefreshOperation
    const registerAction = useCallback((name: string, action: PageRefreshAction) => {
        pageRefreshManager.registerAction(name, action);
    }, []);

    // CancelRegisterOperation
    const unregisterAction = useCallback((name: string) => {
        return pageRefreshManager.unregisterAction(name);
    }, []);

    // 手动ExecuteOperation
    const executeAction = useCallback(async (name: string) => {
        await pageRefreshManager.executeAction(name);
    }, []);

    // ExecuteAllOperation
    const executeAllActions = useCallback(async () => {
        await pageRefreshManager.executeAllActions();
    }, []);

    // GetStatus
    const getStatus = useCallback(() => {
        return pageRefreshManager.getStatus();
    }, []);

    // 自动RegisterOperation
    useEffect(() => {
        if (action) {
            registerAction(actionName, action);
            
            // ComponentUnmount时CancelRegister
            return () => {
                unregisterAction(actionName);
            };
        }
    }, [actionName, action, registerAction, unregisterAction]);

    return {
        registerAction,
        unregisterAction,
        executeAction,
        executeAllActions,
        getStatus,
        // 便捷Method
        register: registerAction,
        unregister: unregisterAction,
        execute: executeAction,
        executeAll: executeAllActions
    };
};

/**
 * 简化的PageRefreshHook
 * 只Used for在PageRefresh后ExecuteOperation
 */
export const usePageRefresh = (action: PageRefreshAction) => {
    return usePageRefreshManager(action, 'pageRefresh');
}; 