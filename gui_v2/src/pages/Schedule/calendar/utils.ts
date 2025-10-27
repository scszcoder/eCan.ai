/**
 * Calendar Utility Functions
 * 日历工具函数
 */

import dayjs from 'dayjs';
import isoWeek from 'dayjs/plugin/isoWeek';
import weekday from 'dayjs/plugin/weekday';
import isSameOrBefore from 'dayjs/plugin/isSameOrBefore';
import isSameOrAfter from 'dayjs/plugin/isSameOrAfter';
import isBetween from 'dayjs/plugin/isBetween';
import 'dayjs/locale/zh-cn';

// Initialize plugins
dayjs.extend(isoWeek);
dayjs.extend(weekday);
dayjs.extend(isSameOrBefore);
dayjs.extend(isSameOrAfter);
dayjs.extend(isBetween);
dayjs.locale('zh-cn');

import type { TaskSchedule } from '../Schedule.types';
import type {
  CalendarEvent,
  CalendarDateCell,
  CalendarWeek,
  CalendarMonth,
  TimeSlot,
  CalendarConfig,
  EventConflict,
} from './types';

/**
 * 默认日历配置
 */
export const DEFAULT_CALENDAR_CONFIG: CalendarConfig = {
  weekStartsOn: 0, // Sunday (标准日历格式)
  timeSlotDuration: 30, // 30 minutes
  dayStartHour: 0, // 从0点开始
  dayEndHour: 24, // 到24点结束（全天24小时）
  showWeekNumbers: true,
  showWeekends: true,
  locale: 'zh-CN',
};

/**
 * 状态对应的颜色
 */
export const STATUS_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  pending: {
    bg: 'rgba(250, 173, 20, 0.1)',
    border: '#faad14',
    text: '#faad14',
  },
  running: {
    bg: 'rgba(24, 144, 255, 0.1)',
    border: '#1890ff',
    text: '#1890ff',
  },
  in_progress: {
    bg: 'rgba(24, 144, 255, 0.1)',
    border: '#1890ff',
    text: '#1890ff',
  },
  completed: {
    bg: 'rgba(82, 196, 26, 0.1)',
    border: '#52c41a',
    text: '#52c41a',
  },
  failed: {
    bg: 'rgba(255, 77, 79, 0.1)',
    border: '#ff4d4f',
    text: '#ff4d4f',
  },
  cancelled: {
    bg: 'rgba(140, 140, 140, 0.1)',
    border: '#8c8c8c',
    text: '#8c8c8c',
  },
};

/**
 * 优先级对应的颜色
 */
export const PRIORITY_COLORS: Record<string, string> = {
  low: '#52c41a',
  medium: '#1890ff',
  high: '#faad14',
  urgent: '#ff4d4f',
};

/**
 * 将TaskSchedule转换为CalendarEvent
 */
export function scheduleToEvent(schedule: TaskSchedule, task?: any): CalendarEvent {
  // Parse time string: "2025-03-31 23:59:59:000" -> "2025-03-31T23:59:59.000"
  // Remove the last ":000" and replace with ".000", then replace space with "T"
  const parseTimeString = (timeStr: string) => {
    // "2025-03-31 23:59:59:000" -> ["2025-03-31 23:59:59", "000"]
    const parts = timeStr.split(':');
    if (parts.length === 4) {
      // Has milliseconds: "YYYY-MM-DD HH:MM:SS:mmm"
      const dateTimePart = parts.slice(0, 3).join(':'); // "2025-03-31 23:59:59"
      const milliseconds = parts[3]; // "000"
      return `${dateTimePart.replace(' ', 'T')}.${milliseconds}`; // "2025-03-31T23:59:59.000"
    } else {
      // No milliseconds: "YYYY-MM-DD HH:MM:SS"
      return timeStr.replace(' ', 'T');
    }
  };
  
  const startDate = dayjs(parseTimeString(schedule.start_date_time)).toDate();
  const endDate = dayjs(parseTimeString(schedule.end_date_time)).toDate();
  
  const isRecurring = schedule.repeat_type !== 'none';
  const status = task?.status || 'pending';
  const priority = task?.priority || 'medium';
  
  // Use executionStatus from backend if available
  const executionStatus = schedule.executionStatus || 'pending';
  
  // Choose color based on execution status
  let statusColor = STATUS_COLORS[status] || STATUS_COLORS.pending;
  
  // Override with execution status colors
  const EXECUTION_STATUS_COLORS = {
    running: { bg: '#d4edda', border: '#28a745', text: '#155724' },    // Green
    scheduled: { bg: '#cce5ff', border: '#007bff', text: '#004085' },  // Blue
    completed: { bg: '#e2e3e5', border: '#6c757d', text: '#383d41' },  // Gray
    pending: { bg: '#fff3cd', border: '#ffc107', text: '#856404' },    // Yellow
    error: { bg: '#f8d7da', border: '#dc3545', text: '#721c24' },      // Red
  };
  
  if (executionStatus && EXECUTION_STATUS_COLORS[executionStatus]) {
    statusColor = EXECUTION_STATUS_COLORS[executionStatus];
  }
  
  // Build title - keep it clean without emoji prefixes
  // Icons will be shown separately in the UI components
  let title = schedule.taskName || 'Untitled Task';
  
  return {
    id: schedule.taskId || `schedule_${Math.random()}`,
    title,
    start: startDate,
    end: endDate,
    allDay: false,
    
    taskId: schedule.taskId,
    taskName: schedule.taskName,
    schedule,
    task,
    
    isRecurring,
    isOneTime: !isRecurring,
    
    // Execution status
    executionStatus,
    isLongPeriod: schedule.isLongPeriod,
    isNextExecution: schedule.isNextExecution,
    
    status,
    priority,
    
    color: statusColor.text,
    backgroundColor: statusColor.bg,
    borderColor: statusColor.border,
    
    metadata: {
      repeatType: schedule.repeat_type,
      repeatNumber: schedule.repeat_number,
      repeatUnit: schedule.repeat_unit,
      weekDays: schedule.week_days,
      months: schedule.months,
      lastRunDateTime: schedule.lastRunDateTime,
      alreadyRun: schedule.alreadyRun,
      originalEndTime: schedule.originalEndTime,
    },
  };
}

/**
 * 将TaskSchedule数组转换为CalendarEvent数组
 */
export function schedulesToEvents(
  schedules: TaskSchedule[],
  tasksMap?: Map<string, any>
): CalendarEvent[] {
  return schedules.map(schedule => {
    const task = schedule.taskId && tasksMap ? tasksMap.get(schedule.taskId) : undefined;
    return scheduleToEvent(schedule, task);
  });
}

/**
 * 将跨天长任务拆分为每日事件
 * Split long-duration tasks into daily events
 */
export function splitLongTaskIntoDays(
  event: CalendarEvent,
  rangeStart: Date,
  rangeEnd: Date
): CalendarEvent[] {
  const startDate = dayjs(event.start);
  const endDate = dayjs(event.end);
  const duration = endDate.diff(startDate, 'day', true);
  
  // 如果任务持续时间小于1天，不需要拆分
  if (duration < 1) {
    return [event];
  }
  
  const events: CalendarEvent[] = [];
  const rangeStartDayjs = dayjs(rangeStart);
  const rangeEndDayjs = dayjs(rangeEnd);
  
  // 从任务开始日期到结束日期，每天创建一个事件
  let currentDay = startDate.startOf('day');
  const taskEndDay = endDate.startOf('day');
  
  while (currentDay.isSameOrBefore(taskEndDay)) {
    // 只处理在视图范围内的日期
    if (currentDay.isSameOrAfter(rangeStartDayjs.startOf('day')) && 
        currentDay.isSameOrBefore(rangeEndDayjs.endOf('day'))) {
      
      let dayStart: dayjs.Dayjs;
      let dayEnd: dayjs.Dayjs;
      
      // 第一天：使用实际开始时间
      if (currentDay.isSame(startDate, 'day')) {
        dayStart = startDate;
        dayEnd = startDate.endOf('day');
        // 如果任务在当天就结束，使用实际结束时间
        if (endDate.isSame(startDate, 'day')) {
          dayEnd = endDate;
        }
      }
      // 最后一天：从00:00开始，到实际结束时间
      else if (currentDay.isSame(endDate, 'day')) {
        dayStart = currentDay.startOf('day');
        dayEnd = endDate;
      }
      // 中间的天：整天显示 (00:00 - 23:59:59)
      else {
        dayStart = currentDay.startOf('day');
        dayEnd = currentDay.endOf('day');
      }
      
      events.push({
        ...event,
        id: `${event.id}_day_${currentDay.format('YYYY-MM-DD')}`,
        start: dayStart.toDate(),
        end: dayEnd.toDate(),
        // 标记这是拆分的事件
        metadata: {
          ...event.metadata,
          isSplitDay: true,
          originalStart: event.start,
          originalEnd: event.end,
          isFirstDay: currentDay.isSame(startDate, 'day'),
          isLastDay: currentDay.isSame(endDate, 'day'),
        },
      });
    }
    
    currentDay = currentDay.add(1, 'day');
  }
  
  return events.length > 0 ? events : [event];
}

/**
 * 生成重复事件的所有实例（在指定日期范围内）
 */
export function generateRecurringEvents(
  event: CalendarEvent,
  rangeStart: Date,
  rangeEnd: Date
): CalendarEvent[] {
  if (!event.isRecurring) {
    // 对于非重复任务，也要拆分跨天的长任务
    return splitLongTaskIntoDays(event, rangeStart, rangeEnd);
  }

  const { schedule } = event;
  const events: CalendarEvent[] = [];
  
  let currentDate = dayjs(event.start);
  const originalDuration = dayjs(event.end).diff(event.start, 'minute');
  
  let instanceCount = 0;
  const maxInstances = 1000; // 防止无限循环
  
  const rangeEndDayjs = dayjs(rangeEnd);
  
  while (currentDate.isSameOrBefore(rangeEndDayjs) && instanceCount < maxInstances) {
    // 检查是否在范围内
    if (currentDate.isSameOrAfter(dayjs(rangeStart))) {
      // 检查星期限制
      const dayOfWeek = currentDate.format('dd'); // Mo, Tu, We, Th, Fr, Sa, Su
      const dayMap: Record<string, string> = {
        '一': 'M',
        '二': 'Tu',
        '三': 'W',
        '四': 'Th',
        '五': 'F',
        '六': 'SA',
        '日': 'SU',
      };
      const mappedDay = dayMap[dayOfWeek] || dayOfWeek;
      
      const weekDaysMatch = !schedule.week_days || 
        schedule.week_days.length === 0 || 
        schedule.week_days.includes(mappedDay as any);
      
      // 检查月份限制
      const monthName = currentDate.format('MMM'); // Jan, Feb, etc.
      const monthsMatch = !schedule.months || 
        schedule.months.length === 0 || 
        schedule.months.includes(monthName as any);
      
      if (weekDaysMatch && monthsMatch) {
        const eventEnd = currentDate.add(originalDuration, 'minute');
        
        // 创建这个重复实例的事件
        const instanceEvent: CalendarEvent = {
          ...event,
          id: `${event.id}_${currentDate.format('YYYY-MM-DD-HH-mm')}`,
          start: currentDate.toDate(),
          end: eventEnd.toDate(),
        };
        
        // 重复任务不需要拆分！
        // 因为重复任务本身就是"每天一次"的概念
        // 每个实例代表一天的执行
        events.push(instanceEvent);
      }
    }
    
    // 计算下一个实例的时间
    switch (schedule.repeat_type) {
      case 'by seconds':
        currentDate = currentDate.add(schedule.repeat_number || 1, 'second');
        break;
      case 'by minutes':
        currentDate = currentDate.add(schedule.repeat_number || 1, 'minute');
        break;
      case 'by hours':
        currentDate = currentDate.add(schedule.repeat_number || 1, 'hour');
        break;
      case 'by days':
        currentDate = currentDate.add(schedule.repeat_number || 1, 'day');
        break;
      case 'by weeks':
        currentDate = currentDate.add(schedule.repeat_number || 1, 'week');
        break;
      case 'by months':
        currentDate = currentDate.add(schedule.repeat_number || 1, 'month');
        break;
      case 'by years':
        currentDate = currentDate.add(schedule.repeat_number || 1, 'year');
        break;
      default:
        // 如果类型不匹配，跳出循环
        currentDate = rangeEndDayjs.add(1, 'day');
    }
    
    instanceCount++;
  }
  
  return events;
}

// 缓存已展开的事件，避免重复展开
const expandedEventsCache = new Map<string, CalendarEvent[]>();

/**
 * 获取日期范围内的所有事件（包括重复事件的实例）
 */
export function getEventsInRange(
  events: CalendarEvent[],
  rangeStart: Date,
  rangeEnd: Date
): CalendarEvent[] {
  const allEvents: CalendarEvent[] = [];
  const rangeStartDayjs = dayjs(rangeStart);
  const rangeEndDayjs = dayjs(rangeEnd);
  
  for (const event of events) {
    // 生成缓存键
    const cacheKey = `${event.id}_${rangeStart.getTime()}_${rangeEnd.getTime()}`;
    
    if (event.isRecurring) {
      // 重复任务：检查缓存
      if (expandedEventsCache.has(cacheKey)) {
        allEvents.push(...expandedEventsCache.get(cacheKey)!);
      } else {
        const instances = generateRecurringEvents(event, rangeStart, rangeEnd);
        expandedEventsCache.set(cacheKey, instances);
        allEvents.push(...instances);
      }
    } else {
      // 一次性事件：检查是否在范围内
      const eventStart = dayjs(event.start);
      const eventEnd = dayjs(event.end);
      
      if (
        eventStart.isBetween(rangeStartDayjs, rangeEndDayjs, null, '[]') ||
        eventEnd.isBetween(rangeStartDayjs, rangeEndDayjs, null, '[]') ||
        (eventStart.isSameOrBefore(rangeStartDayjs) && eventEnd.isSameOrAfter(rangeEndDayjs))
      ) {
        // 一次性任务：检查缓存
        if (expandedEventsCache.has(cacheKey)) {
          allEvents.push(...expandedEventsCache.get(cacheKey)!);
        } else {
          const splitEvents = splitLongTaskIntoDays(event, rangeStart, rangeEnd);
          expandedEventsCache.set(cacheKey, splitEvents);
          allEvents.push(...splitEvents);
        }
      }
    }
  }
  
  // 按开始时间排序
  return allEvents.sort((a, b) => dayjs(a.start).valueOf() - dayjs(b.start).valueOf());
}

/**
 * 生成月视图数据
 */
export function generateMonthView(
  date: Date,
  events: CalendarEvent[],
  _config: CalendarConfig = DEFAULT_CALENDAR_CONFIG
): CalendarMonth {
  const monthStart = dayjs(date).startOf('month');
  const monthEnd = dayjs(date).endOf('month');
  
  // 获取日历显示的第一天和最后一天（包含前后月份的日期）
  // 从周日开始 (day() === 0)
  const firstDayOfMonth = monthStart.day(); // 0 = Sunday, 1 = Monday, ...
  const calendarStart = monthStart.subtract(firstDayOfMonth, 'day');
  
  const lastDayOfMonth = monthEnd.day();
  const calendarEnd = monthEnd.add(6 - lastDayOfMonth, 'day');
  
  // 获取范围内的所有事件
  const rangeEvents = getEventsInRange(events, calendarStart.toDate(), calendarEnd.toDate());
  
  // 生成所有周
  const weeks: CalendarWeek[] = [];
  let currentWeekStart = calendarStart;
  
  while (currentWeekStart.isSameOrBefore(calendarEnd)) {
    const days: CalendarDateCell[] = [];
    
    for (let i = 0; i < 7; i++) {
      const day = currentWeekStart.add(i, 'day');
      
      // 获取当天的事件
      // 只匹配开始时间在当天的事件
      const dayEvents = rangeEvents.filter(event => {
        const eventStart = dayjs(event.start);
        return eventStart.isSame(day, 'day');
      });
      
      days.push({
        date: day.toDate(),
        isToday: day.isSame(dayjs(), 'day'),
        isCurrentMonth: day.isSame(monthStart, 'month'),
        isWeekend: day.day() === 0 || day.day() === 6,
        events: dayEvents,
        hasEvents: dayEvents.length > 0,
        eventCount: dayEvents.length,
      });
    }
    
    weeks.push({
      weekNumber: currentWeekStart.isoWeek(),
      days,
    });
    
    currentWeekStart = currentWeekStart.add(1, 'week');
  }
  
  return {
    year: monthStart.year(),
    month: monthStart.month(),
    weeks,
    firstDay: calendarStart.toDate(),
    lastDay: calendarEnd.toDate(),
  };
}

/**
 * 生成周视图数据
 */
export function generateWeekView(
  date: Date,
  events: CalendarEvent[],
  _config: CalendarConfig = DEFAULT_CALENDAR_CONFIG
): CalendarDateCell[] {
  // 从周日开始 (day() === 0)
  const currentDay = dayjs(date);
  const dayOfWeek = currentDay.day(); // 0 = Sunday, 1 = Monday, ...
  const weekStart = currentDay.subtract(dayOfWeek, 'day');
  const weekEnd = weekStart.add(6, 'day');
  
  const rangeEvents = getEventsInRange(events, weekStart.toDate(), weekEnd.toDate());
  
  const days: CalendarDateCell[] = [];
  
  for (let i = 0; i < 7; i++) {
    const day = weekStart.add(i, 'day');
    
    // 只匹配开始时间在当天的事件
    const dayEvents = rangeEvents.filter(event => {
      const eventStart = dayjs(event.start);
      return eventStart.isSame(day, 'day');
    });
    
    days.push({
      date: day.toDate(),
      isToday: day.isSame(dayjs(), 'day'),
      isCurrentMonth: true,
      isWeekend: day.day() === 0 || day.day() === 6,
      events: dayEvents,
      hasEvents: dayEvents.length > 0,
      eventCount: dayEvents.length,
    });
  }
  
  return days;
}

/**
 * 生成日视图的时间槽
 */
export function generateTimeSlots(
  date: Date,
  _events: CalendarEvent[],
  config: CalendarConfig = DEFAULT_CALENDAR_CONFIG
): TimeSlot[] {
  const slots: TimeSlot[] = [];
  
  // 确保时间范围有效
  const startHour = Math.max(0, Math.min(23, config.dayStartHour));
  const endHour = Math.max(startHour + 1, Math.min(24, config.dayEndHour));
  
  for (let hour = startHour; hour < endHour; hour++) {
    for (let minute = 0; minute < 60; minute += config.timeSlotDuration) {
      const slotTime = dayjs(date).hour(hour).minute(minute).second(0);
      
      slots.push({
        hour,
        minute,
        label: slotTime.format('HH:mm'),
        events: [],
      });
    }
  }
  
  return slots;
}

/**
 * 检测事件时间冲突
 */
export function detectEventConflicts(events: CalendarEvent[]): EventConflict[] {
  const conflicts: EventConflict[] = [];
  
  for (let i = 0; i < events.length; i++) {
    for (let j = i + 1; j < events.length; j++) {
      const event1 = events[i];
      const event2 = events[j];
      
      const event1Start = dayjs(event1.start);
      const event1End = dayjs(event1.end);
      const event2Start = dayjs(event2.start);
      const event2End = dayjs(event2.end);
      
      // 检查时间是否重叠
      if (
        (event1Start.isSameOrBefore(event2Start) && event1End.isAfter(event2Start)) ||
        (event2Start.isSameOrBefore(event1Start) && event2End.isAfter(event1Start))
      ) {
        const overlapStart = event1Start.isAfter(event2Start) ? event1Start : event2Start;
        const overlapEnd = event1End.isBefore(event2End) ? event1End : event2End;
        const overlapDuration = overlapEnd.diff(overlapStart, 'minute');
        
        conflicts.push({
          event1,
          event2,
          overlapDuration,
        });
      }
    }
  }
  
  return conflicts;
}

/**
 * 格式化日期范围
 */
export function formatDateRange(start: Date, end: Date, language: string = 'zh-CN'): string {
  const startDayjs = dayjs(start);
  const endDayjs = dayjs(end);
  const isChinese = language === 'zh-CN';
  
  if (startDayjs.isSame(endDayjs, 'day')) {
    return startDayjs.format(isChinese ? 'YYYY年M月D日 HH:mm' : 'YYYY-MM-DD HH:mm');
  }
  
  return isChinese
    ? `${startDayjs.format('YYYY年M月D日 HH:mm')} - ${endDayjs.format('M月D日 HH:mm')}`
    : `${startDayjs.format('YYYY-MM-DD HH:mm')} - ${endDayjs.format('MM-DD HH:mm')}`;
}

/**
 * 导航到上一个周期
 */
export function navigatePrevious(date: Date, viewType: 'month' | 'week' | 'day'): Date {
  const dateDayjs = dayjs(date);
  
  switch (viewType) {
    case 'month':
      return dateDayjs.subtract(1, 'month').toDate();
    case 'week':
      return dateDayjs.subtract(1, 'week').toDate();
    case 'day':
      return dateDayjs.subtract(1, 'day').toDate();
    default:
      return date;
  }
}

/**
 * 导航到下一个周期
 */
export function navigateNext(date: Date, viewType: 'month' | 'week' | 'day'): Date {
  const dateDayjs = dayjs(date);
  
  switch (viewType) {
    case 'month':
      return dateDayjs.add(1, 'month').toDate();
    case 'week':
      return dateDayjs.add(1, 'week').toDate();
    case 'day':
      return dateDayjs.add(1, 'day').toDate();
    default:
      return date;
  }
}

/**
 * 格式化视图标题
 */
export function formatViewTitle(date: Date, viewType: 'month' | 'week' | 'day', language: string = 'zh-CN'): string {
  const dateDayjs = dayjs(date);
  const isChinese = language === 'zh-CN';
  
  switch (viewType) {
    case 'month':
      return dateDayjs.format(isChinese ? 'YYYY年 M月' : 'YYYY-MM');
    case 'week': {
      const weekStart = dateDayjs.startOf('week');
      const weekEnd = dateDayjs.endOf('week');
      return isChinese
        ? `${weekStart.format('M月D日')} - ${weekEnd.format('M月D日')}`
        : `${weekStart.format('MM-DD')} - ${weekEnd.format('MM-DD')}`;
    }
    case 'day':
      return dateDayjs.format(isChinese ? 'YYYY年 M月D日 dddd' : 'YYYY-MM-DD dddd');
    default:
      return '';
  }
}
