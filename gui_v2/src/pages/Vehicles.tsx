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

const initialVehicles: Vehicle[] = [
    {
        id: 1,
        name: 'Vehicle Alpha',
        type: 'Ground Vehicle',
        status: 'active',
        battery: 85,
        location: 'Zone A',
        lastMaintenance: '2 weeks ago',
        totalDistance: 1560,
        currentTask: 'Delivery Task #123',
        nextMaintenance: '2 weeks from now',
    },
    {
        id: 2,
        name: 'Vehicle Beta',
        type: 'Aerial Vehicle',
        status: 'maintenance',
        battery: 45,
        location: 'Maintenance Bay',
        lastMaintenance: '1 day ago',
        totalDistance: 2340,
        nextMaintenance: '1 week from now',
    },
    {
        id: 3,
        name: 'Vehicle Gamma',
        type: 'Ground Vehicle',
        status: 'offline',
        battery: 100,
        location: 'Charging Station',
        lastMaintenance: '1 month ago',
        totalDistance: 890,
        nextMaintenance: '3 weeks from now',
    },
];

const Vehicles: React.FC = () => {
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
            location: newStatus === 'maintenance' ? 'Maintenance Bay' : 
                     newStatus === 'offline' ? 'Charging Station' : 'Zone A',
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
                location: 'Maintenance Bay',
                lastMaintenance: 'Just now',
                nextMaintenance: '2 weeks from now',
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
                        label: 'Status',
                        options: [
                            { label: 'Active', value: 'active' },
                            { label: 'Maintenance', value: 'maintenance' },
                            { label: 'Offline', value: 'offline' },
                        ],
                    },
                    {
                        key: 'type',
                        label: 'Type',
                        options: [
                            { label: 'Ground Vehicle', value: 'Ground Vehicle' },
                            { label: 'Aerial Vehicle', value: 'Aerial Vehicle' },
                        ],
                    },
                ]}
                placeholder="Search vehicles..."
            />
            <ActionButtons
                onAdd={() => {}}
                onEdit={() => {}}
                onDelete={() => {}}
                onRefresh={() => {}}
                onExport={() => {}}
                onImport={() => {}}
                onSettings={() => {}}
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
                                    <Tag color="processing">Task: {vehicle.currentTask}</Tag>
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
            return <Text type="secondary">Select a vehicle to view details</Text>;
        }

        return (
            <Space direction="vertical" style={{ width: '100%' }}>
                <DetailCard
                    title="Vehicle Information"
                    items={[
                        {
                            label: 'Name',
                            value: selectedVehicle.name,
                            icon: <CarOutlined />,
                        },
                        {
                            label: 'Type',
                            value: selectedVehicle.type,
                            icon: <CarOutlined />,
                        },
                        {
                            label: 'Status',
                            value: <StatusTag status={selectedVehicle.status} />,
                            icon: <CheckCircleOutlined />,
                        },
                        {
                            label: 'Location',
                            value: selectedVehicle.location,
                            icon: <EnvironmentOutlined />,
                        },
                    ]}
                />
                <DetailCard
                    title="Performance Metrics"
                    items={[
                        {
                            label: 'Battery Level',
                            value: (
                                <Statistic
                                    value={selectedVehicle.battery}
                                    suffix="%"
                                    prefix={<ThunderboltOutlined />}
                                    valueStyle={{ 
                                        color: selectedVehicle.battery < 20 ? '#cf1322' : 
                                               selectedVehicle.battery < 50 ? '#faad14' : '#3f8600'
                                    }}
                                />
                            ),
                        },
                        {
                            label: 'Total Distance',
                            value: (
                                <Statistic
                                    value={selectedVehicle.totalDistance}
                                    suffix="km"
                                    prefix={<CarOutlined />}
                                />
                            ),
                        },
                    ]}
                />
                <DetailCard
                    title="Maintenance Information"
                    items={[
                        {
                            label: 'Last Maintenance',
                            value: selectedVehicle.lastMaintenance,
                            icon: <ClockCircleOutlined />,
                        },
                        {
                            label: 'Next Maintenance',
                            value: selectedVehicle.nextMaintenance,
                            icon: <ClockCircleOutlined />,
                        },
                    ]}
                />
                {selectedVehicle.currentTask && (
                    <DetailCard
                        title="Current Task"
                        items={[
                            {
                                label: 'Task',
                                value: selectedVehicle.currentTask,
                                span: 24,
                            },
                        ]}
                        extra={
                            <Button 
                                type="primary"
                                onClick={() => handleTaskComplete(selectedVehicle.id)}
                            >
                                Mark as Complete
                            </Button>
                        }
                    />
                )}
                <Space>
                    <Button 
                        type="primary" 
                        icon={<PlusOutlined />}
                        onClick={() => handleStatusChange(selectedVehicle.id, 'active')}
                        disabled={selectedVehicle.status === 'active'}
                    >
                        Activate
                    </Button>
                    <Button 
                        icon={<ToolOutlined />}
                        onClick={() => handleMaintenance(selectedVehicle.id)}
                        disabled={selectedVehicle.status === 'maintenance'}
                    >
                        Schedule Maintenance
                    </Button>
                    <Button 
                        icon={<HistoryOutlined />}
                        onClick={() => handleStatusChange(selectedVehicle.id, 'offline')}
                        disabled={selectedVehicle.status === 'offline'}
                    >
                        Set Offline
                    </Button>
                </Space>
            </Space>
        );
    };

    return (
        <DetailLayout
            listTitle="Vehicles"
            detailsTitle="Vehicle Details"
            listContent={renderListContent()}
            detailsContent={renderDetailsContent()}
        />
    );
};

export default Vehicles; 