/**
 * Org Details Component
 */

import React, { useRef } from 'react';
import { useEffectOnActive } from 'keepalive-for-react';
import { Card, Button, Space, Typography, Tag, Popconfirm, Tooltip } from 'antd';
import { EditOutlined, DeleteOutlined, TeamOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import type { Org, OrgAgent } from '../types';
import { ORG_STATUSES, ORG_TYPES } from '../constants';
import AgentList from './AgentList';
import DetailCard from '../../../components/Common/DetailCard';

const { Text } = Typography;

const StyledIconButton = styled(Button, {
  shouldForwardProp: (prop) => prop !== '$iconColor'
})<{ $iconColor?: string }>`
  &.ant-btn {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;

    &:hover {
      background: rgba(255, 255, 255, 0.1) !important;
    }

    &:active {
      opacity: 0.8 !important;
    }

    .anticon {
      color: ${props => props.$iconColor || 'rgba(96, 165, 250, 0.9)'} !important;
      transition: all 0.3s ease !important;
    }

    &:hover .anticon {
      color: ${props => props.$iconColor ? props.$iconColor : 'rgba(96, 165, 250, 1)'} !important;
    }
  }
`;

interface OrgDetailsProps {
  org: Org | null;
  agents: OrgAgent[];
  onEdit: (org: Org) => void;
  onDelete: (orgId: string) => void;
  onBindAgents: () => void;
  onUnbindAgent: (agentId: string) => void;
  onChatWithAgent: (agent: OrgAgent) => void;
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
  
  // ScrollPositionSave
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const savedScrollPositionRef = useRef<number>(0);
  
  // 使用 useEffectOnActive 在ComponentActive时RestoreScrollPosition
  useEffectOnActive(
    () => {
      const container = scrollContainerRef.current;
      if (container && savedScrollPositionRef.current > 0) {
        requestAnimationFrame(() => {
          container.scrollTop = savedScrollPositionRef.current;
        });
      }
      
      return () => {
        const container = scrollContainerRef.current;
        if (container) {
          savedScrollPositionRef.current = container.scrollTop;
        }
      };
    },
    []
  );

  if (!org) {
    return (
      <Card style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
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

  // 准备 DetailCard 的Data
  const orgInfoItems = [
    {
      label: t('pages.org.form.name'),
      value: org.name,
    },
    {
      label: t('pages.org.form.type'),
      value: t(typeConfig.key),
    },
    {
      label: t('pages.org.form.description'),
      value: org.description || '-',
    },
    {
      label: t('pages.org.form.level'),
      value: org.level,
    },
    {
      label: t('pages.org.form.status'),
      value: (
        <Tag color={statusConfig.color}>
          {t(statusConfig.key)}
        </Tag>
      ),
    },
    ...(org.children && org.children.length > 0 ? [{
      label: t('pages.org.form.childDepartments'),
      value: org.children.length,
    }] : []),
    {
      label: t('pages.org.form.created'),
      value: org.created_at
        ? new Date(org.created_at).toLocaleDateString()
        : '-',
    },
  ];

  return (
    <Card
      title={
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
          <Space>
            <TeamOutlined />
            {t('pages.org.details.title')}
          </Space>
          <Space>
            <Tooltip
              title={t('pages.org.actions.edit')}
              mouseEnterDelay={0.5}
              mouseLeaveDelay={0.1}
              placement="bottom"
            >
              <StyledIconButton
                size="small"
                icon={<EditOutlined />}
                onClick={() => onEdit(org)}
                shape="circle"
              />
            </Tooltip>
            <Tooltip
              title={t('pages.org.actions.delete')}
              mouseEnterDelay={0.5}
              mouseLeaveDelay={0.1}
              placement="bottom"
            >
              <StyledIconButton
                size="small"
                $iconColor="rgba(239, 68, 68, 0.9)"
                icon={<DeleteOutlined />}
                shape="circle"
                onClick={() => onDelete(org.id)}
              />
            </Tooltip>
          </Space>
        </div>
      }
      style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
      styles={{ body: { flex: 1, overflowX: 'hidden', padding: 0 } }}
    >
      <div ref={scrollContainerRef} style={{ height: '100%', overflowY: 'auto', padding: '16px' }}>
      {/* Org Info */}
      <DetailCard
        title={t('pages.org.info.title')}
        columns={2}
        items={orgInfoItems}
      />

      {/* Agents Section */}
      <div style={{ marginTop: 16 }}>
        {/* 非叶子节点Display子节点Count和All叶子节点的Agent */}
        {org.children && org.children.length > 0 ? (
          <AgentList
            agents={agents}
            onBindAgents={onBindAgents}
            onUnbindAgent={onUnbindAgent}
            onChatWithAgent={onChatWithAgent}
            title={t('pages.org.agents.allLeafAgents') || 'All子部门的代理'}
          />
        ) : (
          /* 叶子节点Display绑定的Agent */
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
