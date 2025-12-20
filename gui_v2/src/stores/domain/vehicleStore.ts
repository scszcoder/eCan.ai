/**
 * Vehicle Store
 * Device/Vehicle data management store
 * 
 * Uses standardized store pattern with complete CRUD functionality
 */

import { createExtendedResourceStore } from '../base/createBaseStore';
import { BaseStoreState, CACHE_DURATION } from '../base/types';
import { Vehicle, VehicleStatus, VehicleType } from '../../types/domain/vehicle';
import { VehicleAPI } from '../../services/api/vehicleApi';

/**
 * Vehicle Store extended interface
 * Adds device-specific query methods on top of the base store
 */
export interface VehicleStoreState extends BaseStoreState<Vehicle> {
  // Current selected device name (compatible with old vehicleStore)
  vehiclename: string | null;
  setVehiclename: (vehiclename: string | null) => void;
  
  // Extended query methods
  getVehiclesByStatus: (status: VehicleStatus) => Vehicle[];
  getVehiclesByType: (type: VehicleType) => Vehicle[];
  getOnlineVehicles: () => Vehicle[];
  getOfflineVehicles: () => Vehicle[];
  getAvailableVehicles: () => Vehicle[];
  getVehiclesByLocation: (location: string) => Vehicle[];
  
  // Extended operation methods
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
 * // Get devices
 * await fetchItems(username);
 * 
 * // Query online devices
 * const onlineVehicles = useVehicleStore.getState().getOnlineVehicles();
 * 
 * // Update device status
 * await useVehicleStore.getState().updateVehicleStatus(username, vehicleId, VehicleStatus.ACTIVE);
 * ```
 */
export const useVehicleStore = createExtendedResourceStore<Vehicle, VehicleStoreState>(
  {
    name: 'vehicle',
    persist: false,  // 关闭持久化，避免数据不一致
    cacheDuration: CACHE_DURATION.MEDIUM,
  },
  new VehicleAPI(),
  (baseState, set, get) => ({
    ...baseState,
    
    // Current selected device name (compatible with old vehicleStore)
    vehiclename: null,
    setVehiclename: (vehiclename: string | null) => set({ vehiclename }),
    
    // Extended query methods
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
    
    // Extended operation methods
    createVehicle: async (username: string, vehicle: Vehicle) => {
      set({ loading: true, error: null });
      
      try {
        const api = new VehicleAPI();
        const response = await api.create(username, vehicle);
        
        if (response.success && response.data) {
          // Add to local state
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
          // Update local state
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
          // Update local state
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
          // Remove from local state
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

