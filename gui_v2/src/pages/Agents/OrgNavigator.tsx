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

// 提取All agents（Recursive）
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
    
    // Recursive统计When前节点及其All子节点的 agent 总数
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
      agentCount: totalAgentCount,  // 使用Recursive统计的总数
      hasChildren,
      childrenCount: child.children?.length || 0,
    });
  });


  return doors;
};

// IterateSearch组织树（替代Recursive，减少内存占用）
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
  
  // 使用栈进行IterateTraverse，避免Recursive
  const stack: TreeOrgNode[] = [rootNode];
  
  while (stack.length > 0) {
    const node = stack.pop()!;
    
    // CheckWhen前组织是否匹配
    const orgMatches = 
      (node.name && node.name.toLowerCase().includes(lowerQuery)) ||
      (node.description && node.description.toLowerCase().includes(lowerQuery));
    
    // GetWhen前组织的 agents
    const orgAgents = allAgentsMap.get(node.id) || [];
    
    // Check agents 是否匹配
    const matchedAgentsInOrg = orgAgents.filter(agent => 
      (agent.name && agent.name.toLowerCase().includes(lowerQuery)) ||
      (agent.description && agent.description.toLowerCase().includes(lowerQuery))
    );
    
    // If组织Name匹配，or有匹配的 agents，则Include这个组织
    if (orgMatches || matchedAgentsInOrg.length > 0) {
      matchedOrgs.push(node);
      matchedAgents.push(...matchedAgentsInOrg);
    }
    
    // 将子节点加入栈（反向Add以保持原始顺序）
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
  // ⚠️ 关键Optimize：提取 pathname 字符串，避免 location 对象Reference变化导致重复Render
  const pathname = location.pathname;
  
  const { t } = useTranslation();
  const username = useUserStore((state) => state.username);
  const [searchQuery, setSearchQuery] = useState('');
  
  // ScrollPositionSave
  const navigatorRef = useRef<HTMLDivElement>(null);
  const savedScrollPosition = useRef<number>(0);
  
  // 使用 useEffectOnActive 在ComponentActive时RestoreScrollPosition
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
  // 🔧 Optimize：Remove window 对象污染，使用 Store 代替
  // SearchStatus现在通过 useOrgStore 管理，不Need全局变量
  // ============================================================================
  
  // 从 URL Path中提取 orgId，而not使用 useParams
  // 因为 useParams 在不同Cache实例间可能保留旧Value
  // ⚠️ 重要：只Dependency pathname 字符串，避免 location 对象Reference变化
  const actualOrgId = useMemo(() => {
    // 使用正则表达式从 pathname 中提取 orgId
    const orgMatches = pathname.match(/organization\/([^/]+)/g);
    
    if (orgMatches && orgMatches.length > 0) {
      const lastMatch = orgMatches[orgMatches.length - 1];
      const extractedOrgId = lastMatch.replace('organization/', '');
      return extractedOrgId;
    }
    // IfPath中没有 organization，返回 undefined（表示根节点）
    return undefined;
  }, [pathname]); // ⚠️ 只Dependency pathname 字符串，不Dependency location 对象

  const {
    loading,
    error,
    setAllOrgAgents,
    setLoading,
    setError,
    shouldFetchData,
  } = useOrgStore();

  const setAgents = useAgentStore((state) => state.setAgents);

  // 🔥 简化：直接使用扁平的 agents List，不再从树中提取
  const allAgentsFromStore = useOrgStore((state) => state.agents);
  const rootNode = useOrgStore((state) => state.treeOrgs[0]);
  
  // 使用 useMemo 确保 isRootView 和 actualOrgId SyncUpdate
  const isRootView = useMemo(() => {
    // 根视图的判断条件：
    // 1. 没有 orgId（URL 是 /agents）
    // 2. orgId 是 'root'
    // 3. orgId 等于根组织的 ID（避免根组织被当作子组织处理）
    const rootOrgId = rootNode?.id;
    return !actualOrgId || actualOrgId === 'root' || (rootOrgId && actualOrgId === rootOrgId);
  }, [actualOrgId, rootNode]); // 添加 rootNode 依赖以获取根组织 ID
  
  const isUnassignedView = false;

  // When开始Search时，自动跳转到主页Display全局SearchResult
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

  // 🔥 简化：直接从扁平List中按 org_id Filter，不再从树中提取
  const agentsForDisplay = useMemo(() => {
    if (!allAgentsFromStore || allAgentsFromStore.length === 0) {
      return [];
    }

    let filteredAgents: OrgAgent[];
    
    if (isRootView) {
      // 根视图：Display根组织的 agents 和未分配的 agents
      // 1. 属于根组织的 agents（org_id === rootNode.id）
      // 2. 未分配的 agents（!agent.org_id 或 org_id === null/undefined）
      const rootOrgId = rootNode?.id;
      if (rootOrgId) {
        filteredAgents = allAgentsFromStore.filter(agent => 
          agent.org_id === rootOrgId || !agent.org_id
        );
      } else {
        // If没有根节点，只Display未分配的 agents
        filteredAgents = allAgentsFromStore.filter(agent => !agent.org_id);
      }
    } else if (actualOrgId) {
      // 特定组织：Display该组织的 agents
      filteredAgents = allAgentsFromStore.filter(agent => agent.org_id === actualOrgId);
    } else {
      filteredAgents = [];
    }

    // Convert为Frontend格式
    return filteredAgents.map((agent) => mapOrgAgentToAgent(agent, actualOrgId));
  }, [allAgentsFromStore, actualOrgId, isRootView, rootNode]);


  // SearchResult：全局Search整个组织树
  const searchResults = useMemo(() => {
    if (!searchQuery.trim() || !rootNode) {
      return null; // 没有Search时返回 null
    }

    // 全局Search：始终从根节点开始Search

    // 构建 agents Map：orgId -> agents[]
    const agentsMap = new Map<string, OrgAgent[]>();
    allAgentsFromStore.forEach(agent => {
      const orgId = agent.org_id || 'root';
      if (!agentsMap.has(orgId)) {
        agentsMap.set(orgId, []);
      }
      agentsMap.get(orgId)!.push(agent);
    });

    // 从根节点开始Search（全局Search）
    const results = searchInOrgTree(rootNode, searchQuery, agentsMap);
    return results;
  }, [searchQuery, rootNode, allAgentsFromStore]);

  // 合并doors和agents到统一的itemsList，Used for统一Render
  const allItems = useMemo(() => {
    
    const items: Array<{type: 'door' | 'agent', data: any, sortOrder: number}> = [];
    
    // If有SearchResult，DisplaySearchResult
    if (searchResults) {
      // Add匹配的组织
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
      
      // Add匹配的 agents
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
      // 没有Search时，DisplayWhen前层级的Content
      // AddAlldoors（子组织）
      levelDoors.forEach(door => {
        items.push({
          type: 'door',
          data: door,
          sortOrder: door.sort_order || 0
        });
      });
      
      // AddAllagents，SortValueSettings为较大Value，让agentsDisplay在doors之后
      // Filter掉System后台 agent (My Twin Agent)
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
    
    // 按sortOrderSort
    items.sort((a, b) => a.sortOrder - b.sortOrder);
    return items;
  }, [levelDoors, agentsForDisplay, searchResults]);
  // Note：Remove了 isRootView, actualOrgId, searchQuery, rootNode, allAgentsFromStore
  // 因为它们已经通过 levelDoors, agentsForDisplay, searchResults 间接Include
  // 避免不必要的重新计算


  const handleDoorClick = useCallback(
    (door: DisplayNode) => {
      // If在Search模式下，清除Search并Navigation
      if (searchQuery) {
        // 🔧 Optimize：Remove window 对象Reference
        setSearchQuery('');
        
        // 构建完整Path
        if (rootNode) {
          const buildOrgPath = (targetId: string, node: TreeOrgNode, path: string[] = []): string[] | null => {
            // 先将当前节点加入路径
            const currentPath = [...path, node.id];
            
            // 如果当前节点就是目标，返回路径（包含目标节点）
            if (node.id === targetId) {
              return currentPath;
            }
            
            // 否则在子节点中继续查找
            if (node.children) {
              for (const child of node.children) {
                const result = buildOrgPath(targetId, child, currentPath);
                if (result) return result;
              }
            }
            return null;
          };

          const orgPath = buildOrgPath(door.id, rootNode);
          
          if (orgPath && orgPath.length > 0) {
            // 构建完整Path：/agents/organization/id1/organization/id2/...
            let fullPath = '/agents';
            // 跳过根节点（第一个元素），添加路径上的所有组织（包括目标组织）
            orgPath.slice(1).forEach(id => {
              fullPath += `/organization/${id}`;
            });
            navigate(fullPath);
            return;
          }
        }
      }

      // 正常模式：构建相对Path
      const currentPath = pathname.replace(/\/$/, ''); // Remove末尾斜杠
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

        // 🔧 Optimize：使用ComponentExternal的Function，避免重复Definition
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
  // 🔧 Optimize：Remove重复Code，复用 fetchOrgStructure
  // ListenURLParameter变化，When有refreshParameter时重新GetData
  // ============================================================================
  useEffect(() => {
    const searchParams = new URLSearchParams(location.search);
    const refreshParam = searchParams.get('refresh');
    if (refreshParam && username) {
      logger.info('[OrgNavigator] Refresh parameter detected, forcing data refresh...');
      // 复用 fetchOrgStructure，无需重复Code
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
      {/* 🔧 Optimize：简化 SVG 背景，减少 DOM 节点 */}
      <svg className="navigator-bg-svg" width="100%" height="100%" viewBox="0 0 1200 800" style={{position:'absolute',left:0,top:0,zIndex:0}}>
        <ellipse cx="600" cy="700" rx="420" ry="80" fill="var(--ant-primary-1, #e6f4ff)" opacity="0.4" />
        <ellipse cx="600" cy="700" rx="200" ry="40" fill="none" stroke="var(--ant-primary-2, #91caff)" strokeWidth="1" opacity="0.15" />
        <ellipse cx="600" cy="700" rx="260" ry="52" fill="none" stroke="var(--ant-primary-2, #91caff)" strokeWidth="1" opacity="0.15" />
      </svg>
      {/* 保留光斑效果 */}
      <div className="navigator-bg-blur navigator-bg-blur1" />
      <div className="navigator-bg-blur navigator-bg-blur2" />

      {/* 统一网格Layout - 同时Displaydoors和agents */}
      {allItems.length > 0 && (
        <div className="unified-grid" data-item-count={allItems.length}>
          {allItems.map((item) => {
            if (item.type === 'door') {
              const door = item.data;
              let displayName = door.name;

              if (displayName.startsWith('pages.')) {
                displayName = t(displayName) || displayName;
              }

              // Display该组织及其All子组织的 agent 总数
              if (door.type === 'org_with_children' && typeof door.agentCount === 'number') {
                displayName = `${displayName} (${door.agentCount})`;
              } else if (door.type === 'org_with_agents' && typeof door.agentCount === 'number') {
                displayName = `${displayName} (${door.agentCount})`;
              }

              // Remove未分配agents门的Display逻辑

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

      {/* Add Agent 浮动Button */}
      <FloatButton
        icon={<PlusOutlined />}
        type="primary"
        style={{ right: 24, bottom: 24 }}
        tooltip={t('pages.agents.add_agent') || 'Add Agent'}
        onClick={() => {
          // 传递When前组织ID作为QueryParameter
          // If在根视图，使用根组织的ID；否则使用When前组织ID
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
