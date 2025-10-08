/**
 * Agent List Component
 */

import React from 'react';
import { Button, Typography, List, Avatar, Tooltip, Popconfirm, Empty, Card } from 'antd';
import { PlusOutlined, TeamOutlined, UserOutlined, MessageOutlined, DisconnectOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import type { Agent } from '../types';

const { Title } = Typography;

interface AgentListProps {
  agents: Agent[];
  onBindAgents: () => void;
  onUnbindAgent: (agentId: string) => void;
  onChatWithAgent: (agent: Agent) => void;
  title?: string; // 可选的自定义标题
}

const AgentList: React.FC<AgentListProps> = ({
  agents,
  onBindAgents,
  onUnbindAgent,
  onChatWithAgent,
  title,
}) => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  // 跳转到 Agent 详情页（编辑页面）
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
            <Button
              type="primary"
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
                  <Button
                    type="text"
                    size="small"
                    icon={<MessageOutlined />}
                    onClick={() => onChatWithAgent(agent)}
                  />
                </Tooltip>,
                <Tooltip title={t('pages.org.tooltip.details')} key="details">
                  <Button
                    type="text"
                    size="small"
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
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DisconnectOutlined />}
                    />
                  </Popconfirm>
                </Tooltip>
              ]}
            >
              <List.Item.Meta
                avatar={
                  <Avatar
                    src={agent.avatar}
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
