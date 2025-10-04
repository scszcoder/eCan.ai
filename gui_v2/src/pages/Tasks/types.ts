/**
 * Tasks 页面特有类型定义
 * 基础类型请从 @/types/domain/task 导入
 */

// 从 domain 层导入基础类型
export type { Task } from '@/types/domain/task';
export { TaskStatus, TaskPriority } from '@/types/domain/task';

// 页面特有类型
export interface Schedule {
  repeat_type: string;
  repeat_number: number;
  repeat_unit: string;
  start_date_time: string;
  end_date_time: string;
  time_out: number;
} 