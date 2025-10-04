/**
 * Vehicle Store
 * 设备/车辆数据管理 Store
 * 
 * 使用标准化的 store 模式，提供完整的 CRUD 功能
 */

import { createExtendedResourceStore } from '../base/createBaseStore';
import { BaseStoreState, CACHE_DURATION } from '../base/types';
import { Vehicle, VehicleStatus, VehicleType } from '../../types/domain/vehicle';
import { VehicleAPI } from '../../services/api/vehicleApi';

/**
 * Vehicle Store 扩展接口
 * 在基础 store 之上添加设备特定的查询方法
 */
export interface VehicleStoreState extends BaseStoreState<Vehicle> {
  // 当前选中的设备名称（兼容旧的 vehicleStore）
  vehiclename: string | null;
  setVehiclename: (vehiclename: string | null) => void;
  
  // 扩展查询方法
  getVehiclesByStatus: (status: VehicleStatus) => Vehicle[];
  getVehiclesByType: (type: VehicleType) => Vehicle[];
  getOnlineVehicles: () => Vehicle[];
  getOfflineVehicles: () => Vehicle[];
  getAvailableVehicles: () => Vehicle[];
  getVehiclesByLocation: (location: string) => Vehicle[];
  
  // 扩展操作方法
  createVehicle: (username: string, vehicle: Vehicle) => Promise<void>;
  updateVehicle: (username: string, vehicleId: string, updates: Partial<Vehicle>) => Promise<void>;
  updateVehicleStatus: (username: string, vehicleId: string, status: VehicleStatus) => Promise<void>;
  deleteVehicle: (username: string, vehicleId: string) => Promise<void>;
}

/**
 * Vehicle Store
 * 
 * @example
 * ```typescript
 * const { items: vehicles, loading, fetchItems } = useVehicleStore();
 * 
 * // 获取设备
 * await fetchItems(username);
 * 
 * // 查询在线设备
 * const onlineVehicles = useVehicleStore.getState().getOnlineVehicles();
 * 
 * // 更新设备状态
 * await useVehicleStore.getState().updateVehicleStatus(username, vehicleId, VehicleStatus.ACTIVE);
 * ```
 */
export const useVehicleStore = createExtendedResourceStore<Vehicle, VehicleStoreState>(
  {
    name: 'vehicle',
    persist: true,
    cacheDuration: CACHE_DURATION.MEDIUM,
  },
  new VehicleAPI(),
  (baseState, set, get) => ({
    ...baseState,
    
    // 当前选中的设备名称（兼容旧的 vehicleStore）
    vehiclename: null,
    setVehiclename: (vehiclename: string | null) => set({ vehiclename }),
    
    // 扩展查询方法
    getVehiclesByStatus: (status: VehicleStatus) => {
      const items = get().items;
      return items.filter(vehicle => vehicle.status === status);
    },
    
    getVehiclesByType: (type: VehicleType) => {
      const items = get().items;
      return items.filter(vehicle => vehicle.type === type);
    },
    
    getOnlineVehicles: () => {
      const items = get().items;
      return items.filter(vehicle => 
        vehicle.status === VehicleStatus.ACTIVE || 
        vehicle.status === VehicleStatus.IDLE ||
        vehicle.status === 'online'
      );
    },
    
    getOfflineVehicles: () => {
      const items = get().items;
      return items.filter(vehicle => 
        vehicle.status === VehicleStatus.OFFLINE ||
        vehicle.status === 'offline'
      );
    },
    
    getAvailableVehicles: () => {
      const items = get().items;
      return items.filter(vehicle => 
        (vehicle.status === VehicleStatus.ACTIVE || 
         vehicle.status === VehicleStatus.IDLE ||
         vehicle.status === 'online') &&
        (!vehicle.health_score || vehicle.health_score > 0.5)
      );
    },
    
    getVehiclesByLocation: (location: string) => {
      const items = get().items;
      return items.filter(vehicle => vehicle.location === location);
    },
    
    // 扩展操作方法
    createVehicle: async (username: string, vehicle: Vehicle) => {
      set({ loading: true, error: null });
      
      try {
        const api = new VehicleAPI();
        const response = await api.create(username, vehicle);
        
        if (response.success && response.data) {
          // 添加到本地状态
          get().addItem(response.data);
          set({ loading: false });
        } else {
          throw new Error(response.error?.message || 'Failed to create vehicle');
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        set({ error: errorMessage, loading: false });
        throw error;
      }
    },
    
    updateVehicle: async (username: string, vehicleId: string, updates: Partial<Vehicle>) => {
      set({ loading: true, error: null });
      
      try {
        const api = new VehicleAPI();
        const response = await api.update(username, vehicleId, updates);
        
        if (response.success && response.data) {
          // 更新本地状态
          get().updateItem(vehicleId, updates);
          set({ loading: false });
        } else {
          throw new Error(response.error?.message || 'Failed to update vehicle');
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        set({ error: errorMessage, loading: false });
        throw error;
      }
    },
    
    updateVehicleStatus: async (username: string, vehicleId: string, status: VehicleStatus) => {
      set({ loading: true, error: null });
      
      try {
        const api = new VehicleAPI();
        const response = await api.update(username, vehicleId, { status });
        
        if (response.success && response.data) {
          // 更新本地状态
          get().updateItem(vehicleId, { status });
          set({ loading: false });
        } else {
          throw new Error(response.error?.message || 'Failed to update vehicle status');
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        set({ error: errorMessage, loading: false });
        throw error;
      }
    },
    
    deleteVehicle: async (username: string, vehicleId: string) => {
      set({ loading: true, error: null });
      
      try {
        const api = new VehicleAPI();
        const response = await api.delete(username, vehicleId);
        
        if (response.success) {
          // 从本地状态移除
          get().removeItem(vehicleId);
          set({ loading: false });
        } else {
          throw new Error(response.error?.message || 'Failed to delete vehicle');
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        set({ error: errorMessage, loading: false });
        throw error;
      }
    },
  })
);

