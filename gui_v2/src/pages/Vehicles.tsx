import React, { useState } from 'react';
import { List, Tag, Typography, Space, Button, Progress, Row, Col, Statistic, Card, Badge } from 'antd';
import { 
    CarOutlined, 
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
import DetailLayout from '../components/Layout/DetailLayout';
import { useDetailView } from '../hooks/useDetailView';
import SearchFilter from '../components/Common/SearchFilter';
import ActionButtons from '../components/Common/ActionButtons';
import StatusTag from '../components/Common/StatusTag';
import DetailCard from '../components/Common/DetailCard';
import { useTranslation } from 'react-i18next';

const { Text, Title } = Typography;

const VehicleItem = styled.div`
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

interface Vehicle {
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

const Vehicles: React.FC = () => {
    const { t } = useTranslation();
    
    const initialVehicles: Vehicle[] = [
        {
            id: 1,
            name: 'Vehicle Alpha',
            type: t('pages.vehicles.groundVehicle'),
            status: 'active',
            battery: 85,
            location: t('pages.vehicles.zoneA'),
            lastMaintenance: t('pages.vehicles.lastMaintenance', { time: '2 weeks ago' }),
            totalDistance: 1560,
            currentTask: t('pages.vehicles.currentTask', { task: 'Delivery Task #123' }),
            nextMaintenance: t('pages.vehicles.nextMaintenance', { time: '2 weeks from now' }),
        },
        {
            id: 2,
            name: 'Vehicle Beta',
            type: t('pages.vehicles.aerialVehicle'),
            status: 'maintenance',
            battery: 45,
            location: t('pages.vehicles.maintenanceBay'),
            lastMaintenance: t('pages.vehicles.lastMaintenance', { time: '1 day ago' }),
            totalDistance: 2340,
            nextMaintenance: t('pages.vehicles.nextMaintenance', { time: '1 week from now' }),
        },
        {
            id: 3,
            name: 'Vehicle Gamma',
            type: t('pages.vehicles.groundVehicle'),
            status: 'offline',
            battery: 100,
            location: t('pages.vehicles.chargingStation'),
            lastMaintenance: t('pages.vehicles.lastMaintenance', { time: '1 month ago' }),
            totalDistance: 890,
            nextMaintenance: t('pages.vehicles.nextMaintenance', { time: '3 weeks from now' }),
        },
    ];

    const {
        selectedItem: selectedVehicle,
        items: vehicles,
        selectItem,
        updateItem,
    } = useDetailView<Vehicle>(initialVehicles);

    const [filters, setFilters] = useState<Record<string, any>>({});

    const handleStatusChange = (id: number, newStatus: Vehicle['status']) => {
        updateItem(id, {
            status: newStatus,
            location: newStatus === 'maintenance' ? t('pages.vehicles.maintenanceBay') : 
                     newStatus === 'offline' ? t('pages.vehicles.chargingStation') : t('pages.vehicles.zoneA'),
        });
    };

    const handleTaskComplete = (id: number) => {
        const vehicle = vehicles.find(v => v.id === id);
        if (vehicle) {
            updateItem(id, {
                status: 'active',
                currentTask: undefined,
                totalDistance: vehicle.totalDistance + 10,
                battery: Math.max(vehicle.battery - 5, 0),
            });
        }
    };

    const handleMaintenance = (id: number) => {
        const vehicle = vehicles.find(v => v.id === id);
        if (vehicle) {
            updateItem(id, {
                status: 'maintenance',
                location: t('pages.vehicles.maintenanceBay'),
                lastMaintenance: t('pages.vehicles.lastMaintenance', { time: t('pages.schedule.justNow') }),
                nextMaintenance: t('pages.vehicles.nextMaintenance', { time: t('pages.schedule.twoWeeksFromNow') }),
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
            <Title level={2}>{t('pages.vehicles.title')}</Title>
            <SearchFilter
                onSearch={handleSearch}
                onFilterChange={handleFilterChange}
                onReset={handleReset}
                filterOptions={[
                    {
                        key: 'status',
                        label: t('pages.vehicles.status'),
                        options: [
                            { label: t('pages.vehicles.status.active'), value: 'active' },
                            { label: t('pages.vehicles.status.maintenance'), value: 'maintenance' },
                            { label: t('pages.vehicles.status.offline'), value: 'offline' },
                        ],
                    },
                    {
                        key: 'type',
                        label: t('pages.vehicles.type'),
                        options: [
                            { label: t('pages.vehicles.groundVehicle'), value: t('pages.vehicles.groundVehicle') },
                            { label: t('pages.vehicles.aerialVehicle'), value: t('pages.vehicles.aerialVehicle') },
                        ],
                    },
                ]}
                placeholder={t('pages.vehicles.searchPlaceholder')}
            />
            <ActionButtons
                onAdd={() => {}}
                onEdit={() => {}}
                onDelete={() => {}}
                onRefresh={() => {}}
                onExport={() => {}}
                onImport={() => {}}
                onSettings={() => {}}
                addText={t('pages.vehicles.addVehicle')}
                editText={t('pages.vehicles.editVehicle')}
                deleteText={t('pages.vehicles.deleteVehicle')}
                refreshText={t('pages.vehicles.refreshVehicles')}
                exportText={t('pages.vehicles.exportVehicles')}
                importText={t('pages.vehicles.importVehicles')}
                settingsText={t('pages.vehicles.vehicleSettings')}
            />
            <List
                dataSource={vehicles}
                renderItem={vehicle => (
                    <VehicleItem onClick={() => selectItem(vehicle)}>
                        <Space direction="vertical" style={{ width: '100%' }}>
                            <Space>
                                <StatusTag status={vehicle.status} />
                                <CarOutlined />
                                <Text strong>{vehicle.name}</Text>
                            </Space>
                            <Space>
                                <Tag color="blue">{vehicle.type}</Tag>
                                {vehicle.currentTask && (
                                    <Tag color="processing">{t('pages.vehicles.currentTask')}: {vehicle.currentTask}</Tag>
                                )}
                            </Space>
                            <Space>
                                <EnvironmentOutlined />
                                <Text type="secondary">{vehicle.location}</Text>
                            </Space>
                            <Progress 
                                percent={vehicle.battery} 
                                size="small"
                                status={vehicle.battery < 20 ? 'exception' : 'normal'}
                            />
                        </Space>
                    </VehicleItem>
                )}
            />
        </>
    );

    const renderDetailsContent = () => {
        if (!selectedVehicle) {
            return <Text type="secondary">{t('pages.vehicles.selectVehicle')}</Text>;
        }

        return (
            <Space direction="vertical" style={{ width: '100%' }}>
                <DetailCard
                    title={t('pages.vehicles.vehicleInformation')}
                    items={[
                        {
                            label: t('pages.vehicles.name'),
                            value: selectedVehicle.name,
                            icon: <CarOutlined />,
                        },
                        {
                            label: t('pages.vehicles.type'),
                            value: selectedVehicle.type,
                            icon: <CarOutlined />,
                        },
                        {
                            label: t('pages.vehicles.status'),
                            value: <StatusTag status={selectedVehicle.status} />,
                            icon: <CheckCircleOutlined />,
                        },
                        {
                            label: t('pages.vehicles.location'),
                            value: selectedVehicle.location,
                            icon: <EnvironmentOutlined />,
                        },
                    ]}
                />
                <DetailCard
                    title={t('pages.vehicles.performanceMetrics')}
                    items={[
                        {
                            label: t('pages.vehicles.batteryLevel'),
                            value: (
                                <Statistic
                                    value={selectedVehicle.battery}
                                    suffix="%"
                                    prefix={<ThunderboltOutlined />}
                                />
                            ),
                            icon: <ThunderboltOutlined />,
                        },
                        {
                            label: t('pages.vehicles.totalDistance'),
                            value: (
                                <Statistic
                                    value={selectedVehicle.totalDistance}
                                    suffix="km"
                                />
                            ),
                            icon: <CarOutlined />,
                        },
                        {
                            label: t('pages.vehicles.lastMaintenance'),
                            value: selectedVehicle.lastMaintenance,
                            icon: <ToolOutlined />,
                        },
                        {
                            label: t('pages.vehicles.nextMaintenance'),
                            value: selectedVehicle.nextMaintenance,
                            icon: <ClockCircleOutlined />,
                        },
                    ]}
                />
                <Space>
                    <Button 
                        type="primary" 
                        icon={<PlusOutlined />}
                        onClick={() => handleStatusChange(selectedVehicle.id, 'active')}
                        disabled={selectedVehicle.status === 'active'}
                    >
                        {t('pages.vehicles.activate')}
                    </Button>
                    <Button 
                        icon={<ToolOutlined />}
                        onClick={() => handleMaintenance(selectedVehicle.id)}
                        disabled={selectedVehicle.status === 'maintenance'}
                    >
                        {t('pages.vehicles.scheduleMaintenance')}
                    </Button>
                    <Button 
                        icon={<HistoryOutlined />}
                        onClick={() => handleStatusChange(selectedVehicle.id, 'offline')}
                        disabled={selectedVehicle.status === 'offline'}
                    >
                        {t('pages.vehicles.setOffline')}
                    </Button>
                </Space>
            </Space>
        );
    };

    return (
        <DetailLayout
            listTitle={t('pages.vehicles.title')}
            detailsTitle={t('pages.vehicles.vehicleInformation')}
            listContent={renderListContent()}
            detailsContent={renderDetailsContent()}
        />
    );
};

export default Vehicles; 