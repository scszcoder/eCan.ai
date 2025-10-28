/**
 * Tasks Page特有TypeDefinition
 * BaseType请从 @/types/domain/task Import
 */

// 从 domain 层ImportBaseType
export type { Task } from '@/types/domain/task';
export { TaskStatus, TaskPriority } from '@/types/domain/task';

// Page特有Type
export interface Schedule {
  repeat_type: string;
  repeat_number: number;
  repeat_unit: string;
  start_date_time: string;
  end_date_time: string;
  time_out: number;
} 