import React, { useEffect, useCallback, useRef, useMemo, forwardRef, useImperativeHandle } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { useAppDataStore } from '../../stores/appDataStore';
import { useUserStore } from '../../stores/userStore';
import { Agent } from './types';
import { logger } from '@/utils/logger';
import { get_ipc_api } from '@/services/ipc_api';
import { useTranslation } from 'react-i18next';

// 定义组件的 ref 类型
export interface AgentsRef {
  refresh: () => void;
}

const Agents = forwardRef<AgentsRef>((props, ref) => {
    const { t } = useTranslation();
    const location = useLocation();
    const setAgents = useAppDataStore((state) => state.setAgents);
    const setError = useAppDataStore((state) => state.setError);
    const shouldFetchAgents = useAppDataStore((state) => state.shouldFetchAgents);
    const username = useUserStore((state) => state.username);
    const agents = useAppDataStore((state) => state.agents);
    const hasFetchedRef = useRef(false);
    const isInitializedRef = useRef(false);
    const lastLocationRef = useRef(location.pathname);

    // 添加调试信息
    console.log('Agents: Component rendered', { 
      username, 
      agentsCount: agents?.length || 0, 
      location: location.pathname,
      hasFetched: hasFetchedRef.current,
      isInitialized: isInitializedRef.current
    });

    // 使用 useImperativeHandle 暴露稳定的方法
    useImperativeHandle(ref, () => ({
      refresh: () => {
        // 只在需要时刷新数据
        if (username && shouldFetchAgents()) {
          fetchAgents();
        }
      },
    }), [username, shouldFetchAgents]);

    const fetchAgents = useCallback(async () => {
        if (!username) return;
        // 简化缓存逻辑：总是获取数据，除非已经获取过且时间很短
        if (hasFetchedRef.current && shouldFetchAgents() === false) {
          console.log('Agents: Skipping fetch - already fetched and cache is valid');
          return;
        }

        console.log('Agents: fetchAgents called', { username, shouldFetch: shouldFetchAgents(), hasFetched: hasFetchedRef.current });

        // 强制获取最新数据，在后台静默更新，不显示loading状态避免页面闪烁
        setError(null);
        try {
            const response = await get_ipc_api().getAgents<{ agents: Agent[] }>(username, []);
            console.log(t('pages.agents.fetched_agents') || 'Fetched agents:', response.data);
            if (response.success && response.data) {
                // 总是更新store中的agents数据，即使是空数组也更新
                setAgents(response.data.agents || []);
                logger.info(t('pages.agents.updated_data_from_api') || 'Updated agents data from API:', response.data.agents?.length || 0, t('common.agents') || 'agents');
            } else {
                logger.error(t('pages.agents.fetch_failed') || 'Failed to fetch agents:', response.error?.message);
                // 可以选择显示错误消息，但不影响页面显示
                // messageApi.error(`${t('common.failed')}: ${response.error?.message || 'Unknown error'}`);
            }
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : t('common.unknown_error') || 'Unknown error';
            setError(errorMessage);
            logger.error(t('pages.agents.error_fetching') || 'Error fetching agents:', errorMessage);
            // 可以选择显示错误消息，但不影响页面显示
            // messageApi.error(`${t('common.failed')}: ${errorMessage}`);
        } finally {
            hasFetchedRef.current = true;
        }
    }, [username, setError, setAgents, shouldFetchAgents, t]);

    useEffect(() => {
        // 只在组件首次挂载时执行，避免重复初始化
        console.log('Agents: useEffect called', { isInitialized: isInitializedRef.current, username });
        // 简化逻辑：总是尝试获取数据
        if (!isInitializedRef.current || !hasFetchedRef.current) {
            fetchAgents();
            isInitializedRef.current = true;
        }
    }, [fetchAgents]);

    // 使用 Outlet 渲染子路由，这样主组件保持挂载状态
    return <Outlet />;
});

// 使用 React.memo 包装组件，避免不必要的重新渲染
// 添加自定义比较函数，确保组件只在真正需要时重新渲染
export default React.memo(Agents, () => {
    // 由于这个组件没有props，总是返回true表示不需要重新渲染
    return true;
});