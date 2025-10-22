import React, { useMemo, useCallback, useEffect, useState } from 'react';
import { Alert, Button, Spin, FloatButton } from 'antd';
import { PlusOutlined, InboxOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
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
  return text.toLowerCase().includes(query.toLowerCase());
};

// 递归搜索组织树，返回匹配的组织和其中的 agents
const searchInOrgTree = (
  node: TreeOrgNode,
  query: string,
  allAgentsMap: Map<string, OrgAgent[]>
): { matchedOrgs: TreeOrgNode[], matchedAgents: OrgAgent[] } => {
  if (!query.trim()) {
    return { matchedOrgs: [], matchedAgents: [] };
  }

  const results: { matchedOrgs: TreeOrgNode[], matchedAgents: OrgAgent[] } = {
    matchedOrgs: [],
    matchedAgents: []
  };

  // 检查当前组织是否匹配
  const orgMatches = matchesSearchQuery(node.name, query) || 
                     matchesSearchQuery(node.description, query);

  // 获取当前组织的 agents
  const orgAgents = allAgentsMap.get(node.id) || [];
  
  // 检查 agents 是否匹配
  const matchedAgentsInOrg = orgAgents.filter(agent => 
    matchesSearchQuery(agent.name, query) || 
    matchesSearchQuery(agent.description, query)
  );

  // 如果组织名称匹配，或者有匹配的 agents，则包含这个组织
  if (orgMatches || matchedAgentsInOrg.length > 0) {
    results.matchedOrgs.push(node);
    results.matchedAgents.push(...matchedAgentsInOrg);
  }

  // 递归搜索子组织
  if (node.children && node.children.length > 0) {
    node.children.forEach(child => {
      const childResults = searchInOrgTree(child, query, allAgentsMap);
      results.matchedOrgs.push(...childResults.matchedOrgs);
      results.matchedAgents.push(...childResults.matchedAgents);
    });
  }

  return results;
};

const OrgNavigator: React.FC = () => {
  const navigate = useNavigate();
  const { orgId } = useParams<{ orgId?: string }>();
  const location = useLocation();
  const { t } = useTranslation();
  const username = useUserStore((state) => state.username);
  const [searchQuery, setSearchQuery] = useState('');
  
  // 将搜索状态暴露给父组件（通过 window 对象）
  useEffect(() => {
    (window as any).__agentsSearchQuery = searchQuery;
    (window as any).__setAgentsSearchQuery = setSearchQuery;
    return () => {
      delete (window as any).__agentsSearchQuery;
      delete (window as any).__setAgentsSearchQuery;
    };
  }, [searchQuery]);

  // 解析嵌套路径中的实际 orgId
  const actualOrgId = useMemo(() => {
    // 从完整路径中提取最后一个 organization 后面的 orgId
    const orgMatches = location.pathname.match(/organization\/([^/]+)/g);
    console.log('[OrgNavigator] Current path:', location.pathname);
    console.log('[OrgNavigator] Org matches:', orgMatches);
    console.log('[OrgNavigator] useParams orgId:', orgId);
    
    if (orgMatches && orgMatches.length > 0) {
      const lastMatch = orgMatches[orgMatches.length - 1];
      const extractedOrgId = lastMatch.replace('organization/', '');
      console.log('[OrgNavigator] Extracted orgId:', extractedOrgId);
      return extractedOrgId;
    }
    return orgId;
  }, [location.pathname, orgId]);

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
  const isRootView = !actualOrgId || actualOrgId === 'root';
  const isUnassignedView = false;

  // 当开始搜索时，自动跳转到主页显示全局搜索结果
  useEffect(() => {
    if (searchQuery && searchQuery.trim() && !isRootView) {
      console.log('[OrgNavigator] Search query detected, navigating to root for global search');
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
      // 根视图：显示没有 org_id 的 agents（未分配）
      filteredAgents = allAgentsFromStore.filter(agent => !agent.org_id);
    } else if (actualOrgId) {
      // 特定组织：显示该组织的 agents
      filteredAgents = allAgentsFromStore.filter(agent => agent.org_id === actualOrgId);
    } else {
      filteredAgents = [];
    }

    // 转换为前端格式
    return filteredAgents.map((agent) => mapOrgAgentToAgent(agent, actualOrgId));
  }, [allAgentsFromStore, actualOrgId, isRootView]);


  // 搜索结果：全局搜索整个组织树
  const searchResults = useMemo(() => {
    if (!searchQuery.trim() || !rootNode) {
      return null; // 没有搜索时返回 null
    }

    console.log('[OrgNavigator] Performing GLOBAL search for:', searchQuery);
    console.log('[OrgNavigator] Current location:', location.pathname);
    console.log('[OrgNavigator] isRootView:', isRootView);

    // 全局搜索：始终从根节点开始搜索
    console.log('[OrgNavigator] Searching from ROOT node:', rootNode.name, rootNode.id);

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
    
    console.log('[OrgNavigator] GLOBAL search results:', {
      matchedOrgs: results.matchedOrgs.length,
      matchedAgents: results.matchedAgents.length,
      orgNames: results.matchedOrgs.map(o => o.name)
    });
    
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
    
    // 调试日志
    console.log('[OrgNavigator] allItems:', {
      totalItems: items.length,
      doors: items.filter(i => i.type === 'door').length,
      agents: items.filter(i => i.type === 'agent').length,
      agentsForDisplayCount: agentsForDisplay.length,
      isRootView,
      actualOrgId,
      searchQuery,
      hasSearchResults: !!searchResults
    });
    
    return items;
  }, [levelDoors, agentsForDisplay, isRootView, actualOrgId, searchQuery, searchResults, rootNode, allAgentsFromStore]);


  const handleDoorClick = useCallback(
    (door: DisplayNode) => {
      console.log('[OrgNavigator] handleDoorClick called with door:', door);
      console.log('[OrgNavigator] searchQuery:', searchQuery);
      console.log('[OrgNavigator] rootNode:', rootNode?.id);
      
      // 如果在搜索模式下，清除搜索并导航
      if (searchQuery) {
        console.log('[OrgNavigator] In search mode, clearing search and navigating...');
        
        // 先清除搜索
        setSearchQuery('');
        if ((window as any).__setAgentsSearchQuery) {
          (window as any).__setAgentsSearchQuery('');
        }
        
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
          console.log('[OrgNavigator] Found org path:', orgPath);
          
          if (orgPath && orgPath.length > 0) {
            // 构建完整路径：/agents/organization/id1/organization/id2/...
            let fullPath = '/agents';
            orgPath.slice(1).forEach(id => {
              fullPath += `/organization/${id}`;
            });
            console.log('[OrgNavigator] Search mode - Navigating to:', fullPath);
            navigate(fullPath);
            return;
          }
        }
      }

      // 正常模式：构建相对路径
      const currentPath = location.pathname.replace(/\/$/, ''); // 移除末尾斜杠
      const newPath = `${currentPath}/organization/${door.id}`;
      
      console.log('[OrgNavigator] Normal mode - Navigating from:', currentPath, 'to:', newPath);
      console.log('[OrgNavigator] Current actualOrgId:', actualOrgId, 'Target door.id:', door.id);
      
      navigate(newPath);
    },
    [navigate, location.pathname, actualOrgId, searchQuery, rootNode, setSearchQuery]
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

        const extractAllAgents = (node: TreeOrgNode): OrgAgent[] => {
          let allAgents: OrgAgent[] = [];

          if (node.agents && Array.isArray(node.agents)) {
            allAgents = allAgents.concat(node.agents);
          }

          if (node.children && Array.isArray(node.children)) {
            node.children.forEach((child) => {
              allAgents = allAgents.concat(extractAllAgents(child));
            });
          }

          return allAgents;
        };

        const allAgents = extractAllAgents(response.data.orgs);

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

  // 监听URL参数变化，当有refresh参数时重新获取数据
  useEffect(() => {
    const searchParams = new URLSearchParams(location.search);
    const refreshParam = searchParams.get('refresh');
    if (refreshParam && username) {
      console.log('[OrgNavigator] Refresh parameter detected, force reloading data');
      
      // 强制刷新数据，不检查shouldFetchData
      const forceRefresh = async () => {
        setLoading(true);
        setError(null);

        try {
          logger.info('[OrgNavigator] Force fetching organization structure...');
          const response = await get_ipc_api().getAllOrgAgents<GetAllOrgAgentsResponse>(username);

          if (response.success && response.data) {
            setAllOrgAgents(response.data);

            const extractAllAgents = (node: TreeOrgNode): OrgAgent[] => {
              let allAgents: OrgAgent[] = [];

              if (node.agents && Array.isArray(node.agents)) {
                allAgents = allAgents.concat(node.agents);
              }

              if (node.children && Array.isArray(node.children)) {
                node.children.forEach((child) => {
                  allAgents = allAgents.concat(extractAllAgents(child));
                });
              }

              return allAgents;
            };

            const allAgents = extractAllAgents(response.data.orgs);

            if (allAgents.length > 0) {
              setAgents(
                allAgents.map((agent) =>
                  mapOrgAgentToAgent(agent, agent.org_id || undefined)
                )
              );
              logger.info(`[OrgNavigator] Force refresh: Extracted and saved ${allAgents.length} agents to agentStore`);
            } else {
              logger.warn('[OrgNavigator] Force refresh: No agents found in organization structure');
            }
          } else {
            const errorMessage = response.error?.message || 'Failed to fetch organization structure';
            setError(errorMessage);
            logger.error('[OrgNavigator] Force refresh failed:', errorMessage);
          }
        } catch (err) {
          const errorMessage = err instanceof Error ? err.message : 'Unknown error occurred';
          setError(errorMessage);
          logger.error('[OrgNavigator] Force refresh error:', errorMessage);
        } finally {
          setLoading(false);
        }
      };
      
      forceRefresh();
    }
  }, [location.search, username, setLoading, setError, setAllOrgAgents, setAgents]);

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
    <div className="org-navigator">
      {/* 简化的科技感背景 */}
      <svg className="navigator-bg-svg" width="100%" height="100%" viewBox="0 0 1200 800" style={{position:'absolute',left:0,top:0,zIndex:0}}>
        {/* 简化的地板网格 - 只保留3层 */}
        <ellipse cx="600" cy="700" rx="420" ry="80" fill="var(--ant-primary-1, #e6f4ff)" opacity="0.4" />
        {Array.from({length: 3}).map((_,i) => (
          <ellipse key={i} cx="600" cy="700" rx={200+i*60} ry={40+i*12} fill="none" stroke="var(--ant-primary-2, #91caff)" strokeWidth="1" opacity="0.15" />
        ))}
        {/* 保留几个关键节点 */}
        {[{cx:300,cy:250},{cx:900,cy:250},{cx:600,cy:450}].map((n,i)=>(
          <circle key={i} cx={n.cx} cy={n.cy} r="12" fill="var(--ant-primary-color, #1677ff)" opacity="0.12" />
        ))}
      </svg>
      {/* 保留光斑效果 */}
      <div className="navigator-bg-blur navigator-bg-blur1" />
      <div className="navigator-bg-blur navigator-bg-blur2" />
      {/* 保留一个静态灯光 */}
      <div className="navigator-space-lights">
        <div className="navigator-space-light navigator-space-light1" />
      </div>

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
          console.log('[OrgNavigator] Add button clicked');
          console.log('[OrgNavigator] - isRootView:', isRootView);
          console.log('[OrgNavigator] - actualOrgId:', actualOrgId);
          console.log('[OrgNavigator] - rootNode.id:', rootNode?.id);
          console.log('[OrgNavigator] - targetOrgId:', targetOrgId);

          const queryParams = new URLSearchParams();
          if (targetOrgId && targetOrgId !== 'root') {
            console.log('[OrgNavigator] Setting orgId query param:', targetOrgId);
            queryParams.set('orgId', targetOrgId);
          } else {
            console.log('[OrgNavigator] Not setting orgId - targetOrgId:', targetOrgId);
          }
          const queryString = queryParams.toString();
          const targetUrl = `/agents/add${queryString ? `?${queryString}` : ''}`;
          console.log('[OrgNavigator] Navigating to:', targetUrl);
          navigate(targetUrl);
        }}
      />
    </div>
  );
};

export default React.memo(OrgNavigator);
