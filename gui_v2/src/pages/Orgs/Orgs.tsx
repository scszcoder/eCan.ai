/**
 * Orgs Management Page
 * 组织管理Page - 完整ImplementationUI需求和国际化
 */

import React from 'react';
import { Row, Col, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { ApartmentOutlined } from '@ant-design/icons';
import { useOrgs } from './hooks/useOrgs';
import OrgTree from './components/OrgTree';
import OrgDetails from './components/OrgDetails';
import OrgModal from './components/OrgModal';
import AgentBindingModal from './components/AgentBindingModal';
import type { Org, OrgAgent, OrgFormData, AgentBindingFormData } from './types';

const { Title } = Typography;

const Orgs: React.FC = () => {
  const { t } = useTranslation();
  const { state, actions } = useOrgs();



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
    const { dragNode, node, dropToGap } = info;
    actions.moveOrg(dragNode.key, node.key, dropToGap);
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
