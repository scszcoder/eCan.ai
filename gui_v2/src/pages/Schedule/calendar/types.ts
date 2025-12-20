/**
 * Calendar View Types and Interfaces
 * 日历视图TypeDefinition
 */

import { TaskSchedule } from '../Schedule.types';
import { Task } from '@/types/domain/task';

/**
 * 日历视图Type
 */
export enum CalendarViewType {
  MONTH = 'month',
  WEEK = 'week',
  DAY = 'day',
}

/**
 * 日程Event（Used for日历Display）
 */
export interface CalendarEvent {
  id: string;
  title: string;
  start: Date;
  end: Date;
  allDay?: boolean;
  
  // 关联的任务和日程Information
  taskId?: string;
  taskName?: string;
  schedule: TaskSchedule;
  task?: Task;
  
  // EventType
  isRecurring: boolean; // 是否是重复Event
  isOneTime: boolean;   // 是否是一次性Event
  
  // ExecuteStatus
  executionStatus?: 'running' | 'scheduled' | 'completed' | 'pending' | 'error';
  isLongPeriod?: boolean;     // 是否是长周期任务
  isNextExecution?: boolean;  // 是否是计算的下次ExecuteTime
  
  // StatusInformation
  status?: string;
  priority?: string;
  
  // Display样式
  color?: string;
  backgroundColor?: string;
  borderColor?: string;
  
  // ExtendedInformation
  metadata?: Record<string, any>;
}

/**
 * 日历Date单元格
 */
export interface CalendarDateCell {
  date: Date;
  isToday: boolean;
  isCurrentMonth: boolean;
  isWeekend: boolean;
  events: CalendarEvent[];
  hasEvents: boolean;
  eventCount: number;
}

/**
 * 日历周Information
 */
export interface CalendarWeek {
  weekNumber: number;
  days: CalendarDateCell[];
}

/**
 * 日历月Information
 */
export interface CalendarMonth {
  year: number;
  month: number; // 0-11
  weeks: CalendarWeek[];
  firstDay: Date;
  lastDay: Date;
}

/**
 * Time段（Used for日视图和周视图）
 */
export interface TimeSlot {
  hour: number;
  minute: number;
  label: string;
  events: CalendarEvent[];
}

/**
 * 日历Filter器
 */
export interface CalendarFilters {
  taskIds?: string[];
  statuses?: string[];
  priorities?: string[];
  showRecurring?: boolean;
  showOneTime?: boolean;
  searchQuery?: string;
}

/**
 * 日历Configuration
 */
export interface CalendarConfig {
  weekStartsOn: 0 | 1; // 0=Sunday, 1=Monday
  timeSlotDuration: number; // minutes
  dayStartHour: number; // 0-23
  dayEndHour: number; // 0-23
  showWeekNumbers: boolean;
  showWeekends: boolean;
  locale: string;
}

/**
 * EventTime冲突
 */
export interface EventConflict {
  event1: CalendarEvent;
  event2: CalendarEvent;
  overlapDuration: number; // minutes
}

