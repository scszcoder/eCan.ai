import React, { useState, useCallback, useEffect } from 'react';
import { List, Tag, Typography, Space, Button, Progress, Row, Col, Statistic, Card, Badge } from 'antd';
import { 
    CarOutlined,
    ClusterOutlined, 
    CheckCircleOutlined,
    ClockCircleOutlined,
    ThunderboltOutlined,
    EnvironmentOutlined,
    ToolOutlined,
    PlusOutlined,
    HistoryOutlined,
    ReadOutlined,
    EditOutlined
} from '@ant-design/icons';
import styled from '@emotion/styled';
import DetailLayout from '../components/Layout/DetailLayout';
import { useDetailView } from '../hooks/useDetailView';
import SearchFilter from '../components/Common/SearchFilter';
import ActionButtons from '../components/Common/ActionButtons';
import StatusTag from '../components/Common/StatusTag';
import DetailCard from '../components/Common/DetailCard';
import { useTranslation } from 'react-i18next';

const { Text, Title } = Typography;

const KnowledgeItem = styled.div`
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

interface KnowledgePoint {
    id: number;
    name: string;
    type: string;
    status: 'active' | 'maintenance' | 'offline';
    battery: number;
    location: string;
    lastMaintenance: string;
    totalDistance: number;
    currentTask?: string;
    nextMaintenance?: string;
}

const knowledgeEventBus = {
    listeners: new Set<(data: KnowledgePoint[]) => void>(),
    subscribe(listener: (data: KnowledgePoint[]) => void) {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    },
    emit(data: KnowledgePoint[]) {
        this.listeners.forEach(listener => listener(data));
    }
};

// 导出更新数据的函数
export const updateKnowledgeGUI = (data: KnowledgePoint[]) => {
    knowledgeEventBus.emit(data);
};

const Knowledge: React.FC = () => {
    const { t } = useTranslation();
    
    const initialKnowledge: KnowledgePoint[] = [
        {
            id: 1,
            name: 'Product A',
            type: t('pages.knowledge.groundVehicle'),
            status: 'active',
            battery: 85,
            location: t('pages.knowledge.zoneA'),
            lastMaintenance: t('pages.knowledge.lastMaintenance', { time: '2 weeks ago' }),
            totalDistance: 1560,
            currentTask: t('pages.knowledge.currentTask', { task: 'Delivery Task #123' }),
            nextMaintenance: t('pages.knowledge.nextMaintenance', { time: '2 weeks from now' }),
        },
        {
            id: 2,
            name: 'Service Beta',
            type: t('pages.knowledge.aerialVehicle'),
            status: 'maintenance',
            battery: 45,
            location: t('pages.knowledge.maintenanceBay'),
            lastMaintenance: t('pages.knowledge.lastMaintenance', { time: '1 day ago' }),
            totalDistance: 2340,
            nextMaintenance: t('pages.knowledge.nextMaintenance', { time: '1 week from now' }),
        },
        {
            id: 3,
            name: 'Product Gamma',
            type: t('pages.knowledge.groundVehicle'),
            status: 'offline',
            battery: 100,
            location: t('pages.knowledge.chargingStation'),
            lastMaintenance: t('pages.knowledge.lastMaintenance', { time: '1 month ago' }),
            totalDistance: 890,
            nextMaintenance: t('pages.knowledge.nextMaintenance', { time: '3 weeks from now' }),
        },
    ];


    const {
        selectedItem: selectedKnowledge,
        items: knowledges,
        selectItem,
        updateItem,
    } = useDetailView<KnowledgePoint>(initialKnowledge);

    const [filters, setFilters] = useState<Record<string, any>>({});

    const handleStatusChange = (id: number, newStatus: Vehicle['status']) => {
        updateItem(id, {
            status: newStatus,
            location: newStatus === 'maintenance' ? t('pages.knowledge.maintenanceBay') :
                     newStatus === 'offline' ? t('pages.knowledge.chargingStation') : t('pages.knowledge.zoneA'),
        });
    };

    const handleTaskComplete = (id: number) => {
        const knowledgePoint = knowledges.find(k => k.id === id);
        if (knowledgePoint) {
            updateItem(id, {
                status: 'active',
                currentTask: undefined,
                totalDistance: knowledgePoint.totalDistance + 10,
                battery: Math.max(knowledgePoint.battery - 5, 0),
            });
        }
    };

    const handleMaintenance = (id: number) => {
        const knowledgePoint = knowledges.find(k => k.id === id);
        if (knowledgePoint) {
            updateItem(id, {
                status: 'maintenance',
                location: t('pages.knowledge.maintenanceBay'),
                lastMaintenance: t('pages.knowledge.lastMaintenance', { time: t('pages.schedule.justNow') }),
                nextMaintenance: t('pages.knowledge.nextMaintenance', { time: t('pages.schedule.twoWeeksFromNow') }),
            });
        }
    };

    const handleSearch = (value: string) => {
        // Implement search logic
    };

    const handleFilterChange = (newFilters: Record<string, any>) => {
        setFilters(prev => ({ ...prev, ...newFilters }));
    };

    const handleReset = () => {
        setFilters({});
    };

    const renderListContent = () => (
        <>
            <Title level={2}>{t('pages.knowledge.title')}</Title>
            <SearchFilter
                onSearch={handleSearch}
                onFilterChange={handleFilterChange}
                onReset={handleReset}
                filterOptions={[
                    {
                        key: 'status',
                        label: t('pages.knowledge.status'),
                        options: [
                            { label: t('pages.knowledge.status.active'), value: 'active' },
                            { label: t('pages.knowledge.status.maintenance'), value: 'maintenance' },
                            { label: t('pages.knowledge.status.offline'), value: 'offline' },
                        ],
                    },
                    {
                        key: 'type',
                        label: t('pages.knowledge.type'),
                        options: [
                            { label: t('pages.knowledge.groundVehicle'), value: t('pages.knowledge.groundVehicle') },
                            { label: t('pages.knowledge.aerialVehicle'), value: t('pages.knowledge.aerialVehicle') },
                        ],
                    },
                ]}
                placeholder={t('pages.knowledge.searchPlaceholder')}
            />
            <ActionButtons
                onAdd={() => {}}
                onEdit={() => {}}
                onDelete={() => {}}
                onRefresh={() => {}}
                onExport={() => {}}
                onImport={() => {}}
                onSettings={() => {}}
                addText={t('pages.knowledge.addVehicle')}
                editText={t('pages.knowledge.editVehicle')}
                deleteText={t('pages.knowledge.deleteVehicle')}
                refreshText={t('pages.knowledge.refreshVehicles')}
                exportText={t('pages.knowledge.exportVehicles')}
                importText={t('pages.knowledge.importVehicles')}
                settingsText={t('pages.knowledge.vehicleSettings')}
            />
            <List
                dataSource={knowledges}
                renderItem={knowledgePoint => (
                    <KnowledgeItem onClick={() => selectItem(knowledgePoint)}>
                        <Space direction="vertical" style={{ width: '100%' }}>
                            <Space>
                                <StatusTag status={knowledgePoint.status} />
                                <ClusterOutlined />
                                <Text strong>{knowledgePoint.name}</Text>
                            </Space>
                            <Space>
                                <Tag color="blue">{knowledgePoint.type}</Tag>
                                {knowledgePoint.currentTask && (
                                    <Tag color="processing">{t('pages.knowledge.currentTask')}: {knowledgePoint.currentTask}</Tag>
                                )}
                            </Space>
                            <Space>
                                <EnvironmentOutlined />
                                <Text type="secondary">{knowledgePoint.location}</Text>
                            </Space>
                            <Progress 
                                percent={knowledgePoint.battery}
                                size="small"
                                status={knowledgePoint.battery < 20 ? 'exception' : 'normal'}
                            />
                        </Space>
                    </KnowledgeItem>
                )}
            />
        </>
    );

    const renderDetailsContent = () => {
        if (!selectedKnowledge) {
            return <Text type="secondary">{t('pages.knowledge.selectVehicle')}</Text>;
        }

        return (
            <Space direction="vertical" style={{ width: '100%' }}>
                <DetailCard
                    title={t('pages.knowledge.vehicleInformation')}
                    items={[
                        {
                            label: t('pages.knowledge.name'),
                            value: selectedKnowledge.name,
                            icon: <ClusterOutlined />,
                        },
                        {
                            label: t('pages.knowledge.type'),
                            value: selectedKnowledge.type,
                            icon: <ClusterOutlined />,
                        },
                        {
                            label: t('pages.knowledge.status'),
                            value: <StatusTag status={selectedKnowledge.status} />,
                            icon: <CheckCircleOutlined />,
                        },
                        {
                            label: t('pages.knowledge.location'),
                            value: selectedKnowledge.location,
                            icon: <EnvironmentOutlined />,
                        },
                    ]}
                />
                <DetailCard
                    title={t('pages.knowledge.performanceMetrics')}
                    items={[
                        {
                            label: t('pages.knowledge.batteryLevel'),
                            value: (
                                <Statistic
                                    value={selectedKnowledge.battery}
                                    suffix="%"
                                    prefix={<ThunderboltOutlined />}
                                />
                            ),
                            icon: <ThunderboltOutlined />,
                        },
                        {
                            label: t('pages.knowledge.totalDistance'),
                            value: (
                                <Statistic
                                    value={selectedKnowledge.totalDistance}
                                    suffix="km"
                                />
                            ),
                            icon: <ClusterOutlined />,
                        },
                        {
                            label: t('pages.knowledge.lastMaintenance'),
                            value: selectedKnowledge.lastMaintenance,
                            icon: <ToolOutlined />,
                        },
                        {
                            label: t('pages.knowledge.nextMaintenance'),
                            value: selectedKnowledge.nextMaintenance,
                            icon: <ClockCircleOutlined />,
                        },
                    ]}
                />
                <Space>
                    <Button 
                        type="primary" 
                        icon={<PlusOutlined />}
                        onClick={() => handleStatusChange(selectedKnowledge.id, 'active')}
                        disabled={selectedKnowledge.status === 'active'}
                    >
                        {t('pages.knowledge.activate')}
                    </Button>
                    <Button 
                        icon={<ToolOutlined />}
                        onClick={() => handleMaintenance(selectedKnowledge.id)}
                        disabled={selectedKnowledge.status === 'maintenance'}
                    >
                        {t('pages.knowledge.scheduleMaintenance')}
                    </Button>
                    <Button 
                        icon={<HistoryOutlined />}
                        onClick={() => handleStatusChange(selectedKnowledge.id, 'offline')}
                        disabled={selectedKnowledge.status === 'offline'}
                    >
                        {t('pages.knowledge.setOffline')}
                    </Button>
                </Space>
            </Space>
        );
    };

    return (
        <DetailLayout
            listContent={renderListContent()}
        />
    );
};

export default Knowledge;