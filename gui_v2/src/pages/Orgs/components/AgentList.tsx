/**
 * Agent List Component
 */

import React from 'react';
import { Button, List, Avatar, Tooltip, Popconfirm, Empty, Card } from 'antd';
import { PlusOutlined, TeamOutlined, UserOutlined, MessageOutlined, DisconnectOutlined, InfoCircleOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import type { OrgAgent } from '../types';

const StyledAddButton = styled(Button)`
  &.ant-btn {
    background: transparent !important;
    border: none !important;
    color: rgba(203, 213, 225, 0.9) !important;
    box-shadow: none !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;

    &:hover {
      background: rgba(255, 255, 255, 0.1) !important;
      color: rgba(248, 250, 252, 0.95) !important;
    }

    &:active {
      opacity: 0.8 !important;
    }

    .anticon {
      transition: all 0.3s ease !important;
    }
  }
`;

const StyledActionButton = styled(Button, {
  shouldForwardProp: (prop) => prop !== '$iconColor'
})<{ $iconColor?: string }>`
  &.ant-btn {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    padding: 4px 8px !important;

    &:hover {
      background: rgba(255, 255, 255, 0.05) !important;
    }

    &:active {
      opacity: 0.8 !important;
    }

    .anticon {
      color: ${props => props.$iconColor || 'rgba(148, 163, 184, 0.9)'} !important;
      font-size: 16px !important;
      transition: all 0.3s ease !important;
    }

    &:hover .anticon {
      color: ${props => props.$iconColor || 'rgba(148, 163, 184, 1)'} !important;
      transform: scale(1.1);
    }
  }
`;

interface AgentListProps {
  agents: OrgAgent[];
  onBindAgents: () => void;
  onUnbindAgent: (agentId: string) => void;
  onChatWithAgent: (agent: OrgAgent) => void;
  title?: string; // Optional的Custom标题
}

/**
 * Get Agent 的头像 URL
 * Support多种 avatar Data格式：
 * 1. avatar 是对象且Include imageUrl Field
 * 2. avatar 是字符串（直接作为 URL）
 * 3. 没有 avatar（返回 undefined，DisplayDefault图标）
 */
const getAgentAvatarUrl = (agent: OrgAgent): string | undefined => {
  if (!agent.avatar) {
    return undefined;
  }
  
  // If avatar 是对象且有 imageUrl Field
  if (typeof agent.avatar === 'object' && 'imageUrl' in agent.avatar) {
    return (agent.avatar as { imageUrl: string }).imageUrl;
  }
  
  // If avatar 是字符串
  if (typeof agent.avatar === 'string') {
    return agent.avatar;
  }
  
  return undefined;
};

const AgentList: React.FC<AgentListProps> = ({
  agents,
  onBindAgents,
  onUnbindAgent,
  onChatWithAgent,
  title,
}) => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  // 跳转到 Agent Details页（EditPage）
  const handleViewDetails = (agentId: string) => {
    navigate(`/agents/details/${agentId}`);
  };

  return (
    <Card
      title={
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
          <span>
            <TeamOutlined /> {title || t('pages.org.agents.title')} ({agents.length})
          </span>
          <Tooltip
            title={t('pages.org.actions.bind')}
            mouseEnterDelay={0.5}
            mouseLeaveDelay={0.1}
            placement="bottom"
          >
            <StyledAddButton
              size="small"
              icon={<PlusOutlined />}
              onClick={onBindAgents}
              shape="circle"
            />
          </Tooltip>
        </div>
      }
      size="small"
    >
      {agents.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t('pages.org.placeholder.noAgents')}
        />
      ) : (
        <List
          dataSource={agents}
          renderItem={(agent) => (
            <List.Item
              actions={[
                <Tooltip title={t('pages.org.tooltip.chat')} key="chat">
                  <StyledActionButton
                    size="small"
                    $iconColor="rgba(16, 185, 129, 0.9)"
                    icon={<MessageOutlined />}
                    onClick={() => onChatWithAgent(agent)}
                  />
                </Tooltip>,
                <Tooltip title={t('pages.org.tooltip.details')} key="details">
                  <StyledActionButton
                    size="small"
                    $iconColor="rgba(96, 165, 250, 0.9)"
                    icon={<InfoCircleOutlined />}
                    onClick={() => handleViewDetails(agent.id)}
                  />
                </Tooltip>,
                <Tooltip title={t('pages.org.tooltip.unbind')} key="unbind">
                  <Popconfirm
                    title={t('pages.org.confirm.unbind')}
                    onConfirm={() => onUnbindAgent(agent.id)}
                    okText={t('common.confirm')}
                    cancelText={t('common.cancel')}
                  >
                    <StyledActionButton
                      size="small"
                      $iconColor="rgba(239, 68, 68, 0.9)"
                      icon={<DisconnectOutlined />}
                    />
                  </Popconfirm>
                </Tooltip>
              ]}
            >
              <List.Item.Meta
                avatar={
                  <Avatar
                    src={getAgentAvatarUrl(agent)}
                    icon={<UserOutlined />}
                  />
                }
                title={agent.name}
                description={
                  agent.description ? (
                    <div
                      style={{
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        maxWidth: '100%'
                      }}
                      title={agent.description}
                    >
                      {agent.description}
                    </div>
                  ) : undefined
                }
              />
            </List.Item>
          )}
        />
      )}
    </Card>
  );
};

export default AgentList;
