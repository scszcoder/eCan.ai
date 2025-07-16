export interface Vehicle {
    id: number; // 兼容原 vid 字段
    vid?: number; // 兼容旧数据
    ip?: string;
    name: string;
    type?: string; // 新增，兼容页面
    os?: string;
    arch?: string;
    bot_ids?: any[];
    status: 'active' | 'maintenance' | 'offline' | string;
    functions?: string;
    test_disabled?: boolean;
    last_update_time?: string;
    battery?: number;
    location?: string;
    lastMaintenance?: string;
    totalDistance?: number;
    currentTask?: string;
    nextMaintenance?: string;
    // 新增字段
    CAP?: number;
    mstats?: any[];
    field_link?: string;
    daily_mids?: any[];
} 