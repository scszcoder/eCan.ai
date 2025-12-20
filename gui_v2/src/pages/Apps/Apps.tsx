import React, { useState, useCallback, useEffect } from 'react';
import { List, Tag, Typography, Space, Button, Avatar, Row, Col, Progress, Card } from 'antd';
import { 
    AppstoreOutlined,
    CheckCircleOutlined,
    ClockCircleOutlined,
    StarOutlined,
    DownloadOutlined,
    SettingOutlined,
    OrderedListOutlined,
    DeleteOutlined
} from '@ant-design/icons';
import styled from '@emotion/styled';
import DetailLayout from '../../components/Layout/DetailLayout';
import { useDetailView } from '../../hooks/useDetailView';
import { useTranslation } from 'react-i18next';
import ActionButtons from '../../components/Common/ActionButtons';
import { IPCAPI } from '@/services/ipc/api';

const { Text, Title } = Typography;

const AppItem = styled.div`
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
        name: 'TaskManager',
        version: '2.1.0',
        status: 'active',
        category: 'Productivity',
        size: '45MB',
        lastUpdated: '2 days ago',
        rating: 4.5,
        description: 'TaskManager',
        features: ['TaskCreation', 'ProgressTracking', 'TeamCollaboration', 'FileSharing'],
    },
    {
        id: 2,
        name: 'DataAnalyzer',
        version: '1.5.2',
        status: 'updating',
        category: 'Analytics',
        size: '78MB',
        lastUpdated: '1 hour ago',
        rating: 4.2,
        description: 'DataAnalyzer',
        features: ['DataImport', 'Visualization', 'ReportGeneration', 'ExportOptions'],
    },
    {
        id: 3,
        name: 'SystemMonitor',
        version: '3.0.1',
        status: 'error',
        category: 'System',
        size: '32MB',
        lastUpdated: '1 week ago',
        rating: 4.8,
        description: 'SystemMonitor',
        features: ['ResourceMonitoring', 'AlertSystem', 'PerformanceReports', 'LogAnalysis'],
    },
];

const Apps: React.FC = () => {
    const { t } = useTranslation();
    const {
        selectedItem: selectedApp,
        items: apps,
        selectItem,
        removeItem,
        updateItem,
    } = useDetailView<App>(initialApps);

    const translateApp = (app: App): App => {
        // If已经是翻译后的文本（Include中文或特殊字符），直接返回
        if (app.name.includes('管理器') || app.name.includes('分析器') || app.name.includes('监视器')) {
            return app;
        }

        return {
            ...app,
            name: t(`pages.apps.apps.${app.name}.name`),
            category: t(`pages.apps.categoriesMap.${app.category}`),
            description: t(`pages.apps.apps.${app.name}.description`),
            features: app.features.map(feature => {
                // If功能Name已经是中文，直接返回
                if (feature.includes('Create') || feature.includes('跟踪') || feature.includes('协作')) {
                    return feature;
                }
                return t(`pages.apps.apps.${app.name}.featuresMap.${feature}`);
            }),
            lastUpdated: app.lastUpdated === '2 days ago'
                ? t('pages.apps.time.daysAgo', { days: 2 })
                : app.lastUpdated === '1 hour ago'
                ? t('pages.apps.time.hoursAgo', { hours: 1 })
                : app.lastUpdated === '1 week ago'
                ? t('pages.apps.time.weeksAgo', { weeks: 1 })
                : app.lastUpdated
        };
    };

    const translatedApps = (apps || []).map(translateApp);

    const handleUpdate = (id: number) => {
        updateItem(id, { status: 'updating' });
        // Simulate update process
        setTimeout(() => {
            updateItem(id, { 
                status: 'active',
                version: (parseFloat(apps.find(app => app.id === id)?.version || '0') + 0.1).toFixed(1),
                lastUpdated: t('pages.apps.time.justNow')
            });
        }, 2000);
    };

    const handleUninstall = (id: number) => {
        removeItem(id);
    };

    const renderListContent = () => (
        <List
            dataSource={translatedApps}
            renderItem={app => (
                <AppItem onClick={() => selectItem(app)}>
                    <Space direction="vertical" style={{ width: '100%' }}>
                        <Space>
                            <Avatar icon={<AppstoreOutlined />} />
                            <Text strong>{app.name}</Text>
                        </Space>
                        <Space>
                            <Tag color={getStatusColor(app.status)}>{t(`pages.apps.statusMap.${app.status}`)}</Tag>
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
            return <Text type="secondary">{t('pages.apps.selectApp')}</Text>;
        }

        const translatedApp = translateApp(selectedApp);

        return (
            <Space direction="vertical" style={{ width: '100%' }}>
                <Space>
                    <Avatar size={64} icon={<AppstoreOutlined />} />
                    <div>
                        <Title level={4} style={{ margin: 0 }}>{translatedApp.name}</Title>
                        <Text type="secondary">{t('pages.apps.version', { version: translatedApp.version })}</Text>
                    </div>
                </Space>
                <Space>
                    <Tag color={getStatusColor(translatedApp.status)}>
                        <CheckCircleOutlined /> {t('pages.apps.status')}: {t(`pages.apps.statusMap.${translatedApp.status}`)}
                    </Tag>
                    <Tag>
                        <ClockCircleOutlined /> {t('pages.apps.lastUpdated')}: {translatedApp.lastUpdated}
                    </Tag>
                    <Tag>
                        <StarOutlined /> {t('pages.apps.rating')}: {translatedApp.rating}/5
                    </Tag>
                </Space>
                <div>
                    <Text strong>{t('pages.apps.description')}</Text>
                    <br />
                    <Text>{translatedApp.description}</Text>
                </div>
                <div>
                    <Text strong>{t('pages.apps.features')}</Text>
                    <br />
                    <Space wrap>
                        {translatedApp.features.map(feature => (
                            <Tag key={feature} color="green">{feature}</Tag>
                        ))}
                    </Space>
                </div>
                <Row gutter={16}>
                    <Col span={12}>
                        <Card>
                            <Space direction="vertical" style={{ width: '100%' }}>
                                <Text>{t('pages.apps.storageUsage')}</Text>
                                <Progress percent={75} />
                                <Text type="secondary">{translatedApp.size}</Text>
                            </Space>
                        </Card>
                    </Col>
                    <Col span={12}>
                        <Card>
                            <Space direction="vertical" style={{ width: '100%' }}>
                                <Text>{t('pages.apps.userRating')}</Text>
                                <Progress percent={translatedApp.rating * 20} />
                                <Text type="secondary">{translatedApp.rating}/5</Text>
                            </Space>
                        </Card>
                    </Col>
                </Row>
                <Space>
                    <Button 
                        type="primary" 
                        icon={<DownloadOutlined />}
                        onClick={() => handleUpdate(translatedApp.id)}
                        disabled={translatedApp.status === 'updating'}
                    >
                        {t('pages.apps.update')}
                    </Button>
                    <Button 
                        icon={<SettingOutlined />}
                        onClick={() => {}}
                    >
                        {t('pages.apps.settings')}
                    </Button>
                    <Button 
                        danger
                        icon={<DeleteOutlined />}
                        onClick={() => handleUninstall(translatedApp.id)}
                    >
                        {t('pages.apps.uninstall')}
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
                    addText={t('pages.apps.addApp')}
                    editText={t('pages.apps.editApp')}
                    deleteText={t('pages.apps.deleteApp')}
                    refreshText={t('pages.apps.refreshApps')}
                    exportText={t('pages.apps.exportApps')}
                    importText={t('pages.apps.importApps')}
                    settingsText={t('pages.apps.appSettings')}
                />
            </Space>
        );
    };

    return (
        <DetailLayout
            listTitle={t('pages.apps.title')}
            detailsTitle={t('pages.apps.details')}
            listContent={renderListContent()}
            detailsContent={renderDetailsContent()}
        />
    );
};

export default Apps; 