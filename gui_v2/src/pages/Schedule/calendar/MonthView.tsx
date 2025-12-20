/**
 * Month View Component
 * 月视图日历Component - 性能优化版
 */

import React, { useMemo, useRef, memo, useCallback } from 'react';
import styled from '@emotion/styled';
import dayjs from 'dayjs';
import { Badge, Tooltip } from 'antd';
import { SyncOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useEffectOnActive } from 'keepalive-for-react';
import type { CalendarEvent, CalendarConfig } from './types';
import { generateMonthView, DEFAULT_CALENDAR_CONFIG } from './utils';

const MonthViewContainer = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-secondary);
  border-radius: 12px;
  overflow: hidden;
`;

// 横向ScrollContainer - 包裹整个日历以Support横向Scroll
const ScrollableContainer = styled.div`
  flex: 1;
  overflow: auto;
  display: flex;
  flex-direction: column;
  min-width: 0; // AllowContent收缩
`;

// ContentContainer - SettingsMinimumWidth以Support横向Scroll
const CalendarContent = styled.div`
  min-width: 840px; // 7列 * 120px = 840px，更紧凑适合小屏幕
  display: flex;
  flex-direction: column;
  flex: 1;
`;

const WeekdayHeader = styled.div`
  display: grid;
  grid-template-columns: repeat(7, minmax(120px, 1fr)); // Minimum120px，屏幕宽时自动Extended
  background: rgba(0, 0, 0, 0.85); // 提高不透明度，移除backdrop-filter以减少GPU消耗
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  padding: 6px 4px; // Minimum化padding
  gap: 3px;
  position: sticky; // 固定在Top
  top: 0;
  z-index: 1; // 只Need在日历Content上方，不能遮挡下拉Menu
  flex-shrink: 0; // 防止被压缩
`;

const WeekdayCell = styled.div<{ $isWeekend?: boolean }>`
  text-align: center;
  font-weight: 600;
  font-size: 13px;
  color: ${props => props.$isWeekend ? 'rgba(255, 107, 129, 0.85)' : 'rgba(255, 255, 255, 0.65)'};
  text-transform: uppercase;
  letter-spacing: 0.5px;
  min-width: 0; // Allow文字收缩
`;

const WeeksContainer = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 4px; // Minimum化padding以Maximum化可视区域
  min-height: 0; // AllowContent收缩
`;

const WeekRow = styled.div`
  display: grid;
  grid-template-columns: repeat(7, minmax(120px, 1fr)); // 与Header保持一致
  gap: 3px; // 减少列间距
  margin-bottom: 3px; // 减少行间距
  height: 145px; // 适配4行任务显示
  
  &:last-child {
    margin-bottom: 0;
  }
`;

const DayCell = styled.div<{ 
  $isToday?: boolean; 
  $isCurrentMonth?: boolean; 
  $isWeekend?: boolean;
  $hasEvents?: boolean;
}>`
  background: ${props => {
    if (props.$isToday) return 'linear-gradient(135deg, rgba(24, 144, 255, 0.2) 0%, rgba(24, 144, 255, 0.1) 100%)';
    if (props.$hasEvents) return 'rgba(255, 255, 255, 0.03)';
    return 'rgba(255, 255, 255, 0.02)';
  }};
  border: 1px solid ${props => {
    if (props.$isToday) return 'rgba(24, 144, 255, 0.5)';
    return 'rgba(255, 255, 255, 0.08)';
  }};
  border-radius: 6px;
  padding: 4px;
  display: flex;
  flex-direction: column;
  position: relative;
  cursor: pointer;
  opacity: ${props => props.$isCurrentMonth ? 1 : 0.4};
  height: 100%;
  min-height: 0;
  overflow: hidden;
  
  &:hover {
    background: rgba(24, 144, 255, 0.1);
    border-color: rgba(24, 144, 255, 0.3);
    z-index: 1;
  }
`;

const DayNumber = styled.div<{ $isToday?: boolean; $isWeekend?: boolean }>`
  font-size: 14px;
  font-weight: ${props => props.$isToday ? 700 : 600};
  color: ${props => {
    if (props.$isToday) return '#1890ff';
    if (props.$isWeekend) return 'rgba(255, 107, 129, 0.85)';
    return 'rgba(255, 255, 255, 0.85)';
  }};
  margin-bottom: 4px; // 减少间距
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0; // 防止Date数字被压缩
`;

const TodayIndicator = styled.div`
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #1890ff; // 使用纯色替代渐变，减少GPU消耗
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 12px;
  font-weight: 700;
  box-shadow: 0 2px 4px rgba(24, 144, 255, 0.3); // 减小阴影范围
`;

const EventsContainer = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px; // 减少任务项之间的间距
  overflow: hidden; // Hide超出的Content
  min-height: 0; // AllowContent收缩
`;

const EventItem = styled.div<{ $color?: string; $backgroundColor?: string; $borderColor?: string }>`
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 2px 5px;
  background: ${props => props.$backgroundColor || 'rgba(24, 144, 255, 0.1)'};
  border-left: 2px solid ${props => props.$borderColor || '#1890ff'};
  border-radius: 3px;
  font-size: 11px;
  color: ${props => props.$color || '#1890ff'};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: pointer;
  
  &:hover {
    background: ${props => props.$backgroundColor ? `${props.$backgroundColor}dd` : 'rgba(24, 144, 255, 0.2)'};
  }
`;

const EventDot = styled.div<{ $color?: string }>`
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: ${props => props.$color || '#1890ff'};
  flex-shrink: 0;
`;

const EventTitle = styled.span`
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
`;

const RecurringBadge = styled.div`
  font-size: 10px;
  padding: 1px 4px;
  background: rgba(82, 196, 26, 0.2);
  color: #52c41a;
  border-radius: 3px;
  font-weight: 600;
  flex-shrink: 0;
`;

const MoreEventsIndicator = styled.div`
  font-size: 10px;
  color: rgba(255, 255, 255, 0.5);
  text-align: center;
  padding: 2px;
  cursor: pointer;
  
  &:hover {
    color: rgba(255, 255, 255, 0.8);
    text-decoration: underline;
  }
`;

// 性能优化：提取常量样式，避免每次渲染创建新对象
const BADGE_STYLE = {
  backgroundColor: 'rgba(24, 144, 255, 0.6)',
  fontSize: 10,
  height: 16,
  minWidth: 16,
  lineHeight: '16px',
} as const;

// 性能优化：日期格式化缓存，避免重复调用dayjs.format
const dateFormatCache = new Map<string, string>();
const formatDateNumber = (date: Date): string => {
  const key = date.toISOString();
  if (!dateFormatCache.has(key)) {
    dateFormatCache.set(key, dayjs(date).format('D'));
    // 限制缓存大小
    if (dateFormatCache.size > 100) {
      const firstKey = dateFormatCache.keys().next().value;
      if (firstKey) {
        dateFormatCache.delete(firstKey);
      }
    }
  }
  return dateFormatCache.get(key)!;
};

// 性能优化：提取EventItem组件，避免重复创建
const EventItemComponent = memo<{
  event: CalendarEvent;
  onClick: (event: CalendarEvent, e: React.MouseEvent) => void;
  t: any;
}>(({ event, onClick, t }) => {
  const eventTime = useMemo(() => dayjs(event.start).format('HH:mm'), [event.start]);
  const isSameTime = useMemo(() => event.start.getTime() === event.end.getTime(), [event.start, event.end]);
  const endTime = useMemo(() => dayjs(event.end).format('HH:mm'), [event.end]);
  
  const tooltipTitle = useMemo(() => (
    <div>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{event.title}</div>
      <div style={{ fontSize: 12 }}>
        {isSameTime 
          ? `${eventTime} (${t('pages.schedule.calendar.instantTask')})`
          : `${eventTime} - ${endTime}`
        }
      </div>
      {event.isRecurring && (
        <div style={{ fontSize: 11, marginTop: 4, color: '#52c41a' }}>
          {t('pages.schedule.calendar.recurringTask')}
        </div>
      )}
      <div style={{ fontSize: 11, marginTop: 4, opacity: 0.8 }}>
        {t('common.status')}: {event.status ? t(`pages.schedule.status.${event.status}`) : '-'}
      </div>
    </div>
  ), [event.title, eventTime, endTime, isSameTime, event.isRecurring, event.status, t]);
  
  return (
    <Tooltip 
      title={tooltipTitle}
      mouseEnterDelay={0.5}
      destroyOnHidden
    >
      <EventItem
        $color={event.color}
        $backgroundColor={event.backgroundColor}
        $borderColor={event.borderColor}
        onClick={(e) => onClick(event, e)}
      >
        <EventDot $color={event.borderColor} />
        <EventTitle>
          {eventTime} {event.title}
        </EventTitle>
        {event.isRecurring && (
          <RecurringBadge title={t('pages.schedule.calendar.recurringTask')}>
            <SyncOutlined />
          </RecurringBadge>
        )}
      </EventItem>
    </Tooltip>
  );
});

EventItemComponent.displayName = 'EventItemComponent';

interface MonthViewProps {
  currentDate: Date;
  events: CalendarEvent[];
  config?: Partial<CalendarConfig>;
  onEventClick?: (event: CalendarEvent) => void;
  onDateClick?: (date: Date) => void;
  onMoreEventsClick?: (date: Date, events: CalendarEvent[]) => void;
  maxEventsPerDay?: number;
}

const MonthView: React.FC<MonthViewProps> = ({
  currentDate,
  events,
  config = {},
  onEventClick,
  onDateClick,
  onMoreEventsClick,
  maxEventsPerDay = 4, // 显示4行任务，视觉效果更好
}) => {
  const { t } = useTranslation();
  const calendarConfig = { ...DEFAULT_CALENDAR_CONFIG, ...config };
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const savedScrollPositionRef = useRef<{ top: number; left: number }>({ top: 0, left: 0 });
  
  const monthData = useMemo(() => {
    return generateMonthView(currentDate, events, calendarConfig);
  }, [currentDate, events, calendarConfig]);
  
  // 周从周日开始（Standard日历格式）
  const weekdayLabels = [
    t('pages.schedule.calendar.weekdaysShort.sun'),
    t('pages.schedule.calendar.weekdaysShort.mon'),
    t('pages.schedule.calendar.weekdaysShort.tue'),
    t('pages.schedule.calendar.weekdaysShort.wed'),
    t('pages.schedule.calendar.weekdaysShort.thu'),
    t('pages.schedule.calendar.weekdaysShort.fri'),
    t('pages.schedule.calendar.weekdaysShort.sat')
  ];
  
  const handleEventClick = useCallback((event: CalendarEvent, e: React.MouseEvent) => {
    e.stopPropagation();
    onEventClick?.(event);
  }, [onEventClick]);
  
  const handleDateClick = useCallback((date: Date) => {
    onDateClick?.(date);
  }, [onDateClick]);
  
  const handleMoreEventsClick = useCallback((date: Date, allEvents: CalendarEvent[], e: React.MouseEvent) => {
    e.stopPropagation();
    onMoreEventsClick?.(date, allEvents);
  }, [onMoreEventsClick]);
  
  // 使用 useEffectOnActive 在ComponentActive时RestoreScrollPosition
  useEffectOnActive(
    () => {
      // ComponentActive时：RestoreScrollPosition
      const container = scrollContainerRef.current;
      if (container && (savedScrollPositionRef.current.top !== 0 || savedScrollPositionRef.current.left !== 0)) {
        requestAnimationFrame(() => {
          container.scrollTop = savedScrollPositionRef.current.top;
          container.scrollLeft = savedScrollPositionRef.current.left;
        });
      }
      
      // 返回CleanupFunction，在Component失活前SaveScrollPosition
      return () => {
        const container = scrollContainerRef.current;
        if (container) {
          savedScrollPositionRef.current = {
            top: container.scrollTop,
            left: container.scrollLeft,
          };
        }
      };
    },
    []
  );
  
  // 性能优化：使用复用组件渲染事件
  const renderEvent = useCallback((event: CalendarEvent) => {
    return (
      <EventItemComponent
        key={event.id}
        event={event}
        onClick={handleEventClick}
        t={t}
      />
    );
  }, [handleEventClick, t]);
  
  return (
    <MonthViewContainer>
      <ScrollableContainer ref={scrollContainerRef}>
        <CalendarContent>
          {/* Weekday Headers */}
          <WeekdayHeader>
            {weekdayLabels.map((label, index) => (
              <WeekdayCell key={label} $isWeekend={index === 0 || index === 6}>
                {label}
              </WeekdayCell>
            ))}
          </WeekdayHeader>
          
          {/* Weeks and Days */}
          <WeeksContainer>
            {monthData.weeks.map((week, weekIndex) => (
              <WeekRow key={`week-${weekIndex}`}>
                {week.days.map((day, dayIndex) => {
                  // 性能优化：使用useMemo缓存切片和计数，避免重复计算
                  const visibleEvents = useMemo(() => day.events.slice(0, maxEventsPerDay), [day.events, maxEventsPerDay]);
                  const remainingCount = useMemo(() => Math.max(0, day.events.length - maxEventsPerDay), [day.events.length, maxEventsPerDay]);
                  const dayNumber = useMemo(() => formatDateNumber(day.date), [day.date]);
                  
                  return (
                    <DayCell
                      key={`day-${dayIndex}`}
                      $isToday={day.isToday}
                      $isCurrentMonth={day.isCurrentMonth}
                      $isWeekend={day.isWeekend}
                      $hasEvents={day.hasEvents}
                      onClick={() => handleDateClick(day.date)}
                    >
                      <DayNumber $isToday={day.isToday} $isWeekend={day.isWeekend}>
                        {day.isToday ? (
                          <TodayIndicator>{dayNumber}</TodayIndicator>
                        ) : (
                          <span>{dayNumber}</span>
                        )}
                        {day.hasEvents && !day.isToday && (
                          <Badge count={day.eventCount} style={BADGE_STYLE} />
                        )}
                      </DayNumber>
                      
                      <EventsContainer>
                        {visibleEvents.map(renderEvent)}
                        {remainingCount > 0 && (
                          <MoreEventsIndicator 
                            onClick={(e) => handleMoreEventsClick(day.date, day.events, e)}
                          >
                            +{remainingCount} {t('pages.schedule.calendar.more')}
                          </MoreEventsIndicator>
                        )}
                      </EventsContainer>
                    </DayCell>
                  );
                })}
              </WeekRow>
            ))}
          </WeeksContainer>
        </CalendarContent>
      </ScrollableContainer>
    </MonthViewContainer>
  );
};

// 性能优化：使用memo避免不必要的重渲染
export default memo(MonthView);

