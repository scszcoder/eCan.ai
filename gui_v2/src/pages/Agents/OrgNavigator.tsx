import React, { useMemo, useCallback, useEffect } from 'react';
import { Alert, Button, Spin } from 'antd';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useUserStore } from '../../stores/userStore';
import { useOrgStore } from '../../stores/orgStore';
import { useAgentStore } from '../../stores/agentStore';
import OrgDoor from './components/OrgDoor';
import AgentAvatar from './components/AgentAvatar';
import './OrgNavigator.css';
import { logger } from '../../utils/logger';
import { get_ipc_api } from '@/services/ipc_api';
import { DisplayNode, GetAllOrgAgentsResponse, OrgAgent, TreeOrgNode } from '../Orgs/types';
import type { Agent } from './types';
import { useOrgAgentsUpdate } from './hooks/useOrgAgentsUpdate';

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

// 查找到节点的路径
function findPathToNode(node: TreeOrgNode, targetId: string, stack: TreeOrgNode[] = []): TreeOrgNode[] | null {
  const nextStack = [...stack, node];
  if (node.id === targetId) {
    return nextStack;
  }

  if (!node.children || node.children.length === 0) {
    return null;
  }

  for (const child of node.children) {
    const found = findPathToNode(child, targetId, nextStack);
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
  const { departmentId } = useParams<{ departmentId?: string }>();
  const { t } = useTranslation();
  const username = useUserStore((state) => state.username);

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

  const rootNode = treeOrgs[0];
  const isRootView = !departmentId;
  const isUnassignedView = departmentId === UNASSIGNED_NODE_ID;

  const currentNode = useMemo(() => {
    if (!rootNode) {
      return null;
    }

    if (isRootView || isUnassignedView) {
      return rootNode;
    }

    return findTreeNodeById(rootNode, departmentId!);
  }, [departmentId, isRootView, isUnassignedView, rootNode]);

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
  }, [rootNode, currentNode, isRootView, isUnassignedView]);

  const rawAgents = useMemo(() => {
    if (!rootNode) {
      return [] as OrgAgent[];
    }

    if (isUnassignedView) {
      return rootNode.agents || [];
    }

    if (!departmentId || !currentNode) {
      return [] as OrgAgent[];
    }

    return currentNode.agents || [];
  }, [rootNode, currentNode, isUnassignedView, departmentId]);

  const agentsForDisplay = useMemo(() => {
    const orgId = isUnassignedView ? undefined : departmentId;
    return rawAgents.map((agent) => mapOrgAgentToAgent(agent, orgId));
  }, [rawAgents, departmentId, isUnassignedView]);

  const breadcrumbItems = useMemo(() => {
    if (!rootNode) {
      return [];
    }

    const trail: { key: string; title: React.ReactNode }[] = [];
    const rootTitle = rootNode.name || t('pages.agents.organizations') || 'Organizations';

    if (isRootView) {
      trail.push({ key: rootNode.id, title: rootTitle });
      return trail;
    }

    trail.push({
      key: rootNode.id,
      title: (
        <Link to="/agents" replace>
          {rootTitle}
        </Link>
      ),
    });

    if (isUnassignedView) {
      trail.push({
        key: UNASSIGNED_NODE_ID,
        title: t('pages.agents.unassigned_agents') || 'Unassigned Agents',
      });
      return trail;
    }

    if (!currentNode) {
      return trail;
    }

    const path = findPathToNode(rootNode, currentNode.id);
    if (!path) {
      return trail;
    }

    path.slice(1).forEach((node, index, arr) => {
      const isLast = index === arr.length - 1;
      trail.push({
        key: node.id,
        title: isLast ? (
          node.name
        ) : (
          <a
            onClick={() => navigate(`/agents/room/${node.id}`)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                navigate(`/agents/room/${node.id}`);
              }
            }}
            role="link"
            tabIndex={0}
          >
            {node.name}
          </a>
        ),
      });
    });

    return trail;
  }, [rootNode, currentNode, isRootView, isUnassignedView, navigate, t]);

  const handleDoorClick = useCallback(
    (door: DisplayNode) => {
      if (door.type === 'unassigned_agents') {
        navigate('/agents/room/unassigned');
        return;
      }

      navigate(`/agents/room/${door.id}`);
    },
    [navigate]
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

  const forceRefreshOrgStructure = useCallback(async () => {
    if (!username) {
      return;
    }

    logger.info('[OrgNavigator] Force refreshing organization structure...');
    setLoading(true);
    setError(null);

    try {
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
          logger.info(`[OrgNavigator] Force refreshed and saved ${allAgents.length} agents to agentStore`);
        }

        logger.info('[OrgNavigator] Organization structure force refreshed successfully');
      } else {
        const errorMessage = response.error?.message || 'Failed to fetch organization structure';
        setError(errorMessage);
        logger.error('[OrgNavigator] Error in force refresh response:', errorMessage);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';
      setError(errorMessage);
      logger.error('[OrgNavigator] Error force refreshing organization structure:', errorMessage);
    } finally {
      setLoading(false);
    }
  }, [username, setAllOrgAgents, setLoading, setError, setAgents]);

  useOrgAgentsUpdate(forceRefreshOrgStructure, [forceRefreshOrgStructure], 'OrgNavigator');

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
      {/* SVG虚拟地板和网格 */}
      <svg className="navigator-bg-svg" width="100%" height="100%" viewBox="0 0 1200 800" style={{position:'absolute',left:0,top:0,zIndex:0}}>
        {/* 椭圆地板 */}
        <ellipse cx="600" cy="700" rx="420" ry="80" fill="var(--ant-primary-1, #e6f4ff)" opacity="0.7" />
        {/* 网格线条 */}
        {Array.from({length: 7}).map((_,i) => (
          <ellipse key={i} cx="600" cy="700" rx={180+i*40} ry={34+i*8} fill="none" stroke="var(--ant-primary-2, #91caff)" strokeWidth="1.5" opacity="0.18" />
        ))}
        {/* 径向发光线 */}
        {Array.from({length: 12}).map((_,i) => {
          const angle = (2*Math.PI*i)/12;
          return <line key={i} x1={600} y1={700} x2={600+420*Math.cos(angle)} y2={700+80*Math.sin(angle)} stroke="var(--ant-primary-2, #91caff)" strokeWidth="1.2" opacity="0.10" />
        })}
        {/* 智能节点 */}
        {[{cx:300,cy:200},{cx:900,cy:250},{cx:600,cy:400},{cx:400,cy:600},{cx:800,cy:650}].map((n,i)=>(
          <circle key={i} cx={n.cx} cy={n.cy} r="18" fill="var(--ant-primary-color, #1677ff)" opacity="0.18" filter="url(#glow)" />
        ))}
        {/* 卫星点 */}
        {[{ cx: 150, cy: 300, r: 4 },{ cx: 1050, cy: 180, r: 3 },{ cx: 200, cy: 500, r: 2 },{ cx: 950, cy: 420, r: 3 },{ cx: 500, cy: 150, r: 2 },{ cx: 700, cy: 600, r: 4 }].map((dot, i) => (
          <circle key={"sat"+i} cx={dot.cx} cy={dot.cy} r={dot.r} fill="var(--ant-primary-color, #1677ff)" opacity="0.32" filter="url(#glow)" />
        ))}
        {/* 数据流/流程线 */}
        <polyline points="300,200 600,400 900,250" fill="none" stroke="var(--ant-primary-color, #1677ff)" strokeWidth="3" opacity="0.13" />
        <polyline points="400,600 600,400 800,650" fill="none" stroke="var(--ant-primary-2, #91caff)" strokeWidth="2" opacity="0.10" />
        {/* AI脑波/光圈 */}
        <ellipse cx="600" cy="400" rx="80" ry="30" fill="none" stroke="var(--ant-primary-2, #91caff)" strokeWidth="2" opacity="0.10" />
        {/* SVG滤镜：发光 */}
        <defs>
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="8" result="coloredBlur"/>
            <feMerge>
              <feMergeNode in="coloredBlur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
        </defs>
      </svg>
      {/* 光斑/灯光 */}
      <div className="navigator-bg-blur navigator-bg-blur1" />
      <div className="navigator-bg-blur navigator-bg-blur2" />
      <div className="navigator-bg-blur navigator-bg-blur3" />
      {/* 空间灯光 */}
      <div className="navigator-space-lights">
        <div className="navigator-space-light navigator-space-light1" />
        <div className="navigator-space-light navigator-space-light2" />
        <div className="navigator-space-light navigator-space-light3" />
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
                <AgentAvatar
                  key={cardId}
                  agent={agent}
                  onChat={() => navigate(`/chat?agentId=${cardId}`)}
                />
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

export default React.memo(OrgNavigator);
