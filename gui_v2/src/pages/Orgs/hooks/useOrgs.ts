/**
 * Orgs Management Hook
 */

import { useState, useEffect, useCallback } from 'react';
import { message } from 'antd';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '../../../services/ipc_api';
import { userStorageManager } from '../../../services/storage/UserStorageManager';
import type { Org, Agent, OrgState, OrgFormData } from '../types';

export const useOrgs = () => {
  const { t } = useTranslation();
  const username = userStorageManager.getUsername();

  const [state, setState] = useState<OrgState>({
    orgs: [],
    selectedOrg: null,
    orgAgents: [],
    availableAgents: [],
    loading: false,
    modalVisible: false,
    bindModalVisible: false,
    editingOrg: null,
  });

  // Helper function to update state
  const updateState = useCallback((updates: Partial<OrgState>) => {
    setState(prev => ({ ...prev, ...updates }));
  }, []);

  // Load orgs
  const loadOrgs = useCallback(async () => {
    if (!username) return;

    updateState({ loading: true });
    try {
      const api = get_ipc_api();
      const response = await api.getOrgs(username);

      if (response.success && response.data) {
        // Handle both array and object formats
        const orgs = Array.isArray(response.data)
          ? response.data
          : (response.data as any).organizations || [];


        updateState({
          orgs,
          loading: false
        });
      } else {
        message.error(t('pages.org.messages.loadFailed'));
        updateState({ loading: false });
      }
    } catch (error) {
      console.error('Error loading orgs:', error);
      message.error(t('pages.org.messages.loadFailed'));
      updateState({ loading: false });
    }
  }, [username, t, updateState]);

  // Load organization agents
  const loadOrgAgents = useCallback(async (orgId: string) => {
    if (!username) return;

    updateState({ loading: true });
    try {
      const api = get_ipc_api();

      // 找到选中的组织
      const findOrgById = (orgs: Org[], id: string): Org | null => {
        for (const org of orgs) {
          if (org.id === id) return org;
          if (org.children) {
            const found = findOrgById(org.children, id);
            if (found) return found;
          }
        }
        return null;
      };

      const selectedOrg = findOrgById(state.orgs, orgId);

      if (selectedOrg) {
        // 如果是非叶子节点，获取所有子节点的Agent（include_descendants=true）
        // 如果是叶子节点，只获取当前节点的Agent（include_descendants=false）
        const includeDescendants = selectedOrg.children && selectedOrg.children.length > 0;
        const response = await api.getOrgAgents(username, orgId, includeDescendants);

        if (response.success && response.data) {
          const agents = (response.data as any).agents || [];
          const validAgents = agents.filter((agent: any) => agent && agent.id && agent.name);
          updateState({
            orgAgents: validAgents,
            loading: false
          });
        } else {
          message.error(t('pages.org.messages.loadFailed'));
          updateState({ loading: false });
        }
      } else {
        message.error(t('pages.org.messages.orgNotFound'));
        updateState({ loading: false });
      }
    } catch (error) {
      console.error('Error loading org agents:', error);
      message.error(t('pages.org.messages.loadFailed'));
      updateState({ loading: false });
    }
  }, [username, t, updateState, state.orgs]);

  // Load all agents with binding status for binding modal
  const loadAvailableAgents = useCallback(async () => {
    if (!username) return;

    try {
      const api = get_ipc_api();

      // Get all agents
      const allAgentsResponse = await api.getAgents(username, []);

      if (!allAgentsResponse.success || !allAgentsResponse.data) {
        message.error(t('pages.org.messages.loadFailed'));
        return;
      }

      const allAgents = (allAgentsResponse.data as any).agents || [];

      // Get bound agents for current org if selected
      let boundAgentIds: string[] = [];
      if (state.selectedOrg?.id) {
        const boundAgentsResponse = await api.getOrgAgents(username, state.selectedOrg.id, false);
        if (boundAgentsResponse.success && boundAgentsResponse.data) {
          const boundAgents = (boundAgentsResponse.data as any).agents || [];
          boundAgentIds = boundAgents.map((agent: any) => agent.id);
        }
      }

      // Mark agents with binding status and filter out invalid agents
      const agentsWithStatus = allAgents
        .filter((agent: any) => agent && agent.id && agent.name) // Filter out invalid agents
        .map((agent: any) => ({
          ...agent,
          isBound: boundAgentIds.includes(agent.id)
        }));

      updateState({ availableAgents: agentsWithStatus });
    } catch (error) {
      console.error('Error loading agents:', error);
      message.error(t('pages.org.messages.loadFailed'));
    }
  }, [username, state.selectedOrg?.id, t, updateState]);

  // Select organization
  const selectOrg = useCallback((org: Org | null) => {
    updateState({
      selectedOrg: org,
      orgAgents: []
    });
    if (org) {
      loadOrgAgents(org.id);
    }
  }, [loadOrgAgents, updateState]);

  // Create organization
  const createOrg = useCallback(async (data: OrgFormData) => {
    if (!username) return;

    try {
      const api = get_ipc_api();
      const response = await api.createOrg(
        username,
        data.name,
        data.description,
        state.selectedOrg?.id,
        data.org_type
      );

      if (response.success) {
        message.success(t('pages.org.messages.createSuccess'));
        loadOrgs();
        updateState({ modalVisible: false });
      } else {
        message.error(response.error?.message || t('pages.org.messages.createFailed'));
      }
    } catch (error) {
      console.error('Error creating org:', error);
      message.error(t('pages.org.messages.createFailed'));
    }
  }, [username, state.selectedOrg?.id, t, loadOrgs, updateState]);

  // Update organization
  const updateOrg = useCallback(async (id: string, data: Partial<OrgFormData>) => {
    if (!username) return;

    try {
      const api = get_ipc_api();
      const response = await api.updateOrg(
        username,
        id,
        data.name,
        data.description
      );

      if (response.success) {
        message.success(t('pages.org.messages.updateSuccess'));
        loadOrgs();
        updateState({ modalVisible: false });
      } else {
        message.error(response.error?.message || t('pages.org.messages.updateFailed'));
      }
    } catch (error) {
      console.error('Error updating org:', error);
      message.error(t('pages.org.messages.updateFailed'));
    }
  }, [username, t, loadOrgs, updateState]);

  // Delete organization
  const deleteOrg = useCallback(async (id: string) => {
    if (!username) return;

    try {
      const api = get_ipc_api();
      const response = await api.deleteOrg(username, id);

      if (response.success) {
        message.success(t('pages.org.messages.deleteSuccess'));
        loadOrgs();
        if (state.selectedOrg?.id === id) {
          updateState({
            selectedOrg: null,
            orgAgents: []
          });
        }
      } else {
        message.error(response.error?.message || t('pages.org.messages.deleteFailed'));
      }
    } catch (error) {
      console.error('Error deleting org:', error);
      message.error(t('pages.org.messages.deleteFailed'));
    }
  }, [username, state.selectedOrg?.id, t, loadOrgs, updateState]);

  // Bind agents
  const bindAgents = useCallback(async (agentIds: string[]) => {
    if (!username || !state.selectedOrg?.id) return;

    try {
      // Filter out already bound agents
      const unboundAgentIds = agentIds.filter(agentId => {
        const agent = state.availableAgents.find(a => a.id === agentId);
        return agent && !agent.isBound;
      });

      if (unboundAgentIds.length === 0) {
        message.warning(t('pages.org.messages.allAgentsAlreadyBound'));
        return;
      }

      const api = get_ipc_api();
      const promises = unboundAgentIds.map((agentId: string) =>
        api.bindAgentToOrg(username, agentId, state.selectedOrg!.id)
      );

      const results = await Promise.all(promises);
      const failures = results.filter(r => !r.success);

      if (failures.length === 0) {
        message.success(t('pages.org.messages.bindSuccess'));
        loadOrgAgents(state.selectedOrg.id);
        loadAvailableAgents(); // Refresh agent list to update binding status
        updateState({ bindModalVisible: false });
      } else {
        message.error(t('pages.org.messages.bindFailed'));
      }
    } catch (error) {
      console.error('Error binding agents:', error);
      message.error(t('pages.org.messages.bindFailed'));
    }
  }, [username, state.selectedOrg?.id, state.availableAgents, t, loadOrgAgents, loadAvailableAgents, updateState]);

  // Unbind agent
  const unbindAgent = useCallback(async (agentId: string) => {
    if (!username) return;

    try {
      const api = get_ipc_api();
      const response = await api.unbindAgentFromOrg(username, agentId);

      if (response.success) {
        message.success(t('pages.org.messages.unbindSuccess'));
        if (state.selectedOrg) {
          loadOrgAgents(state.selectedOrg.id);
        }
      } else {
        message.error(response.error?.message || t('pages.org.messages.unbindFailed'));
      }
    } catch (error) {
      console.error('Error unbinding agent:', error);
      message.error(t('pages.org.messages.unbindFailed'));
    }
  }, [username, state.selectedOrg, t, loadOrgAgents]);

  // Move organization (drag & drop)
  const moveOrg = useCallback(async (dragNodeId: string, targetNodeId: string, dropToGap: boolean) => {
    if (!username) return;

    try {
      let newParentId: string | null = null;

      if (!dropToGap) {
        newParentId = targetNodeId;
      } else {
        const findOrgById = (orgs: Org[], id: string): Org | null => {
          for (const org of orgs) {
            if (org.id === id) return org;
            if (org.children) {
              const found = findOrgById(org.children, id);
              if (found) return found;
            }
          }
          return null;
        };

        const targetOrg = findOrgById(state.orgs, targetNodeId);
        newParentId = targetOrg?.parent_id || null;
      }

      const ipcApi = get_ipc_api();
      const updateResponse = await ipcApi.updateOrg(
        username,
        dragNodeId,
        undefined, // name
        undefined, // description
        newParentId // parent_id
      );

      if (updateResponse.success) {
        message.success(t('pages.org.messages.moveSuccess'));
        loadOrgs();
      } else {
        message.error(updateResponse.error?.message || t('pages.org.messages.moveFailed'));
      }
    } catch (error) {
      console.error('Error moving org:', error);
      message.error(t('pages.org.messages.moveFailed'));
    }
  }, [username, state.orgs, t, loadOrgs]);

  // Chat with agent
  const chatWithAgent = useCallback((agent: Agent) => {
    try {
      const chatUrl = `/chat?agent=${encodeURIComponent(agent.id)}&name=${encodeURIComponent(agent.name)}`;
      window.location.href = chatUrl;
    } catch (error) {
      console.error('Error navigating to chat:', error);
      message.error(t('pages.org.messages.chatFailed'));
    }
  }, [t]);

  // Initialize data loading when username is available
  useEffect(() => {
    if (username) {
      loadOrgs();
    }
  }, [username, loadOrgs]);

  return {
    state,
    actions: {
      updateState,
      loadOrgs,
      loadOrgAgents,
      loadAvailableAgents,
      selectOrg,
      createOrg,
      updateOrg,
      deleteOrg,
      bindAgents,
      unbindAgent,
      moveOrg,
      chatWithAgent,
    },
  };
};
