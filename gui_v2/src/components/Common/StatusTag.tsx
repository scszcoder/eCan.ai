import React from 'react';
import { Tag, Tooltip } from 'antd';
import { CheckCircleOutlined, ClockCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';

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

const defaultStatusConfigs: Record<string, StatusConfig> = {
    active: {
        type: 'success',
        icon: <CheckCircleOutlined />,
        text: 'Active',
        color: '#52c41a',
    },
    inactive: {
        type: 'default',
        icon: <CloseCircleOutlined />,
        text: 'Inactive',
        color: '#d9d9d9',
    },
    pending: {
        type: 'processing',
        icon: <ClockCircleOutlined />,
        text: 'Pending',
        color: '#1890ff',
    },
    completed: {
        type: 'success',
        icon: <CheckCircleOutlined />,
        text: 'Completed',
        color: '#52c41a',
    },
    failed: {
        type: 'error',
        icon: <CloseCircleOutlined />,
        text: 'Failed',
        color: '#ff4d4f',
    },
    online: {
        type: 'success',
        icon: <CheckCircleOutlined />,
        text: 'Online',
        color: '#52c41a',
    },
    offline: {
        type: 'default',
        icon: <CloseCircleOutlined />,
        text: 'Offline',
        color: '#d9d9d9',
    },
    busy: {
        type: 'warning',
        icon: <ClockCircleOutlined />,
        text: 'Busy',
        color: '#faad14',
    },
};

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