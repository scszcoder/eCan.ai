import { TreeOrgNode, OrgAgent } from '../../Orgs/types';

/**
 * 在树形结构中查找指定ID的节点
 */
export function findTreeNodeById(
  node: TreeOrgNode,
  targetId: string
): TreeOrgNode | null {
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

/**
 * 从树形结构中提取All Agent
 */
export function extractAllAgents(node: TreeOrgNode): OrgAgent[] {
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
}

/**
 * Sort子节点
 */
export function sortTreeChildren(children: TreeOrgNode[]): TreeOrgNode[] {
  return [...children].sort((a, b) => {
    if (a.sort_order !== b.sort_order) {
      return a.sort_order - b.sort_order;
    }
    return a.name.localeCompare(b.name);
  });
}
