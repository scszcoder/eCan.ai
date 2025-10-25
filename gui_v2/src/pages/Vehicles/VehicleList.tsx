import React from 'react';
import { List } from 'antd';
import type { Vehicle } from '@/stores';
import VehicleItem from './VehicleItem';
import SearchFilter from '../../components/Common/SearchFilter';
import ActionButtons from '../../components/Common/ActionButtons';

interface VehicleListProps {
    vehicles: Vehicle[];
    selectedVehicle?: Vehicle | null;
    onSelect: (vehicle: Vehicle) => void;
    filters: Record<string, any>;
    onFilterChange: (filters: Record<string, any>) => void;
    onSearch: (value: string) => void;
    onReset: () => void;
    onAdd?: () => void;
    onEdit?: () => void;
    onDelete?: () => void;
    onRefresh?: () => void;
    t: any;
}

const VehicleList: React.FC<VehicleListProps> = ({ 
    vehicles,
    selectedVehicle,
    onSelect, 
    filters, 
    onFilterChange, 
    onSearch, 
    onReset, 
    onAdd,
    onEdit,
    onDelete,
    onRefresh,
    t 
}) => (
    <>
        <SearchFilter
            onSearch={onSearch}
            onFilter={onFilterChange}
            onFilterReset={onReset}
            filterOptions={[
                {
                    key: 'status',
                    label: t('pages.vehicles.statusLabel'),
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
                        { label: t('pages.vehicles.groundVehicle'), value: 'ground' },
                        { label: t('pages.vehicles.aerialVehicle'), value: 'aerial' },
                    ],
                },
            ]}
            placeholder={t('pages.vehicles.searchPlaceholder')}
        />
        <ActionButtons
            onAdd={onAdd}
            onEdit={onEdit}
            onDelete={onDelete}
            onRefresh={onRefresh}
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
            // grid={{ gutter: 16, xs: 1, sm: 1, md: 2, lg: 2, xl: 3, xxl: 3 }} // 移除grid属性，单列展示
            dataSource={vehicles}
            itemLayout="vertical"
            split={false}
            renderItem={vehicle => (
                <VehicleItem 
                    vehicle={vehicle} 
                    selected={selectedVehicle?.id === vehicle.id}
                    onClick={onSelect} 
                    t={t} 
                />
            )}
        />
    </>
);

export default VehicleList; 