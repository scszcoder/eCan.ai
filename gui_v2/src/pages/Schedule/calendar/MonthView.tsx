/**
 * Month View Component
 * 月视图日历组件
 */

import React, { useMemo, useRef } from 'react';
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

// 横向滚动容器 - 包裹整个日历以支持横向滚动
const ScrollableContainer = styled.div`
  flex: 1;
  overflow: auto;
  display: flex;
  flex-direction: column;
  min-width: 0; // 允许内容收缩
`;

// 内容容器 - 设置最小宽度以支持横向滚动
const CalendarContent = styled.div`
  min-width: 840px; // 7列 * 120px = 840px，更紧凑适合小屏幕
  display: flex;
  flex-direction: column;
  flex: 1;
`;

const WeekdayHeader = styled.div`
  display: grid;
  grid-template-columns: repeat(7, minmax(120px, 1fr)); // 最小120px，屏幕宽时自动扩展
  background: rgba(0, 0, 0, 0.6); // 增加不透明度，避免滚动叠影
  backdrop-filter: blur(10px); // 添加模糊效果
  -webkit-backdrop-filter: blur(10px); // Safari支持
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  padding: 6px 4px; // 最小化padding
  gap: 3px;
  position: sticky; // 固定在顶部
  top: 0;
  z-index: 1; // 只需要在日历内容上方，不能遮挡下拉菜单
  flex-shrink: 0; // 防止被压缩
`;

const WeekdayCell = styled.div<{ $isWeekend?: boolean }>`
  text-align: center;
  font-weight: 600;
  font-size: 13px;
  color: ${props => props.$isWeekend ? 'rgba(255, 107, 129, 0.85)' : 'rgba(255, 255, 255, 0.65)'};
  text-transform: uppercase;
  letter-spacing: 0.5px;
  min-width: 0; // 允许文字收缩
`;

const WeeksContainer = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 4px; // 最小化padding以最大化可视区域
  min-height: 0; // 允许内容收缩
`;

const WeekRow = styled.div`
  display: grid;
  grid-template-columns: repeat(7, minmax(120px, 1fr)); // 与Header保持一致
  gap: 3px; // 减少列间距
  margin-bottom: 3px; // 减少行间距
  height: 150px; // 增加高度以显示更多任务
  
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
  padding: 4px; // 最小化内边距
  display: flex;
  flex-direction: column;
  position: relative;
  cursor: pointer;
  transition: all 0.3s ease;
  opacity: ${props => props.$isCurrentMonth ? 1 : 0.4};
  height: 100%; // 填充WeekRow的固定高度
  min-height: 0; // 允许内容收缩
  overflow: hidden; // 防止内容溢出
  
  &:hover {
    background: rgba(24, 144, 255, 0.1);
    border-color: rgba(24, 144, 255, 0.3);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    z-index: 1; // 悬浮时提升层级
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
  flex-shrink: 0; // 防止日期数字被压缩
`;

const TodayIndicator = styled.div`
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: linear-gradient(135deg, #1890ff 0%, #40a9ff 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 12px;
  font-weight: 700;
  box-shadow: 0 2px 8px rgba(24, 144, 255, 0.4);
`;

const EventsContainer = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px; // 减少任务项之间的间距
  overflow: hidden; // 隐藏超出的内容
  min-height: 0; // 允许内容收缩
`;

const EventItem = styled.div<{ $color?: string; $backgroundColor?: string; $borderColor?: string }>`
  display: flex;
  align-items: center;
  gap: 3px; // 减少间距
  padding: 2px 5px; // 最小化padding
  background: ${props => props.$backgroundColor || 'rgba(24, 144, 255, 0.1)'};
  border-left: 2px solid ${props => props.$borderColor || '#1890ff'}; // 减少边框宽度
  border-radius: 3px;
  font-size: 11px;
  color: ${props => props.$color || '#1890ff'};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: all 0.2s ease;
  cursor: pointer;
  
  &:hover {
    transform: translateX(2px);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
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
  maxEventsPerDay = 4, // 增加到4行任务
}) => {
  const { t } = useTranslation();
  const calendarConfig = { ...DEFAULT_CALENDAR_CONFIG, ...config };
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const savedScrollPositionRef = useRef<{ top: number; left: number }>({ top: 0, left: 0 });
  
  const monthData = useMemo(() => {
    return generateMonthView(currentDate, events, calendarConfig);
  }, [currentDate, events, calendarConfig]);
  
  // 周从周日开始（标准日历格式）
  const weekdayLabels = [
    t('pages.schedule.calendar.weekdaysShort.sun'),
    t('pages.schedule.calendar.weekdaysShort.mon'),
    t('pages.schedule.calendar.weekdaysShort.tue'),
    t('pages.schedule.calendar.weekdaysShort.wed'),
    t('pages.schedule.calendar.weekdaysShort.thu'),
    t('pages.schedule.calendar.weekdaysShort.fri'),
    t('pages.schedule.calendar.weekdaysShort.sat')
  ];
  
  const handleEventClick = (event: CalendarEvent, e: React.MouseEvent) => {
    e.stopPropagation();
    onEventClick?.(event);
  };
  
  const handleDateClick = (date: Date) => {
    onDateClick?.(date);
  };
  
  const handleMoreEventsClick = (date: Date, allEvents: CalendarEvent[], e: React.MouseEvent) => {
    e.stopPropagation();
    onMoreEventsClick?.(date, allEvents);
  };
  
  // 使用 useEffectOnActive 在组件激活时恢复滚动位置
  useEffectOnActive(
    () => {
      // 组件激活时：恢复滚动位置
      const container = scrollContainerRef.current;
      if (container && (savedScrollPositionRef.current.top !== 0 || savedScrollPositionRef.current.left !== 0)) {
        requestAnimationFrame(() => {
          container.scrollTop = savedScrollPositionRef.current.top;
          container.scrollLeft = savedScrollPositionRef.current.left;
        });
      }
      
      // 返回清理函数，在组件失活前保存滚动位置
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
  
  const renderEvent = (event: CalendarEvent) => {
    const eventTime = dayjs(event.start).format('HH:mm');
    const isSameTime = event.start.getTime() === event.end.getTime();
    
    return (
      <Tooltip 
        key={event.id} 
          title={
          <div>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>{event.title}</div>
            <div style={{ fontSize: 12 }}>
              {isSameTime 
                ? `${dayjs(event.start).format('HH:mm')} (${t('pages.schedule.calendar.instantTask')})`
                : `${dayjs(event.start).format('HH:mm')} - ${dayjs(event.end).format('HH:mm')}`
              }
            </div>
            {event.isRecurring && (
              <div style={{ fontSize: 11, marginTop: 4, color: '#52c41a' }}>
                {t('pages.schedule.calendar.recurringTask')}
              </div>
            )}
            <div style={{ fontSize: 11, marginTop: 4, opacity: 0.8 }}>
              {t('common.status')}: {event.status}
            </div>
          </div>
        }
        mouseEnterDelay={0.3}
      >
        <EventItem
          $color={event.color}
          $backgroundColor={event.backgroundColor}
          $borderColor={event.borderColor}
          onClick={(e) => handleEventClick(event, e)}
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
  };
  
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
                  const visibleEvents = day.events.slice(0, maxEventsPerDay);
                  const remainingCount = Math.max(0, day.events.length - maxEventsPerDay);
                  
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
                          <TodayIndicator>{dayjs(day.date).format('D')}</TodayIndicator>
                        ) : (
                          <span>{dayjs(day.date).format('D')}</span>
                        )}
                        {day.hasEvents && !day.isToday && (
                          <Badge 
                            count={day.eventCount} 
                            style={{ 
                              backgroundColor: 'rgba(24, 144, 255, 0.6)',
                              fontSize: 10,
                              height: 16,
                              minWidth: 16,
                              lineHeight: '16px',
                            }} 
                          />
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

export default MonthView;

