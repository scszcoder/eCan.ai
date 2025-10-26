/**
 * Execution Status Display Utilities
 * 执行状态显示工具
 */

import React from 'react';
import { Tag, Tooltip } from 'antd';
import {
  PlayCircleOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  CalendarOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

export type ExecutionStatus = 'running' | 'scheduled' | 'completed' | 'pending' | 'error';

/**
 * 执行状态配置
 */
export const EXECUTION_STATUS_CONFIG = {
  running: {
    color: 'success',
    icon: <PlayCircleOutlined />,
  },
  scheduled: {
    color: 'processing',
    icon: <ClockCircleOutlined />,
  },
  completed: {
    color: 'default',
    icon: <CheckCircleOutlined />,
  },
  pending: {
    color: 'warning',
    icon: <ExclamationCircleOutlined />,
  },
  error: {
    color: 'error',
    icon: <ExclamationCircleOutlined />,
  },
};

/**
 * 渲染执行状态标签
 */
export const ExecutionStatusTag: React.FC<{
  status?: ExecutionStatus;
  showIcon?: boolean;
  locale?: 'zh' | 'en'; // 保留参数以兼容，但不再使用
}> = ({ status = 'pending', showIcon = true }) => {
  const { t } = useTranslation();
  const config = EXECUTION_STATUS_CONFIG[status];
  const label = t(`pages.schedule.calendar.executionStatus.${status}`);
  const description = t(`pages.schedule.calendar.executionStatus.${status}Desc`);

  return (
    <Tooltip title={description}>
      <Tag color={config.color} icon={showIcon ? config.icon : undefined}>
        {label}
      </Tag>
    </Tooltip>
  );
};

/**
 * 渲染长周期任务标签
 */
export const LongPeriodTag: React.FC<{
  originalEndTime?: string;
  locale?: 'zh' | 'en'; // 保留参数以兼容，但不再使用
}> = ({ originalEndTime }) => {
  const { t } = useTranslation();
  const label = t('pages.schedule.calendar.executionStatus.longPeriod');
  const description = originalEndTime
    ? t('pages.schedule.calendar.executionStatus.longPeriodOriginal', { time: originalEndTime })
    : t('pages.schedule.calendar.executionStatus.longPeriodDesc');

  return (
    <Tooltip title={description}>
      <Tag color="blue" icon={<CalendarOutlined />}>
        {label}
      </Tag>
    </Tooltip>
  );
};

/**
 * 渲染下次执行标签
 */
export const NextExecutionTag: React.FC<{
  locale?: 'zh' | 'en'; // 保留参数以兼容，但不再使用
}> = () => {
  const { t } = useTranslation();
  const label = t('pages.schedule.calendar.executionStatus.nextExecution');
  const description = t('pages.schedule.calendar.executionStatus.nextExecutionDesc');

  return (
    <Tooltip title={description}>
      <Tag color="cyan" icon={<ClockCircleOutlined />}>
        {label}
      </Tag>
    </Tooltip>
  );
};

/**
 * 获取执行状态的颜色
 */
export function getExecutionStatusColor(status?: ExecutionStatus): string {
  const config = EXECUTION_STATUS_CONFIG[status || 'pending'];
  const colorMap = {
    success: '#52c41a',
    processing: '#1890ff',
    default: '#d9d9d9',
    warning: '#faad14',
    error: '#f5222d',
  };
  return colorMap[config.color as keyof typeof colorMap] || colorMap.default;
}

/**
 * 获取执行状态的背景色
 */
export function getExecutionStatusBgColor(status?: ExecutionStatus): string {
  const config = EXECUTION_STATUS_CONFIG[status || 'pending'];
  const bgColorMap = {
    success: '#f6ffed',
    processing: '#e6f7ff',
    default: '#fafafa',
    warning: '#fffbe6',
    error: '#fff1f0',
  };
  return bgColorMap[config.color as keyof typeof bgColorMap] || bgColorMap.default;
}
