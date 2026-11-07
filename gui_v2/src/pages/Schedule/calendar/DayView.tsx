/**
 * Day View Component
 * 日视图日历Component
 */

import React, { useMemo, useRef, useEffect } from 'react';
import styled from '@emotion/styled';
import dayjs from 'dayjs';
import { Tooltip, Badge } from 'antd';
import { SyncOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useEffectOnActive } from 'keepalive-for-react';
import 'dayjs/locale/zh-cn';
import 'dayjs/locale/en';
import type { CalendarEvent, CalendarConfig } from './types';
import { generateTimeSlots, DEFAULT_CALENDAR_CONFIG, getEventsInRange } from './utils';

const DayViewContainer = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  /* Transparent so this grid inherits the sunken CalendarView shell instead of
     rendering white-on-white against it (see MonthView). */
  background: transparent;
  border-radius: 12px;
  overflow: hidden;
`;

const DayHeader = styled.div`
  background: var(--surface-subtle);
  border-bottom: 2px solid var(--border-color);
  padding: 16px 20px;
  position: sticky;
  top: 0;
  z-index: 1; // 只Need在日历Content上方，不能遮挡下拉Menu
  
  .date-info {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
  }
  
  .date-main {
    display: flex;
    align-items: baseline;
    gap: 12px;
  }
  
  .day-number {
    font-size: 32px;
    font-weight: 700;
    color: var(--text-primary);
  }
  
  .date-text {
    font-size: 16px;
    color: var(--text-secondary);
  }
  
  .event-summary {
    display: flex;
    align-items: center;
    gap: 16px;
    font-size: 13px;
    color: var(--text-secondary);
    
    .summary-item {
      display: flex;
      align-items: center;
      gap: 6px;
    }
  }
`;

const TimeGridContainer = styled.div`
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  position: relative;
`;

const TimeGrid = styled.div`
  display: grid;
  grid-template-columns: 80px 1fr;
  position: relative;
`;

const TimeSlotRow = styled.div`
  display: contents;
`;

const TimeLabel = styled.div<{ $isHour?: boolean }>`
  padding: 8px 12px;
  font-size: ${props => props.$isHour ? '13px' : '11px'};
  font-weight: ${props => props.$isHour ? 600 : 400};
  color: ${props => props.$isHour ? 'var(--text-secondary)' : 'var(--text-tertiary)'};
  text-align: right;
  border-right: 2px solid ${props => props.$isHour ? 'var(--border-color-hover)' : 'var(--border-color)'};
  border-bottom: 1px solid ${props => props.$isHour ? 'var(--border-color-hover)' : 'var(--border-color)'};
  font-family: 'Consolas', 'Monaco', monospace;
  height: 60px;
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  background: ${props => props.$isHour ? 'var(--surface-subtle)' : 'transparent'};
`;

const TimeSlotCell = styled.div<{ $isHour?: boolean }>`
  border-right: 1px solid var(--border-color);
  border-bottom: 1px solid ${props => props.$isHour ? 'var(--border-color-hover)' : 'var(--border-color)'};
  min-height: 60px;
  padding: 4px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  cursor: pointer;
  transition: background-color 0.2s ease;
  
  &:hover {
    background: rgba(24, 144, 255, 0.05);
  }
`;

const EventBlock = styled.div<{ 
  $color?: string; 
  $backgroundColor?: string; 
  $borderColor?: string;
}>`
  background: ${props => props.$backgroundColor || 'rgba(24, 144, 255, 0.15)'};
  border-left: 4px solid ${props => props.$borderColor || 'var(--primary-color)'};
  border-radius: 6px;
  padding: 8px 10px;
  min-height: 32px;
  cursor: pointer;
  overflow: hidden;
  z-index: 1;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15); // 减小阴影范围
  transition: all 0.2s ease; // 恢复hover效果
  
  &:hover {
    z-index: 5;
    background: ${props => props.$backgroundColor ? `${props.$backgroundColor}ee` : 'rgba(24, 144, 255, 0.15)'}; // 增加背景亮度
    box-shadow: 0 3px 10px rgba(24, 144, 255, 0.3); // 增强hover阴影
    border-left-width: 4px; // 增加左边框宽度，更明显的反馈
  }
  
  .event-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 4px;
  }
  
  .event-time {
    font-size: 11px;
    font-weight: 600;
    color: ${props => props.$color || 'var(--primary-color)'};
    opacity: 0.9;
  }
  
  .event-title {
    font-size: 14px;
    font-weight: 600;
    color: ${props => props.$color || 'var(--primary-color)'};
    line-height: 1.4;
    margin-bottom: 6px;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
  }
  
  .event-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    font-size: 10px;
    
    .meta-badge {
      padding: 2px 6px;
      border-radius: 3px;
      font-weight: 600;
    }
    
    .recurring-badge {
      background: rgba(82, 196, 26, 0.2);
      color: var(--success-text);
    }
    
    .status-badge {
      background: var(--surface-subtle);
      color: var(--text-secondary);
    }
    
    .priority-badge {
      background: rgba(250, 173, 20, 0.2);
      color: var(--warning-text);
    }
  }
`;

const CurrentTimeIndicator = styled.div<{ $top: number }>`
  position: absolute;
  left: 80px;
  right: 0;
  top: ${props => props.$top}px;
  height: 2px;
  background: var(--error-color);
  z-index: 10;
  box-shadow: 0 0 3px rgba(255, 77, 79, 0.4); // 减小阴影范围
  
  &::before {
    content: '';
    position: absolute;
    left: -6px;
    top: -5px;
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: var(--error-color);
    box-shadow: 0 0 4px rgba(255, 77, 79, 0.5); // 减小阴影范围
  }
  
  &::after {
    content: '';
    position: absolute;
    left: -80px;
    top: -10px;
    padding: 2px 6px;
    background: var(--error-color);
    color: var(--text-on-primary);
    font-size: 10px;
    font-weight: 600;
    border-radius: 3px;
    content: attr(data-time);
  }
`;

const NoEventsPlaceholder = styled.div`
  grid-column: 1 / -1;
  padding: 40px 20px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 14px;
`;

interface DayViewProps {
  currentDate: Date;
  events: CalendarEvent[];
  config?: Partial<CalendarConfig>;
  onEventClick?: (event: CalendarEvent) => void;
  onTimeSlotClick?: (date: Date, hour: number, minute: number) => void;
  showCurrentTimeIndicator?: boolean;
}

const DayView: React.FC<DayViewProps> = ({
  currentDate,
  events,
  config = {},
  onEventClick,
  onTimeSlotClick,
  showCurrentTimeIndicator = true,
}) => {
  const { t, i18n } = useTranslation();
  const calendarConfig = { ...DEFAULT_CALENDAR_CONFIG, ...config };
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const savedScrollPositionRef = useRef<number>(0);
  
  // 动态Settings dayjs locale
  useEffect(() => {
    const locale = i18n.language === 'zh-CN' ? 'zh-cn' : 'en';
    dayjs.locale(locale);
  }, [i18n.language]);
  
  const timeSlots = useMemo(() => {
    return generateTimeSlots(currentDate, [], calendarConfig);
  }, [currentDate, calendarConfig]);
  
  const dayEvents = useMemo(() => {
    const dayStart = dayjs(currentDate).startOf('day').toDate();
    const dayEnd = dayjs(currentDate).endOf('day').toDate();
    return getEventsInRange(events, dayStart, dayEnd);
  }, [currentDate, events]);
  
  // Calculate current time indicator position
  const currentTimeInfo = useMemo(() => {
    if (!showCurrentTimeIndicator) return null;
    
    const now = new Date();
    const hours = now.getHours();
    const minutes = now.getMinutes();
    
    if (hours < calendarConfig.dayStartHour || hours >= calendarConfig.dayEndHour) {
      return null;
    }
    
    const totalMinutes = (hours - calendarConfig.dayStartHour) * 60 + minutes;
    const slotHeight = 60;
    const pixelsPerMinute = slotHeight / calendarConfig.timeSlotDuration;
    const top = totalMinutes * pixelsPerMinute;
    const time = dayjs(now).format('HH:mm');
    
    return { top, time };
  }, [showCurrentTimeIndicator, calendarConfig]);
  
  const handleEventClick = (event: CalendarEvent, e: React.MouseEvent) => {
    e.stopPropagation();
    onEventClick?.(event);
  };
  
  const handleTimeSlotClick = (hour: number, minute: number) => {
    onTimeSlotClick?.(currentDate, hour, minute);
  };
  
  // 使用 useEffectOnActive 在ComponentActive时RestoreScrollPosition
  useEffectOnActive(
    () => {
      // ComponentActive时：RestoreScrollPosition
      const container = scrollContainerRef.current;
      if (container && savedScrollPositionRef.current > 0) {
        requestAnimationFrame(() => {
          container.scrollTop = savedScrollPositionRef.current;
        });
      }
      
      // 返回CleanupFunction，在Component失活前SaveScrollPosition
      return () => {
        const container = scrollContainerRef.current;
        if (container) {
          savedScrollPositionRef.current = container.scrollTop;
        }
      };
    },
    []
  );
  
  // Get某个Time槽内的任务（Process跨天任务）
  const getEventsForSlot = (slotHour: number, slotMinute: number) => {
    const slotStart = dayjs(currentDate).hour(slotHour).minute(slotMinute).second(0);
    const slotEnd = slotStart.add(calendarConfig.timeSlotDuration, 'minute');
    const dayStart = dayjs(currentDate).startOf('day');
    const isFirstSlotOfDay = slotHour === calendarConfig.dayStartHour && slotMinute === 0;
    
    return dayEvents
      .filter(event => {
        const eventStart = dayjs(event.start);
        const eventEnd = dayjs(event.end);
        
        // If任务在这个Time槽内开始，Display它
        const startsInSlot = eventStart.isSameOrAfter(slotStart) && eventStart.isBefore(slotEnd);
        
        // If是When天的第一个Time槽，且任务是跨天In progress的（开始Time早于今天，结束Time晚于今天开始）
        const isContinuingTask = isFirstSlotOfDay && 
                                 eventStart.isBefore(dayStart) && 
                                 eventEnd.isAfter(dayStart);
        
        return startsInSlot || isContinuingTask;
      })
      .sort((a, b) => {
        // 优先Display今天开始的任务，然后是继续In progress的任务
        const aStartsToday = dayjs(a.start).isSame(dayStart, 'day');
        const bStartsToday = dayjs(b.start).isSame(dayStart, 'day');
        
        if (aStartsToday && !bStartsToday) return -1;
        if (!aStartsToday && bStartsToday) return 1;
        
        // 按开始TimeSort，相同Time按NameSort
        const timeDiff = a.start.getTime() - b.start.getTime();
        if (timeDiff !== 0) return timeDiff;
        return (a.title || '').localeCompare(b.title || '');
      })
      .map(event => {
        // 标记任务是今天开始还是继续In progress
        const startsToday = dayjs(event.start).isSame(dayStart, 'day');
        return { ...event, startsToday };
      });
  };
  
  const eventSummary = useMemo(() => {
    const total = dayEvents.length;
    const recurring = dayEvents.filter(e => e.isRecurring).length;
    const completed = dayEvents.filter(e => e.status === 'completed').length;
    
    return { total, recurring, completed };
  }, [dayEvents]);
  
  return (
    <DayViewContainer>
      {/* Day Header */}
      <DayHeader>
        <div className="date-info">
          <div className="date-main">
            <div className="day-number">{dayjs(currentDate).format('D')}</div>
            <div className="date-text">
              {dayjs(currentDate).format(
                i18n.language === 'zh-CN' ? 'YYYY年 M月 dddd' : 'YYYY-MM-DD dddd'
              )}
            </div>
          </div>
        </div>
        <div className="event-summary">
          <div className="summary-item">
            <Badge 
              count={eventSummary.total} 
              style={{ backgroundColor: 'var(--primary-color)' }} 
            />
            <span>{t('pages.schedule.calendar.totalTasks', { count: eventSummary.total })}</span>
          </div>
          {eventSummary.recurring > 0 && (
            <div className="summary-item">
              <Badge 
                count={eventSummary.recurring} 
                style={{ backgroundColor: 'var(--success-color)' }} 
              />
              <span>{t('pages.schedule.calendar.recurringTasks', { count: eventSummary.recurring })}</span>
            </div>
          )}
          {eventSummary.completed > 0 && (
            <div className="summary-item">
              <Badge 
                count={eventSummary.completed} 
                style={{ backgroundColor: 'var(--success-color)' }} 
              />
              <span>{t('pages.schedule.calendar.completedTasks', { count: eventSummary.completed })}</span>
            </div>
          )}
        </div>
      </DayHeader>
      
      {/* Time Grid */}
      <TimeGridContainer ref={scrollContainerRef}>
        <TimeGrid>
          {timeSlots.map((slot, slotIndex) => {
            const isHour = slot.minute === 0;
            
            return (
              <TimeSlotRow key={`slot-${slotIndex}`}>
                <TimeLabel $isHour={isHour}>
                  {isHour ? slot.label : ''}
                </TimeLabel>
                
                <TimeSlotCell
                  $isHour={isHour}
                  onClick={() => handleTimeSlotClick(slot.hour, slot.minute)}
                >
                  {/* Render该Time槽的任务 */}
                  {getEventsForSlot(slot.hour, slot.minute).map((eventWithFlag: any) => {
                    const event = eventWithFlag as CalendarEvent;
                    const startsToday = (eventWithFlag as any).startsToday;
                    const isSameTime = event.start.getTime() === event.end.getTime();
                    const isLongTask = dayjs(event.end).diff(event.start, 'hour') >= 1;
                    
                    return (
                    <Tooltip
                      key={`${event.id}-${startsToday ? 'start' : 'continue'}`}
                      title={
                        <div>
                          <div style={{ fontWeight: 600, marginBottom: 6 }}>{event.title}</div>
                          <div style={{ fontSize: 12, marginBottom: 4 }}>
                            {isSameTime 
                              ? `${dayjs(event.start).format('HH:mm')} (${t('pages.schedule.calendar.instantTask')})`
                              : `${dayjs(event.start).format('YYYY-MM-DD HH:mm')} - ${dayjs(event.end).format('YYYY-MM-DD HH:mm')}`
                            }
                          </div>
                          {!startsToday && (
                            <Tooltip title={t('pages.schedule.calendar.continuingTask')}>
                              <div style={{ fontSize: 11, marginBottom: 4, color: 'var(--warning-text)', display: 'flex', alignItems: 'center', gap: 4 }}>
                                <ClockCircleOutlined />
                              </div>
                            </Tooltip>
                          )}
                          {event.isRecurring && (
                            <Tooltip title={`${t('pages.schedule.calendar.recurringTask')}: ${event.metadata?.repeatType}`}>
                              <div style={{ fontSize: 11, marginBottom: 4, color: 'var(--success-text)', display: 'flex', alignItems: 'center', gap: 4 }}>
                                <SyncOutlined />
                              </div>
                            </Tooltip>
                          )}
                          <div style={{ fontSize: 11, opacity: 0.9 }}>
                            {t('common.status')}: {event.status ? t(`pages.schedule.status.${event.status}`) : '-'} | {t('common.priority')}: {event.priority ? t(`pages.tasks.priority.${event.priority}`) : '-'}
                          </div>
                          {isLongTask && (
                            <div style={{ fontSize: 11, marginTop: 4, color: 'var(--primary-text)' }}>
                              {t('pages.schedule.calendar.duration')}: {dayjs(event.end).diff(event.start, 'hour')} {t('pages.schedule.calendar.hours')}
                            </div>
                          )}
                          {event.taskId && (
                            <div style={{ fontSize: 10, marginTop: 6, opacity: 0.7 }}>
                              Task ID: {event.taskId}
                            </div>
                          )}
                        </div>
                      }
                      mouseEnterDelay={0.3}
                    >
                      <EventBlock
                        $color={event.color}
                        $backgroundColor={startsToday ? event.backgroundColor : (event.backgroundColor ? `${event.backgroundColor}80` : 'rgba(24, 144, 255, 0.08)')}
                        $borderColor={event.borderColor}
                        onClick={(e) => handleEventClick(event, e)}
                        style={{
                          opacity: startsToday ? 1 : 0.7,
                          borderLeftStyle: startsToday ? 'solid' : 'dashed',
                        }}
                      >
                        <div className="event-header">
                          <div className="event-time">
                            {startsToday ? (
                              isSameTime 
                                ? dayjs(event.start).format('HH:mm')
                                : `${dayjs(event.start).format('HH:mm')}-${dayjs(event.end).format('HH:mm')}`
                            ) : `⏳ ${t('common.continue')}`}
                          </div>
                        </div>
                        <div className="event-title">
                          {startsToday ? event.title : `${event.title} (${t('pages.schedule.calendar.crossDayTask')})`}
                        </div>
                        <div className="event-meta">
                          {event.isRecurring && startsToday && (
                            <div className="meta-badge recurring-badge">{t('pages.schedule.calendar.recurringTask')}</div>
                          )}
                          {startsToday && event.status && (
                            <div className="meta-badge status-badge">{t(`pages.schedule.status.${event.status}`)}</div>
                          )}
                          {event.priority && event.priority !== 'medium' && startsToday && (
                            <div className="meta-badge priority-badge">{t(`pages.tasks.priority.${event.priority}`)}</div>
                          )}
                        </div>
                      </EventBlock>
                    </Tooltip>
                  );
                  })}
                </TimeSlotCell>
              </TimeSlotRow>
            );
          })}
          
          {dayEvents.length === 0 && (
            <NoEventsPlaceholder>
              📅 今天没有安排的任务
            </NoEventsPlaceholder>
          )}
        </TimeGrid>
        
        {/* Current Time Indicator */}
        {currentTimeInfo && (
          <CurrentTimeIndicator 
            $top={currentTimeInfo.top}
            data-time={currentTimeInfo.time}
          />
        )}
      </TimeGridContainer>
    </DayViewContainer>
  );
};

export default DayView;



