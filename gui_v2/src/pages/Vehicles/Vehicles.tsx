import React, { useCallback, useEffect, useState } from 'react';
import { List, Tag, Space, Button, Progress, Row, Col, Statistic, Card, Badge } from 'antd';
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
    EditOutlined,
    ReloadOutlined
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
import { useUserStore } from '../../stores/userStore';
import { Vehicle } from './types';
import VehicleList from './VehicleList';
import VehicleDetails from './VehicleDetails';

const VehicleItem = styled.div`
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
        setItems: setVehicles  // Add this line
    } = useDetailView<Vehicle>(initialVehicles);

    const username = useUserStore((state) => state.username) ?? '';

    useEffect(() => {
        if (!username) return;
        (async () => {
            const response = await IPCAPI.getInstance().get_vehicles();
            console.log(response.data)
            if (response && response.success && response.data) {
                setVehicles(response.data.vehicles);
            }
        })();
    }, [username, setVehicles]);

    const handleRefresh = useCallback(async () => {
        if (!username) return;
        try {
            const response = await IPCAPI.getInstance().get_vehicles();
            console.log('Vehicles refreshed:', response);
            if (response && response.success && response.data) {
                setVehicles(response.data.vehicles);
            }
        } catch (error) {
            console.error('Error refreshing vehicles:', error);
        }
    }, [setVehicles, username]);

    // Add refresh button to the list title
    const listTitle = (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span>{t('pages.vehicles.title')}</span>
            <Button
                type="text"
                icon={<ReloadOutlined style={{ color: 'white' }} />}
                onClick={handleRefresh}
                title={t('pages.vehicles.refresh')}
            />
        </div>
    );

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
                totalDistance: (vehicle.totalDistance ?? 0) + 10,
                battery: Math.max((vehicle.battery ?? 0) - 5, 0),
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
        // setVehicles([]); // 不再重置 setVehicles，避免类型错误
    };

    return (
        <DetailLayout
            listTitle={listTitle}
            detailsTitle={t('pages.vehicles.vehicleInformation')}
            listContent={
                <VehicleList
                    vehicles={vehicles}
                    onSelect={selectItem}
                    filters={filters}
                    onFilterChange={handleFilterChange}
                    onSearch={handleSearch}
                    onReset={handleReset}
                    t={t}
                />
            }
            detailsContent={
                <VehicleDetails
                    vehicle={selectedVehicle ?? undefined}
                    onStatusChange={handleStatusChange}
                    onMaintenance={handleMaintenance}
                    t={t}
                />
            }
        />
    );
};

export default Vehicles; 