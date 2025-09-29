import React, { useEffect, useCallback, useRef, forwardRef, useImperativeHandle } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { useAgentStore } from '../../stores/agentStore';
import { useUserStore } from '../../stores/userStore';
import { useOrgStore } from '../../stores/orgStore';
import { Agent } from './types';
import { DisplayNode } from '../Orgs/types';
import { logger } from '@/utils/logger';
import { useTranslation } from 'react-i18next';
import { useOrgAgentsUpdate } from './hooks/useOrgAgentsUpdate';

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
        
        console.log('Agents: fetchAgents called', { username, shouldFetch: shouldFetchAgents(), hasFetched: hasFetchedRef.current });

        // 首先检查 agentStore 中是否已经有数据
        const currentAgents = useAgentStore.getState().agents;
        console.log('Agents: Checking agentStore - current agents:', currentAgents?.length || 0);
        
        // 如果 agentStore 中有数据，直接使用（不检查缓存时间，因为数据可能是最新的）
        if (currentAgents && currentAgents.length > 0) {
          console.log('Agents: Using data from agentStore:', currentAgents.length, 'agents');
          setAgents(currentAgents);
          hasFetchedRef.current = true;
          return;
        }

        // 检查是否已经有组织数据（从 OrgNavigator 获取）
        const { displayNodes } = useOrgStore.getState();
        console.log('Agents: Checking displayNodes:', displayNodes?.length || 0, 'nodes');
        
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
            
            console.log('Agents: Total agents extracted from displayNodes:', allAgents.length);
            
            if (allAgents.length > 0) {
                setAgents(allAgents);
                logger.info('Agents: Using cached data from organization structure:', allAgents.length, 'agents');
                hasFetchedRef.current = true;
                return;
            }
        }

        // 检查组织数据是否正在加载
        const { loading: orgLoading } = useOrgStore.getState();
        
        if (orgLoading) {
            console.log('Agents: Organization data is still loading, waiting...');
            // 组织数据正在加载，等待一段时间后重试
            setTimeout(() => {
                if (!hasFetchedRef.current) {
                    console.log('Agents: Retrying after org data load...');
                    fetchAgents();
                }
            }, 500); // 减少到500ms，更快响应
            return;
        }
        
        // 最后检查：如果有组织结构但没有agents，显示空状态
        const { root, treeOrgs } = useOrgStore.getState();
        if (root || (treeOrgs && treeOrgs.length > 0)) {
            console.log('Agents: Organization structure exists but no agents found, showing empty state');
            setAgents([]);
            hasFetchedRef.current = true;
            return;
        }

        // 完全没有组织数据的情况下，显示空状态
        console.log('Agents: No organization data available, showing empty state');
        setAgents([]);
        hasFetchedRef.current = true;
    }, [username, setError, setAgents, shouldFetchAgents, t]);

    // 监听组织数据变化，当有数据时触发 agents 获取
    const displayNodes = useOrgStore((state) => state.displayNodes);
    const orgLoading = useOrgStore((state) => state.loading);
    
    // 监听 agentStore 的变化
    const agentStoreAgents = useAgentStore((state) => state.agents);
    
    useEffect(() => {
        // 只在组件首次挂载时执行，避免重复初始化
        console.log('Agents: useEffect called', { 
            isInitialized: isInitializedRef.current, 
            username, 
            hasOrgData: displayNodes && displayNodes.length > 0,
            orgLoading,
            agentStoreCount: agentStoreAgents?.length || 0
        });
        
        // 如果 agentStore 中有数据，直接使用
        if (agentStoreAgents && agentStoreAgents.length > 0 && !hasFetchedRef.current) {
            console.log('Agents: Found agents in agentStore, using them directly');
            setAgents(agentStoreAgents);
            hasFetchedRef.current = true;
            isInitializedRef.current = true;
            return;
        }
        
        // 只有在用户名存在且未初始化时才获取数据
        if (username && !isInitializedRef.current) {
            fetchAgents();
            isInitializedRef.current = true;
        }
        // 如果组织数据加载完成且之前没有成功获取到 agents，重新尝试
        else if (username && !orgLoading && displayNodes && displayNodes.length > 0 && !hasFetchedRef.current) {
            console.log('Agents: Organization data loaded, retrying agent fetch...');
            fetchAgents();
        }
    }, [username, displayNodes, orgLoading, agentStoreAgents, setAgents]); // 添加 agentStoreAgents 依赖

    // 强制刷新 agents 数据的回调
    const forceRefreshAgents = useCallback(() => {
        logger.info('[Agents] Force refreshing agents data...');
        
        // 重置所有缓存标记，强制重新获取数据
        hasFetchedRef.current = false;
        isInitializedRef.current = false;
        
        // 立即检查 agentStore 中是否有最新数据
        const currentAgents = useAgentStore.getState().agents;
        logger.info('[Agents] Current agentStore has:', currentAgents?.length || 0, 'agents');
        
        if (currentAgents && currentAgents.length > 0) {
            logger.info('[Agents] Using fresh data from agentStore');
            setAgents(currentAgents);
            hasFetchedRef.current = true;
            return;
        }
        
        // 如果 agentStore 中没有数据，调用 fetchAgents
        if (username) {
            logger.info('[Agents] Calling fetchAgents with force refresh...');
            fetchAgents();
        } else {
            logger.warn('[Agents] No username available for force refresh');
        }
    }, [username, fetchAgents, setAgents]);

    // 使用自定义 Hook 监听组织数据更新事件
    useOrgAgentsUpdate(forceRefreshAgents, [forceRefreshAgents], 'Agents');

    // 使用 Outlet 渲染子路由，这样主组件保持挂载状态
    return <Outlet />;
});

// 使用 React.memo 包装组件，避免不必要的重新渲染
// 由于这个组件主要是路由容器，props变化较少，使用默认比较即可
export default React.memo(Agents);
