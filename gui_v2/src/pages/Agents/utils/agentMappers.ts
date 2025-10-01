import { OrgAgent, TreeOrgNode, DisplayNode } from '../../Orgs/types';
import type { Agent } from '../types';
import { sortTreeChildren } from './orgTreeUtils';

export const UNASSIGNED_NODE_ID = 'unassigned';

/**
 * 将 OrgAgent 转换为 Agent 类型
 */
export function mapOrgAgentToAgent(
  orgAgent: OrgAgent,
  orgId?: string
): Agent {
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
}

/**
 * 为节点构建 Door 显示列表
 */
export function buildDoorsForNode(
  node: TreeOrgNode,
  includeUnassignedDoor: boolean
): DisplayNode[] {
  const doors: DisplayNode[] = [];
  const sortedChildren = sortTreeChildren(node.children || []);

  sortedChildren.forEach((child) => {
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

  // 添加未分配的 Agent 门
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
}
