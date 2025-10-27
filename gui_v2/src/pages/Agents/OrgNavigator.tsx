import React, { useMemo, useCallback, useEffect, useState, useRef } from 'react';
import { useEffectOnActive } from 'keepalive-for-react';
import { Alert, Button, Spin, FloatButton } from 'antd';
import { PlusOutlined, InboxOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useNavigate, useLocation } from 'react-router-dom';
import { useUserStore } from '../../stores/userStore';
import { useOrgStore } from '../../stores/orgStore';
import { useAgentStore } from '../../stores/agentStore';
import OrgDoor from './components/OrgDoor';
import AgentCard from './components/AgentCard';
import './OrgNavigator.css';
import { logger } from '../../utils/logger';
import { get_ipc_api } from '@/services/ipc_api';
import { DisplayNode, GetAllOrgAgentsResponse, OrgAgent, TreeOrgNode } from '../Orgs/types';
import type { Agent } from './types';
import { extractAllAgents } from './utils/orgTreeUtils';

// 提取所有 agents（递归）
const extractAllAgentsFromTree = (node: TreeOrgNode): OrgAgent[] => {
  let allAgents: OrgAgent[] = [];

  if (node.agents && Array.isArray(node.agents)) {
    allAgents = allAgents.concat(node.agents);
  }

  if (node.children && Array.isArray(node.children)) {
    node.children.forEach((child) => {
      allAgents = allAgents.concat(extractAllAgentsFromTree(child));
    });
  }

  return allAgents;
};

// 查找树节点
function findTreeNodeById(node: TreeOrgNode, targetId: string): TreeOrgNode | null {
  if (node.id === targetId) {
    return node;
  }

  if (!node.children || node.children.length === 0) {
    return null;
  }

  for (const child of node.children) {
    const found = findTreeNodeById(child, targetId);
    if (found) {
      return found;
    }
  }

  return null;
}

const mapOrgAgentToAgent = (orgAgent: OrgAgent, orgId?: string): Agent => {
  const resolvedOrgId = orgId ?? (orgAgent.org_id ?? undefined);
  const normalizedOrgId =
    resolvedOrgId !== undefined && resolvedOrgId !== null
      ? String(resolvedOrgId)
      : undefined;

  // Check if orgAgent already has nested card structure (from backend)
  if ((orgAgent as any).card) {
    // Backend returns nested structure, use it directly
    return {
      ...(orgAgent as any),
      org_id: normalizedOrgId || (orgAgent as any).org_id || '',
    };
  }

  // Fallback: construct card from flat structure (for backward compatibility)
  return {
    card: {
      id: orgAgent.id,
      name: orgAgent.name,
      description: orgAgent.description || '',
      url: '',
      provider: null,
      version: '1.0.0',
      documentationUrl: null,
      capabilities: {
        streaming: false,
        pushNotifications: false,
        stateTransitionHistory: false,
      },
      authentication: null,
      defaultInputModes: [],
      defaultOutputModes: [],
    },
    supervisor_id: '',
    rank: 'member',
    org_id: normalizedOrgId || '',
    job_description: orgAgent.description || '',
    personalities: [],
  };
};

const buildDoorsForNode = (
  node: TreeOrgNode
): DisplayNode[] => {
  const doors: DisplayNode[] = [];
  const children = [...(node.children || [])];
  children.sort((a, b) => {
    if (a.sort_order !== b.sort_order) {
      return a.sort_order - b.sort_order;
    }
    return a.name.localeCompare(b.name);
  });

  children.forEach((child) => {
    const hasChildren = !!(child.children && child.children.length > 0);
    
    // 递归统计当前节点及其所有子节点的 agent 总数
    const allAgents = extractAllAgents(child);
    const totalAgentCount = allAgents.length;
    
    doors.push({
      id: child.id,
      name: child.name,
      type: hasChildren ? 'org_with_children' : 'org_with_agents',
      description: child.description || '',
      sort_order: child.sort_order,
      org: child,
      agents: child.agents,
      agentCount: totalAgentCount,  // 使用递归统计的总数
      hasChildren,
      childrenCount: child.children?.length || 0,
    });
  });


  return doors;
};

// 搜索匹配函数：检查文本是否包含搜索关键字
const matchesSearchQuery = (text: string | undefined | null, query: string): boolean => {
  if (!text || !query) return true;
  const lowerQuery = query.toLowerCase();
  return text.toLowerCase().includes(lowerQuery);
};

// 迭代搜索组织树（替代递归，减少内存占用）
const searchInOrgTree = (
  rootNode: TreeOrgNode,
  query: string,
  allAgentsMap: Map<string, OrgAgent[]>
): { matchedOrgs: TreeOrgNode[], matchedAgents: OrgAgent[] } => {
  if (!query.trim()) {
    return { matchedOrgs: [], matchedAgents: [] };
  }

  const matchedOrgs: TreeOrgNode[] = [];
  const matchedAgents: OrgAgent[] = [];
  const lowerQuery = query.toLowerCase();
  
  // 使用栈进行迭代遍历，避免递归
  const stack: TreeOrgNode[] = [rootNode];
  
  while (stack.length > 0) {
    const node = stack.pop()!;
    
    // 检查当前组织是否匹配
    const orgMatches = 
      (node.name && node.name.toLowerCase().includes(lowerQuery)) ||
      (node.description && node.description.toLowerCase().includes(lowerQuery));
    
    // 获取当前组织的 agents
    const orgAgents = allAgentsMap.get(node.id) || [];
    
    // 检查 agents 是否匹配
    const matchedAgentsInOrg = orgAgents.filter(agent => 
      (agent.name && agent.name.toLowerCase().includes(lowerQuery)) ||
      (agent.description && agent.description.toLowerCase().includes(lowerQuery))
    );
    
    // 如果组织名称匹配，或者有匹配的 agents，则包含这个组织
    if (orgMatches || matchedAgentsInOrg.length > 0) {
      matchedOrgs.push(node);
      matchedAgents.push(...matchedAgentsInOrg);
    }
    
    // 将子节点加入栈（反向添加以保持原始顺序）
    if (node.children && node.children.length > 0) {
      for (let i = node.children.length - 1; i >= 0; i--) {
        stack.push(node.children[i]);
      }
    }
  }

  return { matchedOrgs, matchedAgents };
};

const OrgNavigator: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  // ⚠️ 关键优化：提取 pathname 字符串，避免 location 对象引用变化导致重复渲染
  const pathname = location.pathname;
  
  const { t } = useTranslation();
  const username = useUserStore((state) => state.username);
  const [searchQuery, setSearchQuery] = useState('');
  
  // 滚动位置保存
  const navigatorRef = useRef<HTMLDivElement>(null);
  const savedScrollPosition = useRef<number>(0);
  
  // 使用 useEffectOnActive 在组件激活时恢复滚动位置
  useEffectOnActive(
    () => {
      const container = navigatorRef.current;
      if (container && savedScrollPosition.current > 0) {
        requestAnimationFrame(() => {
          container.scrollTop = savedScrollPosition.current;
        });
      }
      
      return () => {
        const container = navigatorRef.current;
        if (container) {
          savedScrollPosition.current = container.scrollTop;
        }
      };
    },
    []
  );
  
  // ============================================================================
  // 🔧 优化：移除 window 对象污染，使用 Store 代替
  // 搜索状态现在通过 useOrgStore 管理，不需要全局变量
  // ============================================================================
  
  // 从 URL 路径中提取 orgId，而不是使用 useParams
  // 因为 useParams 在不同缓存实例间可能保留旧值
  // ⚠️ 重要：只依赖 pathname 字符串，避免 location 对象引用变化
  const actualOrgId = useMemo(() => {
    // 使用正则表达式从 pathname 中提取 orgId
    const orgMatches = pathname.match(/organization\/([^/]+)/g);
    
    if (orgMatches && orgMatches.length > 0) {
      const lastMatch = orgMatches[orgMatches.length - 1];
      const extractedOrgId = lastMatch.replace('organization/', '');
      return extractedOrgId;
    }
    // 如果路径中没有 organization，返回 undefined（表示根节点）
    return undefined;
  }, [pathname]); // ⚠️ 只依赖 pathname 字符串，不依赖 location 对象

  const {
    loading,
    error,
    setAllOrgAgents,
    setLoading,
    setError,
    shouldFetchData,
  } = useOrgStore();

  const setAgents = useAgentStore((state) => state.setAgents);

  // 🔥 简化：直接使用扁平的 agents 列表，不再从树中提取
  const allAgentsFromStore = useOrgStore((state) => state.agents);
  const rootNode = useOrgStore((state) => state.treeOrgs[0]);
  
  // 使用 useMemo 确保 isRootView 和 actualOrgId 同步更新
  const isRootView = useMemo(() => {
    return !actualOrgId || actualOrgId === 'root';
  }, [actualOrgId]); // ⚠️ 只依赖 actualOrgId，不依赖 pathname（避免重复触发）
  
  const isUnassignedView = false;

  // 当开始搜索时，自动跳转到主页显示全局搜索结果
  useEffect(() => {
    if (searchQuery && searchQuery.trim() && !isRootView) {
      navigate('/agents');
    }
  }, [searchQuery, isRootView, navigate]);

  const currentNode = useMemo(() => {
    if (!rootNode) return null;
    if (isRootView || isUnassignedView) return rootNode;
    return findTreeNodeById(rootNode, actualOrgId!);
  }, [actualOrgId, isRootView, isUnassignedView, rootNode]);

  const levelDoors = useMemo(() => {
    if (!rootNode) {
      return [] as DisplayNode[];
    }

    if (isUnassignedView) {
      return [] as DisplayNode[];
    }

    const targetNode = isRootView ? rootNode : currentNode;

    if (!targetNode) {
      return [] as DisplayNode[];
    }

    return buildDoorsForNode(targetNode);
  }, [rootNode, currentNode, isRootView, isUnassignedView]);

  // 🔥 简化：直接从扁平列表中按 org_id 过滤，不再从树中提取
  const agentsForDisplay = useMemo(() => {
    if (!allAgentsFromStore || allAgentsFromStore.length === 0) {
      return [];
    }

    let filteredAgents: OrgAgent[];
    
    if (isRootView) {
      // 根视图：显示根组织的 agents 和未分配的 agents
      // 1. 属于根组织的 agents（org_id === rootNode.id）
      // 2. 未分配的 agents（!agent.org_id 或 org_id === null/undefined）
      const rootOrgId = rootNode?.id;
      if (rootOrgId) {
        filteredAgents = allAgentsFromStore.filter(agent => 
          agent.org_id === rootOrgId || !agent.org_id
        );
      } else {
        // 如果没有根节点，只显示未分配的 agents
        filteredAgents = allAgentsFromStore.filter(agent => !agent.org_id);
      }
    } else if (actualOrgId) {
      // 特定组织：显示该组织的 agents
      filteredAgents = allAgentsFromStore.filter(agent => agent.org_id === actualOrgId);
    } else {
      filteredAgents = [];
    }

    // 转换为前端格式
    return filteredAgents.map((agent) => mapOrgAgentToAgent(agent, actualOrgId));
  }, [allAgentsFromStore, actualOrgId, isRootView, rootNode]);


  // 搜索结果：全局搜索整个组织树
  const searchResults = useMemo(() => {
    if (!searchQuery.trim() || !rootNode) {
      return null; // 没有搜索时返回 null
    }

    // 全局搜索：始终从根节点开始搜索

    // 构建 agents 映射：orgId -> agents[]
    const agentsMap = new Map<string, OrgAgent[]>();
    allAgentsFromStore.forEach(agent => {
      const orgId = agent.org_id || 'root';
      if (!agentsMap.has(orgId)) {
        agentsMap.set(orgId, []);
      }
      agentsMap.get(orgId)!.push(agent);
    });

    // 从根节点开始搜索（全局搜索）
    const results = searchInOrgTree(rootNode, searchQuery, agentsMap);
    return results;
  }, [searchQuery, rootNode, allAgentsFromStore]);

  // 合并doors和agents到统一的items列表，用于统一渲染
  const allItems = useMemo(() => {
    
    const items: Array<{type: 'door' | 'agent', data: any, sortOrder: number}> = [];
    
    // 如果有搜索结果，显示搜索结果
    if (searchResults) {
      // 添加匹配的组织
      searchResults.matchedOrgs.forEach((org, index) => {
        const hasChildren = !!(org.children && org.children.length > 0);
        const orgAgents = searchResults.matchedAgents.filter(a => a.org_id === org.id);
        
        items.push({
          type: 'door',
          data: {
            id: org.id,
            name: org.name,
            type: hasChildren ? 'org_with_children' : 'org_with_agents',
            description: org.description || '',
            sort_order: index,
            org: org,
            agents: orgAgents,
            agentCount: orgAgents.length,
            hasChildren,
            childrenCount: org.children?.length || 0,
          },
          sortOrder: index
        });
      });
      
      // 添加匹配的 agents
      searchResults.matchedAgents
        .filter(agent => {
          const agentId = agent.id;
          const agentName = agent.name;
          return agentId !== 'system_my_twin_agent' && agentName !== 'My Twin Agent';
        })
        .forEach((agent, index) => {
          items.push({
            type: 'agent',
            data: mapOrgAgentToAgent(agent, agent.org_id),
            sortOrder: 1000000 + index
          });
        });
    } else {
      // 没有搜索时，显示当前层级的内容
      // 添加所有doors（子组织）
      levelDoors.forEach(door => {
        items.push({
          type: 'door',
          data: door,
          sortOrder: door.sort_order || 0
        });
      });
      
      // 添加所有agents，排序值设置为较大值，让agents显示在doors之后
      // 过滤掉系统后台 agent (My Twin Agent)
      agentsForDisplay
        .filter(agent => {
          const agentId = (agent as any)?.card?.id ?? (agent as any)?.id;
          const agentName = (agent as any)?.card?.name ?? (agent as any)?.name;
          return agentId !== 'system_my_twin_agent' && agentName !== 'My Twin Agent';
        })
        .forEach((agent, index) => {
          items.push({
            type: 'agent',
            data: agent,
            sortOrder: 1000000 + index
          });
        });
    }
    
    // 按sortOrder排序
    items.sort((a, b) => a.sortOrder - b.sortOrder);
    return items;
  }, [levelDoors, agentsForDisplay, searchResults]);
  // 注意：移除了 isRootView, actualOrgId, searchQuery, rootNode, allAgentsFromStore
  // 因为它们已经通过 levelDoors, agentsForDisplay, searchResults 间接包含
  // 避免不必要的重新计算


  const handleDoorClick = useCallback(
    (door: DisplayNode) => {
      // 如果在搜索模式下，清除搜索并导航
      if (searchQuery) {
        // 🔧 优化：移除 window 对象引用
        setSearchQuery('');
        
        // 构建完整路径
        if (rootNode) {
          const buildOrgPath = (targetId: string, node: TreeOrgNode, path: string[] = []): string[] | null => {
            if (node.id === targetId) {
              return [...path, node.id];
            }
            if (node.children) {
              for (const child of node.children) {
                const result = buildOrgPath(targetId, child, [...path, node.id]);
                if (result) return result;
              }
            }
            return null;
          };

          const orgPath = buildOrgPath(door.id, rootNode);
          
          if (orgPath && orgPath.length > 0) {
            // 构建完整路径：/agents/organization/id1/organization/id2/...
            let fullPath = '/agents';
            orgPath.slice(1).forEach(id => {
              fullPath += `/organization/${id}`;
            });
            navigate(fullPath);
            return;
          }
        }
      }

      // 正常模式：构建相对路径
      const currentPath = pathname.replace(/\/$/, ''); // 移除末尾斜杠
      const newPath = `${currentPath}/organization/${door.id}`;
      navigate(newPath);
    },
    [navigate, pathname, actualOrgId, searchQuery, rootNode, setSearchQuery]
  );


  const fetchOrgStructure = useCallback(async () => {
    if (!username || !shouldFetchData()) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      logger.info('[OrgNavigator] Fetching organization structure...');
      const response = await get_ipc_api().getAllOrgAgents<GetAllOrgAgentsResponse>(username);

      if (response.success && response.data) {
        setAllOrgAgents(response.data);

        // 🔧 优化：使用组件外部的函数，避免重复定义
        const allAgents = extractAllAgentsFromTree(response.data.orgs);

        if (allAgents.length > 0) {
          setAgents(
            allAgents.map((agent) =>
              mapOrgAgentToAgent(agent, agent.org_id || undefined)
            )
          );
          logger.info(`[OrgNavigator] Extracted and saved ${allAgents.length} agents to agentStore`);
        } else {
          logger.warn('[OrgNavigator] No agents found in organization structure');
        }
      } else {
        const errorMessage = response.error?.message || 'Failed to fetch organization structure';
        setError(errorMessage);
        logger.error('[OrgNavigator] Failed to fetch organization structure:', errorMessage);
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error occurred';
      setError(errorMessage);
      logger.error('[OrgNavigator] Error fetching organization structure:', errorMessage);
    } finally {
      setLoading(false);
    }
  }, [username, shouldFetchData, setLoading, setError, setAllOrgAgents, setAgents]);

  useEffect(() => {
    fetchOrgStructure();
  }, [fetchOrgStructure]);

  // ============================================================================
  // 🔧 优化：移除重复代码，复用 fetchOrgStructure
  // 监听URL参数变化，当有refresh参数时重新获取数据
  // ============================================================================
  useEffect(() => {
    const searchParams = new URLSearchParams(location.search);
    const refreshParam = searchParams.get('refresh');
    if (refreshParam && username) {
      logger.info('[OrgNavigator] Refresh parameter detected, forcing data refresh...');
      // 复用 fetchOrgStructure，无需重复代码
      fetchOrgStructure();
    }
  }, [location.search, username, fetchOrgStructure]);

  if (loading && !rootNode) {
    return (
      <div className="org-navigator">
        <div className="navigator-loading">
          <Spin size="large" />
          <div className="loading-text">{t('common.loading') || 'Loading...'}</div>
        </div>
      </div>
    );
  }

  if (error && !rootNode) {
    return (
      <div className="org-navigator">
        <div className="navigator-loading">
          <Alert
            message={t('pages.agents.load_failed') || 'Failed to load organizations'}
            description={error}
            type="error"
            showIcon
            action={
              <Button type="primary" onClick={fetchOrgStructure}>
                {t('common.retry') || 'Retry'}
              </Button>
            }
          />
        </div>
      </div>
    );
  }

  if (!rootNode) {
    return null;
  }

  return (
    <div ref={navigatorRef} className="org-navigator">
      {/* 🔧 优化：简化 SVG 背景，减少 DOM 节点 */}
      <svg className="navigator-bg-svg" width="100%" height="100%" viewBox="0 0 1200 800" style={{position:'absolute',left:0,top:0,zIndex:0}}>
        <ellipse cx="600" cy="700" rx="420" ry="80" fill="var(--ant-primary-1, #e6f4ff)" opacity="0.4" />
        <ellipse cx="600" cy="700" rx="200" ry="40" fill="none" stroke="var(--ant-primary-2, #91caff)" strokeWidth="1" opacity="0.15" />
        <ellipse cx="600" cy="700" rx="260" ry="52" fill="none" stroke="var(--ant-primary-2, #91caff)" strokeWidth="1" opacity="0.15" />
      </svg>
      {/* 保留光斑效果 */}
      <div className="navigator-bg-blur navigator-bg-blur1" />
      <div className="navigator-bg-blur navigator-bg-blur2" />

      {/* 统一网格布局 - 同时显示doors和agents */}
      {allItems.length > 0 && (
        <div className="unified-grid" data-item-count={allItems.length}>
          {allItems.map((item) => {
            if (item.type === 'door') {
              const door = item.data;
              let displayName = door.name;

              if (displayName.startsWith('pages.')) {
                displayName = t(displayName) || displayName;
              }

              // 显示该组织及其所有子组织的 agent 总数
              if (door.type === 'org_with_children' && typeof door.agentCount === 'number') {
                displayName = `${displayName} (${door.agentCount})`;
              } else if (door.type === 'org_with_agents' && typeof door.agentCount === 'number') {
                displayName = `${displayName} (${door.agentCount})`;
              }

              // 移除未分配agents门的显示逻辑

              return (
                <div key={`door-${door.id}`} onClick={() => handleDoorClick(door)}>
                  <OrgDoor 
                    name={displayName} 
                    hasChildren={door.hasChildren}
                    isActive={actualOrgId === door.id}
                    agentCount={door.agentCount || 0}
                  />
                </div>
              );
            } else {
              // agent item
              const agent = item.data;
              const cardId = (agent as any)?.card?.id ?? (agent as any)?.id ?? agent.card.name;
              return (
                <div key={`agent-${cardId}`} className="agent-card-wrapper">
                  <AgentCard
                    agent={agent}
                    onChat={() => navigate(`/chat?agentId=${cardId}`)}
                  />
                </div>
              );
            }
          })}
        </div>
      )}

      {allItems.length === 0 && !isUnassignedView && (
        <div className="empty-state">
          <InboxOutlined style={{ fontSize: 64, color: 'rgba(59, 130, 246, 0.3)', marginBottom: 16 }} />
          <div style={{ fontSize: 18, color: 'rgba(255, 255, 255, 0.7)', marginBottom: 8 }}>
            {searchQuery ? (
              <>
                {t('pages.agents.no_search_results') || 'No results found for'} "{searchQuery}"
              </>
            ) : (
              t('pages.agents.no_items') || 'No organizations or agents available'
            )}
          </div>
          {searchQuery && (
            <div style={{ fontSize: 14, color: 'rgba(255, 255, 255, 0.5)' }}>
              {t('pages.agents.try_different_search') || 'Try a different search term or clear the search'}
            </div>
          )}
        </div>
      )}

      {/* 添加 Agent 浮动按钮 */}
      <FloatButton
        icon={<PlusOutlined />}
        type="primary"
        style={{ right: 24, bottom: 24 }}
        tooltip={t('pages.agents.add_agent') || 'Add Agent'}
        onClick={() => {
          // 传递当前组织ID作为查询参数
          // 如果在根视图，使用根组织的ID；否则使用当前组织ID
          const targetOrgId = isRootView && rootNode ? rootNode.id : actualOrgId;

          const queryParams = new URLSearchParams();
          if (targetOrgId && targetOrgId !== 'root') {
            queryParams.set('orgId', targetOrgId);
          }
          const queryString = queryParams.toString();
          const targetUrl = `/agents/add${queryString ? `?${queryString}` : ''}`;
          navigate(targetUrl);
        }}
      />
    </div>
  );
};

export default React.memo(OrgNavigator);
