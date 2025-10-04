export interface Vehicle {
    id: number; // 兼容原 vid 字段
    vid?: number; // 兼容旧数据
    ip?: string;
    name: string;
    type?: string; // 设备类型
    os?: string;
    arch?: string;
    bot_ids?: any[];
    status: 'active' | 'maintenance' | 'offline' | string;
    functions?: string;
    test_disabled?: boolean;
    last_update_time?: string;
    
    // 设备信息字段
    battery?: number;
    location?: string;
    lastMaintenance?: string;
    totalDistance?: number;
    currentTask?: string;
    nextMaintenance?: string;
    
    // 系统性能指标
    cpuUsage?: number;
    memoryUsage?: number;
    diskUsage?: number;
    networkStatus?: string;
    uptime?: number;
    
    // 原有扩展字段
    CAP?: number;
    mstats?: any[];
    field_link?: string;
    daily_mids?: any[];
} 