/**
 * Organization Management Types
 */

export interface Organization {
  id: string;
  name: string;
  description?: string;
  parent_id?: string;
  organization_type: string;
  level: number;
  sort_order: number;
  status: string;
  created_at?: string;
  updated_at?: string;
  children?: Organization[];
}

export interface Agent {
  id: string;
  name: string;
  description?: string;
  organization_id?: string;
  status: string;
  avatar?: string;
  capabilities?: string[];
}

export interface OrganizationFormData {
  name: string;
  description?: string;
  organization_type: string;
}

export interface AgentBindingFormData {
  agent_ids: string[];
}

export interface OrganizationTreeNode {
  key: string;
  title: React.ReactNode;
  children?: OrganizationTreeNode[];
  isLeaf: boolean;
}

export interface OrganizationState {
  organizations: Organization[];
  selectedOrganization: Organization | null;
  organizationAgents: Agent[];
  availableAgents: Agent[];
  loading: boolean;
  modalVisible: boolean;
  bindModalVisible: boolean;
  editingOrganization: Organization | null;
}

export interface OrganizationActions {
  loadOrganizations: () => Promise<void>;
  loadOrganizationAgents: (organizationId: string) => Promise<void>;
  loadAvailableAgents: () => Promise<void>;
  selectOrganization: (org: Organization | null) => void;
  createOrganization: (data: OrganizationFormData) => Promise<void>;
  updateOrganization: (id: string, data: Partial<OrganizationFormData>) => Promise<void>;
  deleteOrganization: (id: string) => Promise<void>;
  bindAgents: (agentIds: string[]) => Promise<void>;
  unbindAgent: (agentId: string) => Promise<void>;
  moveOrganization: (dragNodeId: string, targetNodeId: string, dropToGap: boolean) => Promise<void>;
  chatWithAgent: (agent: Agent) => void;
}

export type OrganizationType = 'company' | 'department' | 'team' | 'group';

export type OrganizationStatus = 'active' | 'inactive' | 'archived';
