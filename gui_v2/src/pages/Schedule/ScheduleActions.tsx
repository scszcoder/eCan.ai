import React from 'react';
import { Button, Space } from 'antd';
import { PlusOutlined, ClockCircleOutlined, CheckCircleOutlined, DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

const ScheduleActions: React.FC<{
    schedule: {
        id: number;
        status: 'scheduled' | 'in-progress' | 'completed';
    };
    onStatusChange: (id: number, status: 'scheduled' | 'in-progress' | 'completed') => void;
    onDelete: (id: number) => void;
}> = ({ schedule, onStatusChange, onDelete }) => {
    const { t } = useTranslation();
    return (
        <Space>
            <Button 
                type="primary" 
                icon={<PlusOutlined />}
                onClick={() => onStatusChange(schedule.id, 'scheduled')}
                disabled={schedule.status === 'scheduled'}
            >
                {t('pages.schedule.schedule')}
            </Button>
            <Button 
                icon={<ClockCircleOutlined />}
                onClick={() => onStatusChange(schedule.id, 'in-progress')}
                disabled={schedule.status === 'in-progress'}
            >
                {t('pages.schedule.start')}
            </Button>
            <Button 
                icon={<CheckCircleOutlined />}
                onClick={() => onStatusChange(schedule.id, 'completed')}
                disabled={schedule.status === 'completed'}
            >
                {t('pages.schedule.complete')}
            </Button>
            <Button 
                danger
                icon={<DeleteOutlined />}
                onClick={() => onDelete(schedule.id)}
            >
                {t('common.delete')}
            </Button>
        </Space>
    );
};

export default ScheduleActions; 