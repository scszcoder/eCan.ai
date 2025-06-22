import React from 'react';
import { Tag, Typography, Space, Avatar, Descriptions } from 'antd';
import {
    UserOutlined,
    ApiOutlined,
    CloudOutlined,
    CodeOutlined,
    LinkOutlined,
    CheckCircleOutlined
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { Agent } from '../types';

const { Text, Title } = Typography;

interface AgentDetailProps {
    agent: Agent | null;
}

export const AgentDetail: React.FC<AgentDetailProps> = ({ agent }) => {
    const { t } = useTranslation();

    if (!agent) {
        return <Text type="secondary">{t('pages.agents.selectAgent')}</Text>;
    }

    return (
        <Space direction="vertical" style={{ width: '100%' }} size="large">
            <Space>
                <Avatar size={64} icon={<UserOutlined />} />
                <div>
                    <Title level={4} style={{ margin: 0 }}>{agent.card.name}</Title>
                    <Text type="secondary">{agent.card.description}</Text>
                </div>
            </Space>

            <Descriptions bordered column={1} size="small">
                <Descriptions.Item label="ID">{agent.card.id}</Descriptions.Item>
                <Descriptions.Item label="Version">{agent.card.version}</Descriptions.Item>
                <Descriptions.Item label="URL">
                    <a href={agent.card.url} target="_blank" rel="noopener noreferrer">
                        {agent.card.url} <LinkOutlined />
                    </a>
                </Descriptions.Item>
                {agent.card.documentationUrl && (
                    <Descriptions.Item label="Documentation">
                        <a href={agent.card.documentationUrl} target="_blank" rel="noopener noreferrer">
                            {agent.card.documentationUrl} <LinkOutlined />
                        </a>
                    </Descriptions.Item>
                )}
            </Descriptions>

            <Title level={5}>{t('pages.agents.capabilities')}</Title>
            <Space wrap>
                {agent.card.capabilities.streaming && <Tag icon={<ApiOutlined />} color="blue">Streaming</Tag>}
                {agent.card.capabilities.pushNotifications && <Tag icon={<CloudOutlined />} color="green">Push Notifications</Tag>}
                {agent.card.capabilities.stateTransitionHistory && <Tag icon={<CheckCircleOutlined />} color="purple">State History</Tag>}
            </Space>

            <Title level={5}>{t('pages.agents.ioModes')}</Title>
            <Space direction="vertical" style={{ width: '100%' }}>
                <div>
                    <Text strong>{t('pages.agents.defaultInputModes')}: </Text>
                    <Space wrap>
                        {agent.card.defaultInputModes.map(mode => <Tag key={mode} icon={<CodeOutlined />} color="cyan">{mode}</Tag>)}
                    </Space>
                </div>
                <div>
                    <Text strong>{t('pages.agents.defaultOutputModes')}: </Text>
                    <Space wrap>
                        {agent.card.defaultOutputModes.map(mode => <Tag key={mode} icon={<CodeOutlined />} color="geekblue">{mode}</Tag>)}
                    </Space>
                </div>
            </Space>
        </Space>
    );
}; 