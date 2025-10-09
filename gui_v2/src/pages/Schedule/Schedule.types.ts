// 后端任务调度(TaskSchedule)数据结构
export interface TaskSchedule {
  repeat_type: 'none' | 'by seconds' | 'by minutes' | 'by hours' | 'by days' | 'by weeks' | 'by months' | 'by years';
  repeat_number: number;
  repeat_unit: 'second' | 'minute' | 'hour' | 'day' | 'week' | 'month' | 'year';
  start_date_time: string; // "YYYY-MM-DD HH:mm:ss:SSS"
  end_date_time: string;   // "YYYY-MM-DD HH:mm:ss:SSS"
  time_out: number;
  week_days?: Array<'M' | 'Tu' | 'W' | 'Th' | 'F' | 'SA' | 'SU'>;
  months?: Array<'Jan' | 'Feb' | 'Mar' | 'Apr' | 'May' | 'Jun' | 'Jul' | 'Aug' | 'Sep' | 'Oct' | 'Nov' | 'Dec'>;
  custom_fields?: Record<string, any>;
  // Task information
  taskId?: string;
  taskName?: string;
} 