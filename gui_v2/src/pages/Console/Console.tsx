import React, { useState, useCallback, useEffect, useMemo } from 'react';
import { List, Tag, Typography, Space, Button, Progress, Row, Col, Statistic, Card, Badge, Empty } from 'antd';
import { 
    ClusterOutlined, 
    CheckCircleOutlined,
    ClockCircleOutlined,
    ThunderboltOutlined,
    EnvironmentOutlined,
    ToolOutlined,
    PlusOutlined,
    HistoryOutlined,
} from '@ant-design/icons';
import styled from '@emotion/styled';
import DetailLayout from '../../components/Layout/DetailLayout';
import { useDetailView } from '../../hooks/useDetailView';
import { ConsoleFilters, ConsoleFilterOptions } from './components/ConsoleFilters';
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

    const [filters, setFilters] = useState<ConsoleFilterOptions>({
        search: '',
        status: undefined,
        type: undefined,
    });

    // 筛选后的LogList
    const filteredLogs = useMemo(() => {
        let result = [...agentLogs];

        // 按Status筛选
        if (filters.status) {
            result = result.filter(log => log.status === filters.status);
        }

        // 按Type筛选
        if (filters.type) {
            const typeMap: Record<string, string> = {
                ground: t('pages.console.groundVehicle'),
                aerial: t('pages.console.aerialVehicle'),
            };
            const typeName = typeMap[filters.type];
            if (typeName) {
                result = result.filter(log => log.type === typeName);
            }
        }

        // 按Search关键字筛选
        if (filters.search) {
            const searchLower = filters.search.toLowerCase();
            result = result.filter(log =>
                log.name?.toLowerCase().includes(searchLower) ||
                log.location?.toLowerCase().includes(searchLower) ||
                log.currentTask?.toLowerCase().includes(searchLower)
            );
        }

        return result;
    }, [agentLogs, filters, t]);

    const handleStatusChange = (id: number, newStatus: LogMessage['status']) => {
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

    const renderListContent = () => (
        <>
            <ConsoleFilters 
                filters={filters} 
                onChange={setFilters} 
            />
            {filteredLogs.length === 0 ? (
                <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={t('pages.console.noData', '没有找到匹配的Data')}
                    style={{ marginTop: 40 }}
                />
            ) : (
                <List
                    dataSource={filteredLogs}
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
            )}
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
                    columns={2}
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
                    columns={2}
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