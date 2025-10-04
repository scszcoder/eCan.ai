import React, { useCallback, useEffect, useState } from 'react';
import { message } from 'antd';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '@/stores/userStore';
import { useDetailView } from '@/hooks/useDetailView';
import DetailLayout from '../../components/Layout/DetailLayout';
import VehicleList from './VehicleList';
import VehicleDetails from './VehicleDetails';
import VehicleFormModal from './VehicleFormModal';
import { Vehicle } from './types';
import { get_ipc_api } from '@/services/ipc_api';

const Vehicles: React.FC = () => {
  const { t } = useTranslation();
  const username = useUserStore((state) => state.username) ?? '';
  const initialVehicles: Vehicle[] = [];

  const {
    selectedItem: selectedVehicle,
    items: vehicles,
    selectItem,
    setItems: setVehicles
  } = useDetailView<Vehicle>(initialVehicles);

  const [filters, setFilters] = useState<Record<string, any>>({});
  const [isAddModalVisible, setIsAddModalVisible] = useState(false);
  const [isEditModalVisible, setIsEditModalVisible] = useState(false);

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

  const handleStatusChange = useCallback(async (id: number, newStatus: Vehicle['status']) => {
    try {
      const response = await get_ipc_api().updateVehicleStatus(id, newStatus);
      if (response?.success) {
        await fetchVehicles(); // 刷新列表
      }
    } catch (error) {
      console.error('Failed to update vehicle status:', error);
    }
  }, [fetchVehicles]);

  const handleMaintenance = useCallback(async (id: number) => {
    try {
      const response = await get_ipc_api().updateVehicleStatus(id, 'maintenance');
      if (response?.success) {
        await fetchVehicles(); // 刷新列表
      }
    } catch (error) {
      console.error('Failed to set vehicle to maintenance:', error);
    }
  }, [fetchVehicles]);

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
      const response = await get_ipc_api().updateVehicle(selectedVehicle.id, values);
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
      const response = await get_ipc_api().deleteVehicle(selectedVehicle.id);
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