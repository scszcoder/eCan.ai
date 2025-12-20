/**
 * Week View Component
 * 周视图日历Component
 */

import React, { useMemo, useRef } from 'react';
import styled from '@emotion/styled';
import dayjs from 'dayjs';
import { Tooltip } from 'antd';
import { SyncOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useEffectOnActive } from 'keepalive-for-react';
import type { CalendarEvent, CalendarConfig } from './types';
import { generateWeekView, generateTimeSlots, DEFAULT_CALENDAR_CONFIG } from './utils';

const WeekViewContainer = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-secondary);
  border-radius: 12px;
  overflow: hidden;
`;

const WeekHeader = styled.div`
  display: grid;
  grid-template-columns: 60px repeat(7, 1fr);
  background: rgba(0, 0, 0, 0.2);
  border-bottom: 2px solid rgba(255, 255, 255, 0.1);
  padding: 12px 0;
  position: sticky;
  top: 0;
  z-index: 1; // 只Need在日历Content上方，不能遮挡下拉Menu
`;

const TimeColumnHeader = styled.div`
  text-align: center;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.4);
  font-weight: 600;
`;

const DayHeader = styled.div<{ $isToday?: boolean; $isWeekend?: boolean }>`
  text-align: center;
  padding: 0 4px;
  
  .day-name {
    font-size: 11px;
    font-weight: 600;
    color: ${props => {
      if (props.$isToday) return '#1890ff';
      if (props.$isWeekend) return 'rgba(255, 107, 129, 0.85)';
      return 'rgba(255, 255, 255, 0.65)';
    }};
    text-transform: uppercase;
    margin-bottom: 4px;
  }
  
  .day-number {
    font-size: 20px;
    font-weight: 700;
    color: ${props => props.$isToday ? '#1890ff' : 'rgba(255, 255, 255, 0.85)'};
    
    ${props => props.$isToday && `
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 36px;
      height: 36px;
      border-radius: 50%;
      background: #1890ff; // 使用纯色替代渐变，减少GPU消耗
      color: white;
      box-shadow: 0 2px 4px rgba(24, 144, 255, 0.3); // 减小阴影范围
    `}
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
  grid-template-columns: 60px repeat(7, 1fr);
  position: relative;
`;

const TimeSlotRow = styled.div`
  display: contents;
`;

const TimeLabel = styled.div`
  padding: 8px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.5);
  text-align: right;
  border-right: 1px solid rgba(255, 255, 255, 0.08);
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  font-family: 'Consolas', 'Monaco', monospace;
  height: 60px;
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
`;

const DayColumn = styled.div<{ $isToday?: boolean; $isWeekend?: boolean; $isPast?: boolean }>`
  border-right: 1px solid rgba(255, 255, 255, 0.08);
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  background: ${props => {
    if (props.$isToday) return 'rgba(24, 144, 255, 0.03)';
    if (props.$isWeekend) return 'rgba(255, 255, 255, 0.01)';
    return 'transparent';
  }};
  min-height: 60px;
  padding: 4px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  opacity: ${props => props.$isPast ? 0.3 : 1};
  
  &:last-child {
    border-right: none;
  }
`;

const EventBlock = styled.div<{ 
  $color?: string; 
  $backgroundColor?: string; 
  $borderColor?: string;
}>`
  background: ${props => props.$backgroundColor || 'rgba(24, 144, 255, 0.15)'};
  border-left: 3px solid ${props => props.$borderColor || '#1890ff'};
  border-radius: 4px;
  padding: 4px 6px;
  min-height: 28px;
  cursor: pointer;
  overflow: hidden;
  z-index: 1;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15); // 减小阴影范围
  transition: all 0.2s ease; // 恢复hover效果
  
  &:hover {
    z-index: 5;
    background: ${props => props.$backgroundColor ? `${props.$backgroundColor}ee` : 'rgba(24, 144, 255, 0.15)'}; // 增加背景亮度
    box-shadow: 0 2px 6px rgba(24, 144, 255, 0.25); // 增强hover阴影
    border-left-width: 4px; // 增加左边框宽度，更明显的反馈
  }
  
  .event-time {
    font-size: 10px;
    font-weight: 600;
    color: ${props => props.$color || '#1890ff'};
    margin-bottom: 2px;
    opacity: 0.9;
  }
  
  .event-title {
    font-size: 12px;
    font-weight: 600;
    color: ${props => props.$color || '#1890ff'};
    line-height: 1.3;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }
  
  .event-recurring {
    font-size: 9px;
    padding: 1px 4px;
    background: rgba(82, 196, 26, 0.2);
    color: #52c41a;
    border-radius: 2px;
    font-weight: 600;
    display: inline-block;
    margin-top: 2px;
  }
`;

const CurrentTimeIndicator = styled.div<{ $top: number }>`
  position: absolute;
  left: 60px;
  right: 0;
  top: ${props => props.$top}px;
  height: 2px;
  background: #ff4d4f;
  z-index: 10;
  box-shadow: 0 0 3px rgba(255, 77, 79, 0.4); // 减小阴影范围
  
  &::before {
    content: '';
    position: absolute;
    left: -5px;
    top: -4px;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #ff4d4f;
    box-shadow: 0 0 4px rgba(255, 77, 79, 0.5); // 减小阴影范围
  }
`;

interface WeekViewProps {
  currentDate: Date;
  events: CalendarEvent[];
  config?: Partial<CalendarConfig>;
  onEventClick?: (event: CalendarEvent) => void;
  onTimeSlotClick?: (date: Date, hour: number, minute: number) => void;
  showCurrentTimeIndicator?: boolean;
}

const WeekView: React.FC<WeekViewProps> = ({
  currentDate,
  events,
  config = {},
  onEventClick,
  onTimeSlotClick,
  showCurrentTimeIndicator = true,
}) => {
  const { t } = useTranslation();
  const calendarConfig = { ...DEFAULT_CALENDAR_CONFIG, ...config };
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const savedScrollPositionRef = useRef<number>(0);
  
  const weekDays = useMemo(() => {
    return generateWeekView(currentDate, events, calendarConfig);
  }, [currentDate, events, calendarConfig]);
  
  const timeSlots = useMemo(() => {
    if (weekDays.length === 0) return [];
    return generateTimeSlots(weekDays[0].date, [], calendarConfig);
  }, [weekDays, calendarConfig]);
  
  // 周从周日开始（Standard日历格式）
  const weekdayLabels = [
    t('pages.schedule.calendar.weekdays.sunday'),
    t('pages.schedule.calendar.weekdays.monday'),
    t('pages.schedule.calendar.weekdays.tuesday'),
    t('pages.schedule.calendar.weekdays.wednesday'),
    t('pages.schedule.calendar.weekdays.thursday'),
    t('pages.schedule.calendar.weekdays.friday'),
    t('pages.schedule.calendar.weekdays.saturday')
  ];
  
  // Calculate current time indicator position
  const currentTimeTop = useMemo(() => {
    if (!showCurrentTimeIndicator) return null;
    
    const now = new Date();
    const hours = now.getHours();
    const minutes = now.getMinutes();
    
    if (hours < calendarConfig.dayStartHour || hours >= calendarConfig.dayEndHour) {
      return null;
    }
    
    const totalMinutes = (hours - calendarConfig.dayStartHour) * 60 + minutes;
    const slotHeight = 60; // matches TimeLabel height
    const pixelsPerMinute = slotHeight / calendarConfig.timeSlotDuration;
    
    return totalMinutes * pixelsPerMinute;
  }, [showCurrentTimeIndicator, calendarConfig]);
  
  const handleEventClick = (event: CalendarEvent, e: React.MouseEvent) => {
    e.stopPropagation();
    onEventClick?.(event);
  };
  
  const handleTimeSlotClick = (dayDate: Date, hour: number, minute: number) => {
    onTimeSlotClick?.(dayDate, hour, minute);
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
  const getEventsForSlot = (dayDate: Date, slotHour: number, slotMinute: number, dayEvents: CalendarEvent[]) => {
    const slotStart = dayjs(dayDate).hour(slotHour).minute(slotMinute).second(0);
    const slotEnd = slotStart.add(calendarConfig.timeSlotDuration, 'minute');
    const dayStart = dayjs(dayDate).startOf('day');
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
  
  return (
    <WeekViewContainer>
      {/* Week Header */}
      <WeekHeader>
        <TimeColumnHeader>{t('pages.schedule.calendar.time')}</TimeColumnHeader>
        {weekDays.map((day, index) => (
          <DayHeader 
            key={index}
            $isToday={day.isToday}
            $isWeekend={day.isWeekend}
          >
            <div className="day-name">{weekdayLabels[index]}</div>
            <div className="day-number">{dayjs(day.date).format('D')}</div>
          </DayHeader>
        ))}
      </WeekHeader>
      
      {/* Time Grid */}
      <TimeGridContainer ref={scrollContainerRef}>
        <TimeGrid>
          {timeSlots.map((slot, slotIndex) => (
            <TimeSlotRow key={`slot-${slotIndex}`}>
              {/* Time Label */}
              {slot.minute === 0 && (
                <TimeLabel>
                  {slot.label}
                </TimeLabel>
              )}
              {slot.minute !== 0 && <TimeLabel />}
              
              {/* Day Columns */}
              {weekDays.map((day, dayIndex) => {
                // Get这个Time槽的任务
                const slotEvents = getEventsForSlot(day.date, slot.hour, slot.minute, day.events);
                
                return (
                  <DayColumn
                    key={`day-${dayIndex}`}
                    $isToday={day.isToday}
                    $isWeekend={day.isWeekend}
                    onClick={() => handleTimeSlotClick(day.date, slot.hour, slot.minute)}
                  >
                    {slotEvents.map((eventWithFlag: any) => {
                      const event = eventWithFlag as CalendarEvent;
                      const startsToday = (eventWithFlag as any).startsToday;
                      const isSameTime = event.start.getTime() === event.end.getTime();
                      const isLongTask = dayjs(event.end).diff(event.start, 'hour') >= 1;
                      
                      return (
                        <Tooltip
                          key={`${event.id}-${startsToday ? 'start' : 'continue'}`}
                          title={
                            <div>
                              <div style={{ fontWeight: 600, marginBottom: 4 }}>{event.title}</div>
                              <div style={{ fontSize: 12 }}>
                                {isSameTime 
                                  ? `${dayjs(event.start).format('HH:mm')} (${t('pages.schedule.calendar.instantTask')})`
                                  : `${dayjs(event.start).format('YYYY-MM-DD HH:mm')} - ${dayjs(event.end).format('YYYY-MM-DD HH:mm')}`
                                }
                              </div>
                              {!startsToday && (
                                <Tooltip title={t('pages.schedule.calendar.continuingTask')}>
                                  <div style={{ fontSize: 11, marginTop: 4, color: '#faad14', display: 'flex', alignItems: 'center', gap: 4 }}>
                                    <ClockCircleOutlined />
                                  </div>
                                </Tooltip>
                              )}
                              {event.isRecurring && (
                                <Tooltip title={t('pages.schedule.calendar.recurringTask')}>
                                  <div style={{ fontSize: 11, marginTop: 4, color: '#52c41a', display: 'flex', alignItems: 'center', gap: 4 }}>
                                    <SyncOutlined />
                                  </div>
                                </Tooltip>
                              )}
                              <div style={{ fontSize: 11, marginTop: 4, opacity: 0.8 }}>
                                {t('common.status')}: {event.status ? t(`pages.schedule.status.${event.status}`) : '-'} | {t('common.priority')}: {event.priority ? t(`pages.tasks.priority.${event.priority}`) : '-'}
                              </div>
                              {isLongTask && (
                                <div style={{ fontSize: 11, marginTop: 4, color: '#1890ff' }}>
                                  {t('pages.schedule.calendar.duration')}: {dayjs(event.end).diff(event.start, 'hour')} {t('pages.schedule.calendar.hours')}
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
                            <div className="event-time">
                              {startsToday ? (
                                isSameTime 
                                  ? dayjs(event.start).format('HH:mm')
                                  : `${dayjs(event.start).format('HH:mm')}-${dayjs(event.end).format('HH:mm')}`
                              ) : `⏳ ${t('common.continue')}`}
                            </div>
                            <div className="event-title">
                              {startsToday ? event.title : `${event.title} (${t('pages.schedule.calendar.crossDayTask')})`}
                            </div>
                            {event.isRecurring && startsToday && (
                              <div className="event-recurring">{t('pages.schedule.calendar.recurringTask')}</div>
                            )}
                          </EventBlock>
                        </Tooltip>
                      );
                    })}
                  </DayColumn>
                );
              })}
            </TimeSlotRow>
          ))}
        </TimeGrid>
        
        {/* Current Time Indicator */}
        {currentTimeTop !== null && (
          <CurrentTimeIndicator $top={currentTimeTop} />
        )}
      </TimeGridContainer>
    </WeekViewContainer>
  );
};

export default WeekView;

