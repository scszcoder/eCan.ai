/**
 * Vehicle API Service
 * 设备/车辆相关的 API 调用封装
 */

import { createIPCAPI } from '../ipc/api';
import type { IPCAPI } from '../ipc/api';
import { ResourceAPI, APIResponse } from '../../stores/base/types';
import { Vehicle, CreateVehicleInput, UpdateVehicleInput } from '../../types/domain/vehicle';
import { logger } from '../../utils/logger';

/**
 * Vehicle API 服务类
 * 实现 ResourceAPI 接口，提供标准化的 CRUD 操作
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
   * 获取所有设备
   */
  async getAll(username: string): Promise<APIResponse<Vehicle[]>> {
    try {
      logger.debug('[VehicleAPI] Fetching all vehicles');
      
      const response = await this.api.getVehicles();
      
      if (response && response.success && response.data) {
        // 处理不同的响应格式
        let vehicles: Vehicle[] = [];
        
        if (Array.isArray(response.data)) {
          vehicles = response.data;
        } else if (response.data && typeof response.data === 'object' && 'vehicles' in response.data) {
          vehicles = (response.data as any).vehicles || [];
        }
        
        // 确保每个 vehicle 都有 id 字段
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
   * 根据 ID 获取单个设备
   */
  async getById(username: string, id: string): Promise<APIResponse<Vehicle>> {
    try {
      logger.debug('[VehicleAPI] Fetching vehicle by ID:', id);
      
      // 通过 getAll 然后过滤
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
   * 创建新设备
   */
  async create(username: string, vehicle: Vehicle): Promise<APIResponse<Vehicle>> {
    try {
      logger.debug('[VehicleAPI] Creating new vehicle:', vehicle.name);
      
      // 注意：后端可能没有专门的创建设备接口
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
   * 更新设备
   */
  async update(username: string, id: string, updates: Partial<Vehicle>): Promise<APIResponse<Vehicle>> {
    try {
      logger.debug('[VehicleAPI] Updating vehicle:', id);
      
      // 先获取完整的设备数据
      const vehicleResponse = await this.getById(username, id);
      
      if (!vehicleResponse.success || !vehicleResponse.data) {
        throw new Error('Vehicle not found');
      }
      
      const updatedVehicle = { ...vehicleResponse.data, ...updates };
      
      // 如果只是更新状态，使用专门的接口
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
      
      // 其他更新操作可能需要不同的接口
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
   * 删除设备
   */
  async delete(username: string, id: string): Promise<APIResponse<void>> {
    try {
      logger.debug('[VehicleAPI] Deleting vehicle:', id);
      
      // 注意：后端可能没有专门的删除设备接口
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

// 导出单例实例
export const vehicleApi = new VehicleAPI();

