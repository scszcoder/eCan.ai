import React from 'react';
import { List, Tag, Typography, Space, Button, Avatar, Row, Col, Progress, Card } from 'antd';
import { 
    AppstoreOutlined,
    CheckCircleOutlined,
    ClockCircleOutlined,
    StarOutlined,
    DownloadOutlined,
    SettingOutlined,
    DeleteOutlined
} from '@ant-design/icons';
import styled from '@emotion/styled';
import DetailLayout from '../components/Layout/DetailLayout';
import { useDetailView } from '../hooks/useDetailView';

const { Text, Title } = Typography;

const AppItem = styled.div`
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

interface App {
    id: number;
    name: string;
    version: string;
    status: 'active' | 'updating' | 'error';
    category: string;
    size: string;
    lastUpdated: string;
    rating: number;
    description: string;
    features: string[];
}

const getStatusColor = (status: App['status']): string => {
    switch (status) {
        case 'active':
            return 'success';
        case 'updating':
            return 'processing';
        case 'error':
            return 'error';
        default:
            return 'default';
    }
};

const initialApps: App[] = [
    {
        id: 1,
        name: 'Task Manager',
        version: '2.1.0',
        status: 'active',
        category: 'Productivity',
        size: '45MB',
        lastUpdated: '2 days ago',
        rating: 4.5,
        description: 'A comprehensive task management application for organizing and tracking work.',
        features: ['Task Creation', 'Progress Tracking', 'Team Collaboration', 'File Sharing'],
    },
    {
        id: 2,
        name: 'Data Analyzer',
        version: '1.5.2',
        status: 'updating',
        category: 'Analytics',
        size: '78MB',
        lastUpdated: '1 hour ago',
        rating: 4.2,
        description: 'Advanced data analysis and visualization tool for business intelligence.',
        features: ['Data Import', 'Visualization', 'Report Generation', 'Export Options'],
    },
    {
        id: 3,
        name: 'System Monitor',
        version: '3.0.1',
        status: 'error',
        category: 'System',
        size: '32MB',
        lastUpdated: '1 week ago',
        rating: 4.8,
        description: 'Real-time system monitoring and performance tracking tool.',
        features: ['Resource Monitoring', 'Alert System', 'Performance Reports', 'Log Analysis'],
    },
];

const Apps: React.FC = () => {
    const {
        selectedItem: selectedApp,
        items: apps,
        selectItem,
        removeItem,
        updateItem,
    } = useDetailView<App>(initialApps);

    const handleUpdate = (id: number) => {
        updateItem(id, { status: 'updating' });
        // Simulate update process
        setTimeout(() => {
            updateItem(id, { 
                status: 'active',
                version: (parseFloat(apps.find(app => app.id === id)?.version || '0') + 0.1).toFixed(1),
                lastUpdated: 'Just now'
            });
        }, 2000);
    };

    const handleUninstall = (id: number) => {
        removeItem(id);
    };

    const renderListContent = () => (
        <List
            dataSource={apps}
            renderItem={app => (
                <AppItem onClick={() => selectItem(app)}>
                    <Space direction="vertical" style={{ width: '100%' }}>
                        <Space>
                            <Avatar icon={<AppstoreOutlined />} />
                            <Text strong>{app.name}</Text>
                        </Space>
                        <Space>
                            <Tag color={getStatusColor(app.status)}>{app.status}</Tag>
                            <Tag color="blue">{app.category}</Tag>
                        </Space>
                        <Space>
                            <Text type="secondary">v{app.version}</Text>
                            <Text type="secondary">{app.size}</Text>
                        </Space>
                    </Space>
                </AppItem>
            )}
        />
    );

    const renderDetailsContent = () => {
        if (!selectedApp) {
            return <Text type="secondary">Select an application to view details</Text>;
        }

        return (
            <Space direction="vertical" style={{ width: '100%' }}>
                <Space>
                    <Avatar size={64} icon={<AppstoreOutlined />} />
                    <div>
                        <Title level={4} style={{ margin: 0 }}>{selectedApp.name}</Title>
                        <Text type="secondary">Version {selectedApp.version}</Text>
                    </div>
                </Space>
                <Space>
                    <Tag color={getStatusColor(selectedApp.status)}>
                        <CheckCircleOutlined /> Status: {selectedApp.status}
                    </Tag>
                    <Tag>
                        <ClockCircleOutlined /> Last Updated: {selectedApp.lastUpdated}
                    </Tag>
                    <Tag>
                        <StarOutlined /> Rating: {selectedApp.rating}/5
                    </Tag>
                </Space>
                <div>
                    <Text strong>Description</Text>
                    <br />
                    <Text>{selectedApp.description}</Text>
                </div>
                <div>
                    <Text strong>Features</Text>
                    <br />
                    <Space wrap>
                        {selectedApp.features.map(feature => (
                            <Tag key={feature} color="green">{feature}</Tag>
                        ))}
                    </Space>
                </div>
                <Row gutter={16}>
                    <Col span={12}>
                        <Card>
                            <Space direction="vertical" style={{ width: '100%' }}>
                                <Text>Storage Usage</Text>
                                <Progress percent={75} />
                                <Text type="secondary">{selectedApp.size}</Text>
                            </Space>
                        </Card>
                    </Col>
                    <Col span={12}>
                        <Card>
                            <Space direction="vertical" style={{ width: '100%' }}>
                                <Text>User Rating</Text>
                                <Progress percent={selectedApp.rating * 20} />
                                <Text type="secondary">{selectedApp.rating}/5</Text>
                            </Space>
                        </Card>
                    </Col>
                </Row>
                <Space>
                    <Button 
                        type="primary" 
                        icon={<DownloadOutlined />}
                        onClick={() => handleUpdate(selectedApp.id)}
                        loading={selectedApp.status === 'updating'}
                    >
                        Update
                    </Button>
                    <Button icon={<SettingOutlined />}>
                        Settings
                    </Button>
                    <Button 
                        danger 
                        icon={<DeleteOutlined />}
                        onClick={() => handleUninstall(selectedApp.id)}
                    >
                        Uninstall
                    </Button>
                </Space>
            </Space>
        );
    };

    return (
        <DetailLayout
            listTitle="Applications"
            detailsTitle="Application Details"
            listContent={renderListContent()}
            detailsContent={renderDetailsContent()}
        />
    );
};

export default Apps; 