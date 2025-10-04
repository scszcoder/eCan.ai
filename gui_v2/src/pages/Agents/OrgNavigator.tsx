import React, { useMemo, useCallback, useEffect } from 'react';
import { Alert, Button, Spin, FloatButton } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
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

const UNASSIGNED_NODE_ID = 'unassigned';

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
    supervisors: [],
    subordinates: [],
    peers: [],
    rank: 'member',
    organizations: normalizedOrgId ? [normalizedOrgId] : [],
    job_description: orgAgent.description || '',
    personalities: [],
  };
};

const buildDoorsForNode = (
  node: TreeOrgNode,
  includeUnassignedDoor: boolean
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

    doors.push({
      id: child.id,
      name: child.name,
      type: hasChildren ? 'org_with_children' : 'org_with_agents',
      description: child.description || '',
      sort_order: child.sort_order,
      org: child,
      agents: child.agents,
      agentCount: child.agents?.length || 0,
      hasChildren,
      childrenCount: child.children?.length || 0,
    });
  });

  if (includeUnassignedDoor && node.agents && node.agents.length > 0) {
    doors.push({
      id: UNASSIGNED_NODE_ID,
      name: 'pages.agents.unassigned_agents',
      type: 'unassigned_agents',
      description: 'pages.agents.unassigned_agents_desc',
      sort_order: Number.MAX_SAFE_INTEGER,
      agents: node.agents,
      agentCount: node.agents.length,
    });
  }

  return doors;
};

const OrgNavigator: React.FC = () => {
  const navigate = useNavigate();
  const { orgId } = useParams<{ orgId?: string }>();
  const location = useLocation();
  const { t } = useTranslation();
  const username = useUserStore((state) => state.username);

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
    treeOrgs,
    loading,
    error,
    setAllOrgAgents,
    setLoading,
    setError,
    shouldFetchData,
  } = useOrgStore();

  const setAgents = useAgentStore((state) => state.setAgents);

  // 使用 useMemo 确保 rootNode 响应 treeOrgs 的变化
  const rootNode = useMemo(() => treeOrgs[0], [treeOrgs]);
  const isRootView = !actualOrgId || actualOrgId === 'root';
  const isUnassignedView = actualOrgId === UNASSIGNED_NODE_ID;

  const currentNode = useMemo(() => {
    if (!rootNode) {
      return null;
    }

    if (isRootView || isUnassignedView) {
      return rootNode;
    }

    return findTreeNodeById(rootNode, actualOrgId!);
  }, [actualOrgId, isRootView, isUnassignedView, rootNode, treeOrgs]);

  const levelDoors = useMemo(() => {
    if (!rootNode) {
      return [] as DisplayNode[];
    }

    if (isUnassignedView) {
      return [] as DisplayNode[];
    }

    const includeUnassignedDoor = isRootView;
    const targetNode = isRootView ? rootNode : currentNode;

    if (!targetNode) {
      return [] as DisplayNode[];
    }

    return buildDoorsForNode(targetNode, includeUnassignedDoor);
  }, [rootNode, currentNode, isRootView, isUnassignedView, treeOrgs]);

  const rawAgents = useMemo(() => {
    if (!rootNode) {
      return [] as OrgAgent[];
    }

    if (isUnassignedView) {
      return rootNode.agents || [];
    }

    if (!actualOrgId || !currentNode) {
      return [] as OrgAgent[];
    }

    return currentNode.agents || [];
  }, [rootNode, currentNode, isUnassignedView, actualOrgId, treeOrgs]);

  const agentsForDisplay = useMemo(() => {
    const currentOrgId = isUnassignedView ? undefined : actualOrgId;
    return rawAgents.map((agent) => mapOrgAgentToAgent(agent, currentOrgId));
  }, [rawAgents, actualOrgId, isUnassignedView]);


  const handleDoorClick = useCallback(
    (door: DisplayNode) => {
      if (door.type === 'unassigned_agents') {
        const currentPath = location.pathname;
        navigate(`${currentPath}/organization/unassigned`);
        return;
      }

      // 构建正确的嵌套路径：当前路径 + /organization/:orgId
      // 这样 PageBackBreadcrumb 组件就能正确解析路径层级
      const currentPath = location.pathname.replace(/\/$/, ''); // 移除末尾斜杠
      const newPath = `${currentPath}/organization/${door.id}`;
      
      console.log('[OrgNavigator] Navigating from:', currentPath, 'to:', newPath);
      console.log('[OrgNavigator] Current actualOrgId:', actualOrgId, 'Target door.id:', door.id);
      
      navigate(newPath);
    },
    [navigate, location.pathname, actualOrgId]
  );

  const doorComponents = useMemo(() => {
    return levelDoors.map((door) => {
      let displayName = door.name;

      if (displayName.startsWith('pages.')) {
        displayName = t(displayName) || displayName;
      }

      if (door.type === 'org_with_agents' && typeof door.agentCount === 'number') {
        displayName = `${displayName} (${door.agentCount})`;
      }

      if (door.type === 'org_with_children' && typeof door.childrenCount === 'number') {
        displayName = `${displayName} (${door.childrenCount})`;
      }

      if (door.type === 'unassigned_agents') {
        displayName = `${displayName} (${door.agentCount || 0})`;
      }

      return (
        <div key={`${door.id}`} onClick={() => handleDoorClick(door)}>
          <OrgDoor name={displayName} />
        </div>
      );
    });
  }, [levelDoors, t, handleDoorClick]);

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

      {/* 门规则网格分布 */}
      {doorComponents.length > 0 && (
        <div className="doors-grid" data-door-count={doorComponents.length}>
          {doorComponents}
        </div>
      )}

      {doorComponents.length === 0 && !isUnassignedView && (
        <div className="doors-empty-state">
          {t('pages.agents.no_sub_orgs') || 'No sub organizations available.'}
        </div>
      )}

      {agentsForDisplay.length > 0 && (
        <div className="agent-roster">
          <div className="agent-roster-grid">
            {agentsForDisplay.map((agent) => {
              const cardId = (agent as any)?.card?.id ?? (agent as any)?.id ?? agent.card.name;
              return (
                <AgentCard
                  key={cardId}
                  agent={agent}
                  onChat={() => navigate(`/chat?agentId=${cardId}`)}
                />
              );
            })}
          </div>
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
          console.log('[OrgNavigator] Add button clicked, actualOrgId:', actualOrgId);
          const queryParams = new URLSearchParams();
          if (actualOrgId && actualOrgId !== 'root' && actualOrgId !== UNASSIGNED_NODE_ID) {
            console.log('[OrgNavigator] Setting orgId query param:', actualOrgId);
            queryParams.set('orgId', actualOrgId);
          } else {
            console.log('[OrgNavigator] Not setting orgId - actualOrgId:', actualOrgId, 'UNASSIGNED:', UNASSIGNED_NODE_ID);
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
