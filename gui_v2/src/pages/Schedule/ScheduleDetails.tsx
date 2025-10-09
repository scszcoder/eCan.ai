import React from 'react';
import { Space, Typography, Button, Row, Col } from 'antd';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { ArrowRightOutlined, ClockCircleOutlined, CalendarOutlined, ThunderboltOutlined } from '@ant-design/icons';
import type { TaskSchedule } from './Schedule.types';
import styled from '@emotion/styled';

const { Text } = Typography;

const DetailContainer = styled.div`
    width: 100%;
    max-height: 100%;
    overflow-y: auto;
    padding: 24px;
    background: rgba(0, 0, 0, 0.2);
`;

const TaskInfoCard = styled.div`
    padding: 20px;
    background: linear-gradient(135deg, rgba(64, 169, 255, 0.15) 0%, rgba(102, 126, 234, 0.15) 100%);
    border: 1px solid rgba(64, 169, 255, 0.3);
    border-radius: 12px;
    margin-bottom: 24px;
    position: relative;
    overflow: hidden;
    
    &::before {
        content: '';
        position: absolute;
        left: 0;
        top: 0;
        height: 100%;
        width: 4px;
        background: linear-gradient(180deg, #1890ff 0%, #667eea 100%);
    }
    
    .task-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 16px;
    }
    
    .task-info {
        flex: 1;
    }
    
    .task-label {
        font-size: 11px;
        font-weight: 600;
        color: rgba(255, 255, 255, 0.5);
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 8px;
    }
    
    .task-name {
        font-size: 20px;
        font-weight: 700;
        color: rgba(255, 255, 255, 0.95);
        margin-bottom: 8px;
        line-height: 1.3;
    }
    
    .task-id {
        font-size: 12px;
        font-family: 'Consolas', 'Monaco', monospace;
        color: rgba(255, 255, 255, 0.6);
        background: rgba(0, 0, 0, 0.2);
        padding: 4px 8px;
        border-radius: 4px;
        display: inline-block;
    }
`;

const InfoSection = styled.div`
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 16px;
    
    .section-title {
        font-size: 14px;
        font-weight: 600;
        color: rgba(255, 255, 255, 0.85);
        margin-bottom: 16px;
        display: flex;
        align-items: center;
        gap: 8px;
        
        .anticon {
            font-size: 16px;
            color: rgba(64, 169, 255, 0.8);
        }
    }
`;

const InfoItem = styled.div`
    margin-bottom: 12px;
    
    &:last-child {
        margin-bottom: 0;
    }
    
    .label {
        font-size: 12px;
        color: rgba(255, 255, 255, 0.5);
        margin-bottom: 4px;
    }
    
    .value {
        font-size: 14px;
        font-weight: 500;
        color: rgba(255, 255, 255, 0.9);
    }
    
    .value-mono {
        font-family: 'Consolas', 'Monaco', monospace;
        background: rgba(0, 0, 0, 0.2);
        padding: 6px 10px;
        border-radius: 6px;
        display: inline-block;
    }
`;

interface ScheduleDetailsProps {
    schedule: TaskSchedule | null;
}

const ScheduleDetails: React.FC<ScheduleDetailsProps> = ({ schedule }) => {
    const { t } = useTranslation();
    const navigate = useNavigate();

    const handleNavigateToTask = () => {
        if (schedule?.taskId) {
            navigate(`/tasks?taskId=${schedule.taskId}`);
        }
    };

    if (!schedule) {
        return (
            <DetailContainer>
                <Text type="secondary">{t('pages.schedule.selectSchedule')}</Text>
            </DetailContainer>
        );
    }
    return (
        <DetailContainer>
            <Space direction="vertical" style={{ width: '100%' }} size={16}>
                {/* Task Information Card */}
                {schedule.taskId && (
                    <TaskInfoCard>
                        <div className="task-header">
                            <div className="task-info">
                                <div className="task-label">{t('pages.schedule.belongsToTask', '所属任务')}</div>
                                <div className="task-name">{schedule.taskName || t('pages.schedule.unknownTask', '未知任务')}</div>
                                <div className="task-id">{schedule.taskId}</div>
                            </div>
                        </div>
                        <Button
                            type="primary"
                            icon={<ArrowRightOutlined />}
                            onClick={handleNavigateToTask}
                            block
                            size="large"
                        >
                            {t('pages.schedule.viewTaskDetail', '查看任务详情')}
                        </Button>
                    </TaskInfoCard>
                )}

                {/* Repeat Settings Section */}
                <InfoSection>
                    <div className="section-title">
                        <ThunderboltOutlined />
                        {t('pages.schedule.repeatSettings', '重复设置')}
                    </div>
                    <Row gutter={[16, 16]}>
                        <Col span={12}>
                            <InfoItem>
                                <div className="label">{t('pages.schedule.repeatType', '重复类型')}</div>
                                <div className="value">{t(`pages.schedule.repeatTypeMap.${schedule.repeat_type}`, schedule.repeat_type)}</div>
                            </InfoItem>
                        </Col>
                        <Col span={12}>
                            <InfoItem>
                                <div className="label">{t('pages.schedule.repeatFrequency', '重复频率')}</div>
                                <div className="value">{schedule.repeat_number} {t(`pages.schedule.repeatUnitMap.${schedule.repeat_unit}`, schedule.repeat_unit)}</div>
                            </InfoItem>
                        </Col>
                        <Col span={12}>
                            <InfoItem>
                                <div className="label">{t('pages.schedule.timeOut', '超时时间')}</div>
                                <div className="value">{schedule.time_out}s</div>
                            </InfoItem>
                        </Col>
                    </Row>
                </InfoSection>

                {/* Time Range Section */}
                <InfoSection>
                    <div className="section-title">
                        <CalendarOutlined />
                        {t('pages.schedule.timeRange', '时间范围')}
                    </div>
                    <Row gutter={[16, 16]}>
                        <Col span={24}>
                            <InfoItem>
                                <div className="label">{t('pages.schedule.startTime', '开始时间')}</div>
                                <div className="value value-mono">{schedule.start_date_time}</div>
                            </InfoItem>
                        </Col>
                        <Col span={24}>
                            <InfoItem>
                                <div className="label">{t('pages.schedule.endTime', '结束时间')}</div>
                                <div className="value value-mono">{schedule.end_date_time}</div>
                            </InfoItem>
                        </Col>
                    </Row>
                </InfoSection>

                {/* Week Days Section */}
                {schedule.week_days && schedule.week_days.length > 0 && (
                    <InfoSection>
                        <div className="section-title">
                            <ClockCircleOutlined />
                            {t('pages.schedule.weekDays', '星期')}
                        </div>
                        <InfoItem>
                            <div className="value">
                                {schedule.week_days.map(day => t(`pages.schedule.weekDayNames.${day}`, day)).join(', ')}
                            </div>
                        </InfoItem>
                    </InfoSection>
                )}

                {/* Months Section */}
                {schedule.months && schedule.months.length > 0 && (
                    <InfoSection>
                        <div className="section-title">
                            <CalendarOutlined />
                            {t('pages.schedule.months', '月份')}
                        </div>
                        <InfoItem>
                            <div className="value">
                                {schedule.months.map(m => t(`pages.schedule.monthNames.${m}`, m)).join(', ')}
                            </div>
                        </InfoItem>
                    </InfoSection>
                )}

                {/* Custom Fields Section */}
                {schedule.custom_fields && Object.keys(schedule.custom_fields).length > 0 && (
                    <InfoSection>
                        <div className="section-title">
                            {t('pages.schedule.customFields', '自定义字段')}
                        </div>
                        <Row gutter={[16, 16]}>
                            {Object.entries(schedule.custom_fields).map(([key, value]) => (
                                <Col span={12} key={key}>
                                    <InfoItem>
                                        <div className="label">{key}</div>
                                        <div className="value">{String(value)}</div>
                                    </InfoItem>
                                </Col>
                            ))}
                        </Row>
                    </InfoSection>
                )}
            </Space>
        </DetailContainer>
    );
};

export default ScheduleDetails; 