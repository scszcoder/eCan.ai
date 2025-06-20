import React, { useState, useCallback, useEffect } from 'react';
import { List, Tag, Typography, Space, Button, Avatar, Statistic, Row, Col, Card, Badge, message } from 'antd';
import {
    TeamOutlined,
    CheckCircleOutlined,
    ClockCircleOutlined,
    StarOutlined,
    ThunderboltOutlined,
    UserOutlined,
    EditOutlined,
    HistoryOutlined,
    PlusOutlined,
    ReloadOutlined,
    MessageOutlined
} from '@ant-design/icons';
import styled from '@emotion/styled';
import DetailLayout from '../../components/Layout/DetailLayout';
import { useDetailView } from '../../hooks/useDetailView';
import { useTranslation } from 'react-i18next';
import ActionButtons from '../../components/Common/ActionButtons';
import {get_ipc_api} from '../../services/ipc_api';
import { useNavigate } from 'react-router-dom';
import { useUserStore } from '../../stores/userStore';

const { Text, Title } = Typography;
// const username = useUserStore((state) => state.username);
const AgentItem = styled.div`
    position: relative;
    padding: 12px;
    border-bottom: 1px solid var(--border-color);
    &:last-child {
        border-bottom: none;
    }
    cursor: pointer;
    transition: all 0.3s ease;
    background-color: var(--bg-secondary);
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
    .ant-progress-text {
        color: var(--text-primary);
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

interface Agent {
    id: number;
    name: string;
    role: string;
    status: 'active' | 'busy' | 'offline';
    skills: string[];
    tasksCompleted: number;
    efficiency: number;
    lastActive: string;
    avatar?: string;
    currentTask?: string;
}

// 创建事件总线
const agentsEventBus = {
    listeners: new Set<(data: Agent[]) => void>(),
    subscribe(listener: (data: Agent[]) => void) {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    },
    emit(data: Agent[]) {
        this.listeners.forEach(listener => listener(data));
    }
};

// 导出更新数据的函数
export const updateAgentsGUI = (data: Agent[]) => {
    agentsEventBus.emit(data);
};


const getStatusColor = (status: Agent['status']): string => {
    switch (status) {
        case 'active':
            return 'success';
        case 'busy':
            return 'processing';
        case 'offline':
            return 'default';
        default:
            return 'default';
    }
};

const getAgents = () => {
    const ipc_api = get_ipc_api();
    const response = ipc_api.getAgents([]);
    console.log("ipc response:", response);
    return response['result'];
};

const initialAgents: Agent[] = [];

const Agents: React.FC = () => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const [loading, setLoading] = useState(false);
    const {
        selectedItem: selectedAgent,
        items: agents,
        selectItem,
        updateItem,
        updateItems,
    } = useDetailView<Agent>(initialAgents);

    const translateAgent = (agent: Agent): Agent => {
        if (agent.name.includes('协调员') || agent.name.includes('分析师') || agent.name.includes('专员')) {
            return agent;
        }

        return {
            ...agent,
            name: t(`pages.agents.roles.${agent.role.replace(/\s+/g, '')}`),
            role: t(`pages.agents.roles.${agent.role.replace(/\s+/g, '')}`),
            skills: agent.skills.map(skill => {
                if (skill.includes('管理') || skill.includes('通信') || skill.includes('解决')) {
                    return skill;
                }
                return t(`pages.agents.skills.${skill.replace(/\s+/g, '')}`);
            }),
            currentTask: agent.currentTask ?
                (agent.currentTask.includes('规划') || agent.currentTask.includes('处理') ?
                    agent.currentTask :
                    t(`pages.agents.tasks.${agent.currentTask.replace(/\s+/g, '')}`))
                : undefined,
            lastActive: agent.lastActive === '2 minutes ago'
                ? t('pages.agents.time.minutesAgo', { minutes: 2 })
                : agent.lastActive === '5 minutes ago'
                ? t('pages.agents.time.minutesAgo', { minutes: 5 })
                : agent.lastActive === '1 hour ago'
                ? t('pages.agents.time.hoursAgo', { hours: 1 })
                : agent.lastActive
        };
    };

    const translatedAgents = agents.map(translateAgent);

    // Function to handle chat button click
    const handleChatWithAgent = useCallback((agent: Agent, e: React.MouseEvent) => {
        e.stopPropagation(); // Prevent triggering the agent selection

        // Create a chat object for this agent
        const chatWithAgent = {
            id: agent.id, // Using agent ID as chat ID for consistency
            name: agent.name,
            type: 'bot' as const,
            status: agent.status === 'offline' ? 'offline' : 'online',
            lastMessage: t('pages.chat.startConversation'),
            lastMessageTime: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            lastSessionTime: new Date().toLocaleDateString(),
            unreadCount: 0
        };

        // Store the chat in localStorage or context/state management
        const existingChats = JSON.parse(localStorage.getItem('chats') || '[]');
        const chatExists = existingChats.some((chat: any) => chat.id === chatWithAgent.id);

        if (!chatExists) {
            existingChats.push(chatWithAgent);
            localStorage.setItem('chats', JSON.stringify(existingChats));
        }

        // Navigate to the chat page with the agent's ID
        navigate(`/chat?agentId=${agent.id}`);
    }, [navigate, t]);

    const renderListContent = () => (
        <List
            dataSource={translatedAgents}
            renderItem={agent => (
                <AgentItem onClick={() => selectItem(agent)}>
                    <Button
                        className="chat-button"
                        type="text"
                        icon={<MessageOutlined />}
                        onClick={(e) => handleChatWithAgent(agent, e)}
                        title={t('pages.agents.chatWithAgent', { name: agent.name })}
                    />
                    <Space direction="vertical" style={{ width: '100%' }}>
                        <Space>
                            <Badge status={getStatusColor(agent.status) as any} />
                            <Avatar icon={<UserOutlined />} />
                            <Text strong>{agent.name}</Text>
                        </Space>
                        <Space>
                            <Tag color="blue">{agent.role}</Tag>
                            {agent.currentTask && (
                                <Tag color="processing">{t('pages.agents.currentTask')}: {agent.currentTask}</Tag>
                            )}
                        </Space>
                        <Space wrap>
                            {agent.skills.slice(0, 2).map(skill => (
                                <Tag key={skill} color="green">{skill}</Tag>
                            ))}
                            {agent.skills.length > 2 && (
                                <Tag color="green">+{agent.skills.length - 2}</Tag>
                            )}
                        </Space>
                    </Space>
                </AgentItem>
            )}
        />
    );

    const renderDetailsContent = () => {
        if (!selectedAgent) {
            return <Text type="secondary">{t('pages.agents.selectAgent')}</Text>;
        }

        const translatedAgent = translateAgent(selectedAgent);

        return (
            <Space direction="vertical" style={{ width: '100%' }}>
                <Space>
                    <Avatar size={64} icon={<UserOutlined />} />
                    <div>
                        <Title level={4} style={{ margin: 0 }}>{translatedAgent.name}</Title>
                        <Text type="secondary">{translatedAgent.role}</Text>
                    </div>
                </Space>
                <Space>
                    <Tag color={getStatusColor(translatedAgent.status)}>
                        <CheckCircleOutlined /> {t('pages.agents.status')}: {t(`pages.agents.status.${translatedAgent.status}`)}
                    </Tag>
                    <Tag>
                        <ClockCircleOutlined /> {t('pages.agents.lastActive')}: {translatedAgent.lastActive}
                    </Tag>
                </Space>
                <Title level={5}>{t('pages.agents.skills')}</Title>
                <Space wrap>
                    {translatedAgent.skills.map(skill => (
                        <Tag key={skill} color="green">
                            <ThunderboltOutlined /> {skill}
                        </Tag>
                    ))}
                </Space>
                <Row gutter={16}>
                    <Col span={12}>
                        <Card>
                            <Statistic
                                title={t('pages.agents.tasksCompleted')}
                                value={translatedAgent.tasksCompleted}
                                prefix={<StarOutlined />}
                            />
                        </Card>
                    </Col>
                    <Col span={12}>
                        <Card>
                            <Statistic
                                title={t('pages.agents.efficiency')}
                                value={translatedAgent.efficiency}
                                suffix="%"
                                prefix={<ThunderboltOutlined />}
                            />
                        </Card>
                    </Col>
                </Row>
                {translatedAgent.currentTask && (
                    <Card>
                        <Space direction="vertical" style={{ width: '100%' }}>
                            <Text strong>{t('pages.agents.currentTask')}</Text>
                            <Text>{translatedAgent.currentTask}</Text>
                            <Button 
                                type="primary"
                                onClick={() => handleTaskComplete(translatedAgent.id)}
                            >
                                {t('pages.agents.markComplete')}
                            </Button>
                        </Space>
                    </Card>
                )}
                <Space>
                    <Button 
                        type="primary" 
                        icon={<PlusOutlined />}
                        onClick={() => handleStatusChange(translatedAgent.id, 'active')}
                        disabled={translatedAgent.status === 'active'}
                    >
                        {t('pages.agents.activate')}
                    </Button>
                    <Button 
                        icon={<EditOutlined />}
                        onClick={() => handleStatusChange(translatedAgent.id, 'busy')}
                        disabled={translatedAgent.status === 'busy'}
                    >
                        {t('pages.agents.setBusy')}
                    </Button>
                    <Button 
                        icon={<HistoryOutlined />}
                        onClick={() => handleStatusChange(translatedAgent.id, 'offline')}
                        disabled={translatedAgent.status === 'offline'}
                    >
                        {t('pages.agents.setOffline')}
                    </Button>
                </Space>
                <ActionButtons
                    onAdd={async () => await add1agent()}
                    onEdit={async () => await save1agent([selectedAgent])}
                    onDelete={async () => await delete1agent()}
                    onRefresh={async () => await get1agent()}
                    onExport={() => {}}
                    onImport={() => {}}
                    onSettings={() => {}}
                    addText={t('pages.agents.addAgent')}
                    editText={t('pages.agents.editAgent')}
                    deleteText={t('pages.agents.deleteAgent')}
                    refreshText={t('pages.agents.refreshAgents')}
                    exportText={t('pages.agents.exportAgents')}
                    importText={t('pages.agents.importAgents')}
                    settingsText={t('pages.agents.agentSettings')}
                />
            </Space>
        );
    };

    useEffect(() => {
        const unsubscribe = agentsEventBus.subscribe((newData) => {
            updateItems(newData);
        });
        return () => {
            unsubscribe();
        };
    }, []);

    // Function to handle refresh button click
    const handleRefresh = useCallback(async () => {
        try {
            const ipc_api = get_ipc_api();
            const response = await ipc_api.getAgents([]);
            console.log('Agents refreshed:', response);
            if (response && response.success && response.data) {
                updateItems(response.data);
            }
        } catch (error) {
            console.error('Error refreshing agents:', error);
        }
    }, [updateItems]);

    // Add refresh button to the list title
    const listTitle = (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span>{t('pages.agents.title')}</span>
            <Button 
                type="text" 
                icon={<ReloadOutlined style={{ color: 'white' }} />} 
                onClick={handleRefresh}
                title={t('pages.agents.refresh')}
            />
        </div>
    );

    return (
        <DetailLayout
            listTitle={listTitle}
            detailsTitle={t('pages.agents.details')}
            listContent={renderListContent()}
            detailsContent={renderDetailsContent()}
        />
    );
};

export default Agents;