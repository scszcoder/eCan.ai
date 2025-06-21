// 车辆相关的类型定义
export interface Vehicle {
  vid: number;
  ip: string;
  name: string;
  os: string;
  arch: string;
  bot_ids: any[];
  status: string;
  functions: string;
  test_disabled: boolean;
  last_update_time: string;
} 