/**
 * Orgs Management Hook - Clean Architecture v2
 * 完全重新设计的简洁架构，避免所有状态管理问题
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { App } from 'antd';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { get_ipc_api } from '../../../services/ipc_api';
import { userStorageManager } from '../../../services/storage/UserStorageManager';
import type { Org, OrgFormData } from '../types';

// 极简状态接口 - 只包含必要状态
interface OrgState {
  orgs: Org[];
  selectedOrg: Org | null;
  orgAgents: any[];
  availableAgents: any[];
  loading: boolean;
}

// UI 状态单独管理
interface UIState {
  modalVisible: boolean;
  bindModalVisible: boolean;
  editingOrg: Org | null;
}

export const useOrgs = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const username = userStorageManager.getUsername();
  
  // 数据状态 - 稳定的引用
  const [dataState, setDataState] = useState<OrgState>({
    orgs: [],
    selectedOrg: null,
    orgAgents: [],
    availableAgents: [],
    loading: false,
  });

  // UI 状态 - 独立管理
  const [uiState, setUIState] = useState<UIState>({
    modalVisible: false,
    bindModalVisible: false,
    editingOrg: null,
  });

  // 使用 ref 避免依赖问题
  const dataStateRef = useRef(dataState);
  dataStateRef.current = dataState;

  // 稳定的更新函数 - 无依赖
  const updateDataState = useCallback((updates: Partial<OrgState>) => {
    setDataState(prev => ({ ...prev, ...updates }));
  }, []);

  const updateUIState = useCallback((updates: Partial<UIState>) => {
    setUIState(prev => ({ ...prev, ...updates }));
  }, []);

  // API 函数 - 使用 ref 避免依赖
  const loadOrgs = useCallback(async () => {
    if (!username) return;

    updateDataState({ loading: true });
    try {
      const api = get_ipc_api();
      const response = await api.getOrgs(username);

      if (response.success && response.data) {
        const orgs = Array.isArray(response.data)
          ? response.data
          : (response.data as any).organizations || [];

        updateDataState({ orgs, loading: false });
      } else {
        message.error(t('pages.org.messages.loadFailed'));
        updateDataState({ loading: false });
      }
    } catch (error) {
      console.error('Error loading orgs:', error);
      message.error(t('pages.org.messages.loadFailed'));
      updateDataState({ loading: false });
    }
  }, [username, t, updateDataState]);

  const loadOrgAgents = useCallback(async (orgId: string) => {
    if (!username) return;

    updateDataState({ loading: true });
    try {
      const api = get_ipc_api();
      // 修改为 false，只加载当前组织的 agents，不包含子组织
      const response = await api.getOrgAgents(username, orgId, false);

      if (response.success && response.data) {
        const agents = (response.data as any).agents || [];
        const validAgents = agents.filter((agent: any) => agent && agent.id && agent.name);
        updateDataState({ orgAgents: validAgents, loading: false });
      } else {
        message.error(t('pages.org.messages.loadFailed'));
        updateDataState({ loading: false });
      }
    } catch (error) {
      console.error('Error loading org agents:', error);
      message.error(t('pages.org.messages.loadFailed'));
      updateDataState({ loading: false });
    }
  }, [username, t, updateDataState]);

  const loadAvailableAgents = useCallback(async (selectedOrgId?: string) => {
    if (!username) return;

    try {
      const api = get_ipc_api();
      const allAgentsResponse = await api.getAgents(username, []);

      console.log('[loadAvailableAgents] allAgentsResponse:', allAgentsResponse);

      if (!allAgentsResponse.success || !allAgentsResponse.data) {
        message.error(t('pages.org.messages.loadFailed'));
        return;
      }

      const allAgents = (allAgentsResponse.data as any).agents || [];
      console.log('[loadAvailableAgents] allAgents count:', allAgents.length);
      console.log('[loadAvailableAgents] allAgents:', allAgents);

      let boundAgentIds: string[] = [];

      if (selectedOrgId) {
        const boundAgentsResponse = await api.getOrgAgents(username, selectedOrgId, false);
        console.log('[loadAvailableAgents] boundAgentsResponse:', boundAgentsResponse);
        if (boundAgentsResponse.success && boundAgentsResponse.data) {
          const boundAgents = (boundAgentsResponse.data as any).agents || [];
          boundAgentIds = boundAgents.map((agent: any) => agent.id);
          console.log('[loadAvailableAgents] boundAgentIds:', boundAgentIds);
        }
      }

      const agentsWithStatus = allAgents
        .filter((agent: any) => agent && agent.id && agent.name)
        .map((agent: any) => ({
          ...agent,
          isBound: boundAgentIds.includes(agent.id)
        }));

      console.log('[loadAvailableAgents] agentsWithStatus count:', agentsWithStatus.length);
      console.log('[loadAvailableAgents] agentsWithStatus:', agentsWithStatus);

      updateDataState({ availableAgents: agentsWithStatus });
    } catch (error) {
      console.error('Error loading agents:', error);
      message.error(t('pages.org.messages.loadFailed'));
    }
  }, [username, t, updateDataState]);

  // 业务操作函数 - 使用新架构
  const selectOrg = useCallback((org: Org | null) => {
    updateDataState({ selectedOrg: org, orgAgents: [] });
    if (org) {
      loadOrgAgents(org.id);
    }
  }, [updateDataState, loadOrgAgents]);

  const createOrg = useCallback(async (data: OrgFormData) => {
    if (!username) return;
    try {
      const api = get_ipc_api();
      const response = await api.createOrg(username, data.name, data.description, dataStateRef.current.selectedOrg?.id, data.org_type);
      if (response.success) {
        message.success(t('pages.org.messages.createSuccess'));
        loadOrgs();
        updateUIState({ modalVisible: false });
      } else {
        message.error(response.error?.message || t('pages.org.messages.createFailed'));
      }
    } catch (error) {
      console.error('Error creating org:', error);
      message.error(t('pages.org.messages.createFailed'));
    }
  }, [username, t, loadOrgs, updateUIState]);

  // 简化的其他业务函数
  const updateOrg = useCallback(async (id: string, data: Partial<OrgFormData>) => {
    if (!username) return;
    try {
      const api = get_ipc_api();
      const response = await api.updateOrg(username, id, data.name, data.description);
      if (response.success) {
        message.success(t('pages.org.messages.updateSuccess'));
        // 重新加载组织树
        await loadOrgs();
        // 如果当前选中的组织是被编辑的组织，需要更新选中组织的信息
        const currentSelectedOrg = dataStateRef.current.selectedOrg;
        if (currentSelectedOrg && currentSelectedOrg.id === id) {
          // 从更新后的组织树中找到对应的组织
          const findOrgById = (orgs: Org[], targetId: string): Org | null => {
            for (const org of orgs) {
              if (org.id === targetId) return org;
              if (org.children) {
                const found = findOrgById(org.children, targetId);
                if (found) return found;
              }
            }
            return null;
          };
          // 等待 loadOrgs 完成后再查找
          setTimeout(() => {
            const updatedOrg = findOrgById(dataStateRef.current.orgs, id);
            if (updatedOrg) {
              updateDataState({ selectedOrg: updatedOrg });
            }
          }, 100);
        }
        updateUIState({ modalVisible: false });
      } else {
        message.error(response.error?.message || t('pages.org.messages.updateFailed'));
      }
    } catch (error) {
      console.error('Error updating org:', error);
      message.error(t('pages.org.messages.updateFailed'));
    }
  }, [username, t, loadOrgs, updateUIState, updateDataState]);

  const deleteOrg = useCallback(async (id: string) => {
    if (!username) return;
    try {
      const api = get_ipc_api();
      const response = await api.deleteOrg(username, id);
      if (response.success) {
        message.success(t('pages.org.messages.deleteSuccess'));
        loadOrgs();
        if (dataStateRef.current.selectedOrg?.id === id) {
          updateDataState({ selectedOrg: null, orgAgents: [] });
        }
      } else {
        message.error(response.error?.message || t('pages.org.messages.deleteFailed'));
      }
    } catch (error) {
      console.error('Error deleting org:', error);
      message.error(t('pages.org.messages.deleteFailed'));
    }
  }, [username, t, loadOrgs, updateDataState]);

  const bindAgents = useCallback(async (agentIds: string[]) => {
    const selectedOrg = dataStateRef.current.selectedOrg;
    if (!username || !selectedOrg?.id) return;
    
    try {
      const api = get_ipc_api();
      const promises = agentIds.map(agentId => api.bindAgentToOrg(username, agentId, selectedOrg.id));
      const results = await Promise.all(promises);
      const failures = results.filter(r => !r.success);
      
      if (failures.length === 0) {
        message.success(t('pages.org.messages.bindSuccess'));
        updateUIState({ bindModalVisible: false });
        loadOrgAgents(selectedOrg.id);
        loadAvailableAgents(selectedOrg.id);
      } else {
        message.error(t('pages.org.messages.bindFailed'));
      }
    } catch (error) {
      console.error('Error binding agents:', error);
      message.error(t('pages.org.messages.bindFailed'));
    }
  }, [username, t, updateUIState, loadOrgAgents, loadAvailableAgents]);

  const unbindAgent = useCallback(async (agentId: string) => {
    if (!username) return;
    try {
      const api = get_ipc_api();
      const response = await api.unbindAgentFromOrg(username, agentId);
      if (response.success) {
        message.success(t('pages.org.messages.unbindSuccess'));
        const selectedOrg = dataStateRef.current.selectedOrg;
        if (selectedOrg) {
          loadOrgAgents(selectedOrg.id);
        }
      } else {
        message.error(response.error?.message || t('pages.org.messages.unbindFailed'));
      }
    } catch (error) {
      console.error('Error unbinding agent:', error);
      message.error(t('pages.org.messages.unbindFailed'));
    }
  }, [username, t, loadOrgAgents]);

  const moveOrg = useCallback(async (dragNodeId: string, targetNodeId: string) => {
    if (!username) return;
    try {
      const api = get_ipc_api();
      const response = await api.updateOrg(username, dragNodeId, undefined, undefined, targetNodeId);
      if (response.success) {
        message.success(t('pages.org.messages.moveSuccess'));
        loadOrgs();
      } else {
        message.error(response.error?.message || t('pages.org.messages.moveFailed'));
      }
    } catch (error) {
      console.error('Error moving org:', error);
      message.error(t('pages.org.messages.moveFailed'));
    }
  }, [username, t, loadOrgs]);

  const chatWithAgent = useCallback((agent: any) => {
    try {
      // 应用内路由跳转到 /chat 页面（聊天框），并传递 agentId 参数
      navigate(`/chat?agentId=${encodeURIComponent(agent.id)}`);
    } catch (error) {
      console.error('Error navigating to chat:', error);
      message.error(t('pages.org.messages.chatFailed'));
    }
  }, [navigate, message, t]);

  // 初始化数据加载
  useEffect(() => {
    if (username) {
      loadOrgs();
    }
  }, [username, loadOrgs]);

  // 合并状态返回
  const combinedState = {
    ...dataState,
    ...uiState,
  };

  return {
    state: combinedState,
    actions: {
      updateState: updateUIState, // 兼容现有组件
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
