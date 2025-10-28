/**
 * Orgs Management Hook - Clean Architecture v2
 * 完全重新设计的Concise架构，避免AllStatus管理问题
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { App } from 'antd';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { get_ipc_api } from '../../../services/ipc_api';
import { userStorageManager } from '../../../services/storage/UserStorageManager';
import type { Org, OrgFormData } from '../types';

// 极简StatusInterface - 只Include必要Status
interface OrgState {
  orgs: Org[];
  selectedOrg: Org | null;
  orgAgents: any[];
  availableAgents: any[];
  loading: boolean;
}

// UI Status单独管理
interface UIState {
  modalVisible: boolean;
  bindModalVisible: boolean;
  editingOrg: Org | null;
}

export const useOrgs = () => {
  const { t } = useTranslation();
  const { message, modal } = App.useApp();
  const navigate = useNavigate();
  const username = userStorageManager.getUsername();
  
  // DataStatus - Stable的Reference
  const [dataState, setDataState] = useState<OrgState>({
    orgs: [],
    selectedOrg: null,
    orgAgents: [],
    availableAgents: [],
    loading: false,
  });

  // UI Status - 独立管理
  const [uiState, setUIState] = useState<UIState>({
    modalVisible: false,
    bindModalVisible: false,
    editingOrg: null,
  });

  // 使用 ref 避免Dependency问题
  const dataStateRef = useRef(dataState);
  dataStateRef.current = dataState;

  // Stable的UpdateFunction - 无Dependency
  const updateDataState = useCallback((updates: Partial<OrgState>) => {
    setDataState(prev => ({ ...prev, ...updates }));
  }, []);

  const updateUIState = useCallback((updates: Partial<UIState>) => {
    setUIState(prev => ({ ...prev, ...updates }));
  }, []);

  // API Function - 使用 ref 避免Dependency
  const loadOrgs = useCallback(async () => {
    if (!username) return;

    updateDataState({ loading: true });
    try {
      const api = get_ipc_api();
      // 使用 getAllOrgAgents 获取包含代理信息的完整树结构
      const response = await api.getAllOrgAgents(username);

      if (response.success && response.data) {
        const data = response.data as any;
        
        // 直接将后端的树形结构转换为前端需要的格式，并计算包含子节点的总代理数
        const convertTreeNode = (node: any): any => {
          if (!node || !node.id || !node.name) return null;
          
          const org: any = {
            id: node.id,
            name: node.name,
            description: node.description,
            parent_id: node.parent_id,
            org_type: node.org_type,
            level: node.level,
            sort_order: node.sort_order,
            status: node.status,
            created_at: node.created_at,
            updated_at: node.updated_at,
            children: []
          };
          
          // 递归转换子组织
          if (node.children && node.children.length > 0) {
            org.children = node.children
              .map((child: any) => convertTreeNode(child))
              .filter((child: any) => child !== null);
          }
          
          // 计算总代理数：当前节点的直属代理 + 所有子节点的代理总数
          const directAgentCount = (node.agents || []).length;
          const childrenAgentCount = org.children.reduce((sum: number, child: any) => {
            return sum + (child.agent_count || 0);
          }, 0);
          org.agent_count = directAgentCount + childrenAgentCount;
          
          return org;
        };
        
        const rootNode = convertTreeNode(data.orgs);
        // 返回包含根节点的数组，这样根节点也会显示在树中
        const orgs = rootNode ? [rootNode] : [];

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
      
      // 使用 getAllOrgAgents 获取完整的组织和代理树结构
      const response = await api.getAllOrgAgents(username);
      
      if (response.success && response.data) {
        const data = response.data as any;
        
        // 从树形数据中找到对应组织的代理
        const findOrgAgents = (node: any, targetOrgId: string): any[] => {
          if (!node) return [];
          
          // 如果找到目标组织（包括根节点）
          if (node.id === targetOrgId) {
            return node.agents || [];
          }
          
          // 递归查找子组织
          if (node.children && node.children.length > 0) {
            for (const child of node.children) {
              const agents = findOrgAgents(child, targetOrgId);
              if (agents.length > 0) {
                return agents;
              }
            }
          }
          
          return [];
        };
        
        const agents = findOrgAgents(data.orgs, orgId);
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

      if (!allAgentsResponse.success || !allAgentsResponse.data) {
        message.error(t('pages.org.messages.loadFailed'));
        return;
      }

      const allAgents = (allAgentsResponse.data as any).agents || [];

      // GetWhen前组织已绑定的 Agent IDs（Used for区分When前组织绑定 vs 其他组织绑定）
      let currentOrgAgentIds: string[] = [];
      if (selectedOrgId) {
        const boundAgentsResponse = await api.getOrgAgents(username, selectedOrgId, false);
        if (boundAgentsResponse.success && boundAgentsResponse.data) {
          const boundAgents = (boundAgentsResponse.data as any).agents || (boundAgentsResponse.data as any) || [];
          currentOrgAgentIds = boundAgents.map((agent: any) => agent.id || agent.card?.id).filter(Boolean);
        }
      }

      const agentsWithStatus = allAgents
        .filter((agent: any) => agent && agent.id && agent.name)
        .map((agent: any) => {
          const agentId = agent.id || agent.card?.id;
          // Agent 已绑定的条件：
          // 1. 绑定到When前组织：agent.org_id === selectedOrgId
          // 2. 绑定到其他组织：agent.org_id 存在且不为空
          const isBoundToCurrentOrg = currentOrgAgentIds.includes(agentId);
          const isBoundToOtherOrg = agent.org_id && agent.org_id !== selectedOrgId;
          const isBound = isBoundToCurrentOrg || isBoundToOtherOrg;
          
          return {
            ...agent,
            isBound,
            isBoundToCurrentOrg,
            boundOrgId: agent.org_id
          };
        });

      updateDataState({ availableAgents: agentsWithStatus });
    } catch (error) {
      console.error('Error loading agents:', error);
      message.error(t('pages.org.messages.loadFailed'));
    }
  }, [username, t, updateDataState]);

  // 业务OperationFunction - 使用新架构
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

  // 简化的其他业务Function
  const updateOrg = useCallback(async (id: string, data: Partial<OrgFormData>) => {
    if (!username) return;
    try {
      const api = get_ipc_api();
      const response = await api.updateOrg(username, id, data.name, data.description);
      if (response.success) {
        message.success(t('pages.org.messages.updateSuccess'));
        // 重新Load组织树
        await loadOrgs();
        // IfWhen前选中的组织是被Edit的组织，NeedUpdate选中组织的Information
        const currentSelectedOrg = dataStateRef.current.selectedOrg;
        if (currentSelectedOrg && currentSelectedOrg.id === id) {
          // 从Update后的组织树中找到对应的组织
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
          // 等待 loadOrgs Completed后再查找
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

  const deleteOrg = useCallback(async (id: string, force: boolean = false) => {
    if (!username) return;
    
    // Ifnot强制Delete，先DisplayConfirmDialog
    if (!force) {
      modal.confirm({
        title: t('pages.org.confirm.delete', 'Delete Organization'),
        content: t('pages.org.confirm.deleteMessage', 'Are you sure you want to delete this organization?'),
        okText: t('common.delete', 'Delete'),
        okType: 'danger',
        cancelText: t('common.cancel', 'Cancel'),
        centered: true,
        onOk: async () => {
          // Execute实际Delete
          await performDelete(id, false);
        },
      });
      return;
    }
    
    // 强制Delete直接Execute
    await performDelete(id, true);
    
    async function performDelete(orgId: string, forceDelete: boolean) {
      if (!username) return;
      try {
        const api = get_ipc_api();
        const response = await api.deleteOrg(username, orgId, forceDelete);
        if (response.success) {
          message.success(t('pages.org.messages.deleteSuccess'));
          loadOrgs();
          if (dataStateRef.current.selectedOrg?.id === orgId) {
            updateDataState({ selectedOrg: null, orgAgents: [] });
          }
        } else {
          const errorMsg = response.error?.message || '';
          // Check是否是因为有agents导致DeleteFailed
          if (errorMsg.includes('agents') && errorMsg.includes('force')) {
            // 询问User是否强制Delete
            modal.confirm({
              title: t('pages.org.messages.deleteConfirmTitle', 'Force Delete Organization'),
              content: t('pages.org.messages.deleteConfirmWithAgents', 'This organization contains agents. Do you want to force delete it? All agents will be moved to the parent organization or become orphaned.'),
              okText: t('common.delete', 'Delete'),
              okType: 'danger',
              cancelText: t('common.cancel', 'Cancel'),
              centered: true,
              onOk: async () => {
                // 强制Delete
                await deleteOrg(orgId, true);
              },
            });
          } else {
            message.error(errorMsg || t('pages.org.messages.deleteFailed'));
          }
        }
      } catch (error) {
        console.error('Error deleting org:', error);
        message.error(t('pages.org.messages.deleteFailed'));
      }
    }
  }, [username, t, loadOrgs, updateDataState, modal]);

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
      // 应用内路由跳转到 /chat Page（聊天框），并传递 agentId Parameter
      navigate(`/chat?agentId=${encodeURIComponent(agent.id)}`);
    } catch (error) {
      console.error('Error navigating to chat:', error);
      message.error(t('pages.org.messages.chatFailed'));
    }
  }, [navigate, message, t]);

  // InitializeDataLoad
  useEffect(() => {
    if (username) {
      loadOrgs();
    }
  }, [username, loadOrgs]);

  // 合并Status返回
  const combinedState = {
    ...dataState,
    ...uiState,
  };

  return {
    state: combinedState,
    actions: {
      updateState: updateUIState, // Compatible现有Component
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
