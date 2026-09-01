import React, { useCallback, useEffect, useState } from 'react';
import { message, Button, Space, Tooltip, Modal } from 'antd';
import { PlusOutlined, ReloadOutlined, AppstoreOutlined, UnorderedListOutlined, FullscreenOutlined, FullscreenExitOutlined, CloseOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '@/stores/userStore';
import { useVehicleStore } from '@/stores/domain/vehicleStore';
import { VehicleStatus, type Vehicle } from '@/types/domain/vehicle';
import { useDetailView } from '@/hooks/useDetailView';
import DetailLayout from '../../components/Layout/DetailLayout';
import VehicleList, { type VehicleViewMode } from './VehicleList';
import VehicleDetails from './VehicleDetails';
import VehicleFormModal from './VehicleFormModal';
import { logger } from '@/utils/logger';
import { get_ipc_api } from '@/services/ipc_api';

const StyledActionButton = styled(Button)`
  &.ant-btn {
    background: transparent !important;
    border: none !important;
    color: rgba(203, 213, 225, 0.9) !important;
    box-shadow: none !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;

    &:hover {
      background: rgba(255, 255, 255, 0.1) !important;
      color: rgba(248, 250, 252, 0.95) !important;
    }

    &:active {
      opacity: 0.8 !important;
    }

    .anticon {
      transition: all 0.3s ease !important;
    }
  }
`;

const ViewToggleContainer = styled.div`
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
`;

const ViewToggleButton = styled(Button, {
  shouldForwardProp: (prop) => prop !== '$isActive',
})<{ $isActive?: boolean }>`
  height: 32px !important;
  width: 32px !important;
  min-width: 32px !important;
  padding: 0 !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  border-radius: 6px !important;
  background: ${props => props.$isActive
    ? 'linear-gradient(135deg, rgba(59, 130, 246, 0.9) 0%, rgba(99, 102, 241, 0.9) 100%)'
    : 'transparent'} !important;
  border: ${props => props.$isActive
    ? '1px solid rgba(59, 130, 246, 0.5)'
    : '1px solid transparent'} !important;
  color: ${props => props.$isActive ? 'white' : 'rgba(203, 213, 225, 0.9)'} !important;
  transition: all 0.2s ease !important;

  &:hover {
    background: linear-gradient(135deg, rgba(59, 130, 246, 0.9) 0%, rgba(99, 102, 241, 0.9) 100%) !important;
    color: white !important;
    border-color: rgba(59, 130, 246, 0.5) !important;
  }

  .anticon {
    font-size: 16px;
  }
`;

const DeviceDetailModal = styled(Modal)<{ $fullscreen?: boolean }>`
  .ant-modal-content {
    background: var(--bg-primary) !important;
    height: ${props => props.$fullscreen ? '100vh' : '88vh'};
    max-height: ${props => props.$fullscreen ? '100vh' : '88vh'};
    display: flex;
    flex-direction: column;
    padding: 0;
    overflow: hidden;
    border-radius: ${props => props.$fullscreen ? '0' : '16px'};
  }

  .ant-modal-header {
    padding: 14px 18px;
    background: linear-gradient(135deg, rgba(59, 130, 246, 0.12) 0%, rgba(99, 102, 241, 0.08) 100%);
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  }

  .ant-modal-title {
    color: var(--text-primary);
  }

  .ant-modal-body {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    padding: 0;
    overflow: hidden;
  }
`;

const ModalTitleRow = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
`;

const ModalTitleMeta = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
`;

const ModalTitleName = styled.div`
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const ModalActions = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
`;

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
  const [viewMode, setViewMode] = useState<VehicleViewMode>('grid');
  const [isGridDetailOpen, setIsGridDetailOpen] = useState(false);
  const [isGridDetailFullscreen, setIsGridDetailFullscreen] = useState(false);

  // Get车辆Data
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
      await fetchVehicles(); // RefreshList
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
      await fetchVehicles(); // RefreshList
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

    // ConfirmDelete
    if (!window.confirm(t('pages.vehicles.confirmDelete', { name: selectedVehicle.name }))) {
      return;
    }

    try {
      // Convert string id to number if needed
      const vehicleId = typeof selectedVehicle.id === 'string' ? parseInt(selectedVehicle.id) : selectedVehicle.id;
      const response = await get_ipc_api().deleteVehicle(vehicleId);
      if (response?.success) {
        await fetchVehicles(); // RefreshList
      } else {
        alert(t('pages.vehicles.deleteFailed'));
      }
    } catch (error) {
      console.error('Failed to delete vehicle:', error);
      alert(t('pages.vehicles.deleteFailed'));
    }
  }, [selectedVehicle, fetchVehicles, t]);

  const handleSearch = (_value: string) => {
    // TODO: ImplementationSearch逻辑
  };

  const handleFilterChange = (newFilters: Record<string, any>) => {
    setFilters(prev => ({ ...prev, ...newFilters }));
  };

  const handleReset = () => {
    setFilters({});
  };

  // Handle vehicle selection — in grid mode, open detail modal
  const handleSelectVehicle = useCallback((vehicle: Vehicle) => {
    selectItem(vehicle);
    if (viewMode === 'grid') {
      setIsGridDetailOpen(true);
    }
  }, [selectItem, viewMode]);

  const handleCloseGridDetail = useCallback(() => {
    setIsGridDetailOpen(false);
    setIsGridDetailFullscreen(false);
    selectItem(null as any);
  }, [selectItem]);

  // Keyboard navigation in grid mode
  useEffect(() => {
    if (!isGridDetailOpen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        handleCloseGridDetail();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isGridDetailOpen, handleCloseGridDetail]);

  const listTitle = (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
      <span style={{ fontSize: '16px', fontWeight: 600, lineHeight: '24px' }}>{t('pages.vehicles.title')}</span>
      <Space size={0}>
        <ViewToggleContainer>
          <Tooltip title={t('pages.vehicles.view.list', '列表视图')}>
            <ViewToggleButton
              $isActive={viewMode === 'list'}
              onClick={() => setViewMode('list')}
              icon={<UnorderedListOutlined />}
            />
          </Tooltip>
          <Tooltip title={t('pages.vehicles.view.grid', '网格视图')}>
            <ViewToggleButton
              $isActive={viewMode === 'grid'}
              onClick={() => setViewMode('grid')}
              icon={<AppstoreOutlined />}
            />
          </Tooltip>
        </ViewToggleContainer>
        <Tooltip title={t('pages.vehicles.refreshVehicles', 'Refresh')}>
          <StyledActionButton
            shape="circle"
            icon={<ReloadOutlined />}
            onClick={handleRefresh}
          />
        </Tooltip>
        <Tooltip title={t('pages.vehicles.addVehicle', 'Add车辆')}>
          <StyledActionButton
            shape="circle"
            icon={<PlusOutlined />}
            onClick={handleAdd}
          />
        </Tooltip>
      </Space>
    </div>
  );

  return (
    <>
      <DetailLayout
        listTitle={listTitle}
        detailsTitle={t('pages.vehicles.vehicleInformation')}
        listContent={
          <VehicleList
            vehicles={vehicles}
            selectedVehicle={selectedVehicle}
            onSelect={handleSelectVehicle}
            filters={filters}
            onFilterChange={handleFilterChange}
            onSearch={handleSearch}
            onReset={handleReset}
            onEdit={handleEdit}
            onDelete={handleDelete}
            viewMode={viewMode}
            t={t}
          />
        }
        detailsContent={
          viewMode === 'list' && selectedVehicle ? (
            <VehicleDetails
              vehicle={selectedVehicle}
              onStatusChange={handleStatusChange}
              onMaintenance={handleMaintenance}
              t={t}
            />
          ) : undefined
        }
        defaultListWidth={viewMode === 'grid' ? 560 : 400}
        minListWidth={viewMode === 'grid' ? 480 : 340}
        maxListWidth={viewMode === 'grid' ? 720 : 600}
        fillListAvailableWidth={viewMode === 'grid'}
        fillDetailsAvailableWidth={viewMode === 'list'}
      />

      {/* Grid View Detail Modal */}
      <DeviceDetailModal
        open={isGridDetailOpen && viewMode === 'grid'}
        onCancel={handleCloseGridDetail}
        footer={null}
        width={isGridDetailFullscreen ? '100vw' : 'min(1200px, 96vw)'}
        style={isGridDetailFullscreen ? { top: 0, paddingBottom: 0 } : undefined}
        centered={!isGridDetailFullscreen}
        destroyOnHidden={false}
        closable={false}
        $fullscreen={isGridDetailFullscreen}
        title={
          <ModalTitleRow>
            <ModalTitleMeta>
              <ModalTitleName>
                {selectedVehicle?.name || t('pages.vehicles.vehicleInformation')}
              </ModalTitleName>
            </ModalTitleMeta>
            <ModalActions>
              <Tooltip title={isGridDetailFullscreen ? t('common.exitFullscreen', '退出全屏') : t('common.fullscreen', '全屏')}>
                <StyledActionButton
                  shape="circle"
                  icon={isGridDetailFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
                  onClick={() => setIsGridDetailFullscreen((prev) => !prev)}
                />
              </Tooltip>
              <Tooltip title={t('common.close', '关闭')}>
                <StyledActionButton
                  shape="circle"
                  icon={<CloseOutlined />}
                  onClick={handleCloseGridDetail}
                />
              </Tooltip>
            </ModalActions>
          </ModalTitleRow>
        }
      >
        {isGridDetailOpen && selectedVehicle ? (
          <VehicleDetails
            vehicle={selectedVehicle}
            onStatusChange={handleStatusChange}
            onMaintenance={handleMaintenance}
            t={t}
          />
        ) : null}
      </DeviceDetailModal>

      {/* Add Vehicle Dialog */}
      <VehicleFormModal
        visible={isAddModalVisible}
        vehicle={null}
        onOk={handleAddSubmit}
        onCancel={() => setIsAddModalVisible(false)}
        t={t}
      />

      {/* Edit Vehicle Dialog */}
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
