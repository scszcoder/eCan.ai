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
  // Tree data structure
  root: RootNode | null;
  treeOrgs: TreeOrgNode[];
  rootAgents: OrgAgent[];
  
  // Raw data (backward compatible)
  orgs: Org[];
  agents: OrgAgent[];
  unassignedAgents: OrgAgent[];
  
  // Processed data
  orgTree: OrgTreeNode[];
  displayNodes: DisplayNode[];
  
  // State
  loading: boolean;
  error: string | null;
  lastFetchTime: number | null;
  lastUpdateTime: number;  // Used to force re-render
  
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
  // Tree data structure
  root: null,
  treeOrgs: [],
  rootAgents: [],
  
  // Raw data (backward compatible)
  orgs: [],
  agents: [],
  unassignedAgents: [],
  
  // Processed data
  orgTree: [],
  displayNodes: [],
  
  // State
  loading: false,
  error: null,
  lastFetchTime: null,
  lastUpdateTime: 0,
  
  setAllOrgAgents: (data: GetAllOrgAgentsResponse) => {
    console.log('[OrgStore] setAllOrgAgents called with data:', data);
    console.log('[OrgStore] data.orgs:', data.orgs);
    
    // Use raw data (avoid data loss from JSON serialization)
    const treeRoot = data.orgs;
    
    // Extract flat organization list and all agents from tree structure (backward compatible)
    const flattenTree = (treeNode: TreeOrgNode): { orgs: Org[], agents: OrgAgent[] } => {
      const orgs: Org[] = [];
      const agents: OrgAgent[] = [];
      
      const traverse = (node: TreeOrgNode) => {
        // Add organization information
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
        
        // Add agents from this node
        if (node.agents && node.agents.length > 0) {
          agents.push(...node.agents);
        }
        
        // Recursively process child nodes
        if (node.children && node.children.length > 0) {
          node.children.forEach(traverse);
        }
      };
      
      traverse(treeNode);
      return { orgs, agents };
    };
    
    const { orgs: flatOrgs, agents: allAgents } = flattenTree(treeRoot);
    
    console.log('[OrgStore] Flattened agents:', allAgents);
    console.log('[OrgStore] Agents count:', allAgents.length);
    if (allAgents.length > 0) {
      console.log('[OrgStore] Sample agent:', allAgents[0]);
    }
    
    // Separate unassigned agents (backward compatible)
    const unassignedAgents = allAgents.filter(agent => !agent.org_id);
    
    // Build organization tree (backward compatible)
    const orgTree = buildOrgTree(flatOrgs);
    
    // Build display nodes - based on tree structure
    const displayNodes = buildDisplayNodesFromTree(null, treeRoot);
    
    const now = Date.now();
    set({ 
      // New tree data
      root: {
        id: treeRoot.id,
        name: treeRoot.name,
        description: treeRoot.description || ''
      },
      treeOrgs: [treeRoot],  // Wrap as array for compatibility
      rootAgents: treeRoot.agents || [],
      
      // Backward compatible flat data
      orgs: flatOrgs,
      agents: allAgents,  // 🔥 Use all agents (with and without org_id)
      unassignedAgents: unassignedAgents,
      orgTree,
      displayNodes,
      lastFetchTime: now,
      lastUpdateTime: now,  // Update timestamp to force re-render
      error: null 
    });
  },
  
  setLoading: (loading: boolean) => set({ loading }),
  
  setError: (error: string | null) => set({ error, loading: false }),
  
  clearData: () => set({ 
    // Clear tree data
    root: null,
    treeOrgs: [],
    rootAgents: [],
    
    // Clear backward compatible data
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
