/**
 * Org Management Types
 */

export interface Org {
  id: string;
  name: string;
  description?: string;
  parent_id?: string;
  org_type: string;
  level: number;
  sort_order: number;
  status: string;
  created_at?: string;
  updated_at?: string;
  children?: Org[];
}



export interface Agent {
  id: string;
  name: string;
  description?: string;
  org_id?: string;
  status: string;
  avatar?: string;
  capabilities?: string[];
  isBound?: boolean; // 是否已绑定到当前组织
}

export interface OrgFormData {
  name: string;
  description?: string;
  org_type: string;
}

export interface AgentBindingFormData {
  agent_ids: string[];
}

export interface OrgTreeNode {
  key: string;
  title: React.ReactNode;
  children?: OrgTreeNode[];
  isLeaf: boolean;
}



export interface OrgState {
  orgs: Org[];
  selectedOrg: Org | null;
  orgAgents: Agent[];
  availableAgents: Agent[];
  loading: boolean;
  modalVisible: boolean;
  bindModalVisible: boolean;
  editingOrg: Org | null;
}



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
  chatWithAgent: (agent: Agent) => void;
}



export type OrgType = 'company' | 'department' | 'team' | 'group';
export type OrgStatus = 'active' | 'inactive' | 'archived';


