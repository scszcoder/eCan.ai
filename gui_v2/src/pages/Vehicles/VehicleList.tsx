import React from 'react';
import { Empty } from 'antd';
import styled from '@emotion/styled';
import type { Vehicle } from '@/types/domain/vehicle';
import VehicleItem from './VehicleItem';
import SearchFilter from '../../components/Common/SearchFilter';

export type VehicleViewMode = 'list' | 'grid';

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

const GridScrollArea = styled.div`
    flex: 1;
    padding: 4px 12px 12px;
    overflow-y: auto;
    overflow-x: hidden;
    min-height: 0;
`;

const GridContainer = styled.div`
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 12px;
    align-items: stretch;

    @media (min-width: 1600px) {
        grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    }

    @media (max-width: 1200px) {
        grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    }

    @media (max-width: 768px) {
        grid-template-columns: 1fr;
    }
`;

const EmptyWrapper = styled.div`
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    min-height: 240px;
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
    viewMode?: VehicleViewMode;
    t: any;
}

const VehicleList: React.FC<VehicleListProps> = ({
    vehicles,
    selectedVehicle,
    onSelect,
    onFilterChange,
    onSearch,
    onReset,
    viewMode = 'list',
    t,
}) => {
    const isGrid = viewMode === 'grid';
    const isEmpty = vehicles.length === 0;

    return (
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

            {/* Empty state */}
            {isEmpty && (
                <EmptyWrapper>
                    <Empty
                        description={t('pages.vehicles.noDevices', '暂无电脑设备')}
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                    />
                </EmptyWrapper>
            )}

            {/* List View */}
            {!isEmpty && !isGrid && (
                <ListScrollArea>
                    {vehicles.map((vehicle, index) => (
                        <VehicleItem
                            key={`${vehicle.id || vehicle.vid || 'veh'}-${index}`}
                            vehicle={vehicle}
                            selected={selectedVehicle?.id === vehicle.id}
                            onClick={onSelect}
                            viewMode="list"
                            t={t}
                        />
                    ))}
                </ListScrollArea>
            )}

            {/* Grid View */}
            {!isEmpty && isGrid && (
                <GridScrollArea>
                    <GridContainer>
                        {vehicles.map((vehicle, index) => (
                            <VehicleItem
                                key={`${vehicle.id || vehicle.vid || 'veh'}-${index}`}
                                vehicle={vehicle}
                                selected={selectedVehicle?.id === vehicle.id}
                                onClick={onSelect}
                                viewMode="grid"
                                t={t}
                            />
                        ))}
                    </GridContainer>
                </GridScrollArea>
            )}
        </ListContainer>
    );
};

export default VehicleList;
