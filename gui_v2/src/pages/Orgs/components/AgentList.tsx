/**
 * Agent List Component
 */

import React from 'react';
import { Button, Typography, List, Avatar, Tooltip, Popconfirm, Empty } from 'antd';
import { PlusOutlined, TeamOutlined, UserOutlined, MessageOutlined, DisconnectOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
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

  return (
    <div>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 16
      }}>
        <Title level={4}>
          <TeamOutlined /> {title || t('pages.org.agents.title')} ({agents.length})
        </Title>
        <Tooltip
          title={t('pages.org.actions.bind')}
          mouseEnterDelay={0.5}
          mouseLeaveDelay={0.1}
          placement="bottom"
        >
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={onBindAgents}
            shape="circle"
          />
        </Tooltip>
      </div>

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
                    icon={<MessageOutlined />}
                    onClick={() => onChatWithAgent(agent)}
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
                    size="large"
                  />
                }
                title={agent.name}
                description={agent.description || '-'}
              />
            </List.Item>
          )}
        />
      )}
    </div>
  );
};

export default AgentList;
