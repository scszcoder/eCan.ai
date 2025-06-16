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
    EditOutlined
} from '@ant-design/icons';
import styled from '@emotion/styled';
import DetailLayout from '../../components/Layout/DetailLayout';
import { useDetailView } from '../../hooks/useDetailView';
import SearchFilter from '../../components/Common/SearchFilter';
import ActionButtons from '../../components/Common/ActionButtons';
import StatusTag from '../../components/Common/StatusTag';
import DetailCard from '../../components/Common/DetailCard';
import { useTranslation } from 'react-i18next';
import { IPCAPI } from '@/services/ipc/api';

const { Text, Title } = Typography;

const ConsoleLogItem = styled.div`
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

interface LogMessage {
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

const Console: React.FC = () => {
    const { t } = useTranslation();
    
    const initialLogs: LogMessage[] = [
        {
            id: 1,
            name: 'Agent Alpha',
            type: t('pages.console.groundVehicle'),
            status: 'active',
            battery: 85,
            location: t('pages.console.zoneA'),
            lastMaintenance: t('pages.console.lastMaintenance', { time: '2 weeks ago' }),
            totalDistance: 1560,
            currentTask: t('pages.console.currentTask', { task: 'Delivery Task #123' }),
            nextMaintenance: t('pages.console.nextMaintenance', { time: '2 weeks from now' }),
        },
        {
            id: 2,
            name: 'Agent Beta',
            type: t('pages.console.aerialVehicle'),
            status: 'maintenance',
            battery: 45,
            location: t('pages.console.maintenanceBay'),
            lastMaintenance: t('pages.console.lastMaintenance', { time: '1 day ago' }),
            totalDistance: 2340,
            nextMaintenance: t('pages.console.nextMaintenance', { time: '1 week from now' }),
        },
        {
            id: 3,
            name: 'Agent Gamma',
            type: t('pages.console.groundVehicle'),
            status: 'offline',
            battery: 100,
            location: t('pages.console.chargingStation'),
            lastMaintenance: t('pages.console.lastMaintenance', { time: '1 month ago' }),
            totalDistance: 890,
            nextMaintenance: t('pages.console.nextMaintenance', { time: '3 weeks from now' }),
        },
    ];

    const {
        selectedItem: selectedAgentLogs,
        items: agentLogs,
        selectItem,
        updateItem,
    } = useDetailView<LogMessage>(initialLogs);

    const [filters, setFilters] = useState<Record<string, any>>({});

    const handleStatusChange = (id: number, newStatus: Vehicle['status']) => {
        updateItem(id, {
            status: newStatus,
            location: newStatus === 'maintenance' ? t('pages.console.maintenanceBay') : 
                     newStatus === 'offline' ? t('pages.console.chargingStation') : t('pages.console.zoneA'),
        });
    };

    const handleTaskComplete = (id: number) => {
        const agentLog = agentLogs.find(v => v.id === id);
        if (agentLog) {
            updateItem(id, {
                status: 'active',
                currentTask: undefined,
                totalDistance: agentLog.totalDistance + 10,
                battery: Math.max(agentLog.battery - 5, 0),
            });
        }
    };

    const handleMaintenance = (id: number) => {
        const agentLog = agentLogs.find(v => v.id === id);
        if (agentLog) {
            updateItem(id, {
                status: 'maintenance',
                location: t('pages.console.maintenanceBay'),
                lastMaintenance: t('pages.console.lastMaintenance', { time: t('pages.schedule.justNow') }),
                nextMaintenance: t('pages.console.nextMaintenance', { time: t('pages.schedule.twoWeeksFromNow') }),
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
            <SearchFilter
                onSearch={handleSearch}
                onFilterChange={handleFilterChange}
                onReset={handleReset}
                filterOptions={[
                    {
                        key: 'status',
                        label: t('pages.console.status'),
                        options: [
                            { label: t('pages.console.status.active'), value: 'active' },
                            { label: t('pages.console.status.maintenance'), value: 'maintenance' },
                            { label: t('pages.console.status.offline'), value: 'offline' },
                        ],
                    },
                    {
                        key: 'type',
                        label: t('pages.console.type'),
                        options: [
                            { label: t('pages.console.groundVehicle'), value: t('pages.console.groundVehicle') },
                            { label: t('pages.console.aerialVehicle'), value: t('pages.console.aerialVehicle') },
                        ],
                    },
                ]}
                placeholder={t('pages.console.searchPlaceholder')}
            />
            <ActionButtons
                onAdd={() => {}}
                onEdit={() => {}}
                onDelete={() => {}}
                onRefresh={() => {}}
                onExport={() => {}}
                onImport={() => {}}
                onSettings={() => {}}
                addText={t('pages.console.addVehicle')}
                editText={t('pages.console.editVehicle')}
                deleteText={t('pages.console.deleteVehicle')}
                refreshText={t('pages.console.refreshVehicles')}
                exportText={t('pages.console.exportVehicles')}
                importText={t('pages.console.importVehicles')}
                settingsText={t('pages.console.vehicleSettings')}
            />
            <List
                dataSource={agentLogs}
                renderItem={agentLog => (
                    <ConsoleLogItem onClick={() => selectItem(agentLog)}>
                        <Space direction="vertical" style={{ width: '100%' }}>
                            <Space>
                                <StatusTag status={agentLog.status} />
                                <ClusterOutlined />
                                <Text strong>{agentLog.name}</Text>
                            </Space>
                            <Space>
                                <Tag color="blue">{agentLog.type}</Tag>
                                {agentLog.currentTask && (
                                    <Tag color="processing">{t('pages.console.currentTask')}: {agentLog.currentTask}</Tag>
                                )}
                            </Space>
                            <Space>
                                <EnvironmentOutlined />
                                <Text type="secondary">{agentLog.location}</Text>
                            </Space>
                            <Progress 
                                percent={agentLog.battery}
                                size="small"
                                status={agentLog.battery < 20 ? 'exception' : 'normal'}
                            />
                        </Space>
                    </ConsoleLogItem>
                )}
            />
        </>
    );

    const renderDetailsContent = () => {
        if (!selectedAgentLogs) {
            return <Text type="secondary">{t('pages.console.selectVehicle')}</Text>;
        }

        return (
            <Space direction="vertical" style={{ width: '100%' }}>
                <DetailCard
                    title={t('pages.console.vehicleInformation')}
                    items={[
                        {
                            label: t('pages.console.name'),
                            value: selectedAgentLogs.name,
                            icon: <ClusterOutlined />,
                        },
                        {
                            label: t('pages.console.type'),
                            value: selectedAgentLogs.type,
                            icon: <ClusterOutlined />,
                        },
                        {
                            label: t('pages.console.status'),
                            value: <StatusTag status={selectedAgentLogs.status} />,
                            icon: <CheckCircleOutlined />,
                        },
                        {
                            label: t('pages.console.location'),
                            value: selectedAgentLogs.location,
                            icon: <EnvironmentOutlined />,
                        },
                    ]}
                />
                <DetailCard
                    title={t('pages.console.performanceMetrics')}
                    items={[
                        {
                            label: t('pages.console.batteryLevel'),
                            value: (
                                <Statistic
                                    value={selectedAgentLogs.battery}
                                    suffix="%"
                                    prefix={<ThunderboltOutlined />}
                                />
                            ),
                            icon: <ThunderboltOutlined />,
                        },
                        {
                            label: t('pages.console.totalDistance'),
                            value: (
                                <Statistic
                                    value={selectedAgentLogs.totalDistance}
                                    suffix="km"
                                />
                            ),
                            icon: <ClusterOutlined />,
                        },
                        {
                            label: t('pages.console.lastMaintenance'),
                            value: selectedAgentLogs.lastMaintenance,
                            icon: <ToolOutlined />,
                        },
                        {
                            label: t('pages.console.nextMaintenance'),
                            value: selectedAgentLogs.nextMaintenance,
                            icon: <ClockCircleOutlined />,
                        },
                    ]}
                />
                <Space>
                    <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={() => handleStatusChange(selectedAgentLogs.id, 'active')}
                        disabled={selectedAgentLogs.status === 'active'}
                    >
                        {t('pages.console.activate')}
                    </Button>
                    <Button
                        icon={<ToolOutlined />}
                        onClick={() => handleMaintenance(selectedAgentLogs.id)}
                        disabled={selectedAgentLogs.status === 'maintenance'}
                    >
                        {t('pages.console.scheduleMaintenance')}
                    </Button>
                    <Button
                        icon={<HistoryOutlined />}
                        onClick={() => handleStatusChange(selectedAgentLogs.id, 'offline')}
                        disabled={selectedAgentLogs.status === 'offline'}
                    >
                        {t('pages.console.setOffline')}
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

export default Console;