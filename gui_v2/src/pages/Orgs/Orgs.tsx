/**
 * Organizations Management Page
 * 组织管理页面 - 完整实现UI需求和国际化
 */

import React from 'react';
import { Row, Col, Button, Space, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { GlobalOutlined } from '@ant-design/icons';
import { useOrgs } from './hooks/useOrgs';
import OrgTree from './components/OrgTree';
import OrgDetails from './components/OrgDetails';
import OrgModal from './components/OrgModal';
import AgentBindingModal from './components/AgentBindingModal';
import type { Organization, Agent, OrganizationFormData, AgentBindingFormData } from './types';

const { Title } = Typography;

const Orgs: React.FC = () => {
  const { t, i18n } = useTranslation();
  const { state, actions } = useOrgs();

  // 语言切换
  const toggleLanguage = () => {
    const newLang = i18n.language === 'zh-CN' ? 'en-US' : 'zh-CN';
    i18n.changeLanguage(newLang);
  };

  // Tree selection handler
  const handleTreeSelect = (selectedKeys: React.Key[]) => {
    if (selectedKeys.length > 0) {
      const selectedId = selectedKeys[0] as string;
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
      
      const selectedOrg = findOrganizationById(state.organizations, selectedId);
      actions.selectOrganization(selectedOrg);
    } else {
      actions.selectOrganization(null);
    }
  };

  // Tree drag & drop handler
  const handleTreeDrop = (info: any) => {
    const { dragNode, node, dropToGap } = info;
    actions.moveOrganization(dragNode.key, node.key, dropToGap);
  };

  // Modal handlers
  const handleAddOrganization = () => {
    actions.updateState({ 
      modalVisible: true, 
      editingOrganization: null 
    });
  };

  const handleEditOrganization = (org: Organization) => {
    actions.updateState({ 
      modalVisible: true, 
      editingOrganization: org 
    });
  };

  const handleDeleteOrganization = (orgId: string) => {
    actions.deleteOrganization(orgId);
  };

  const handleOrganizationModalOk = async (values: OrganizationFormData) => {
    if (state.editingOrganization) {
      await actions.updateOrganization(state.editingOrganization.id, values);
    } else {
      await actions.createOrganization(values);
    }
  };

  const handleOrganizationModalCancel = () => {
    actions.updateState({ 
      modalVisible: false, 
      editingOrganization: null 
    });
  };

  // Agent binding handlers
  const handleBindAgents = () => {
    actions.updateState({ bindModalVisible: true });
  };

  const handleAgentBindingModalOk = async (values: AgentBindingFormData) => {
    await actions.bindAgents(values.agent_ids);
  };

  const handleAgentBindingModalCancel = () => {
    actions.updateState({ bindModalVisible: false });
  };

  const handleUnbindAgent = (agentId: string) => {
    actions.unbindAgent(agentId);
  };

  const handleChatWithAgent = (agent: Agent) => {
    actions.chatWithAgent(agent);
  };

  return (
    <div style={{ padding: '24px', height: '100vh' }}>
      {/* 页面标题和语言切换 */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '16px'
      }}>
        <Title level={2} style={{ margin: 0 }}>
          {t('org.title', '组织管理')}
        </Title>
        <Space>
          <Button
            icon={<GlobalOutlined />}
            onClick={toggleLanguage}
            type="default"
          >
            {i18n.language === 'zh-CN' ? 'English' : '中文'}
          </Button>
        </Space>
      </div>

      <Row gutter={[16, 16]} style={{ height: 'calc(100% - 60px)' }}>
        {/* Organization Tree */}
        <Col span={8} style={{ height: '100%' }}>
          <OrgTree
            organizations={state.organizations}
            loading={state.loading}
            onSelect={handleTreeSelect}
            onDrop={handleTreeDrop}
            onAdd={handleAddOrganization}
          />
        </Col>

        {/* Organization Details */}
        <Col span={16} style={{ height: '100%' }}>
          <OrgDetails
            organization={state.selectedOrganization}
            agents={state.organizationAgents}
            onEdit={handleEditOrganization}
            onDelete={handleDeleteOrganization}
            onBindAgents={handleBindAgents}
            onUnbindAgent={handleUnbindAgent}
            onChatWithAgent={handleChatWithAgent}
          />
        </Col>
      </Row>

      {/* Organization Form Modal */}
      <OrgModal
        visible={state.modalVisible}
        editingOrganization={state.editingOrganization}
        onOk={handleOrganizationModalOk}
        onCancel={handleOrganizationModalCancel}
      />

      {/* Agent Binding Modal */}
      <AgentBindingModal
        visible={state.bindModalVisible}
        availableAgents={state.availableAgents}
        onOk={handleAgentBindingModalOk}
        onCancel={handleAgentBindingModalCancel}
        onLoadAgents={actions.loadAvailableAgents}
      />
    </div>
  );
};

export default Orgs;
