import React from 'react';
import { List } from 'antd';
import styled from '@emotion/styled';
import type { Vehicle } from '@/stores';
import VehicleItem from './VehicleItem';
import SearchFilter from '../../components/Common/SearchFilter';

const ListContainer = styled.div`
    display: flex;
    flex-direction: column;
    height: 100%;
`;

const FilterContainer = styled.div`
    padding: 8px;
    padding-bottom: 12px;
    background: transparent;
    margin-bottom: 8px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    flex-shrink: 0;
`;

const ListScrollArea = styled.div`
    flex: 1;
    padding: 0 8px 8px;
    overflow-y: auto;
    overflow-x: hidden;
    min-height: 0;
`;

interface VehicleListProps {
    vehicles: Vehicle[];
    selectedVehicle?: Vehicle | null;
    onSelect: (vehicle: Vehicle) => void;
    filters: Record<string, any>;
    onFilterChange: (filters: Record<string, any>) => void;
    onSearch: (value: string) => void;
    onReset: () => void;
    onEdit?: () => void;
    onDelete?: () => void;
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
    t 
}) => (
    <ListContainer>
        {/* Filter Section */}
        <FilterContainer>
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
        </FilterContainer>

        {/* Scrollable List */}
        <ListScrollArea>
            <List
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
        </ListScrollArea>
    </ListContainer>
);

export default VehicleList; 