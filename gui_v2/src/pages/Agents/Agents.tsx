import React, { useEffect, useCallback, useRef, forwardRef, useImperativeHandle } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { useAgentStore } from '../../stores/agentStore';
import { useUserStore } from '../../stores/userStore';
import { useOrgStore } from '../../stores/orgStore';
import { Agent } from './types';
import { DisplayNode } from '../Orgs/types';
import { logger } from '@/utils/logger';
import { get_ipc_api } from '@/services/ipc_api';
import { useTranslation } from 'react-i18next';

// 定义组件的 ref 类型
export interface AgentsRef {
  refresh: () => void;
}

const Agents = forwardRef<AgentsRef>((_props, ref) => {
    const { t } = useTranslation();
    const location = useLocation();
    const setAgents = useAgentStore((state) => state.setAgents);
    const setError = useAgentStore((state) => state.setError);
    const shouldFetchAgents = useAgentStore((state) => state.shouldFetchAgents);
    const username = useUserStore((state) => state.username);
    const agents = useAgentStore((state) => state.agents);
    const hasFetchedRef = useRef(false);
    const isInitializedRef = useRef(false);
    const renderCountRef = useRef(0);
    // const lastLocationRef = useRef(location.pathname); // 暂时不需要

    // 添加调试信息 - 只在开发环境显示
    if (process.env.NODE_ENV === 'development') {
      renderCountRef.current++;
      
      // 如果渲染次数过多，发出警告
      if (renderCountRef.current > 5) {
        console.warn('⚠️ Agents组件渲染次数过多:', renderCountRef.current, {
          username, 
          agentsCount: agents?.length || 0, 
          location: location.pathname,
          hasFetched: hasFetchedRef.current,
          isInitialized: isInitializedRef.current
        });
      } else {
        console.log(`🔄 Agents渲染 #${renderCountRef.current}:`, { 
          username, 
          agentsCount: agents?.length || 0, 
          location: location.pathname,
          hasFetched: hasFetchedRef.current,
          isInitialized: isInitializedRef.current
        });
      }
    }

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
        
        // 检查是否已经有数据且缓存仍然有效
        if (hasFetchedRef.current && shouldFetchAgents() === false) {
          console.log('Agents: Skipping fetch - already fetched and cache is valid');
          return;
        }
        
        // 如果已经有agents数据且是最近获取的，跳过请求
        if (agents && agents.length > 0 && shouldFetchAgents() === false) {
          console.log('Agents: Skipping fetch - data already available and fresh');
          hasFetchedRef.current = true;
          return;
        }

        console.log('Agents: fetchAgents called', { username, shouldFetch: shouldFetchAgents(), hasFetched: hasFetchedRef.current });

        // 检查是否已经有组织数据（从 VirtualPlatform 获取）
        // 如果有，则从组织数据中提取 agents，避免重复请求
        const { displayNodes } = useOrgStore.getState();
        console.log('Agents: Checking cache - displayNodes:', displayNodes?.length || 0, 'nodes');
        
        if (displayNodes && displayNodes.length > 0) {
            // 从 displayNodes 中提取所有 agents
            const allAgents: Agent[] = [];
            displayNodes.forEach((node: DisplayNode) => {
                if (node.agents) {
                    console.log(`Agents: Found ${node.agents.length} agents in node:`, node.name);
                    // 转换 OrgAgent 到 Agent 类型 (简化转换)
                    const convertedAgents = node.agents.map(orgAgent => orgAgent as unknown as Agent);
                    allAgents.push(...convertedAgents);
                }
            });
            
            console.log('Agents: Total agents extracted from cache:', allAgents.length);
            
            if (allAgents.length > 0) {
                setAgents(allAgents);
                logger.info('Agents: Using cached data from organization structure:', allAgents.length, 'agents');
                hasFetchedRef.current = true; // 标记为已获取
                return;
            } else {
                console.log('Agents: No agents found in cache, will proceed with API request');
            }
        } else {
            console.log('Agents: No displayNodes available, will proceed with API request');
        }

        // 如果没有缓存数据，才进行 API 请求
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

    // 监听组织数据变化，当有数据时触发 agents 获取
    const displayNodes = useOrgStore((state) => state.displayNodes);
    
    useEffect(() => {
        // 只在组件首次挂载时执行，避免重复初始化
        console.log('Agents: useEffect called', { 
            isInitialized: isInitializedRef.current, 
            username, 
            hasOrgData: displayNodes && displayNodes.length > 0 
        });
        
        // 只有在用户名存在且未初始化时才获取数据
        if (username && !isInitializedRef.current) {
            fetchAgents();
            isInitializedRef.current = true;
        }
    }, [username, displayNodes]); // 依赖 displayNodes，当组织数据加载完成时重新评估

    // 使用 Outlet 渲染子路由，这样主组件保持挂载状态
    return <Outlet />;
});

// 使用 React.memo 包装组件，避免不必要的重新渲染
// 由于这个组件主要是路由容器，props变化较少，使用默认比较即可
export default React.memo(Agents);