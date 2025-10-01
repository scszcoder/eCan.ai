import { create } from 'zustand';
import { 
  Org, 
  OrgTreeNode, 
  OrgAgent, 
  DisplayNode, 
  TreeOrgNode,
  RootNode,
  buildOrgTree, 
  buildDisplayNodesFromTree,
  GetAllOrgAgentsResponse 
} from '../pages/Orgs/types';

interface OrgStoreState {
  // 树形数据结构
  root: RootNode | null;
  treeOrgs: TreeOrgNode[];
  rootAgents: OrgAgent[];
  
  // 原始数据（向后兼容）
  orgs: Org[];
  agents: OrgAgent[];
  unassignedAgents: OrgAgent[];
  
  // 处理后的数据
  orgTree: OrgTreeNode[];
  displayNodes: DisplayNode[];
  
  // 状态
  loading: boolean;
  error: string | null;
  lastFetchTime: number | null;
  
  // Actions
  setAllOrgAgents: (data: GetAllOrgAgentsResponse) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clearData: () => void;
  shouldFetchData: () => boolean;
  
  // Update methods for real-time sync
  updateOrg: (orgId: string, updates: Partial<Org>) => void;
  addAgentToOrg: (orgId: string, agent: OrgAgent) => void;
  removeAgentFromOrg: (agentId: string) => void;
  updateAgent: (agentId: string, updates: Partial<OrgAgent>) => void;
  refreshOrgData: () => Promise<void>;
}

const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes

export const useOrgStore = create<OrgStoreState>((set, get) => ({
  // 树形数据结构
  root: null,
  treeOrgs: [],
  rootAgents: [],
  
  // 原始数据（向后兼容）
  orgs: [],
  agents: [],
  unassignedAgents: [],
  
  // 处理后的数据
  orgTree: [],
  displayNodes: [],
  
  // 状态
  loading: false,
  error: null,
  lastFetchTime: null,
  
  setAllOrgAgents: (data: GetAllOrgAgentsResponse) => {
    const treeRoot = data.orgs;  // 完整的树形结构（根节点）
    
    // 从树形结构中提取扁平的组织列表和所有 agents（向后兼容）
    const flattenTree = (treeNode: TreeOrgNode): { orgs: Org[], agents: OrgAgent[] } => {
      const orgs: Org[] = [];
      const agents: OrgAgent[] = [];
      
      const traverse = (node: TreeOrgNode) => {
        // 添加组织信息
        orgs.push({
          id: node.id,
          name: node.name,
          description: node.description,
          parent_id: node.parent_id,
          org_type: node.org_type,
          level: node.level,
          sort_order: node.sort_order,
          status: node.status,
          created_at: node.created_at,
          updated_at: node.updated_at
        });
        
        // 添加该节点的 agents
        if (node.agents && node.agents.length > 0) {
          agents.push(...node.agents);
        }
        
        // 递归处理子节点
        if (node.children && node.children.length > 0) {
          node.children.forEach(traverse);
        }
      };
      
      traverse(treeNode);
      return { orgs, agents };
    };
    
    const { orgs: flatOrgs, agents: allAgents } = flattenTree(treeRoot);
    
    // 分离有归属和无归属的 Agent
    const orgAgents = allAgents.filter(agent => agent.org_id);
    const unassignedAgents = allAgents.filter(agent => !agent.org_id);
    
    // 构建组织树（向后兼容）
    const orgTree = buildOrgTree(flatOrgs);
    
    // 构建显示节点 - 基于树形结构
    const displayNodes = buildDisplayNodesFromTree(null, treeRoot);
    
    set({ 
      // 新的树形数据
      root: {
        id: treeRoot.id,
        name: treeRoot.name,
        description: treeRoot.description || ''
      },
      treeOrgs: [treeRoot],  // 包装成数组以保持兼容性
      rootAgents: treeRoot.agents || [],
      
      // 向后兼容的扁平数据
      orgs: flatOrgs,
      agents: orgAgents,
      unassignedAgents: unassignedAgents,
      orgTree,
      displayNodes,
      lastFetchTime: Date.now(),
      error: null 
    });
  },
  
  setLoading: (loading: boolean) => set({ loading }),
  
  setError: (error: string | null) => set({ error, loading: false }),
  
  clearData: () => set({ 
    // 清理树形数据
    root: null,
    treeOrgs: [],
    rootAgents: [],
    
    // 清理向后兼容数据
    orgs: [],
    agents: [],
    unassignedAgents: [],
    orgTree: [], 
    displayNodes: [],
    lastFetchTime: null, 
    error: null 
  }),
  
  shouldFetchData: () => {
    const { lastFetchTime } = get();
    if (!lastFetchTime) return true;
    return Date.now() - lastFetchTime > CACHE_DURATION;
  },
  
  // Update a specific organization
  updateOrg: (orgId: string, updates: Partial<Org>) => {
    const updateOrgInTree = (node: TreeOrgNode): TreeOrgNode => {
      if (node.id === orgId) {
        // Ensure we maintain TreeOrgNode structure by preserving children and agents
        return { 
          ...node, 
          ...updates,
          // Preserve required TreeOrgNode properties
          children: node.children,
          agents: node.agents
        };
      }
      if (node.children && node.children.length > 0) {
        return {
          ...node,
          children: node.children.map(updateOrgInTree)
        };
      }
      return node;
    };
    
    set(state => {
      const updatedTreeOrgs = state.treeOrgs.map(updateOrgInTree);
      const updatedOrgs = state.orgs.map(org => 
        org.id === orgId ? { ...org, ...updates } : org
      );
      
      // Rebuild display nodes
      const displayNodes = buildDisplayNodesFromTree(null, updatedTreeOrgs[0]);
      
      return {
        treeOrgs: updatedTreeOrgs,
        orgs: updatedOrgs,
        displayNodes
      };
    });
  },
  
  // Add agent to organization
  addAgentToOrg: (orgId: string, agent: OrgAgent) => {
    const addAgentToNode = (node: TreeOrgNode): TreeOrgNode => {
      if (node.id === orgId) {
        const existingAgents = node.agents || [];
        // Check if agent already exists
        if (existingAgents.some(a => a.id === agent.id)) {
          return node;
        }
        return {
          ...node,
          agents: [...existingAgents, agent]
        };
      }
      if (node.children && node.children.length > 0) {
        return {
          ...node,
          children: node.children.map(addAgentToNode)
        };
      }
      return node;
    };
    
    set(state => {
      const updatedTreeOrgs = state.treeOrgs.map(addAgentToNode);
      const updatedAgents = [...state.agents];
      
      // Add to agents list if not exists
      if (!updatedAgents.some(a => a.id === agent.id)) {
        updatedAgents.push(agent);
      }
      
      // Rebuild display nodes
      const displayNodes = buildDisplayNodesFromTree(null, updatedTreeOrgs[0]);
      
      return {
        treeOrgs: updatedTreeOrgs,
        agents: updatedAgents,
        displayNodes
      };
    });
  },
  
  // Remove agent from organization
  removeAgentFromOrg: (agentId: string) => {
    const removeAgentFromNode = (node: TreeOrgNode): TreeOrgNode => {
      const updatedAgents = (node.agents || []).filter(a => a.id !== agentId);
      const updatedChildren = node.children ? node.children.map(removeAgentFromNode) : [];
      
      return {
        ...node,
        agents: updatedAgents,
        children: updatedChildren
      };
    };
    
    set(state => {
      const updatedTreeOrgs = state.treeOrgs.map(removeAgentFromNode);
      const updatedAgents = state.agents.filter(a => a.id !== agentId);
      
      // Rebuild display nodes
      const displayNodes = buildDisplayNodesFromTree(null, updatedTreeOrgs[0]);
      
      return {
        treeOrgs: updatedTreeOrgs,
        agents: updatedAgents,
        displayNodes
      };
    });
  },
  
  // Update agent information
  updateAgent: (agentId: string, updates: Partial<OrgAgent>) => {
    const updateAgentInNode = (node: TreeOrgNode): TreeOrgNode => {
      const updatedAgents = (node.agents || []).map(agent =>
        agent.id === agentId ? { ...agent, ...updates } : agent
      );
      const updatedChildren = node.children ? node.children.map(updateAgentInNode) : [];
      
      return {
        ...node,
        agents: updatedAgents,
        children: updatedChildren
      };
    };
    
    set(state => {
      const updatedTreeOrgs = state.treeOrgs.map(updateAgentInNode);
      const updatedAgents = state.agents.map(agent =>
        agent.id === agentId ? { ...agent, ...updates } : agent
      );
      
      // Rebuild display nodes
      const displayNodes = buildDisplayNodesFromTree(null, updatedTreeOrgs[0]);
      
      return {
        treeOrgs: updatedTreeOrgs,
        agents: updatedAgents,
        displayNodes
      };
    });
  },
  
  // Refresh org data (for manual refresh)
  refreshOrgData: async () => {
    // This will be implemented by the component that uses the store
    // It's here as a placeholder for future use
    return Promise.resolve();
  },
}));
