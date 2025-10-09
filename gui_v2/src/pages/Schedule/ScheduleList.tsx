import React from 'react';
import { List, Space, Tag } from 'antd';
import { useTranslation } from 'react-i18next';
import SearchFilter from '../../components/Common/SearchFilter';
import type { TaskSchedule } from './Schedule.types';
import styled from '@emotion/styled';

const ScheduleItem = styled.div`
    padding: 12px;
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    background: var(--bg-secondary);
    border-radius: 12px;
    margin: 6px 0;
    border: 2px solid transparent;
    position: relative;
    overflow: hidden;

    &::before {
        content: '';
        position: absolute;
        left: 0;
        top: 0;
        height: 100%;
        width: 4px;
        background: transparent;
        transition: all 0.3s ease;
    }

    &:hover {
        background: var(--bg-tertiary);
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);

        &::before {
            width: 3px;
            background: var(--primary-color);
        }
    }
    
    .ant-typography {
        color: var(--text-primary);
    }
    
    .ant-tag {
        margin: 0;
        padding: 4px 12px;
        border-radius: 6px;
        font-size: 12px;
        font-weight: 500;
        border: none;
    }
`;

const ScheduleSection = styled.div`
    margin-bottom: 12px;
    
    &:last-child {
        margin-bottom: 0;
    }
`;

const SectionLabel = styled.div`
    font-size: 11px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.45);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 6px;
`;

const TimeRange = styled.div`
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: rgba(0, 0, 0, 0.2);
    border-radius: 8px;
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 13px;
    color: rgba(255, 255, 255, 0.85);
    
    .separator {
        color: rgba(255, 255, 255, 0.3);
        font-weight: bold;
    }
`;

const ScheduleTitle = styled.div`
    font-size: 16px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.95);
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
`;

interface ScheduleListProps {
    schedules: TaskSchedule[];
    onSelect: (schedule: TaskSchedule) => void;
    onSearch: (value: string) => void;
    onFilter: (filters: Record<string, any>) => void;
    onFilterReset: () => void;
    filters: Record<string, any>;
}

const ScheduleList: React.FC<ScheduleListProps> = ({ schedules, onSelect, onSearch, onFilter, onFilterReset }) => {
    const { t } = useTranslation();

    return (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
            {/* Fixed Header - Search */}
            <div style={{ 
                padding: '8px',
                borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
                flexShrink: 0
            }}>
                <SearchFilter
                    onSearch={onSearch}
                    onFilter={onFilter}
                    onFilterReset={onFilterReset}
                    filterOptions={[]}
                    placeholder={t('pages.schedule.searchSchedulePlaceholder', '搜索日程...')}
                />
            </div>

            {/* Scrollable List Content */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '8px' }}>
                <List
                    dataSource={schedules}
                    renderItem={(schedule) => (
                    <ScheduleItem onClick={() => onSelect(schedule)}>
                        {/* Task Name as Title */}
                        {schedule.taskName && (
                            <ScheduleTitle>{schedule.taskName}</ScheduleTitle>
                        )}

                        {/* Repeat Settings */}
                        <ScheduleSection>
                            <SectionLabel>{t('pages.schedule.repeatSettings', '重复设置')}</SectionLabel>
                            <Space size={8} wrap>
                                <Tag color="blue">{t(`pages.schedule.repeatTypeMap.${schedule.repeat_type}`, schedule.repeat_type)}</Tag>
                                <Tag color="purple">{schedule.repeat_number} {t(`pages.schedule.repeatUnitMap.${schedule.repeat_unit}`, schedule.repeat_unit)}</Tag>
                                <Tag color="green">{t('pages.schedule.timeOut')}: {schedule.time_out}s</Tag>
                            </Space>
                        </ScheduleSection>

                        {/* Time Range */}
                        <ScheduleSection>
                            <SectionLabel>{t('pages.schedule.timeRange', '时间范围')}</SectionLabel>
                            <TimeRange>
                                <span>{schedule.start_date_time}</span>
                                <span className="separator">~</span>
                                <span>{schedule.end_date_time}</span>
                            </TimeRange>
                        </ScheduleSection>

                        {/* Week Days */}
                        {schedule.week_days && schedule.week_days.length > 0 && (
                            <ScheduleSection>
                                <SectionLabel>{t('pages.schedule.weekDays', '星期')}</SectionLabel>
                                <Space size={6} wrap>
                                    {schedule.week_days.map(day => (
                                        <Tag key={day} color="orange">
                                            {t(`pages.schedule.weekDayNames.${day}`, day)}
                                        </Tag>
                                    ))}
                                </Space>
                            </ScheduleSection>
                        )}

                        {/* Months */}
                        {schedule.months && schedule.months.length > 0 && (
                            <ScheduleSection>
                                <SectionLabel>{t('pages.schedule.months', '月份')}</SectionLabel>
                                <Space size={6} wrap>
                                    {schedule.months.map(m => (
                                        <Tag key={m} color="magenta">
                                            {t(`pages.schedule.monthNames.${m}`, m)}
                                        </Tag>
                                    ))}
                                </Space>
                            </ScheduleSection>
                        )}

                        {/* Custom Fields */}
                        {schedule.custom_fields && Object.keys(schedule.custom_fields).length > 0 && (
                            <ScheduleSection>
                                <SectionLabel>{t('pages.schedule.customFields', '自定义字段')}</SectionLabel>
                                <div style={{ 
                                    padding: '8px 12px', 
                                    background: 'rgba(0, 0, 0, 0.2)', 
                                    borderRadius: '6px',
                                    fontSize: '12px',
                                    fontFamily: 'monospace',
                                    color: 'rgba(255, 255, 255, 0.7)'
                                }}>
                                    {JSON.stringify(schedule.custom_fields, null, 2)}
                                </div>
                            </ScheduleSection>
                        )}
                    </ScheduleItem>
                )}
                />
            </div>
        </div>
    );
};

export default ScheduleList; 