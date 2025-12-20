/**
 * Event Detail Drawer Component
 * EventDetails抽屉Component
 */

import React from 'react';
import styled from '@emotion/styled';
import { Drawer, Button, Tag, Space, Descriptions } from 'antd';
import { 
  ClockCircleOutlined, 
  CalendarOutlined, 
  SyncOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  CloseCircleOutlined,
  EditOutlined,
  DeleteOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import type { CalendarEvent } from './types';
import { useNavigate } from 'react-router-dom';
import { ExecutionStatusTag, LongPeriodTag, NextExecutionTag } from './executionStatus';

const DrawerContent = styled.div`
  padding: 8px;
`;

const EventHeader = styled.div`
  margin-bottom: 24px;
  
  .event-title {
    font-size: 24px;
    font-weight: 700;
    color: rgba(255, 255, 255, 0.95);
    margin-bottom: 12px;
    line-height: 1.3;
  }
  
  .event-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
`;

const InfoSection = styled.div`
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
  
  .section-title {
    font-size: 13px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.7);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
    
    .anticon {
      color: rgba(64, 169, 255, 0.8);
    }
  }
`;

const TimeInfo = styled.div`
  display: flex;
  flex-direction: column;
  gap: 12px;
  
  .time-row {
    display: flex;
    align-items: center;
    gap: 12px;
    
    .time-label {
      font-size: 12px;
      color: rgba(255, 255, 255, 0.5);
      min-width: 60px;
    }
    
    .time-value {
      font-size: 14px;
      font-weight: 600;
      color: rgba(255, 255, 255, 0.9);
      font-family: 'Consolas', 'Monaco', monospace;
      background: rgba(0, 0, 0, 0.2);
      padding: 4px 8px;
      border-radius: 4px;
    }
  }
`;

const RecurringInfo = styled.div`
  .recurring-pattern {
    font-size: 14px;
    color: rgba(255, 255, 255, 0.85);
    margin-bottom: 12px;
    padding: 10px;
    background: rgba(82, 196, 26, 0.1);
    border-left: 3px solid #52c41a;
    border-radius: 4px;
  }
  
  .recurring-details {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
    
    .detail-item {
      .detail-label {
        font-size: 11px;
        color: rgba(255, 255, 255, 0.5);
        margin-bottom: 4px;
      }
      
      .detail-value {
        font-size: 13px;
        color: rgba(255, 255, 255, 0.85);
        font-weight: 500;
      }
    }
  }
`;

const ActionButtons = styled.div`
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-top: 24px;
`;

const StatusIcon = ({ status }: { status?: string }) => {
  switch (status) {
    case 'completed':
      return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
    case 'running':
    case 'in_progress':
      return <SyncOutlined spin style={{ color: '#1890ff' }} />;
    case 'failed':
      return <CloseCircleOutlined style={{ color: '#ff4d4f' }} />;
    case 'pending':
      return <ClockCircleOutlined style={{ color: '#faad14' }} />;
    default:
      return <ExclamationCircleOutlined style={{ color: '#8c8c8c' }} />;
  }
};

const getStatusColor = (status?: string) => {
  switch (status) {
    case 'completed':
      return 'success';
    case 'running':
    case 'in_progress':
      return 'processing';
    case 'failed':
      return 'error';
    case 'pending':
      return 'warning';
    default:
      return 'default';
  }
};

const getPriorityColor = (priority?: string) => {
  switch (priority) {
    case 'urgent':
      return 'red';
    case 'high':
      return 'orange';
    case 'medium':
      return 'blue';
    case 'low':
      return 'green';
    default:
      return 'default';
  }
};

interface EventDetailDrawerProps {
  visible: boolean;
  event: CalendarEvent | null;
  onClose: () => void;
  onEdit?: (event: CalendarEvent) => void;
  onDelete?: (event: CalendarEvent) => void;
  onRun?: (event: CalendarEvent) => void;
}

const EventDetailDrawer: React.FC<EventDetailDrawerProps> = ({
  visible,
  event,
  onClose,
  onEdit,
  onDelete,
  onRun,
}) => {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  
  if (!event) return null;
  
  const handleViewTask = () => {
    if (event.taskId) {
      navigate(`/tasks?taskId=${event.taskId}`);
      onClose();
    }
  };
  
  const formatDateTime = (date: Date) => {
    return dayjs(date).format(i18n.language === 'zh-CN' ? 'YYYY年M月D日 HH:mm' : 'YYYY-MM-DD HH:mm');
  };
  
  const formatDuration = () => {
    const duration = event.end.getTime() - event.start.getTime();
    const hours = Math.floor(duration / (1000 * 60 * 60));
    const minutes = Math.floor((duration % (1000 * 60 * 60)) / (1000 * 60));
    
    if (hours > 0) {
      return `${hours}${t('pages.schedule.calendar.hours')}${minutes > 0 ? ` ${minutes}${t('pages.schedule.calendar.minutes')}` : ''}`;
    }
    return `${minutes}${t('pages.schedule.calendar.minutes')}`;
  };
  
  return (
    <Drawer
      title={t('pages.schedule.calendar.taskDetails')}
      placement="right"
      onClose={onClose}
      open={visible}
      width={480}
      styles={{
        body: { padding: '16px' },
        header: { 
          background: 'rgba(0, 0, 0, 0.2)',
          borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
        },
      }}
    >
      <DrawerContent>
        {/* Event Header */}
        <EventHeader>
          <div className="event-title">{event.title}</div>
          <div className="event-tags">
            {/* Execution Status */}
            {event.executionStatus && (
              <ExecutionStatusTag status={event.executionStatus} showIcon={true} locale="zh" />
            )}
            
            {/* Long Period Task */}
            {event.isLongPeriod && (
              <LongPeriodTag 
                originalEndTime={event.schedule.originalEndTime} 
                locale="zh" 
              />
            )}
            
            {/* Next Execution */}
            {event.isNextExecution && (
              <NextExecutionTag locale="zh" />
            )}
            
            {/* Task Status */}
            <Tag 
              icon={<StatusIcon status={event.status} />} 
              color={getStatusColor(event.status)}
            >
              {event.status ? t(`pages.schedule.status.${event.status}`) : '-'}
            </Tag>
            
            {/* Priority */}
            {event.priority && (
              <Tag color={getPriorityColor(event.priority)}>
                {t('common.priority')}: {t(`pages.tasks.priority.${event.priority}`)}
              </Tag>
            )}
            
            {/* Recurring/One-time */}
            {event.isRecurring && (
              <Tag icon={<SyncOutlined />} color="success">
                {t('pages.schedule.calendar.recurringTask')}
              </Tag>
            )}
            {event.isOneTime && (
              <Tag color="default">
                {t('pages.schedule.calendar.oneTimeTask')}
              </Tag>
            )}
          </div>
        </EventHeader>
        
        {/* Time Information */}
        <InfoSection>
          <div className="section-title">
            <ClockCircleOutlined />
            {t('pages.schedule.calendar.timeInfo')}
          </div>
          <TimeInfo>
            <div className="time-row">
              <div className="time-label">{t('pages.schedule.calendar.startTime')}</div>
              <div className="time-value">{formatDateTime(event.start)}</div>
            </div>
            <div className="time-row">
              <div className="time-label">{t('pages.schedule.calendar.endTime')}</div>
              <div className="time-value">{formatDateTime(event.end)}</div>
            </div>
            <div className="time-row">
              <div className="time-label">{t('pages.schedule.calendar.duration')}</div>
              <div className="time-value">{formatDuration()}</div>
            </div>
          </TimeInfo>
        </InfoSection>
        
        {/* Recurring Information */}
        {event.isRecurring && event.metadata && (
          <InfoSection>
            <div className="section-title">
              <SyncOutlined />
              {t('pages.schedule.calendar.repeatRule')}
            </div>
            <RecurringInfo>
              <div className="recurring-pattern">
                {t('pages.schedule.calendar.repeatEvery')} {event.schedule.repeat_number} {event.schedule.repeat_unit} {t('pages.schedule.calendar.repeatOnce')}
              </div>
              <div className="recurring-details">
                <div className="detail-item">
                  <div className="detail-label">{t('pages.schedule.calendar.repeatType')}</div>
                  <div className="detail-value">{event.metadata.repeatType}</div>
                </div>
                <div className="detail-item">
                  <div className="detail-label">{t('pages.schedule.calendar.timeout')}</div>
                  <div className="detail-value">{event.schedule.time_out}{t('pages.schedule.calendar.seconds')}</div>
                </div>
                {event.metadata.weekDays && event.metadata.weekDays.length > 0 && (
                  <div className="detail-item" style={{ gridColumn: '1 / -1' }}>
                    <div className="detail-label">{t('pages.schedule.calendar.repeatWeekdays')}</div>
                    <div className="detail-value">
                      <Space size={4} wrap>
                        {event.metadata.weekDays.map((day: string) => (
                          <Tag key={day}>{day}</Tag>
                        ))}
                      </Space>
                    </div>
                  </div>
                )}
                {event.metadata.months && event.metadata.months.length > 0 && (
                  <div className="detail-item" style={{ gridColumn: '1 / -1' }}>
                    <div className="detail-label">{t('pages.schedule.calendar.repeatMonths')}</div>
                    <div className="detail-value">
                      <Space size={4} wrap>
                        {event.metadata.months.map((month: string) => (
                          <Tag key={month}>{month}</Tag>
                        ))}
                      </Space>
                    </div>
                  </div>
                )}
              </div>
            </RecurringInfo>
          </InfoSection>
        )}
        
        {/* Task Information */}
        {event.taskId && (
          <InfoSection>
            <div className="section-title">
              <CalendarOutlined />
              {t('pages.schedule.calendar.relatedTask')}
            </div>
            <Descriptions column={1} size="small">
              <Descriptions.Item label={t('pages.schedule.calendar.taskName')}>
                {event.taskName || t('pages.schedule.calendar.unknownTask')}
              </Descriptions.Item>
              <Descriptions.Item label={t('pages.schedule.calendar.taskId')}>
                <code style={{ 
                  fontSize: 11, 
                  background: 'rgba(0, 0, 0, 0.2)',
                  padding: '2px 6px',
                  borderRadius: 3,
                }}>
                  {event.taskId}
                </code>
              </Descriptions.Item>
            </Descriptions>
            <Button 
              type="link" 
              onClick={handleViewTask}
              style={{ padding: 0, marginTop: 8 }}
            >
              {t('pages.schedule.calendar.viewTaskDetails')} →
            </Button>
          </InfoSection>
        )}
        
        {/* Action Buttons */}
        <ActionButtons>
          {onRun && event.status !== 'running' && (
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={() => onRun(event)}
              block
            >
              {t('pages.schedule.calendar.runTask')}
            </Button>
          )}
          {onEdit && (
            <Button
              icon={<EditOutlined />}
              onClick={() => onEdit(event)}
              block
            >
              {t('common.edit')}
            </Button>
          )}
          {onDelete && (
            <Button
              danger
              icon={<DeleteOutlined />}
              onClick={() => onDelete(event)}
              block
              style={{ gridColumn: onRun && event.status !== 'running' ? 'auto' : '1 / -1' }}
            >
              {t('common.delete')}
            </Button>
          )}
        </ActionButtons>
      </DrawerContent>
    </Drawer>
  );
};

export default EventDetailDrawer;

