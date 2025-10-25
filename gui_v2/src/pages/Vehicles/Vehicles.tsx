import React, { useCallback, useEffect, useState } from 'react';
import { message } from 'antd';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '@/stores/userStore';
import { useVehicleStore, VehicleStatus, type Vehicle } from '@/stores';
import { useDetailView } from '@/hooks/useDetailView';
import DetailLayout from '../../components/Layout/DetailLayout';
import VehicleList from './VehicleList';
import VehicleDetails from './VehicleDetails';
import VehicleFormModal from './VehicleFormModal';
import { logger } from '@/utils/logger';
import { get_ipc_api } from '@/services/ipc_api';

const Vehicles: React.FC = () => {
  const { t } = useTranslation();
  const username = useUserStore((state) => state.username) ?? '';

  // 使用新的 vehicleStore
  const vehicles = useVehicleStore((state) => state.items);
  const fetchItems = useVehicleStore((state) => state.fetchItems);
  const forceRefresh = useVehicleStore((state) => state.forceRefresh);
  const updateVehicleStatus = useVehicleStore((state) => state.updateVehicleStatus);

  const {
    selectedItem: selectedVehicle,
    selectItem,
  } = useDetailView<Vehicle>(vehicles);

  const [filters, setFilters] = useState<Record<string, any>>({});
  const [isAddModalVisible, setIsAddModalVisible] = useState(false);
  const [isEditModalVisible, setIsEditModalVisible] = useState(false);

  // 获取车辆数据
  const fetchVehicles = useCallback(async () => {
    if (!username) return;

    try {
      await fetchItems(username);
    } catch (error) {
      logger.error('[Vehicles] Error fetching vehicles:', error);
      message.error(t('pages.vehicles.fetchError') || 'Failed to fetch vehicles');
    }
  }, [username, fetchItems, t]);

  useEffect(() => {
    fetchVehicles();
  }, [fetchVehicles]);

  const handleRefresh = useCallback(async () => {
    if (!username) return;

    try {
      await forceRefresh(username);
    } catch (error) {
      logger.error('[Vehicles] Error refreshing vehicles:', error);
      message.error(t('pages.vehicles.fetchError') || 'Failed to refresh vehicles');
    }
  }, [username, forceRefresh, t]);

  const handleStatusChange = useCallback(async (id: string | number, newStatus: Vehicle['status']) => {
    if (!username) return;

    try {
      await updateVehicleStatus(username, String(id), newStatus as VehicleStatus);
      message.success(t('pages.vehicles.statusUpdateSuccess') || 'Status updated successfully');
      await fetchVehicles(); // 刷新列表
    } catch (error) {
      logger.error('[Vehicles] Failed to update vehicle status:', error);
      message.error(t('pages.vehicles.statusUpdateFailed') || 'Failed to update status');
    }
  }, [username, updateVehicleStatus, fetchVehicles, t]);

  const handleMaintenance = useCallback(async (id: string | number) => {
    if (!username) return;

    try {
      await updateVehicleStatus(username, String(id), VehicleStatus.MAINTENANCE);
      message.success(t('pages.vehicles.maintenanceSuccess') || 'Vehicle set to maintenance');
      await fetchVehicles(); // 刷新列表
    } catch (error) {
      logger.error('[Vehicles] Failed to set vehicle to maintenance:', error);
      message.error(t('pages.vehicles.maintenanceFailed') || 'Failed to set maintenance status');
    }
  }, [username, updateVehicleStatus, fetchVehicles, t]);

  const handleAdd = useCallback(() => {
    setIsAddModalVisible(true);
  }, []);

  const handleEdit = useCallback(() => {
    if (selectedVehicle) {
      setIsEditModalVisible(true);
    }
  }, [selectedVehicle]);

  const handleAddSubmit = useCallback(async (values: any) => {
    try {
      const response = await get_ipc_api().addVehicle(values);
      if (response?.success) {
        message.success(t('pages.vehicles.addSuccess'));
        setIsAddModalVisible(false);
        await fetchVehicles();
      } else {
        message.error(t('pages.vehicles.addFailed'));
      }
    } catch (error) {
      console.error('Failed to add vehicle:', error);
      message.error(t('pages.vehicles.addFailed'));
    }
  }, [fetchVehicles, t]);

  const handleEditSubmit = useCallback(async (values: any) => {
    if (!selectedVehicle) return;

    try {
      // Convert string id to number if needed
      const vehicleId = typeof selectedVehicle.id === 'string' ? parseInt(selectedVehicle.id) : selectedVehicle.id;
      const response = await get_ipc_api().updateVehicle(vehicleId, values);
      if (response?.success) {
        message.success(t('pages.vehicles.updateSuccess'));
        setIsEditModalVisible(false);
        await fetchVehicles();
      } else {
        message.error(t('pages.vehicles.updateFailed'));
      }
    } catch (error) {
      console.error('Failed to update vehicle:', error);
      message.error(t('pages.vehicles.updateFailed'));
    }
  }, [selectedVehicle, fetchVehicles, t]);

  const handleDelete = useCallback(async () => {
    if (!selectedVehicle) return;

    // 确认删除
    if (!window.confirm(t('pages.vehicles.confirmDelete', { name: selectedVehicle.name }))) {
      return;
    }

    try {
      // Convert string id to number if needed
      const vehicleId = typeof selectedVehicle.id === 'string' ? parseInt(selectedVehicle.id) : selectedVehicle.id;
      const response = await get_ipc_api().deleteVehicle(vehicleId);
      if (response?.success) {
        await fetchVehicles(); // 刷新列表
      } else {
        alert(t('pages.vehicles.deleteFailed'));
      }
    } catch (error) {
      console.error('Failed to delete vehicle:', error);
      alert(t('pages.vehicles.deleteFailed'));
    }
  }, [selectedVehicle, fetchVehicles, t]);

  const handleSearch = (_value: string) => {
    // TODO: 实现搜索逻辑
  };

  const handleFilterChange = (newFilters: Record<string, any>) => {
    setFilters(prev => ({ ...prev, ...newFilters }));
  };

  const handleReset = () => {
    setFilters({});
  };

  return (
    <>
      <DetailLayout
        listTitle={t('pages.vehicles.title')}
        detailsTitle={t('pages.vehicles.vehicleInformation')}
        listContent={
          <VehicleList
            vehicles={vehicles}
            selectedVehicle={selectedVehicle}
            onSelect={selectItem}
            filters={filters}
            onFilterChange={handleFilterChange}
            onSearch={handleSearch}
            onReset={handleReset}
            onAdd={handleAdd}
            onEdit={handleEdit}
            onDelete={handleDelete}
            onRefresh={handleRefresh}
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
      
      {/* 添加 Vehicle 对话框 */}
      <VehicleFormModal
        visible={isAddModalVisible}
        vehicle={null}
        onOk={handleAddSubmit}
        onCancel={() => setIsAddModalVisible(false)}
        t={t}
      />
      
      {/* 编辑 Vehicle 对话框 */}
      <VehicleFormModal
        visible={isEditModalVisible}
        vehicle={selectedVehicle}
        onOk={handleEditSubmit}
        onCancel={() => setIsEditModalVisible(false)}
        t={t}
      />
    </>
  );
};

export default Vehicles; 