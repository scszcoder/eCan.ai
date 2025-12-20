/**
 * Organization Types - Unified type definitions for organization management
 */

import type { Agent } from '../Agents/types';

// Base organization interface
export interface Org {
  id: string;
  name: string;
  description?: string;
  parent_id?: string;
  org_type: string;
  level: number;
  sort_order: number;
  status: string;
  settings?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
  
  // Computed properties
  organization_type?: string; // Backward compatibility
  children?: Org[];
  
  // Helper methods (when converted from backend)
  is_leaf?: boolean;
}

// Display节点Type枚举
export type DisplayNodeType = 'org_with_children' | 'org_with_agents' | 'unassigned_agents';

// Display节点Type（Used for OrgNavigator Page的门ComponentDisplay）
export interface DisplayNode {
  id: string;
  name: string;
  type: 'org_with_children' | 'org_with_agents' | 'unassigned_agents';
  description: string;
  sort_order: number;
  
  // OptionalField，根据Type不同而不同
  org?: Org | OrgTreeNode | TreeOrgNode;  // 组织Information（对于组织Type节点）
  agents?: OrgAgent[];     // Agent List（对于 agent Type节点）
  agentCount?: number;     // Agent Count
  hasChildren?: boolean;   // 是否有子节点（对于组织Type节点）
  childrenCount?: number;  // 子节点Count（对于组织Type节点）
}

// Tree node interface for hierarchical display (保持向后Compatible)
export interface OrgTreeNode extends Org {
  children: OrgTreeNode[];
  hasAgents?: boolean;
  agentCount?: number;
}

// Organization-Agent association interface (专门Used for组织-Agent 关联)
export interface OrgAgent {
  id: string;
  name: string;
  description?: string;
  avatar?: string | {
    id: string;
    imageUrl: string;
    videoPath?: string;
    videoExists: boolean;
  };
  status: string;
  org_id?: string;
  created_at?: string;
  updated_at?: string;
  capabilities?: string[];
  isBound?: boolean; // 是否已绑定（到任何组织）
  isBoundToCurrentOrg?: boolean; // 是否绑定到When前选中的组织
  boundOrgId?: string; // 绑定到的组织 ID
}

// API Response types
export interface GetOrgsResponse {
  organizations: Org[];
  message: string;
}

export interface GetOrgAgentsResponse {
  agents: OrgAgent[];
  message: string;
}

// 根节点Information
export interface RootNode {
  id: string;
  name: string;
  description: string;
}

// 树形组织节点（Include子节点和直属 Agent）
export interface TreeOrgNode extends Org {
  children: TreeOrgNode[];
  agents: OrgAgent[];
}

// 新的整合DataResponseType：GetAll组织和对应的 Agent Data（完整树形结构）
export interface GetAllOrgAgentsResponse {
  orgs: TreeOrgNode;        // 完整的树形结构：根节点Include children 和 agents
  message: string;
}

// Form data types
export interface OrgFormData {
  name: string;
  description?: string;
  org_type: string;
}

export interface AgentBindingFormData {
  agent_id: string;  // 改为单选，只绑定一个代理
}

// Tree component types
export interface OrgTreeComponentNode {
  key: string;
  title: React.ReactNode;
  children?: OrgTreeComponentNode[];
  isLeaf: boolean;
}

// Store state types
export interface OrgState {
  orgs: Org[];
  selectedOrg: Org | null;
  orgAgents: OrgAgent[]; // 组织关联的 Agent Information
  availableAgents: Agent[]; // Available的 Agent（使用 Agents Module的 Agent Type）
  loading: boolean;
  modalVisible: boolean;
  bindModalVisible: boolean;
  editingOrg: Org | null;
}

// Store actions types
export interface OrgActions {
  loadOrgs: () => Promise<void>;
  loadOrgAgents: (orgId: string) => Promise<void>;
  loadAvailableAgents: () => Promise<void>;
  selectOrg: (org: Org | null) => void;
  createOrg: (data: OrgFormData) => Promise<void>;
  updateOrg: (id: string, data: Partial<OrgFormData>) => Promise<void>;
  deleteOrg: (id: string) => Promise<void>;
  bindAgents: (agentIds: string[]) => Promise<void>;
  unbindAgent: (agentId: string) => Promise<void>;
  moveOrg: (dragNodeId: string, targetNodeId: string, dropToGap: boolean) => Promise<void>;
  chatWithAgent: (agent: Agent) => void; // 使用 Agents Module的 Agent Type
}

// Enum types
export type OrgType = 'company' | 'department' | 'team' | 'group';
export type OrgStatus = 'active' | 'inactive' | 'archived';

// Helper function to build organization tree
export function buildOrgTree(orgs: Org[]): OrgTreeNode[] {
  const orgMap = new Map<string, OrgTreeNode>();
  const rootNodes: OrgTreeNode[] = [];

  // First pass: create all nodes
  orgs.forEach(org => {
    const node: OrgTreeNode = {
      ...org,
      children: [],
      hasAgents: false,
      agentCount: 0
    };
    orgMap.set(org.id, node);
  });

  // Second pass: build tree structure
  orgs.forEach(org => {
    const node = orgMap.get(org.id)!;
    if (org.parent_id && orgMap.has(org.parent_id)) {
      const parent = orgMap.get(org.parent_id)!;
      parent.children.push(node);
    } else {
      rootNodes.push(node);
    }
  });

  // Sort nodes by sort_order and name
  const sortNodes = (nodes: OrgTreeNode[]) => {
    nodes.sort((a, b) => {
      if (a.sort_order !== b.sort_order) {
        return a.sort_order - b.sort_order;
      }
      return a.name.localeCompare(b.name);
    });
    nodes.forEach(node => sortNodes(node.children));
  };

  sortNodes(rootNodes);
  return rootNodes;
}

// Helper function to find leaf nodes (organizations without children)
export function getLeafNodes(nodes: OrgTreeNode[]): OrgTreeNode[] {
  const leafNodes: OrgTreeNode[] = [];
  
  const traverse = (node: OrgTreeNode) => {
    if (node.children.length === 0) {
      leafNodes.push(node);
    } else {
      node.children.forEach(traverse);
    }
  };

  nodes.forEach(traverse);
  return leafNodes;
}

// Helper function to find organization by ID
export function findOrgById(nodes: OrgTreeNode[], id: string): OrgTreeNode | null {
  for (const node of nodes) {
    if (node.id === id) {
      return node;
    }
    const found = findOrgById(node.children, id);
    if (found) {
      return found;
    }
  }
  return null;
}

// 构建Display节点List的Function（Based on扁平组织Data）
export function buildDisplayNodes(
  organizations: Org[], 
  agents: OrgAgent[]
): DisplayNode[] {
  const displayNodes: DisplayNode[] = [];
  
  // 构建组织树
  const orgTree = buildOrgTree(organizations);
  
  // 分离有归属和无归属的 Agent
  const orgAgents = agents.filter(agent => agent.org_id);
  const unassignedAgents = agents.filter(agent => !agent.org_id);
  
  // Create Agent 按组织分组的Map
  const agentsByOrg = new Map<string, OrgAgent[]>();
  orgAgents.forEach(agent => {
    if (agent.org_id) {
      if (!agentsByOrg.has(agent.org_id)) {
        agentsByOrg.set(agent.org_id, []);
      }
      agentsByOrg.get(agent.org_id)!.push(agent);
    }
  });
  
  // Process根节点的子节点
  orgTree.forEach(rootNode => {
    processOrgNode(rootNode, agentsByOrg, displayNodes);
  });
  
  // Add无归属的 Agent 作为独立节点
  if (unassignedAgents.length > 0) {
    displayNodes.push({
      id: 'unassigned',
      name: 'pages.agents.unassigned_agents', // 国际化键
      type: 'unassigned_agents',
      description: 'pages.agents.unassigned_agents_desc', // 国际化键
      sort_order: 999, // 排在最后
      agents: unassignedAgents,
      agentCount: unassignedAgents.length
    });
  }
  
  // 按 sort_order Sort
  displayNodes.sort((a, b) => a.sort_order - b.sort_order);
  
  return displayNodes;
}

// 构建Display节点List的Function（Based on树形Data结构）
// 直接Display根节点的Content（children 和 agents），不Display根节点本身
export function buildDisplayNodesFromTree(
  _root: RootNode | null,  // 根节点Information，暂时未使用但保留Used for将来的PathDisplay
  treeRoot: TreeOrgNode,   // 完整的树形根节点
  _rootAgents?: OrgAgent[] // 向后CompatibleParameter，现在从 treeRoot.agents Get
): DisplayNode[] {
  const displayNodes: DisplayNode[] = [];
  
  // 直接Process根节点的子组织（不Display根节点本身）
  if (treeRoot.children && treeRoot.children.length > 0) {
    treeRoot.children.forEach(childNode => {
      processTreeOrgNode(childNode, displayNodes);
    });
  }
  
  // Add根节点的 Agent（未分配的代理）- Display在最后面
  if (treeRoot.agents && treeRoot.agents.length > 0) {
    displayNodes.push({
      id: 'root_agents',
      name: 'pages.agents.unassigned_agents', // 国际化键
      type: 'unassigned_agents',
      description: 'pages.agents.unassigned_agents_desc', // 国际化键
      sort_order: 999, // 排在最后面
      agents: treeRoot.agents,
      agentCount: treeRoot.agents.length
    });
  }
  
  // 按 sort_order Sort
  displayNodes.sort((a, b) => a.sort_order - b.sort_order);
  
  return displayNodes;
}

// RecursiveProcess组织节点
function processOrgNode(
  orgNode: OrgTreeNode, 
  agentsByOrg: Map<string, OrgAgent[]>, 
  displayNodes: DisplayNode[]
): void {
  const orgAgents = agentsByOrg.get(orgNode.id) || [];
  const hasChildren = orgNode.children.length > 0;
  
  if (hasChildren) {
    // 有子节点的组织
    displayNodes.push({
      id: orgNode.id,
      name: orgNode.name,
      type: 'org_with_children',
      description: orgNode.description || '',
      sort_order: orgNode.sort_order,
      org: orgNode,
      hasChildren: true
    });
    
    // If该组织也有直属 Agent，单独Add一个 Agent 节点
    if (orgAgents.length > 0) {
      displayNodes.push({
        id: `${orgNode.id}_agents`,
        name: `${orgNode.name} (直属代理)`,
        type: 'org_with_agents',
        description: `${orgNode.name}的直属代理`,
        sort_order: orgNode.sort_order + 0.1, // 紧跟在组织节点后面
        org: orgNode,
        agents: orgAgents,
        agentCount: orgAgents.length
      });
    }
  } else {
    // 叶子节点组织，只Display Agent
    if (orgAgents.length > 0) {
      displayNodes.push({
        id: orgNode.id,
        name: orgNode.name,
        type: 'org_with_agents',
        description: orgNode.description || '',
        sort_order: orgNode.sort_order,
        org: orgNode,
        agents: orgAgents,
        agentCount: orgAgents.length
      });
    } else {
      // 空的叶子节点，也Display（可能将来会有 Agent）
      displayNodes.push({
        id: orgNode.id,
        name: orgNode.name,
        type: 'org_with_agents',
        description: orgNode.description || '',
        sort_order: orgNode.sort_order,
        org: orgNode,
        agents: [],
        agentCount: 0
      });
    }
  }
}

// RecursiveProcess树形组织节点
function processTreeOrgNode(
  treeNode: TreeOrgNode, 
  displayNodes: DisplayNode[]
): void {
  const hasChildren = treeNode.children && treeNode.children.length > 0;
  const hasAgents = treeNode.agents && treeNode.agents.length > 0;
  
  // 使用组织的原始 sort_order（未分配代理使用 999 排在最后）
  const orgSortOrder = treeNode.sort_order;
  
  if (hasChildren) {
    // 有子节点的组织 - Display为部门 room（可进入的组织节点）
    displayNodes.push({
      id: treeNode.id,
      name: treeNode.name,
      type: 'org_with_children',
      description: treeNode.description || '',
      sort_order: orgSortOrder,
      org: treeNode,
      hasChildren: true,
      childrenCount: treeNode.children.length
    });
    
    // If该组织也有直属 Agent，单独Add一个 Agent List节点
    if (hasAgents) {
      displayNodes.push({
        id: `${treeNode.id}_agents`,
        name: `${treeNode.name} (直属代理)`, // 组织名 + 固定文本，在Display时Need国际化Process
        type: 'org_with_agents',
        description: `pages.org.direct_agents_desc`, // 国际化键，Need在Display时插Value组织名
        sort_order: orgSortOrder + 0.1, // 紧跟在组织节点后面
        org: treeNode,
        agents: treeNode.agents,
        agentCount: treeNode.agents.length
      });
    }
  } else if (hasAgents) {
    // 叶子节点组织，直接Display为 Agent List
    displayNodes.push({
      id: treeNode.id,
      name: treeNode.name,
      type: 'org_with_agents',
      description: treeNode.description || '',
      sort_order: orgSortOrder,
      org: treeNode,
      agents: treeNode.agents,
      agentCount: treeNode.agents.length
    });
  } else {
    // 空组织（既没有子节点也没有 agents）- Display为部门 room
    displayNodes.push({
      id: treeNode.id,
      name: treeNode.name,
      type: 'org_with_children', // Display为组织节点，可能将来会有Content
      description: treeNode.description || '空组织',
      sort_order: orgSortOrder,
      org: treeNode,
      hasChildren: false,
      childrenCount: 0
    });
  }
}

// Backward compatibility exports
export type Organization = Org;
export type OrganizationTreeNode = OrgTreeNode;
export type OrganizationAgent = OrgAgent;
export type GetOrganizationsResponse = GetOrgsResponse;
export const buildOrganizationTree = buildOrgTree;
export const findOrganizationById = findOrgById;

// Re-export Agent type for convenience
export type { Agent } from '../Agents/types';
