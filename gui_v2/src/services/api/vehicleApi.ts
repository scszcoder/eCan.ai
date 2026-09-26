/**
 * Vehicle API Service
 * 设备/车辆Related to API 调用封装
 */

import { createIPCAPI } from '../ipc/api';
import type { IPCAPI } from '../ipc/api';
import { ResourceAPI, APIResponse } from '../../stores/base/types';
import { Vehicle, CreateVehicleInput, UpdateVehicleInput } from '../../types/domain/vehicle';
import { logger } from '../../utils/logger';

// A desktop heartbeats every 60 s; three missed = offline (same as the desktop's list).
const ONLINE_WITHIN_MS = 180_000;
const LEGACY_NAME = /:(win|mac|linux|other)$/i;

function heartbeatAgeMs(stamp?: string | null): number | null {
  if (!stamp) return null;
  let s = String(stamp).trim();
  if (!/[zZ]|[+-]\d\d:?\d\d$/.test(s)) s = `${s.replace(' ', 'T')}Z`;   // the server stamps UTC
  const t = Date.parse(s);
  return Number.isNaN(t) ? null : Date.now() - t;
}

/** One cloud vehicle row as a Computers-page entry, or null when it isn't a live machine. */
export function fromCloudVehicleRow(row: any): Vehicle | null {
  if (!row?.id) return null;
  let meta: any = row.extra_metadata;
  if (typeof meta === 'string') { try { meta = JSON.parse(meta); } catch { meta = {}; } }
  const isPod = row.vehicle_type === 'pod';
  if (isPod && row.status !== 'online') return null;           // pod tombstones: Pods panel
  if (!isPod && !row.last_heartbeat) return null;              // never-stamped legacy duplicates
  const age = heartbeatAgeMs(row.last_heartbeat);
  const online = isPod || (row.status === 'online' && age !== null && age < ONLINE_WITHIN_MS);
  return {
    id: String(row.id),
    name: String(row.name || row.hostname || row.id).replace(LEGACY_NAME, ''),
    role: String(meta?.role || ''),
    type: isPod ? 'cloud' : 'desktop',
    status: online ? 'active' : 'offline',
    ip: row.ip_address || '',
    os: row.platform || '',
    arch: row.architecture || '',
    last_heartbeat: row.last_heartbeat || undefined,
    owner: row.owner,
  } as Vehicle;
}

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
        
        // Web: raw cloud rows -> the page's machine entries (the desktop's
        // local server already returns them in that shape).
        if (vehicles.some(v => 'vehicle_type' in (v as any) && !('source' in (v as any)))) {
          vehicles = vehicles.map(v => fromCloudVehicleRow(v as any)).filter(Boolean) as Vehicle[];
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
        // The identifier has to survive as-is. In-memory vehicles serialize
        // `vid` (a number) while DB-backed rows carry a non-numeric string
        // `id`, and parseInt() turned the latter into NaN — which JSON
        // encodes as null, so the handler was told no id had been sent at all
        // and answered INVALID_PARAMS.
        const vehicleId = updatedVehicle.vid ?? updatedVehicle.id ?? id;
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

