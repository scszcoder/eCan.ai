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
}));
