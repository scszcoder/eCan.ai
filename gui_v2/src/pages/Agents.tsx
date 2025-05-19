import React from 'react';
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

const { Text, Title } = Typography;

const AgentItem = styled.div`
    padding: 12px;
    border-bottom: 1px solid #f0f0f0;
    &:last-child {
        border-bottom: none;
    }
    cursor: pointer;
    transition: background-color 0.3s;
    &:hover {
        background-color: #f5f5f5;
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
        name: 'Alpha Agent',
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
        name: 'Beta Agent',
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
        name: 'Gamma Agent',
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
    } = useDetailView<Agent>(initialAgents);

    const handleStatusChange = (id: number, newStatus: Agent['status']) => {
        updateItem(id, {
            status: newStatus,
            lastActive: 'Just now',
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
                lastActive: 'Just now',
            });
        }
    };

    const renderListContent = () => (
        <List
            dataSource={agents}
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

        return (
            <Space direction="vertical" style={{ width: '100%' }}>
                <Space>
                    <Avatar size={64} icon={<UserOutlined />} />
                    <div>
                        <Title level={4} style={{ margin: 0 }}>{selectedAgent.name}</Title>
                        <Text type="secondary">{selectedAgent.role}</Text>
                    </div>
                </Space>
                <Space>
                    <Tag color={getStatusColor(selectedAgent.status)}>
                        <CheckCircleOutlined /> {t('pages.agents.status')}: {t(`pages.agents.status.${selectedAgent.status}`)}
                    </Tag>
                    <Tag>
                        <ClockCircleOutlined /> {t('pages.agents.lastActive')}: {selectedAgent.lastActive}
                    </Tag>
                </Space>
                <Title level={5}>{t('pages.agents.skills')}</Title>
                <Space wrap>
                    {selectedAgent.skills.map(skill => (
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
                                value={selectedAgent.tasksCompleted}
                                prefix={<StarOutlined />}
                            />
                        </Card>
                    </Col>
                    <Col span={12}>
                        <Card>
                            <Statistic
                                title={t('pages.agents.efficiency')}
                                value={selectedAgent.efficiency}
                                suffix="%"
                                prefix={<ThunderboltOutlined />}
                            />
                        </Card>
                    </Col>
                </Row>
                {selectedAgent.currentTask && (
                    <Card>
                        <Space direction="vertical" style={{ width: '100%' }}>
                            <Text strong>{t('pages.agents.currentTask')}</Text>
                            <Text>{selectedAgent.currentTask}</Text>
                            <Button 
                                type="primary"
                                onClick={() => handleTaskComplete(selectedAgent.id)}
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
                        onClick={() => handleStatusChange(selectedAgent.id, 'active')}
                        disabled={selectedAgent.status === 'active'}
                    >
                        {t('pages.agents.activate')}
                    </Button>
                    <Button 
                        icon={<EditOutlined />}
                        onClick={() => handleStatusChange(selectedAgent.id, 'busy')}
                        disabled={selectedAgent.status === 'busy'}
                    >
                        {t('pages.agents.setBusy')}
                    </Button>
                    <Button 
                        icon={<HistoryOutlined />}
                        onClick={() => handleStatusChange(selectedAgent.id, 'offline')}
                        disabled={selectedAgent.status === 'offline'}
                    >
                        {t('pages.agents.setOffline')}
                    </Button>
                </Space>
                <ActionButtons
                    onAdd={() => {}}
                    onEdit={() => {}}
                    onDelete={() => {}}
                    onRefresh={() => {}}
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