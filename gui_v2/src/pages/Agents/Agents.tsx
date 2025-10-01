/**
 * Agents 路由容器组件
 * 
 * 职责：
 * 1. 作为路由容器，渲染子路由
 * 2. 协调数据获取，避免重复加载
 * 3. 监听组织数据变化，及时更新 agents 数据
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

  // 使用 useImperativeHandle 暴露刷新方法
  useImperativeHandle(ref, () => ({
    refresh: () => {
      if (username) {
        fetchAgents();
      }
    },
  }), [username]);

  const fetchAgents = useCallback(async () => {
    if (!username) return;

    // 首先检查 agentStore 中是否已经有数据
    const currentAgents = useAgentStore.getState().agents;
    
    if (currentAgents && currentAgents.length > 0) {
      setAgents(currentAgents);
      hasFetchedRef.current = true;
      return;
    }

    // 检查是否已经有组织数据（从 OrgNavigator 获取）
    const { displayNodes, loading: orgLoading } = useOrgStore.getState();
    
    if (displayNodes && displayNodes.length > 0) {
      // 从 displayNodes 中提取所有 agents
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
      // 组织数据正在加载，等待后重试
      setTimeout(() => {
        if (!hasFetchedRef.current) {
          fetchAgents();
        }
      }, 500);
      return;
    }
    
    // 显示空状态
    setAgents([]);
    hasFetchedRef.current = true;
  }, [username, setError, setAgents]);

  // 监听组织数据变化
  const displayNodes = useOrgStore((state) => state.displayNodes);
  const orgLoading = useOrgStore((state) => state.loading);
  const agentStoreAgents = useAgentStore((state) => state.agents);
  
  useEffect(() => {
    // 如果 agentStore 中有数据，直接使用
    if (agentStoreAgents && agentStoreAgents.length > 0 && !hasFetchedRef.current) {
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
      fetchAgents();
    }
  }, [username, displayNodes, orgLoading, agentStoreAgents, setAgents]);

  return <Outlet />;
});

export default React.memo(Agents);
