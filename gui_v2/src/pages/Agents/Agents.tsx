/**
 * Agents 路由ContainerComponent
 * 
 * 职责：
 * 1. 作为路由Container，Render子路由
 * 2. 协调DataGet，避免重复Load
 * 3. Listen组织Data变化，及时Update agents Data
 */

import React, { useRef, useCallback, useEffect, useImperativeHandle, forwardRef } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { useAgentStore } from '@/stores/agentStore';
import { useOrgStore } from '@/stores/orgStore';
import { useUserStore } from '@/stores/userStore';
import type { Agent } from './types';
import type { DisplayNode } from '@/stores/orgStore';

const Agents = forwardRef<any, any>((props, ref) => {
  const location = useLocation();
  const setAgents = useAgentStore((state) => state.setAgents);
  const setError = useAgentStore((state) => state.setError);
  const username = useUserStore((state) => state.username);
  const agents = useAgentStore((state) => state.agents);
  const hasFetchedRef = useRef(false);
  const isInitializedRef = useRef(false);

  // 使用 useImperativeHandle 暴露RefreshMethod
  useImperativeHandle(ref, () => ({
    refresh: () => {
      if (username) {
        fetchAgents();
      }
    },
  }), [username]);

  const fetchAgents = useCallback(async () => {
    if (!username) return;

    // 首先Check agentStore 中是否已经有Data
    const currentAgents = useAgentStore.getState().agents;
    
    if (currentAgents && currentAgents.length > 0) {
      setAgents(currentAgents);
      hasFetchedRef.current = true;
      return;
    }

    // Check是否已经有组织Data（从 OrgNavigator Get）
    const { displayNodes, loading: orgLoading } = useOrgStore.getState();
    
    if (displayNodes && displayNodes.length > 0) {
      // 从 displayNodes 中提取All agents
      const allAgents: Agent[] = [];
      displayNodes.forEach((node: DisplayNode) => {
        if (node.agents) {
          const convertedAgents = node.agents.map(orgAgent => orgAgent as unknown as Agent);
          allAgents.push(...convertedAgents);
        }
      });
      
      if (allAgents.length > 0) {
        setAgents(allAgents);
        hasFetchedRef.current = true;
        return;
      }
    }

    if (orgLoading) {
      // 组织Data正在Load，等待后Retry
      setTimeout(() => {
        if (!hasFetchedRef.current) {
          fetchAgents();
        }
      }, 500);
      return;
    }
    
    // Display空Status
    setAgents([]);
    hasFetchedRef.current = true;
  }, [username, setError, setAgents]);

  // Listen组织Data变化
  const displayNodes = useOrgStore((state) => state.displayNodes);
  const orgLoading = useOrgStore((state) => state.loading);
  const agentStoreAgents = useAgentStore((state) => state.agents);
  
  useEffect(() => {
    // If agentStore 中有Data，直接使用
    if (agentStoreAgents && agentStoreAgents.length > 0 && !hasFetchedRef.current) {
      setAgents(agentStoreAgents);
      hasFetchedRef.current = true;
      isInitializedRef.current = true;
      return;
    }
    
    // 只有在User名存在且未Initialize时才GetData
    if (username && !isInitializedRef.current) {
      fetchAgents();
      isInitializedRef.current = true;
    }
    // If组织DataLoadCompleted且之前没有SuccessGet到 agents，重新尝试
    else if (username && !orgLoading && displayNodes && displayNodes.length > 0 && !hasFetchedRef.current) {
      fetchAgents();
    }
  }, [username, displayNodes, orgLoading, agentStoreAgents, setAgents]);

  return <Outlet />;
});

export default React.memo(Agents);
