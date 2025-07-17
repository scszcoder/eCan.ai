import React, { useCallback, useEffect, useState } from 'react';
import { Button } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import DetailLayout from '../../components/Layout/DetailLayout';
import { useDetailView } from '../../hooks/useDetailView';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '../../stores/userStore';
import { Vehicle } from './types';
import VehicleList from './VehicleList';
import VehicleDetails from './VehicleDetails';
import { get_ipc_api } from '@/services/ipc_api';

const Vehicles: React.FC = () => {
  const { t } = useTranslation();
  const username = useUserStore((state) => state.username) ?? '';

  // 初始数据仅用于本地演示，实际数据从API获取
  const initialVehicles: Vehicle[] = [];

  const {
    selectedItem: selectedVehicle,
    items: vehicles,
    selectItem,
    updateItem,
    setItems: setVehicles
  } = useDetailView<Vehicle>(initialVehicles);

  const [filters, setFilters] = useState<Record<string, any>>({});

  // 获取车辆数据
  const fetchVehicles = useCallback(async () => {
    if (!username) return;
    const response = await get_ipc_api().getVehicles();
    if (
      response &&
      response.success &&
      response.data &&
      Array.isArray((response.data as { vehicles: Vehicle[] }).vehicles)
    ) {
      setVehicles((response.data as { vehicles: Vehicle[] }).vehicles);
    }
  }, [username, setVehicles]);

  useEffect(() => {
    fetchVehicles();
  }, [fetchVehicles]);

  const handleRefresh = useCallback(async () => {
    await fetchVehicles();
  }, [fetchVehicles]);

  const handleStatusChange = useCallback((id: number, newStatus: Vehicle['status']) => {
    updateItem(id, {
      status: newStatus,
      location:
        newStatus === 'maintenance'
          ? t('pages.vehicles.maintenanceBay')
          : newStatus === 'offline'
          ? t('pages.vehicles.chargingStation')
          : t('pages.vehicles.zoneA'),
    });
  }, [updateItem, t]);

  const handleMaintenance = useCallback((id: number) => {
    const vehicle = vehicles.find(v => v.id === id);
    if (vehicle) {
      updateItem(id, {
        status: 'maintenance',
        location: t('pages.vehicles.maintenanceBay'),
        lastMaintenance: t('pages.vehicles.lastMaintenance', { time: t('pages.schedule.justNow') }),
        nextMaintenance: t('pages.vehicles.nextMaintenance', { time: t('pages.schedule.twoWeeksFromNow') }),
      });
    }
  }, [vehicles, updateItem, t]);

  const handleSearch = (value: string) => {
    // TODO: 实现搜索逻辑
  };

  const handleFilterChange = (newFilters: Record<string, any>) => {
    setFilters(prev => ({ ...prev, ...newFilters }));
  };

  const handleReset = () => {
    setFilters({});
  };

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