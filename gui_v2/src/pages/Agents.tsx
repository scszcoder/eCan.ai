import React, { useState, useCallback, useEffect } from 'react';
import { List, Tag, Typography, Space, Button, Avatar, Statistic, Row, Col, Card, Badge } from 'antd';
import { 
    TeamOutlined, 
    CheckCircleOutlined,
    ClockCircleOutlined,
    StarOutlined,
    ThunderboltOutlined,
    UserOutlined,
    EditOutlined,
    HistoryOutlined,
    PlusOutlined
} from '@ant-design/icons';
import styled from '@emotion/styled';
import DetailLayout from '../components/Layout/DetailLayout';
import { useDetailView } from '../hooks/useDetailView';
import { useTranslation } from 'react-i18next';
import ActionButtons from '../components/Common/ActionButtons';
import {get_ipc_api} from '../services/ipc_api';

const { Text, Title } = Typography;

const AgentItem = styled.div`
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
    listeners: new Set<(data: DashboardStats) => void>(),
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

const initialAgents: Agent[] = [
    {
        id: 1,
        name: 'Task Coordinator',
        role: 'Task Coordinator',
        status: 'active',
        skills: ['Task Management', 'Communication', 'Problem Solving'],
        tasksCompleted: 156,
        efficiency: 95,
        lastActive: '2 minutes ago',
        currentTask: 'Project Planning',
    },
    {
        id: 2,
        name: 'Data Analyst',
        role: 'Data Analyst',
        status: 'busy',
        skills: ['Data Analysis', 'Reporting', 'Visualization'],
        tasksCompleted: 89,
        efficiency: 88,
        lastActive: '5 minutes ago',
        currentTask: 'Data Processing',
    },
    {
        id: 3,
        name: 'Support Specialist',
        role: 'Support Specialist',
        status: 'offline',
        skills: ['Customer Support', 'Troubleshooting', 'Documentation'],
        tasksCompleted: 234,
        efficiency: 92,
        lastActive: '1 hour ago',
    },
];

const Agents: React.FC = () => {
    const { t } = useTranslation();
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
    {async () => await add1agent()}

    const save1agent = async (targetAgents) => {
        console.log("adding 1 agent...");
        const ipc_api = get_ipc_api();
        ipc_api.selfTest();

        // If T should match the shape of value, infer it
        await ipc_api.saveAgents(targetAgents);
    };


    const handleStatusChange = (id: number, newStatus: Agent['status']) => {
        updateItem(id, {
            status: newStatus,
            lastActive: t('pages.agents.time.justNow'),
        });
    };


    const handleTaskComplete = (id: number) => {
        const agent = agents.find(a => a.id === id);
        if (agent) {
            updateItem(id, {
                tasksCompleted: agent.tasksCompleted + 1,
                efficiency: Math.min(agent.efficiency + 1, 100),
                status: 'active',
                currentTask: undefined,
                lastActive: t('pages.agents.time.justNow'),
            });
        }
    };

    const renderListContent = () => (
        <List
            dataSource={translatedAgents}
            renderItem={agent => (
                <AgentItem onClick={() => selectItem(agent)}>
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

    return (
        <DetailLayout
            listTitle={t('pages.agents.title')}
            detailsTitle={t('pages.agents.details')}
            listContent={renderListContent()}
            detailsContent={renderDetailsContent()}
        />
    );
};

export default Agents; 