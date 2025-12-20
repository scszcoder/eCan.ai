import { OrgAgent, TreeOrgNode, DisplayNode } from '../../Orgs/types';
import type { Agent } from '../types';
import { sortTreeChildren, extractAllAgents } from './orgTreeUtils';

export const UNASSIGNED_NODE_ID = 'unassigned';

/**
 * 将 OrgAgent Convert为 Agent Type
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
    // 顶层Field（AgentCard 优先读取这些）
    id: orgAgent.id,
    name: orgAgent.name,
    description: orgAgent.description || '',
    // card Field（向后Compatible）
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
  } as Agent;
}

/**
 * 为节点构建 Door DisplayList
 */
export function buildDoorsForNode(
  node: TreeOrgNode,
  includeUnassignedDoor: boolean
): DisplayNode[] {
  const doors: DisplayNode[] = [];
  const sortedChildren = sortTreeChildren(node.children || []);

  sortedChildren.forEach((child) => {
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

  // Add未分配的 Agent 门
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
