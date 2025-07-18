import React from 'react';
import { List, Typography, Space, Tag } from 'antd';
import { useTranslation } from 'react-i18next';
import SearchFilter from '../../components/Common/SearchFilter';
import ActionButtons from '../../components/Common/ActionButtons';
import type { TaskSchedule } from './Schedule.types';
import styled from '@emotion/styled';

const { Text } = Typography;

const ScheduleItem = styled.div`
    padding: 12px;
    border-bottom: 1px solid var(--border-color);
    &:last-child {
        border-bottom: none;
    }
    cursor: pointer;
    transition: all 0.3s ease;
    background-color: var(--bg-secondary);
    border-radius: 8px;
    margin: 4px 0;
    &:hover {
        background-color: var(--bg-tertiary);
        transform: translateX(4px);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    }
    .ant-typography {
        color: var(--text-primary);
    }
    .ant-tag {
        background-color: var(--bg-primary);
        border-color: var(--border-color);
    }
    .ant-progress-text {
        color: var(--text-primary);
    }
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
        <>
            <SearchFilter
                onSearch={onSearch}
                onFilter={onFilter}
                onFilterReset={onFilterReset}
                filterOptions={[]}
                placeholder={t('pages.schedule.searchPlaceholder')}
            />
            <ActionButtons
                onAdd={() => {}}
                onEdit={() => {}}
                onDelete={() => {}}
                onRefresh={() => {}}
                onExport={() => {}}
                onImport={() => {}}
                onSettings={() => {}}
                addText={t('pages.schedule.addSchedule')}
                editText={t('pages.schedule.editSchedule')}
                deleteText={t('pages.schedule.deleteSchedule')}
                refreshText={t('pages.schedule.refreshSchedule')}
                exportText={t('pages.schedule.exportSchedule')}
                importText={t('pages.schedule.importSchedule')}
                settingsText={t('pages.schedule.scheduleSettings')}
            />
            <List
                dataSource={schedules}
                renderItem={(schedule, idx) => (
                    <ScheduleItem onClick={() => onSelect(schedule)}>
                        <Space direction="vertical" style={{ width: '100%' }}>
                            <Space>
                                <Tag color="blue">{t(`pages.schedule.repeatTypeMap.${schedule.repeat_type}`, schedule.repeat_type)}</Tag>
                                <Tag color="purple">{schedule.repeat_number} {t(`pages.schedule.repeatUnitMap.${schedule.repeat_unit}`, schedule.repeat_unit)}</Tag>
                                <Tag color="green">{t('pages.schedule.timeOut')}: {schedule.time_out}s</Tag>
                            </Space>
                            <Space>
                                <Text type="secondary">
                                    {schedule.start_date_time} ~ {schedule.end_date_time}
                                </Text>
                            </Space>
                            {schedule.week_days && (
                                <Space>
                                    <Tag color="orange">{t('pages.schedule.weekDays')}: {schedule.week_days.map(day => t(`pages.schedule.weekDayNames.${day}`, day)).join(', ')}</Tag>
                                </Space>
                            )}
                            {schedule.months && (
                                <Space>
                                    <Tag color="magenta">{t('pages.schedule.months')}: {schedule.months.map(m => t(`pages.schedule.monthNames.${m}`, m)).join(', ')}</Tag>
                                </Space>
                            )}
                            {schedule.custom_fields && (
                                <Space>
                                    <Tag color="gold">{t('pages.schedule.customFields')}: {JSON.stringify(schedule.custom_fields)}</Tag>
                                </Space>
                            )}
                        </Space>
                    </ScheduleItem>
                )}
            />
        </>
    );
};

export default ScheduleList; 