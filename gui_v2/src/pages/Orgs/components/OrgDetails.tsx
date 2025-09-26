/**
 * Organization Details Component
 */

import React from 'react';
import { Card, Button, Space, Typography, Tag, Popconfirm } from 'antd';
import { EditOutlined, DeleteOutlined, TeamOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { Organization, Agent } from '../types';
import { ORGANIZATION_STATUSES } from '../constants';
import AgentList from './AgentList';

const { Title, Text } = Typography;

interface OrganizationDetailsProps {
  organization: Organization | null;
  agents: Agent[];
  onEdit: (org: Organization) => void;
  onDelete: (orgId: string) => void;
  onBindAgents: () => void;
  onUnbindAgent: (agentId: string) => void;
  onChatWithAgent: (agent: Agent) => void;
}

const OrganizationDetails: React.FC<OrganizationDetailsProps> = ({
  organization,
  agents,
  onEdit,
  onDelete,
  onBindAgents,
  onUnbindAgent,
  onChatWithAgent,
}) => {
  const { t } = useTranslation();

  if (!organization) {
    return (
      <Card style={{ flex: 1, textAlign: 'center', padding: '60px 20px' }}>
        <Text type="secondary">{t('org.placeholder.selectOrganization')}</Text>
      </Card>
    );
  }

  const getStatusConfig = (status: string) => {
    return ORGANIZATION_STATUSES.find(s => s.value === status) || ORGANIZATION_STATUSES[0];
  };

  const statusConfig = getStatusConfig(organization.status);

  return (
    <Card 
      title={
        <Space>
          <TeamOutlined />
          {t('org.details.title')}
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => onEdit(organization)}
          >
            {t('org.actions.edit')}
          </Button>
          <Popconfirm
            title={t('org.confirm.delete')}
            onConfirm={() => onDelete(organization.id)}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
          >
            <Button
              size="small"
              danger
              icon={<DeleteOutlined />}
            >
              {t('org.actions.delete')}
            </Button>
          </Popconfirm>
        </Space>
      }
      style={{ flex: 1 }}
    >
      <div>
        {/* Organization Info */}
        <div style={{ marginBottom: 24 }}>
          <Title level={4}>{t('org.info.title')}</Title>
          <Space direction="vertical" style={{ width: '100%' }}>
            <div>
              <Text strong>{t('org.form.name')}:</Text> {organization.name}
            </div>
            <div>
              <Text strong>{t('org.form.description')}:</Text> {organization.description || '-'}
            </div>
            <div>
              <Text strong>{t('org.form.type')}:</Text> {organization.organization_type}
            </div>
            <div>
              <Text strong>{t('org.form.level')}:</Text> {organization.level}
            </div>
            <div>
              <Text strong>{t('org.form.status')}:</Text>
              <Tag color={statusConfig.color} style={{ marginLeft: 8 }}>
                {t(statusConfig.key)}
              </Tag>
            </div>
            {/* Show child nodes count for non-leaf nodes */}
            {organization.children && organization.children.length > 0 && (
              <div>
                <Text strong>{t('org.form.childDepartments')}:</Text> {organization.children.length}
              </div>
            )}
            <div>
              <Text strong>{t('org.form.created')}:</Text> {
                organization.created_at
                  ? new Date(organization.created_at).toLocaleDateString()
                  : '-'
              }
            </div>
          </Space>
        </div>

        {/* Agents Section */}
        <div>
          {/* 非叶子节点显示子节点数量和所有叶子节点的Agent */}
          {organization.children && organization.children.length > 0 ? (
            <div>
              <AgentList
                agents={agents}
                onBindAgents={onBindAgents}
                onUnbindAgent={onUnbindAgent}
                onChatWithAgent={onChatWithAgent}
                title={t('org.agents.allLeafAgents', '所有子部门的Agent')}
              />
            </div>
          ) : (
            /* 叶子节点显示绑定的Agent */
            <AgentList
              agents={agents}
              onBindAgents={onBindAgents}
              onUnbindAgent={onUnbindAgent}
              onChatWithAgent={onChatWithAgent}
            />
          )}
        </div>
      </div>
    </Card>
  );
};

export default OrganizationDetails;
