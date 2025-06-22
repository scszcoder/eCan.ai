import { useEffect, useCallback } from 'react';
import { pageRefreshManager, PageRefreshAction } from '../services/events/PageRefreshManager';
import { logger } from '../utils/logger';

/**
 * 页面刷新管理器Hook
 * 用于在页面刷新后执行指定的操作
 */
export const usePageRefreshManager = (
    action: PageRefreshAction,
    actionName: string = 'default'
) => {
    // 注册页面刷新操作
    const registerAction = useCallback((name: string, action: PageRefreshAction) => {
        pageRefreshManager.registerAction(name, action);
    }, []);

    // 取消注册操作
    const unregisterAction = useCallback((name: string) => {
        return pageRefreshManager.unregisterAction(name);
    }, []);

    // 手动执行操作
    const executeAction = useCallback(async (name: string) => {
        await pageRefreshManager.executeAction(name);
    }, []);

    // 执行所有操作
    const executeAllActions = useCallback(async () => {
        await pageRefreshManager.executeAllActions();
    }, []);

    // 获取状态
    const getStatus = useCallback(() => {
        return pageRefreshManager.getStatus();
    }, []);

    // 自动注册操作
    useEffect(() => {
        if (action) {
            registerAction(actionName, action);
            
            // 组件卸载时取消注册
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
        // 便捷方法
        register: registerAction,
        unregister: unregisterAction,
        execute: executeAction,
        executeAll: executeAllActions
    };
};

/**
 * 简化的页面刷新Hook
 * 只用于在页面刷新后执行操作
 */
export const usePageRefresh = (action: PageRefreshAction) => {
    return usePageRefreshManager(action, 'pageRefresh');
}; 