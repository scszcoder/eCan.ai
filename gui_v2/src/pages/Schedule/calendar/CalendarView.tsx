/**
 * Calendar View Component
 * 日历视图主Component
 */

import React, { useState, useMemo, useCallback, useEffect } from 'react';
import styled from '@emotion/styled';
import { Button, Space, Segmented, Tooltip, Badge, Modal } from 'antd';
import {
  LeftOutlined,
  RightOutlined,
  CalendarOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import 'dayjs/locale/zh-cn';
import 'dayjs/locale/en';
import MonthView from './MonthView';
import WeekView from './WeekView';
import DayView from './DayView';
import EventDetailDrawer from './EventDetailDrawer';
import ScheduleFormModal from './ScheduleFormModal';
import { CalendarViewType } from './types';
import type { CalendarEvent, CalendarConfig } from './types';
import { 
  navigateNext, 
  navigatePrevious, 
  formatViewTitle,
  schedulesToEvents,
  DEFAULT_CALENDAR_CONFIG,
} from './utils';
import type { TaskSchedule } from '../Schedule.types';

const CalendarContainer = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-primary);
  border-radius: 12px;
  overflow: hidden;
`;

const CalendarHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px; // Minimum化padding
  background: rgba(0, 0, 0, 0.2);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  flex-shrink: 0;
`;

const HeaderLeft = styled.div`
  display: flex;
  align-items: center;
  gap: 16px;
`;

const TitleSection = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  
  .calendar-title {
    font-size: 20px;
    font-weight: 700;
    color: rgba(255, 255, 255, 0.95);
    min-width: 200px;
  }
`;

const NavigationButtons = styled.div`
  display: flex;
  gap: 8px;
`;

const HeaderRight = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
`;

const CalendarBody = styled.div`
  flex: 1;
  overflow: hidden;
  padding: 4px; // Minimum化padding以Maximum化可视区域
  contain: layout style paint; // CSS containment 优化渲染性能
`;

const StyledSegmented = styled(Segmented)`
  &.ant-segmented {
    background: rgba(0, 0, 0, 0.2);
    
    .ant-segmented-item {
      color: rgba(255, 255, 255, 0.7);
      
      &:hover {
        color: rgba(255, 255, 255, 0.9);
      }
      
      &-selected {
        background: #1890ff; // 使用纯色替代渐变，减少GPU消耗
        color: white;
      }
    }
  }
`;

const ActionButton = styled(Button)`
  &.ant-btn {
    background: transparent !important;
    border: 1px solid rgba(255, 255, 255, 0.2) !important;
    color: rgba(255, 255, 255, 0.85) !important;
    transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease !important;
    
    &:hover {
      background: rgba(24, 144, 255, 0.1) !important;
      border-color: rgba(24, 144, 255, 0.5) !important;
      color: rgba(255, 255, 255, 0.95) !important;
    }
    
    &.ant-btn-primary {
      background: #1890ff !important; // 使用纯色替代渐变，减少GPU消耗
      border: none !important;
      color: white !important;
      
      &:hover {
        background: #40a9ff !important;
      }
    }
  }
`;

// 性能优化：提取Modal中的常量样式对象，避免每次渲染创建新对象
const MORE_EVENTS_CONTAINER_STYLE = {
  maxHeight: '60vh',
  overflowY: 'auto' as const,
};

const MORE_EVENT_ITEM_BASE_STYLE = {
  padding: '12px',
  marginBottom: '8px',
  borderRadius: '6px',
  cursor: 'pointer' as const,
  border: '1px solid rgba(255, 255, 255, 0.1)',
  background: 'rgba(255, 255, 255, 0.05)',
  transition: 'background-color 0.2s ease, border-color 0.2s ease', // 移除box-shadow transition，减少GPU消耗
};

const MORE_EVENT_HEADER_STYLE = {
  display: 'flex',
  alignItems: 'center' as const,
  gap: '8px',
  marginBottom: '4px',
};

const MORE_EVENT_DOT_STYLE = {
  width: '8px',
  height: '8px',
  borderRadius: '50%',
  flexShrink: 0,
};

const MORE_EVENT_TITLE_STYLE = {
  fontWeight: 500,
  fontSize: '14px',
  flex: 1,
};

const MORE_EVENT_TIME_STYLE = {
  fontSize: '12px',
  color: 'rgba(255, 255, 255, 0.6)',
  marginLeft: '16px',
};

const MORE_EVENT_BADGE_STYLE = {
  backgroundColor: '#52c41a',
  fontSize: '10px',
};

const NO_EVENTS_STYLE = {
  textAlign: 'center' as const,
  padding: '40px',
  color: 'rgba(255, 255, 255, 0.4)',
};

interface CalendarViewProps {
  schedules: TaskSchedule[];
  onRefresh?: () => void;
  onCreateSchedule?: (schedule: any) => void;
  onUpdateSchedule?: (schedule: TaskSchedule) => void;
  onDeleteSchedule?: (schedule: TaskSchedule) => void;
  onRunTask?: (event: CalendarEvent) => void;
  loading?: boolean;
  config?: Partial<CalendarConfig>;
}

const CalendarView: React.FC<CalendarViewProps> = ({
  schedules,
  onRefresh,
  onCreateSchedule,
  onUpdateSchedule,
  onDeleteSchedule,
  onRunTask,
  loading = false,
  config = {},
}) => {
  const { t, i18n } = useTranslation();
  const [currentDate, setCurrentDate] = useState<Date>(new Date());
  const [viewType, setViewType] = useState<CalendarViewType>(CalendarViewType.MONTH);
  const [selectedEvent, setSelectedEvent] = useState<CalendarEvent | null>(null);
  const [detailDrawerVisible, setDetailDrawerVisible] = useState(false);
  const [formModalVisible, setFormModalVisible] = useState(false);
  
  // 动态Settings dayjs locale
  useEffect(() => {
    const locale = i18n.language === 'zh-CN' ? 'zh-cn' : 'en';
    dayjs.locale(locale);
  }, [i18n.language]);
  const [editingSchedule, setEditingSchedule] = useState<TaskSchedule | null>(null);
  
  // 更多EventModalStatus
  const [moreEventsModalVisible, setMoreEventsModalVisible] = useState(false);
  const [moreEventsDate, setMoreEventsDate] = useState<Date | null>(null);
  const [moreEventsList, setMoreEventsList] = useState<CalendarEvent[]>([]);
  
  const calendarConfig = { ...DEFAULT_CALENDAR_CONFIG, ...config };
  
  // Convert schedules to events - 性能优化：缓存转换结果
  const events = useMemo(() => {
    console.time('schedulesToEvents');
    const result = schedulesToEvents(schedules);
    console.timeEnd('schedulesToEvents');
    return result;
  }, [schedules]);
  
  // Calculate statistics
  const statistics = useMemo(() => {
    const total = schedules.length;
    const recurring = schedules.filter(s => s.repeat_type !== 'none').length;
    const oneTime = total - recurring;
    
    return { total, recurring, oneTime };
  }, [schedules]);
  
  // Navigation handlers
  const handlePrevious = useCallback(() => {
    setCurrentDate(prev => navigatePrevious(prev, viewType));
  }, [viewType]);
  
  const handleNext = useCallback(() => {
    setCurrentDate(prev => navigateNext(prev, viewType));
  }, [viewType]);
  
  const handleToday = useCallback(() => {
    setCurrentDate(new Date());
  }, []);
  
  // View type change handler
  const handleViewChange = useCallback((value: unknown) => {
    setViewType(value as CalendarViewType);
  }, []);
  
  // Event handlers
  const handleEventClick = useCallback((event: CalendarEvent) => {
    setSelectedEvent(event);
    setDetailDrawerVisible(true);
  }, []);
  
  const handleDateClick = useCallback((date: Date) => {
    console.log('Date clicked:', date);
    // TODO: Open create modal with pre-filled date
  }, []);
  
  const handleTimeSlotClick = useCallback((date: Date, hour: number, minute: number) => {
    console.log('Time slot clicked:', date, hour, minute);
    // TODO: Open create modal with pre-filled date and time
  }, []);
  
  // Drawer handlers
  const handleCloseDetailDrawer = useCallback(() => {
    setDetailDrawerVisible(false);
    setSelectedEvent(null);
  }, []);
  
  const handleEditEvent = useCallback((event: CalendarEvent) => {
    setEditingSchedule(event.schedule);
    setFormModalVisible(true);
    setDetailDrawerVisible(false);
  }, []);
  
  const handleDeleteEvent = useCallback((event: CalendarEvent) => {
    if (onDeleteSchedule && event.schedule) {
      onDeleteSchedule(event.schedule);
      setDetailDrawerVisible(false);
    }
  }, [onDeleteSchedule]);
  
  const handleRunEvent = useCallback((event: CalendarEvent) => {
    if (onRunTask) {
      onRunTask(event);
    }
  }, [onRunTask]);
  
  // Form modal handlers
  const handleOpenCreateModal = useCallback(() => {
    setEditingSchedule(null);
    setFormModalVisible(true);
  }, []);
  
  const handleCloseFormModal = useCallback(() => {
    setFormModalVisible(false);
    setEditingSchedule(null);
  }, []);
  
  const handleSubmitForm = useCallback((values: any) => {
    if (editingSchedule) {
      // Update existing schedule
      if (onUpdateSchedule) {
        onUpdateSchedule({ ...editingSchedule, ...values });
      }
    } else {
      // Create new schedule
      if (onCreateSchedule) {
        onCreateSchedule(values);
      }
    }
    handleCloseFormModal();
  }, [editingSchedule, onCreateSchedule, onUpdateSchedule, handleCloseFormModal]);
  
  // More events modal handlers - 性能优化：使用Map去重更快
  const handleMoreEventsClick = useCallback((date: Date, events: CalendarEvent[]) => {
    // 去重：使用Map提升性能
    const eventMap = new Map<string, CalendarEvent>();
    events.forEach(event => {
      const key = `${event.title}_${dayjs(event.start).format('YYYY-MM-DD-HH-mm')}`;
      if (!eventMap.has(key)) {
        eventMap.set(key, event);
      }
    });
    const uniqueEvents = Array.from(eventMap.values());
    
    setMoreEventsDate(date);
    setMoreEventsList(uniqueEvents);
    setMoreEventsModalVisible(true);
  }, []);
  
  const handleCloseMoreEventsModal = useCallback(() => {
    setMoreEventsModalVisible(false);
    setMoreEventsDate(null);
    setMoreEventsList([]);
  }, []);
  
  // Get title text - 性能优化：缓存标题文本
  const titleText = useMemo(() => {
    return formatViewTitle(currentDate, viewType, i18n.language);
  }, [currentDate, viewType, i18n.language]);
  
  // 性能优化：缓存 view 的 options，避免每次渲染创建新数组
  const viewOptions = useMemo(() => [
    { label: t('pages.schedule.calendar.month'), value: CalendarViewType.MONTH },
    { label: t('pages.schedule.calendar.week'), value: CalendarViewType.WEEK },
    { label: t('pages.schedule.calendar.day'), value: CalendarViewType.DAY },
  ], [t]);
  
  // Render appropriate view
  const renderView = () => {
    const commonProps = {
      currentDate,
      events,
      config: calendarConfig,
      onEventClick: handleEventClick,
    };
    
    switch (viewType) {
      case CalendarViewType.MONTH:
        return (
          <MonthView
            {...commonProps}
            onDateClick={handleDateClick}
            onMoreEventsClick={handleMoreEventsClick}
          />
        );
      case CalendarViewType.WEEK:
        return (
          <WeekView
            {...commonProps}
            onTimeSlotClick={handleTimeSlotClick}
          />
        );
      case CalendarViewType.DAY:
        return (
          <DayView
            {...commonProps}
            onTimeSlotClick={handleTimeSlotClick}
          />
        );
      default:
        return null;
    }
  };
  
  return (
    <CalendarContainer>
      {/* Calendar Header */}
      <CalendarHeader>
        <HeaderLeft>
          {/* Title and Navigation */}
          <TitleSection>
            <CalendarOutlined style={{ fontSize: 24, color: '#1890ff' }} />
            <div className="calendar-title">{titleText}</div>
          </TitleSection>
          
          <NavigationButtons>
            <ActionButton
              icon={<LeftOutlined />}
              onClick={handlePrevious}
              size="small"
            />
            <ActionButton
              onClick={handleToday}
              size="small"
            >
              {t('pages.schedule.calendar.today')}
            </ActionButton>
            <ActionButton
              icon={<RightOutlined />}
              onClick={handleNext}
              size="small"
            />
          </NavigationButtons>
          
          {/* Statistics */}
          <Space size={12}>
            <Tooltip title={t('pages.tasks.title')}>
              <Badge 
                count={statistics.total} 
                style={{ backgroundColor: '#1890ff' }}
                showZero
              />
            </Tooltip>
            <Tooltip title={t('pages.schedule.calendar.recurringTask')}>
              <Badge 
                count={statistics.recurring} 
                style={{ backgroundColor: '#52c41a' }}
                showZero
              />
            </Tooltip>
            <Tooltip title={t('pages.schedule.repeatSettings')}>
              <Badge 
                count={statistics.oneTime} 
                style={{ backgroundColor: '#faad14' }}
                showZero
              />
            </Tooltip>
          </Space>
        </HeaderLeft>
        
        <HeaderRight>
          {/* View Type Selector */}
          <StyledSegmented
            value={viewType}
            onChange={handleViewChange}
            options={viewOptions}
          />
          
          {/* Action Buttons */}
          <Tooltip title={t('common.refresh')}>
            <ActionButton
              type="text"
              icon={<ReloadOutlined spin={loading} />}
              onClick={onRefresh}
              disabled={loading}
              size="middle"
            />
          </Tooltip>
          
          <Tooltip title={t('pages.schedule.addSchedule')}>
            <ActionButton
              type="text"
              icon={<PlusOutlined />}
              onClick={handleOpenCreateModal}
              size="middle"
              style={{ color: '#1890ff' }}
            />
          </Tooltip>
        </HeaderRight>
      </CalendarHeader>
      
      {/* Calendar Body */}
      <CalendarBody>
        {renderView()}
      </CalendarBody>
      
      {/* Event Detail Drawer */}
      <EventDetailDrawer
        visible={detailDrawerVisible}
        event={selectedEvent}
        onClose={handleCloseDetailDrawer}
        onEdit={handleEditEvent}
        onDelete={handleDeleteEvent}
        onRun={handleRunEvent}
      />
      
      {/* Schedule Form Modal */}
      <ScheduleFormModal
        visible={formModalVisible}
        schedule={editingSchedule}
        onClose={handleCloseFormModal}
        onSubmit={handleSubmitForm}
        loading={loading}
      />
      
      {/* More Events Modal - 性能优化：使用提取的常量样式 */}
      <Modal
        title={moreEventsDate ? `${dayjs(moreEventsDate).format(i18n.language === 'zh-CN' ? 'YYYY年M月D日' : 'YYYY-MM-DD')} - ${t('pages.schedule.calendar.allEvents')}` : t('pages.schedule.calendar.allEvents')}
        open={moreEventsModalVisible}
        onCancel={handleCloseMoreEventsModal}
        footer={null}
        width={600}
        destroyOnHidden
      >
        <div style={MORE_EVENTS_CONTAINER_STYLE}>
          {moreEventsList.map((event, index) => (
            <div
              key={`${event.id}-${index}`}
              onClick={() => {
                handleEventClick(event);
                handleCloseMoreEventsModal();
              }}
              style={MORE_EVENT_ITEM_BASE_STYLE}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)';
                e.currentTarget.style.borderColor = event.color || '#1890ff';
                // 移除box-shadow减少GPU消耗
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'rgba(255, 255, 255, 0.05)';
                e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.1)';
              }}
            >
              <div style={MORE_EVENT_HEADER_STYLE}>
                <div style={{
                  ...MORE_EVENT_DOT_STYLE,
                  background: event.color || '#1890ff',
                }} />
                <div style={MORE_EVENT_TITLE_STYLE}>
                  {event.title}
                </div>
                {event.isRecurring && (
                  <Badge 
                    count={t('pages.schedule.calendar.recurringTask')} 
                    style={MORE_EVENT_BADGE_STYLE} 
                  />
                )}
              </div>
              <div style={MORE_EVENT_TIME_STYLE}>
                {dayjs(event.start).format('HH:mm')} - {dayjs(event.end).format('HH:mm')}
              </div>
            </div>
          ))}
          {moreEventsList.length === 0 && (
            <div style={NO_EVENTS_STYLE}>
              {t('pages.schedule.calendar.noEvents')}
            </div>
          )}
        </div>
      </Modal>
    </CalendarContainer>
  );
};

export default CalendarView;

