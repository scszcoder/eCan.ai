/**
 * Vehicle Domain Types
 * Type definitions for devices/vehicles
 */

/**
 * Device status
 */
export enum VehicleStatus {
  ACTIVE = 'active',
  OFFLINE = 'offline',
  MAINTENANCE = 'maintenance',
  BUSY = 'busy',
  IDLE = 'idle',
}

/**
 * Device type
 */
export enum VehicleType {
  COMPUTER = 'Computer',
  DESKTOP = 'desktop',
  MOBILE = 'mobile',
  CLOUD = 'cloud',
  SERVER = 'server',
  TABLET = 'tablet',
}

/**
 * Network status
 */
export enum NetworkStatus {
  CONNECTED = 'connected',
  DISCONNECTED = 'disconnected',
  LIMITED = 'limited',
}

/**
 * Device/Vehicle type
 */
export interface Vehicle {
  // Basic information
  id: string;
  vid?: number; // Compatible with old data
  name: string;
  owner?: string;
  description?: string;
  
  // Device type and system information
  type?: VehicleType | string;
  os?: string;
  arch?: string;
  platform?: string;
  
  // Network information
  ip?: string;
  hostname?: string;
  port?: number;
  url?: string;
  
  // Status
  status: VehicleStatus | string;
  health_score?: number; // 0.0 to 1.0
  last_heartbeat?: string;
  last_update_time?: string;
  
  // Hardware specifications
  cpu_cores?: number;
  memory_gb?: number;
  storage_gb?: number;
  gpu_info?: any;
  
  // System performance metrics
  cpuUsage?: number;
  memoryUsage?: number;
  diskUsage?: number;
  networkStatus?: NetworkStatus | string;
  uptime?: number; // Uptime in seconds
  
  // Device-specific information
  battery?: number; // Battery percentage
  location?: string;
  timezone?: string;
  environment?: string; // production, staging, development, test
  
  // Maintenance information
  lastMaintenance?: string;
  nextMaintenance?: string;
  totalDistance?: number;
  
  // Tasks and capabilities
  currentTask?: string;
  bot_ids?: any[];
  functions?: string;
  capabilities?: string[];
  limitations?: string[];
  max_concurrent_tasks?: number;
  
  // Security and access
  security_level?: string;
  access_token?: string;
  ssl_enabled?: boolean;
  test_disabled?: boolean;
  
  // Extended fields
  CAP?: number;
  mstats?: any[];
  field_link?: string;
  daily_mids?: any[];
  settings?: Record<string, any>;
  extra_metadata?: Record<string, any>;
  
  // Timestamps
  createdAt?: string;
  updatedAt?: string;
}

/**
 * Create device input type
 */
export interface CreateVehicleInput {
  name: string;
  owner: string;
  type?: VehicleType;
  os?: string;
  arch?: string;
  ip?: string;
  description?: string;
  location?: string;
}

/**
 * Update device input type
 */
export interface UpdateVehicleInput {
  name?: string;
  type?: VehicleType;
  status?: VehicleStatus;
  ip?: string;
  location?: string;
  description?: string;
  currentTask?: string;
  cpuUsage?: number;
  memoryUsage?: number;
  diskUsage?: number;
  battery?: number;
}

/**
 * System information
 */
export interface SystemInfo {
  cpu_usage: number;
  memory_usage: number;
  disk_usage: number;
  network_status: NetworkStatus | string;
  uptime: number;
  battery: number;
  location: string;
  type: VehicleType | string;
}

