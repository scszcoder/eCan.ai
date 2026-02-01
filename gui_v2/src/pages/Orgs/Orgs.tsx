/**
 * Orgs Management Page
 * 组织管理Page - 完整ImplementationUI需求和国际化
 */

import React from 'react';
import { Row, Col, Input, Button, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import { useOrgs } from './hooks/useOrgs';
import OrgTree from './components/OrgTree';
import OrgDetails from './components/OrgDetails';
import OrgModal from './components/OrgModal';
import AgentBindingModal from './components/AgentBindingModal';
import type { Org, OrgAgent, OrgFormData, AgentBindingFormData } from './types';

const Orgs: React.FC = () => {
  const { t } = useTranslation();
  const { state, actions } = useOrgs();
  const [companyName, setCompanyName] = React.useState('');

  // 页面加载时从 localStorage 恢复 companyName 并自动加载组织数据
  React.useEffect(() => {
    try {
      const savedCompanyName = localStorage.getItem('org_company_filter');
      if (savedCompanyName && savedCompanyName.trim()) {
        setCompanyName(savedCompanyName);
        // 自动加载组织数据（带过滤）
        actions.loadOrgs(savedCompanyName);
      } else {
        // 没有保存的 companyName，加载所有组织
        actions.loadOrgs('');
      }
    } catch (error) {
      console.error('Error loading saved company filter:', error);
      // 出错时也尝试加载所有组织
      actions.loadOrgs('');
    }
  }, []); // 只在组件挂载时执行一次

  // 同步 hook 中的 companyName 到本地 state
  React.useEffect(() => {
    if (state.companyName && state.companyName !== companyName) {
      setCompanyName(state.companyName);
    }
  }, [state.companyName]);

  // Tree selection handler
  const handleTreeSelect = (selectedKeys: React.Key[]) => {
    if (selectedKeys.length > 0) {
      const selectedId = selectedKeys[0] as string;
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

      const selectedOrg = findOrgById(state.orgs, selectedId);
      actions.selectOrg(selectedOrg);
    } else {
      actions.selectOrg(null);
    }
  };

  // Tree drag & drop handler
  const handleTreeDrop = (info: any) => {
    const { dragNode, node } = info;
    actions.moveOrg(dragNode.key, node.key);
  };

  // Modal handlers
  const handleAddOrg = () => {
    actions.updateState({
      modalVisible: true,
      editingOrg: null
    });
  };

  const handleEditOrg = (org: Org) => {
    actions.updateState({
      modalVisible: true,
      editingOrg: org
    });
  };

  const handleDeleteOrg = (orgId: string) => {
    actions.deleteOrg(orgId);
  };

  const handleOrgModalOk = async (values: OrgFormData) => {
    if (state.editingOrg) {
      await actions.updateOrg(state.editingOrg.id, values);
    } else {
      await actions.createOrg(values);
    }
  };

  const handleOrgModalCancel = () => {
    actions.updateState({
      modalVisible: false,
      editingOrg: null
    });
  };

  // Agent binding handlers
  const handleBindAgents = () => {
    actions.updateState({ bindModalVisible: true });
  };

  const handleAgentBindingModalOk = async (values: AgentBindingFormData) => {
    await actions.bindAgents([values.agent_id]);  // 将单个 agent_id Convert为数组
  };

  const handleAgentBindingModalCancel = () => {
    actions.updateState({ bindModalVisible: false });
  };

  const handleUnbindAgent = (agentId: string) => {
    actions.unbindAgent(agentId);
  };

  const handleChatWithAgent = (agent: OrgAgent) => {
    actions.chatWithAgent(agent);
  };

  return (
    <div style={{ padding: '16px', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Row gutter={[16, 16]} style={{ flex: 1, minHeight: 0 }}>
        {/* Org Tree */}
        <Col span={8} style={{ height: '100%' }}>
          <div style={{ display: 'flex', gap: '8px', marginBottom: 12 }}>
            <Input
              placeholder={t('pages.org.search.companyPlaceholder', 'Company name')}
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              onPressEnter={() => actions.loadOrgs(companyName)}
              allowClear
              style={{ flex: 1 }}
            />
            <Tooltip title={t('pages.org.search.findTooltip', 'Search organizations')}>
              <Button
                type="primary"
                icon={<SearchOutlined />}
                onClick={() => actions.loadOrgs(companyName)}
              />
            </Tooltip>
            <Tooltip title={t('common.refresh', 'Refresh')}>
              <Button
                icon={<ReloadOutlined />}
                loading={state.loading}
                onClick={() => actions.loadOrgs(companyName)}
              />
            </Tooltip>
          </div>
          <OrgTree
            orgs={state.orgs}
            loading={state.loading}
            onSelect={handleTreeSelect}
            onDrop={handleTreeDrop}
            onAdd={handleAddOrg}
          />
        </Col>

        {/* Org Details */}
        <Col span={16} style={{ height: '100%' }}>
          <OrgDetails
            org={state.selectedOrg}
            agents={state.orgAgents}
            onEdit={handleEditOrg}
            onDelete={handleDeleteOrg}
            onBindAgents={handleBindAgents}
            onUnbindAgent={handleUnbindAgent}
            onChatWithAgent={handleChatWithAgent}
          />
        </Col>
      </Row>

      {/* Org Form Modal */}
      <OrgModal
        visible={state.modalVisible}
        editingOrg={state.editingOrg}
        onOk={handleOrgModalOk}
        onCancel={handleOrgModalCancel}
      />

      {/* Agent Binding Modal */}
      <AgentBindingModal
        visible={state.bindModalVisible}
        availableAgents={state.availableAgents}
        selectedOrgId={state.selectedOrg?.id}
        onOk={handleAgentBindingModalOk}
        onCancel={handleAgentBindingModalCancel}
        onLoadAgents={actions.loadAvailableAgents}
      />
    </div>
  );
};

export default Orgs;
