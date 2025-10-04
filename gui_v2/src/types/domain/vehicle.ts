/**
 * Vehicle Domain Types
 * 设备/车辆相关的类型定义
 */

/**
 * 设备状态
 */
export enum VehicleStatus {
  ACTIVE = 'active',
  OFFLINE = 'offline',
  MAINTENANCE = 'maintenance',
  BUSY = 'busy',
  IDLE = 'idle',
}

/**
 * 设备类型
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
 * 网络状态
 */
export enum NetworkStatus {
  CONNECTED = 'connected',
  DISCONNECTED = 'disconnected',
  LIMITED = 'limited',
}

/**
 * 设备/车辆类型
 */
export interface Vehicle {
  // 基础信息
  id: string;
  vid?: number; // 兼容旧数据
  name: string;
  owner?: string;
  description?: string;
  
  // 设备类型和系统信息
  type?: VehicleType | string;
  os?: string;
  arch?: string;
  platform?: string;
  
  // 网络信息
  ip?: string;
  hostname?: string;
  port?: number;
  url?: string;
  
  // 状态
  status: VehicleStatus | string;
  health_score?: number; // 0.0 to 1.0
  last_heartbeat?: string;
  last_update_time?: string;
  
  // 硬件规格
  cpu_cores?: number;
  memory_gb?: number;
  storage_gb?: number;
  gpu_info?: any;
  
  // 系统性能指标
  cpuUsage?: number;
  memoryUsage?: number;
  diskUsage?: number;
  networkStatus?: NetworkStatus | string;
  uptime?: number; // 运行时间（秒）
  
  // 设备特定信息
  battery?: number; // 电池百分比
  location?: string;
  timezone?: string;
  environment?: string; // production, staging, development, test
  
  // 维护信息
  lastMaintenance?: string;
  nextMaintenance?: string;
  totalDistance?: number;
  
  // 任务和能力
  currentTask?: string;
  bot_ids?: any[];
  functions?: string;
  capabilities?: string[];
  limitations?: string[];
  max_concurrent_tasks?: number;
  
  // 安全和访问
  security_level?: string;
  access_token?: string;
  ssl_enabled?: boolean;
  test_disabled?: boolean;
  
  // 扩展字段
  CAP?: number;
  mstats?: any[];
  field_link?: string;
  daily_mids?: any[];
  settings?: Record<string, any>;
  extra_metadata?: Record<string, any>;
  
  // 时间戳
  createdAt?: string;
  updatedAt?: string;
}

/**
 * 创建设备的输入类型
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
 * 更新设备的输入类型
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
 * 系统信息
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

