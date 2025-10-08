import React from 'react';
import { Space, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import type { TaskSchedule } from './Schedule.types';
import DetailCard from '../../components/Common/DetailCard';
import styled from '@emotion/styled';

const { Text } = Typography;

const DetailContainer = styled.div`
    width: 100%;
    max-height: 100%;
    overflow-y: auto;
    padding: 24px;
    background: rgba(0, 0, 0, 0.2);
`;

interface ScheduleDetailsProps {
    schedule: TaskSchedule | null;
}

const ScheduleDetails: React.FC<ScheduleDetailsProps> = ({ schedule }) => {
    const { t } = useTranslation();
    if (!schedule) {
        return (
            <DetailContainer>
                <Text type="secondary">{t('pages.schedule.selectSchedule')}</Text>
            </DetailContainer>
        );
    }
    return (
        <DetailContainer>
            <Space direction="vertical" style={{ width: '100%' }} size={24}>
            <DetailCard
                title={t('pages.schedule.scheduleInformation')}
                columns={2}
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
                    columns={2}
                    items={Object.entries(schedule.custom_fields).map(([key, value]) => ({
                        label: key,
                        value: String(value),
                    }))}
                />
            )}
            </Space>
        </DetailContainer>
    );
};

export default ScheduleDetails; 