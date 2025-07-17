import React from 'react';
import { Space, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import type { TaskSchedule } from './Schedule.types';
import DetailCard from '../../components/Common/DetailCard';

const { Text } = Typography;

interface ScheduleDetailsProps {
    schedule: TaskSchedule | null;
}

const ScheduleDetails: React.FC<ScheduleDetailsProps> = ({ schedule }) => {
    const { t } = useTranslation();
    if (!schedule) {
        return <Text type="secondary">{t('pages.schedule.selectSchedule')}</Text>;
    }
    return (
        <Space direction="vertical" style={{ width: '100%', maxHeight: '100%', overflowY: 'auto' }}>
            <DetailCard
                title={t('pages.schedule.scheduleInformation')}
                items={[
                    {
                        label: t('pages.schedule.repeatType'),
                        value: t(`pages.schedule.repeatTypeMap.${schedule.repeat_type}`, schedule.repeat_type),
                    },
                    {
                        label: t('pages.schedule.repeatNumber'),
                        value: schedule.repeat_number,
                    },
                    {
                        label: t('pages.schedule.repeatUnit'),
                        value: t(`pages.schedule.repeatUnitMap.${schedule.repeat_unit}`, schedule.repeat_unit),
                    },
                    {
                        label: t('pages.schedule.timeOut'),
                        value: schedule.time_out,
                    },
                ]}
            />
            <DetailCard
                title={t('pages.schedule.timeAndLocation')}
                items={[
                    {
                        label: t('pages.schedule.startTime'),
                        value: schedule.start_date_time,
                    },
                    {
                        label: t('pages.schedule.endTime'),
                        value: schedule.end_date_time,
                    },
                ]}
            />
            {schedule.week_days && (
                <DetailCard
                    title={t('pages.schedule.weekDays')}
                    items={[
                        {
                            label: t('pages.schedule.weekDays'),
                            value: schedule.week_days.map(day => t(`pages.schedule.weekDayNames.${day}`, day)).join(', '),
                        },
                    ]}
                />
            )}
            {schedule.months && (
                <DetailCard
                    title={t('pages.schedule.months')}
                    items={[
                        {
                            label: t('pages.schedule.months'),
                            value: schedule.months.map(m => t(`pages.schedule.monthNames.${m}`, m)).join(', '),
                        },
                    ]}
                />
            )}
            {schedule.custom_fields && (
                <DetailCard
                    title={t('pages.schedule.customFields')}
                    items={Object.entries(schedule.custom_fields).map(([key, value]) => ({
                        label: key,
                        value: String(value),
                    }))}
                />
            )}
        </Space>
    );
};

export default ScheduleDetails; 