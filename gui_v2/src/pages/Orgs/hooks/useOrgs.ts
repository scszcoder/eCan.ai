/**
 * Organizations Management Hook
 */

import { useState, useEffect, useCallback } from 'react';
import { message } from 'antd';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '../../../services/ipc_api';
import { userStorageManager } from '../../../services/storage/UserStorageManager';
import type { Organization, Agent, OrganizationState, OrganizationFormData } from '../types';

export const useOrgs = () => {
  const { t } = useTranslation();
  const username = userStorageManager.getUsername();

  const [state, setState] = useState<OrganizationState>({
    organizations: [],
    selectedOrganization: null,
    organizationAgents: [],
    availableAgents: [],
    loading: false,
    modalVisible: false,
    bindModalVisible: false,
    editingOrganization: null,
  });

  // Helper function to update state
  const updateState = useCallback((updates: Partial<OrganizationState>) => {
    setState(prev => ({ ...prev, ...updates }));
  }, []);

  // Load organizations
  const loadOrganizations = useCallback(async () => {
    if (!username) return;
    
    updateState({ loading: true });
    try {
      const api = get_ipc_api();
      const response = await api.getOrganizations(username);
      
      if (response.success && response.data) {
        // Handle both array and object formats
        const organizations = Array.isArray(response.data)
          ? response.data
          : (response.data as any).organizations || [];

        updateState({
          organizations,
          loading: false
        });
      } else {
        message.error(t('org.messages.loadFailed'));
        updateState({ loading: false });
      }
    } catch (error) {
      console.error('Error loading organizations:', error);
      message.error(t('org.messages.loadFailed'));
      updateState({ loading: false });
    }
  }, [username, t, updateState]);

  // Load organization agents
  const loadOrganizationAgents = useCallback(async (organizationId: string) => {
    if (!username) return;

    try {
      const api = get_ipc_api();

      // 找到选中的组织
      const findOrganizationById = (orgs: Organization[], id: string): Organization | null => {
        for (const org of orgs) {
          if (org.id === id) return org;
          if (org.children) {
            const found = findOrganizationById(org.children, id);
            if (found) return found;
          }
        }
        return null;
      };

      const selectedOrg = findOrganizationById(state.organizations, organizationId);

      if (selectedOrg) {
        // 如果是非叶子节点，获取所有子节点的Agent（include_children=true）
        // 如果是叶子节点，只获取当前节点的Agent（include_children=false）
        const includeChildren = selectedOrg.children && selectedOrg.children.length > 0;
        const response = await api.getOrganizationAgents(username, organizationId, includeChildren);

        if (response.success && response.data) {
          updateState({ organizationAgents: (response.data as any).agents || [] });
        } else {
          message.error(t('org.messages.loadFailed'));
        }
      }
    } catch (error) {
      console.error('Error loading organization agents:', error);
      message.error(t('org.messages.loadFailed'));
    }
  }, [username, t, updateState, state.organizations]);

  // Load available agents for binding
  const loadAvailableAgents = useCallback(async () => {
    if (!username || !state.selectedOrganization?.id) return;
    
    try {
      const api = get_ipc_api();
      const response = await api.getAvailableAgentsForBinding(username, state.selectedOrganization.id);
      
      if (response.success && response.data) {
        updateState({ availableAgents: (response.data as any).agents || [] });
      } else {
        message.error(t('org.messages.loadFailed'));
      }
    } catch (error) {
      console.error('Error loading available agents:', error);
      message.error(t('org.messages.loadFailed'));
    }
  }, [username, state.selectedOrganization?.id, t, updateState]);

  // Select organization
  const selectOrganization = useCallback((org: Organization | null) => {
    updateState({ 
      selectedOrganization: org,
      organizationAgents: [] 
    });
    if (org) {
      loadOrganizationAgents(org.id);
    }
  }, [loadOrganizationAgents, updateState]);

  // Create organization
  const createOrganization = useCallback(async (data: OrganizationFormData) => {
    if (!username) return;
    
    try {
      const api = get_ipc_api();
      const response = await api.createOrganization(
        username,
        data.name,
        data.description,
        state.selectedOrganization?.id,
        data.organization_type
      );
      
      if (response.success) {
        message.success(t('org.messages.createSuccess'));
        loadOrganizations();
        updateState({ modalVisible: false });
      } else {
        message.error(response.error?.message || t('org.messages.createFailed'));
      }
    } catch (error) {
      console.error('Error creating organization:', error);
      message.error(t('org.messages.createFailed'));
    }
  }, [username, state.selectedOrganization?.id, t, loadOrganizations, updateState]);

  // Update organization
  const updateOrganization = useCallback(async (id: string, data: Partial<OrganizationFormData>) => {
    if (!username) return;
    
    try {
      const api = get_ipc_api();
      const response = await api.updateOrganization(
        username,
        id,
        data.name,
        data.description
      );
      
      if (response.success) {
        message.success(t('org.messages.updateSuccess'));
        loadOrganizations();
        updateState({ modalVisible: false });
      } else {
        message.error(response.error?.message || t('org.messages.updateFailed'));
      }
    } catch (error) {
      console.error('Error updating organization:', error);
      message.error(t('org.messages.updateFailed'));
    }
  }, [username, t, loadOrganizations, updateState]);

  // Delete organization
  const deleteOrganization = useCallback(async (id: string) => {
    if (!username) return;
    
    try {
      const api = get_ipc_api();
      const response = await api.deleteOrganization(username, id);
      
      if (response.success) {
        message.success(t('org.messages.deleteSuccess'));
        loadOrganizations();
        if (state.selectedOrganization?.id === id) {
          updateState({ 
            selectedOrganization: null,
            organizationAgents: [] 
          });
        }
      } else {
        message.error(response.error?.message || t('org.messages.deleteFailed'));
      }
    } catch (error) {
      console.error('Error deleting organization:', error);
      message.error(t('org.messages.deleteFailed'));
    }
  }, [username, state.selectedOrganization?.id, t, loadOrganizations, updateState]);

  // Bind agents
  const bindAgents = useCallback(async (agentIds: string[]) => {
    if (!username || !state.selectedOrganization?.id) return;
    
    try {
      const api = get_ipc_api();
      const promises = agentIds.map((agentId: string) =>
        api.bindAgentToOrganization(username, agentId, state.selectedOrganization!.id)
      );
      
      const results = await Promise.all(promises);
      const failures = results.filter(r => !r.success);
      
      if (failures.length === 0) {
        message.success(t('org.messages.bindSuccess'));
        loadOrganizationAgents(state.selectedOrganization.id);
        updateState({ bindModalVisible: false });
      } else {
        message.error(t('org.messages.bindFailed'));
      }
    } catch (error) {
      console.error('Error binding agents:', error);
      message.error(t('org.messages.bindFailed'));
    }
  }, [username, state.selectedOrganization?.id, t, loadOrganizationAgents, updateState]);

  // Unbind agent
  const unbindAgent = useCallback(async (agentId: string) => {
    if (!username) return;
    
    try {
      const api = get_ipc_api();
      const response = await api.unbindAgentFromOrganization(username, agentId);
      
      if (response.success) {
        message.success(t('org.messages.unbindSuccess'));
        if (state.selectedOrganization) {
          loadOrganizationAgents(state.selectedOrganization.id);
        }
      } else {
        message.error(response.error?.message || t('org.messages.unbindFailed'));
      }
    } catch (error) {
      console.error('Error unbinding agent:', error);
      message.error(t('org.messages.unbindFailed'));
    }
  }, [username, state.selectedOrganization, t, loadOrganizationAgents]);

  // Move organization (drag & drop)
  const moveOrganization = useCallback(async (dragNodeId: string, targetNodeId: string, dropToGap: boolean) => {
    if (!username) return;
    
    try {
      let newParentId: string | null = null;
      
      if (!dropToGap) {
        newParentId = targetNodeId;
      } else {
        const findOrganizationById = (orgs: Organization[], id: string): Organization | null => {
          for (const org of orgs) {
            if (org.id === id) return org;
            if (org.children) {
              const found = findOrganizationById(org.children, id);
              if (found) return found;
            }
          }
          return null;
        };
        
        const targetOrg = findOrganizationById(state.organizations, targetNodeId);
        newParentId = targetOrg?.parent_id || null;
      }
      
      const ipcApi = get_ipc_api();
      const updateResponse = await (ipcApi as any).executeRequest('update_organization', {
        username,
        organization_id: dragNodeId,
        parent_id: newParentId
      });
      
      if (updateResponse.success) {
        message.success(t('org.messages.moveSuccess'));
        loadOrganizations();
      } else {
        message.error(updateResponse.error?.message || t('org.messages.moveFailed'));
      }
    } catch (error) {
      console.error('Error moving organization:', error);
      message.error(t('org.messages.moveFailed'));
    }
  }, [username, state.organizations, t, loadOrganizations]);

  // Chat with agent
  const chatWithAgent = useCallback((agent: Agent) => {
    try {
      const chatUrl = `/chat?agent=${encodeURIComponent(agent.id)}&name=${encodeURIComponent(agent.name)}`;
      window.location.href = chatUrl;
    } catch (error) {
      console.error('Error navigating to chat:', error);
      message.error(t('org.messages.chatFailed'));
    }
  }, [t]);

  // Load organizations on mount
  useEffect(() => {
    loadOrganizations();
  }, [loadOrganizations]);

  // Initialize data loading
  useEffect(() => {
    if (username) {
      loadOrganizations();
    }
  }, [username, loadOrganizations]);

  return {
    state,
    actions: {
      updateState,
      loadOrganizations,
      loadOrganizationAgents,
      loadAvailableAgents,
      selectOrganization,
      createOrganization,
      updateOrganization,
      deleteOrganization,
      bindAgents,
      unbindAgent,
      moveOrganization,
      chatWithAgent,
    },
  };
};
