import React from 'react';
import { Tag, Tooltip } from 'antd';
import { CheckCircleOutlined, ClockCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';

const StyledTag = styled(Tag)<{ $color?: string; $textColor?: string }>`
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
    /* Theme token colour; applied as a real colour so it tracks the light theme. */
    color: ${props => props.$textColor || props.$color || 'var(--text-secondary)'};
    background: ${props => props.$textColor
        ? `color-mix(in srgb, ${props.$textColor} 12%, transparent)`
        : 'var(--surface-subtle)'};
    border: 1px solid ${props => props.$textColor
        ? `color-mix(in srgb, ${props.$textColor} 30%, transparent)`
        : 'var(--border-color)'};
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
    /** Optional dedicated text token when the surface tint is too light for `color`. */
    textColor?: string;
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
            color: 'var(--success-text)',
            textColor: 'var(--success-text)',
        },
        inactive: {
            type: 'default',
            icon: <CloseCircleOutlined />,
            text: t('pages.schedule.status.cancelled'),
            color: 'var(--text-tertiary)',
        },
        pending: {
            type: 'processing',
            icon: <ClockCircleOutlined />,
            text: t('pages.schedule.status.inProgress'),
            color: 'var(--primary-text)',
        },
        'in-progress': {
            type: 'processing',
            icon: <ClockCircleOutlined />,
            text: t('pages.schedule.status.inProgress'),
            color: 'var(--primary-text)',
        },
        completed: {
            type: 'success',
            icon: <CheckCircleOutlined />,
            text: t('pages.schedule.status.completed'),
            color: 'var(--success-text)',
            textColor: 'var(--success-text)',
        },
        failed: {
            type: 'error',
            icon: <CloseCircleOutlined />,
            text: t('pages.schedule.status.cancelled'),
            color: 'var(--error-text)',
            textColor: 'var(--error-text)',
        },
        online: {
            type: 'success',
            icon: <CheckCircleOutlined />,
            text: t('pages.chat.online'),
            color: 'var(--success-text)',
            textColor: 'var(--success-text)',
        },
        offline: {
            type: 'default',
            icon: <CloseCircleOutlined />,
            text: t('pages.vehicles.status.offline'),
            color: 'var(--text-tertiary)',
        },
        busy: {
            type: 'warning',
            icon: <ClockCircleOutlined />,
            text: t('pages.chat.busy'),
            color: 'var(--warning-text)',
            textColor: 'var(--warning-text)',
        },
        maintenance: {
            type: 'processing',
            icon: <ClockCircleOutlined />,
            text: t('pages.vehicles.status.maintenance'),
            color: 'var(--primary-text)',
            textColor: 'var(--primary-text)',
        },
        scheduled: {
            type: 'processing',
            icon: <ClockCircleOutlined />,
            text: t('pages.schedule.status.scheduled'),
            color: 'var(--primary-text)',
            textColor: 'var(--primary-text)',
        },
    };

    const config = customConfigs[status] || defaultStatusConfigs[status] || {
        type: 'default',
        icon: null,
        text: status,
        color: 'var(--text-muted)',
    };

    const tag = (
        <StyledTag
            $color={config.color}
            $textColor={config.textColor}
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