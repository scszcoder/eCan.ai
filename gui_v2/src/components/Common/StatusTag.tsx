import React from 'react';
import { Tag, Tooltip } from 'antd';
import { CheckCircleOutlined, ClockCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';

const StyledTag = styled(Tag)`
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
`;

export type StatusType = 
    | 'success' 
    | 'processing' 
    | 'warning' 
    | 'error' 
    | 'default';

export interface StatusConfig {
    type: StatusType;
    icon: React.ReactNode;
    text: string;
    color: string;
}

interface StatusTagProps {
    status: string;
    customConfigs?: Record<string, StatusConfig>;
    tooltip?: string;
}

const StatusTag: React.FC<StatusTagProps> = ({
    status,
    customConfigs = {},
    tooltip,
}) => {
    const { t } = useTranslation();

    const defaultStatusConfigs: Record<string, StatusConfig> = {
        active: {
            type: 'success',
            icon: <CheckCircleOutlined />,
            text: t('pages.vehicles.status.active'),
            color: '#52c41a',
        },
        inactive: {
            type: 'default',
            icon: <CloseCircleOutlined />,
            text: t('pages.schedule.status.cancelled'),
            color: '#d9d9d9',
        },
        pending: {
            type: 'processing',
            icon: <ClockCircleOutlined />,
            text: t('pages.schedule.status.inProgress'),
            color: '#1890ff',
        },
        'in-progress': {
            type: 'processing',
            icon: <ClockCircleOutlined />,
            text: t('pages.schedule.status.inProgress'),
            color: '#1890ff',
        },
        completed: {
            type: 'success',
            icon: <CheckCircleOutlined />,
            text: t('pages.schedule.status.completed'),
            color: '#52c41a',
        },
        failed: {
            type: 'error',
            icon: <CloseCircleOutlined />,
            text: t('pages.schedule.status.cancelled'),
            color: '#ff4d4f',
        },
        online: {
            type: 'success',
            icon: <CheckCircleOutlined />,
            text: t('pages.chat.online'),
            color: '#52c41a',
        },
        offline: {
            type: 'default',
            icon: <CloseCircleOutlined />,
            text: t('pages.vehicles.status.offline'),
            color: '#d9d9d9',
        },
        busy: {
            type: 'warning',
            icon: <ClockCircleOutlined />,
            text: t('pages.chat.busy'),
            color: '#faad14',
        },
        maintenance: {
            type: 'processing',
            icon: <ClockCircleOutlined />,
            text: t('pages.vehicles.status.maintenance'),
            color: '#1890ff',
        },
        scheduled: {
            type: 'processing',
            icon: <ClockCircleOutlined />,
            text: t('pages.schedule.status.scheduled'),
            color: '#1890ff',
        },
    };

    const config = customConfigs[status] || defaultStatusConfigs[status] || {
        type: 'default',
        icon: null,
        text: status,
        color: '#d9d9d9',
    };

    const tag = (
        <StyledTag
            color={config.color}
            icon={config.icon}
        >
            {config.text}
        </StyledTag>
    );

    if (tooltip) {
        return (
            <Tooltip title={tooltip}>
                {tag}
            </Tooltip>
        );
    }

    return tag;
};

export default StatusTag; 