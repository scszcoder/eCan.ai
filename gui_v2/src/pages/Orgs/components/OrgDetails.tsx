/**
 * Org Details Component
 */

import React from 'react';
import { Card, Button, Space, Typography, Tag, Popconfirm, Tooltip } from 'antd';
import { EditOutlined, DeleteOutlined, TeamOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { Org, Agent } from '../types';
import { ORG_STATUSES, ORG_TYPES } from '../constants';
import AgentList from './AgentList';

const { Title, Text } = Typography;

interface OrgDetailsProps {
  org: Org | null;
  agents: Agent[];
  onEdit: (org: Org) => void;
  onDelete: (orgId: string) => void;
  onBindAgents: () => void;
  onUnbindAgent: (agentId: string) => void;
  onChatWithAgent: (agent: Agent) => void;
}

const OrgDetails: React.FC<OrgDetailsProps> = ({
  org,
  agents,
  onEdit,
  onDelete,
  onBindAgents,
  onUnbindAgent,
  onChatWithAgent,
}) => {
  const { t } = useTranslation();

  if (!org) {
    return (
      <Card style={{ flex: 1, textAlign: 'center', padding: '60px 20px' }}>
        <Text type="secondary">{t('pages.org.placeholder.selectOrg')}</Text>
      </Card>
    );
  }

  const getStatusConfig = (status: string) => {
    return ORG_STATUSES.find(s => s.value === status) || ORG_STATUSES[0];
  };

  const getTypeConfig = (type: string) => {
    return ORG_TYPES.find(t => t.value === type) || ORG_TYPES[0];
  };

  const statusConfig = getStatusConfig(org.status);
  const typeConfig = getTypeConfig(org.org_type);

  return (
    <Card
      title={
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
          <Space>
            <TeamOutlined />
            {t('pages.org.details.title')}
          </Space>
          <Space>
            <Tooltip title={t('pages.org.actions.edit')}>
              <Button
                size="small"
                icon={<EditOutlined />}
                onClick={() => onEdit(org)}
                shape="circle"
              />
            </Tooltip>
            <Popconfirm
              title={t('pages.org.confirm.delete')}
              onConfirm={() => onDelete(org.id)}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
            >
              <Tooltip title={t('pages.org.actions.delete')}>
                <Button
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  shape="circle"
                />
              </Tooltip>
            </Popconfirm>
          </Space>
        </div>
      }
      style={{ flex: 1 }}
    >
      <div>
        {/* Org Info */}
        <div style={{ marginBottom: 24 }}>
          <Title level={4}>{t('pages.org.info.title')}</Title>
          <Space direction="vertical" style={{ width: '100%' }}>
            <div>
              <Text strong>{t('pages.org.form.name')}:</Text> {org.name}
            </div>
            <div>
              <Text strong>{t('pages.org.form.description')}:</Text> {org.description || '-'}
            </div>
            <div>
              <Text strong>{t('pages.org.form.type')}:</Text> {t(typeConfig.key)}
            </div>
            <div>
              <Text strong>{t('pages.org.form.level')}:</Text> {org.level}
            </div>
            <div>
              <Text strong>{t('pages.org.form.status')}:</Text>
              <Tag color={statusConfig.color} style={{ marginLeft: 8 }}>
                {t(statusConfig.key)}
              </Tag>
            </div>
            {/* Show child nodes count for non-leaf nodes */}
            {org.children && org.children.length > 0 && (
              <div>
                <Text strong>{t('pages.org.form.childDepartments')}:</Text> {org.children.length}
              </div>
            )}
            <div>
              <Text strong>{t('pages.org.form.created')}:</Text> {
                org.created_at
                  ? new Date(org.created_at).toLocaleDateString()
                  : '-'
              }
            </div>
          </Space>
        </div>

        {/* Agents Section */}
        <div>
          {/* 非叶子节点显示子节点数量和所有叶子节点的Agent */}
          {org.children && org.children.length > 0 ? (
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

export default OrgDetails;
