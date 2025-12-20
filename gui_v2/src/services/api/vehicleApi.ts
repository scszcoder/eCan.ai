/**
 * Vehicle API Service
 * 设备/车辆Related to API 调用封装
 */

import { createIPCAPI } from '../ipc/api';
import type { IPCAPI } from '../ipc/api';
import { ResourceAPI, APIResponse } from '../../stores/base/types';
import { Vehicle, CreateVehicleInput, UpdateVehicleInput } from '../../types/domain/vehicle';
import { logger } from '../../utils/logger';

/**
 * Vehicle API Service类
 * Implementation ResourceAPI Interface，提供Standard化的 CRUD Operation
 */
export class VehicleAPI implements ResourceAPI<Vehicle> {
  private _api?: IPCAPI;

  private get api(): IPCAPI {
    if (!this._api) {
      this._api = createIPCAPI();
    }
    return this._api;
  }

  /**
   * GetAll设备
   */
  async getAll(username: string): Promise<APIResponse<Vehicle[]>> {
    try {
      logger.debug('[VehicleAPI] Fetching all vehicles');
      
      const response = await this.api.getVehicles();
      
      if (response && response.success && response.data) {
        // Process不同的Response格式
        let vehicles: Vehicle[] = [];
        
        if (Array.isArray(response.data)) {
          vehicles = response.data;
        } else if (response.data && typeof response.data === 'object' && 'vehicles' in response.data) {
          vehicles = (response.data as any).vehicles || [];
        }
        
        // 确保每个 vehicle 都有 id Field
        vehicles = vehicles.map(v => ({
          ...v,
          id: v.id || (v.vid ? String(v.vid) : ''),
        }));
        
        logger.debug('[VehicleAPI] Successfully fetched vehicles:', vehicles.length);
        
        return {
          success: true,
          data: vehicles,
        };
      } else {
        throw new Error(response.error?.message || 'Failed to fetch vehicles');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      logger.error('[VehicleAPI] Error fetching vehicles:', errorMessage);
      
      return {
        success: false,
        error: {
          code: 'FETCH_VEHICLES_ERROR',
          message: errorMessage,
        },
      };
    }
  }

  /**
   * 根据 ID Get单个设备
   */
  async getById(username: string, id: string): Promise<APIResponse<Vehicle>> {
    try {
      logger.debug('[VehicleAPI] Fetching vehicle by ID:', id);
      
      // 通过 getAll 然后Filter
      const allVehiclesResponse = await this.getAll(username);
      
      if (allVehiclesResponse.success && allVehiclesResponse.data) {
        const vehicle = allVehiclesResponse.data.find(v => 
          v.id === id || (v.vid && String(v.vid) === id)
        );
        
        if (vehicle) {
          return {
            success: true,
            data: vehicle,
          };
        } else {
          throw new Error(`Vehicle not found: ${id}`);
        }
      } else {
        throw new Error(allVehiclesResponse.error?.message || 'Failed to fetch vehicle');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      logger.error('[VehicleAPI] Error fetching vehicle by ID:', errorMessage);
      
      return {
        success: false,
        error: {
          code: 'FETCH_VEHICLE_ERROR',
          message: errorMessage,
        },
      };
    }
  }

  /**
   * Create新设备
   */
  async create(username: string, vehicle: Vehicle): Promise<APIResponse<Vehicle>> {
    try {
      logger.debug('[VehicleAPI] Creating new vehicle:', vehicle.name);
      
      // Note：Backend可能没有专门的Create设备Interface
      logger.warn('[VehicleAPI] Create vehicle not implemented in backend');
      
      return {
        success: false,
        error: {
          code: 'NOT_IMPLEMENTED',
          message: 'Create vehicle operation is not implemented',
        },
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      logger.error('[VehicleAPI] Error creating vehicle:', errorMessage);
      
      return {
        success: false,
        error: {
          code: 'CREATE_VEHICLE_ERROR',
          message: errorMessage,
        },
      };
    }
  }

  /**
   * Update设备
   */
  async update(username: string, id: string, updates: Partial<Vehicle>): Promise<APIResponse<Vehicle>> {
    try {
      logger.debug('[VehicleAPI] Updating vehicle:', id);
      
      // 先Get完整的设备Data
      const vehicleResponse = await this.getById(username, id);
      
      if (!vehicleResponse.success || !vehicleResponse.data) {
        throw new Error('Vehicle not found');
      }
      
      const updatedVehicle = { ...vehicleResponse.data, ...updates };
      
      // If只是UpdateStatus，使用专门的Interface
      if (updates.status && Object.keys(updates).length === 1) {
        const vehicleId = updatedVehicle.vid || parseInt(id);
        const response = await this.api.updateVehicleStatus(vehicleId, updates.status);
        
        if (response && response.success) {
          logger.debug('[VehicleAPI] Successfully updated vehicle status');
          
          return {
            success: true,
            data: updatedVehicle,
          };
        } else {
          throw new Error(response.error?.message || 'Failed to update vehicle status');
        }
      }
      
      // 其他UpdateOperation可能Need不同的Interface
      logger.warn('[VehicleAPI] General vehicle update not fully implemented');
      
      return {
        success: true,
        data: updatedVehicle,
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      logger.error('[VehicleAPI] Error updating vehicle:', errorMessage);
      
      return {
        success: false,
        error: {
          code: 'UPDATE_VEHICLE_ERROR',
          message: errorMessage,
        },
      };
    }
  }

  /**
   * Delete设备
   */
  async delete(username: string, id: string): Promise<APIResponse<void>> {
    try {
      logger.debug('[VehicleAPI] Deleting vehicle:', id);
      
      // Note：Backend可能没有专门的Delete设备Interface
      logger.warn('[VehicleAPI] Delete vehicle not implemented in backend');
      
      return {
        success: false,
        error: {
          code: 'NOT_IMPLEMENTED',
          message: 'Delete vehicle operation is not implemented',
        },
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      logger.error('[VehicleAPI] Error deleting vehicle:', errorMessage);
      
      return {
        success: false,
        error: {
          code: 'DELETE_VEHICLE_ERROR',
          message: errorMessage,
        },
      };
    }
  }
}

// Export单例实例
export const vehicleApi = new VehicleAPI();

