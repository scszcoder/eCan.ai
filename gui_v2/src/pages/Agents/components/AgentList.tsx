import React, { useCallback } from 'react';
import { List, Tag, Typography, Space, Button, Avatar } from 'antd';
import {
    UserOutlined,
    MessageOutlined
} from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Agent } from '../types';

const { Text } = Typography;

const AgentItem = styled.div<{ $isActive: boolean }>`
    position: relative;
    padding: 12px;
    border-bottom: 1px solid var(--border-color);
    &:last-child {
        border-bottom: none;
    }
    cursor: pointer;
    transition: all 0.3s ease;
    background-color: ${(props) => (props.$isActive ? 'var(--bg-tertiary)' : 'var(--bg-secondary)')};
    border-radius: 8px;
    margin: 4px 0;
    &:hover {
        background-color: var(--bg-tertiary);
        transform: translateX(4px);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        .chat-button {
            opacity: 1;
        }
    }
    .ant-typography {
        color: var(--text-primary);
    }
    .ant-tag {
        background-color: var(--bg-primary);
        border-color: var(--border-color);
    }
    .chat-button {
        position: absolute;
        right: 8px;
        top: 8px;
        opacity: 0;
        transition: opacity 0.3s ease;
        z-index: 1;
        &:hover {
            color: var(--primary-color);
        }
    }
`;

interface AgentListProps {
    agents: Agent[];
    onSelectAgent: (agent: Agent) => void;
    isSelected: (agent: Agent) => boolean;
}

export const AgentList: React.FC<AgentListProps> = ({ agents = [], onSelectAgent, isSelected }) => {
    const { t } = useTranslation();
    const navigate = useNavigate();

    const handleChatWithAgent = useCallback((agent: Agent, e: React.MouseEvent) => {
        e.stopPropagation();
        const chatWithAgent = {
            id: agent.card.id,
            name: agent.card.name,
            type: 'bot' as const,
            status: 'online',
            lastMessage: t('pages.chat.startConversation'),
            lastMessageTime: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            unreadCount: 0
        };

        const existingChats = JSON.parse(localStorage.getItem('chats') || '[]');
        const chatExists = existingChats.some((chat: any) => chat.id === chatWithAgent.id);

        if (!chatExists) {
            existingChats.push(chatWithAgent);
            localStorage.setItem('chats', JSON.stringify(existingChats));
        }

        navigate(`/chat?agentId=${agent.card.id}`);
    }, [navigate, t]);

    return (
        <List
            dataSource={agents}
            renderItem={agent => (
                <List.Item style={{ padding: 0, border: 'none' }}>
                    <AgentItem 
                        onClick={() => onSelectAgent(agent)}
                        $isActive={isSelected(agent)}
                    >
                        <Button
                            className="chat-button"
                            type="text"
                            icon={<MessageOutlined />}
                            onClick={(e) => handleChatWithAgent(agent, e)}
                            title={t('pages.agents.chatWithAgent', { name: agent.card.name })}
                        />
                        <Space direction="vertical" style={{ width: '100%' }}>
                            <Space align="center">
                                <Avatar size="large" src={(agent.card as any).avatar} />
                                <Text strong>{agent.card.name}</Text>
                            </Space>
                            <Space>
                                <Tag color="blue">{agent.card.description}</Tag>
                            </Space>
                        </Space>
                    </AgentItem>
                </List.Item>
            )}
        />
    );
}; 