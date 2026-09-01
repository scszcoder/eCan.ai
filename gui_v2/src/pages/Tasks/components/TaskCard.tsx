import React from 'react';
import { Tag, Progress, Space, Dropdown, Tooltip, Button, Badge } from 'antd';
import type { MenuProps } from 'antd';
import {
  ClockCircleOutlined,
  ThunderboltOutlined,
  CalendarOutlined,
  MessageOutlined,
  RobotOutlined,
  CheckCircleOutlined,
  SyncOutlined,
  ExclamationCircleOutlined,
  StopOutlined,
  MoreOutlined,
  PlayCircleOutlined,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  RightOutlined,
  TeamOutlined,
  CloudOutlined,
  DesktopOutlined,
  DragOutlined,
} from '@ant-design/icons';
import styled from '@emotion/styled';
import { keyframes, css } from '@emotion/react';
import { useTranslation } from 'react-i18next';
import { Task } from '../types';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import 'dayjs/locale/zh-cn';

dayjs.extend(relativeTime);
dayjs.locale('zh-cn');

// Animations
const pulseAnimation = keyframes`
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
`;

const scaleInAnimation = keyframes`
  from {
    opacity: 0;
    transform: scale(0.9);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
`;

// Status Configuration
const STATUS_BASE_CONFIG = {
  SUBMITTED: {
    gradient: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: '#667eea',
    bgColor: 'rgba(102, 126, 234, 0.1)',
    icon: <ClockCircleOutlined />,
    key: 'SUBMITTED',
    defaultText: '已提交',
    pulse: true,
  },
  WORKING: {
    gradient: 'linear-gradient(135deg, #1890FF 0%, #096dd9 100%)',
    color: '#1890FF',
    bgColor: 'rgba(24, 144, 255, 0.1)',
    icon: <SyncOutlined />,
    key: 'WORKING',
    defaultText: '运行中',
    pulse: true,
  },
  INPUT_REQUIRED: {
    gradient: 'linear-gradient(135deg, #FA8C16 0%, #d46b08 100%)',
    color: '#FA8C16',
    bgColor: 'rgba(250, 140, 22, 0.1)',
    icon: <ExclamationCircleOutlined />,
    key: 'INPUT_REQUIRED',
    defaultText: '等待输入',
    pulse: true,
  },
  COMPLETED: {
    gradient: 'linear-gradient(135deg, #52C41A 0%, #389e0d 100%)',
    color: '#52C41A',
    bgColor: 'rgba(82, 196, 26, 0.1)',
    icon: <CheckCircleOutlined />,
    key: 'COMPLETED',
    defaultText: '已完成',
    pulse: false,
  },
  CANCELED: {
    gradient: 'linear-gradient(135deg, #FF4D4F 0%, #cf1322 100%)',
    color: '#FF4D4F',
    bgColor: 'rgba(255, 77, 79, 0.1)',
    icon: <StopOutlined />,
    key: 'CANCELED',
    defaultText: '已取消',
    pulse: false,
  },
  FAILED: {
    gradient: 'linear-gradient(135deg, #FF4D4F 0%, #a8071a 100%)',
    color: '#FF4D4F',
    bgColor: 'rgba(255, 77, 79, 0.1)',
    icon: <ExclamationCircleOutlined />,
    key: 'FAILED',
    defaultText: '失败',
    pulse: false,
  },
  ready: {
    gradient: 'linear-gradient(135deg, #52C41A 0%, #389e0d 100%)',
    color: '#52C41A',
    bgColor: 'rgba(82, 196, 26, 0.1)',
    icon: <CheckCircleOutlined />,
    key: 'ready',
    defaultText: '就绪',
    pulse: false,
  },
  running: {
    gradient: 'linear-gradient(135deg, #1890FF 0%, #096dd9 100%)',
    color: '#1890FF',
    bgColor: 'rgba(24, 144, 255, 0.1)',
    icon: <SyncOutlined />,
    key: 'running',
    defaultText: '运行中',
    pulse: true,
  },
  pending: {
    gradient: 'linear-gradient(135deg, #722ed1 0%, #531d93 100%)',
    color: '#722ed1',
    bgColor: 'rgba(114, 46, 209, 0.1)',
    icon: <ClockCircleOutlined />,
    key: 'pending',
    defaultText: '待处理',
    pulse: true,
  },
  timeout: {
    gradient: 'linear-gradient(135deg, #fa8c16 0%, #d46b08 100%)',
    color: '#FA8C16',
    bgColor: 'rgba(250, 140, 22, 0.1)',
    icon: <ClockCircleOutlined />,
    key: 'timeout',
    defaultText: '超时',
    pulse: false,
  },
  unknown: {
    gradient: 'linear-gradient(135deg, #8C8C8C 0%, #595959 100%)',
    color: '#8C8C8C',
    bgColor: 'rgba(140, 140, 140, 0.1)',
    icon: <ClockCircleOutlined />,
    key: 'unknown',
    defaultText: '未知',
    pulse: false,
  },
};

// Priority Configuration
const PRIORITY_CONFIG = {
  ASAP: {
    color: '#cf1322',
    bgColor: '#fff1f0',
    borderColor: '#ffa39e',
    emoji: '🔴',
    defaultText: '立即',
    level: 5,
  },
  URGENT: {
    color: '#d46b08',
    bgColor: '#fff7e6',
    borderColor: '#ffd591',
    emoji: '🟠',
    defaultText: '紧急',
    level: 4,
  },
  HIGH: {
    color: '#d48806',
    bgColor: '#fffbe6',
    borderColor: '#ffe58f',
    emoji: '🟡',
    defaultText: '高',
    level: 3,
  },
  MID: {
    color: '#096dd9',
    bgColor: '#e6f7ff',
    borderColor: '#91d5ff',
    emoji: '🔵',
    defaultText: '中',
    level: 2,
  },
  LOW: {
    color: '#595959',
    bgColor: '#fafafa',
    borderColor: '#d9d9d9',
    emoji: '⚪',
    defaultText: '低',
    level: 1,
  },
  none: {
    color: '#8c8c8c',
    bgColor: '#fafafa',
    borderColor: '#d9d9d9',
    emoji: '',
    defaultText: '无',
    level: 0,
  },
};

// Trigger Configuration
const TRIGGER_CONFIG: Record<string, {
  icon: React.ReactNode;
  i18nKey: string;
  defaultText: string;
  color: string;
  bgColor: string;
}> = {
  schedule: {
    icon: <CalendarOutlined />,
    i18nKey: 'pages.tasks.trigger.schedule',
    defaultText: '定时',
    color: '#722ed1',
    bgColor: '#f9f0ff',
  },
  message: {
    icon: <MessageOutlined />,
    i18nKey: 'pages.tasks.trigger.message',
    defaultText: '消息',
    color: '#1890ff',
    bgColor: '#e6f7ff',
  },
  auto: {
    icon: <ThunderboltOutlined />,
    i18nKey: 'pages.tasks.trigger.auto',
    defaultText: '自动',
    color: '#52c41a',
    bgColor: '#f6ffed',
  },
  'human chat': {
    icon: <MessageOutlined />,
    i18nKey: 'pages.tasks.trigger.human chat',
    defaultText: '聊天',
    color: '#1890ff',
    bgColor: '#e6f7ff',
  },
  'agent message': {
    icon: <RobotOutlined />,
    i18nKey: 'pages.tasks.trigger.agent message',
    defaultText: '智能体消息',
    color: '#722ed1',
    bgColor: '#f9f0ff',
  },
  interaction: {
    icon: <MessageOutlined />,
    i18nKey: 'pages.tasks.trigger.interaction',
    defaultText: '交互',
    color: '#1890ff',
    bgColor: '#e6f7ff',
  },
  chat_queue: {
    icon: <MessageOutlined />,
    i18nKey: 'pages.tasks.trigger.chat_queue',
    defaultText: '聊天队列',
    color: '#1890ff',
    bgColor: '#e6f7ff',
  },
  a2a_queue: {
    icon: <TeamOutlined />,
    i18nKey: 'pages.tasks.trigger.a2a_queue',
    defaultText: '消息队列',
    color: '#1890ff',
    bgColor: '#e6f7ff',
  },
  manual: {
    icon: <EditOutlined />,
    i18nKey: 'pages.tasks.trigger.manual',
    defaultText: '手动',
    color: '#8c8c8c',
    bgColor: '#fafafa',
  },
};

// Task Type Configuration
const TASK_TYPE_CONFIG = {
  local: {
    icon: <DesktopOutlined />,
    i18nKey: 'pages.tasks.taskType.local',
    defaultText: '本地',
    color: '#52c41a',
  },
  cloud: {
    icon: <CloudOutlined />,
    i18nKey: 'pages.tasks.taskType.cloud',
    defaultText: '云端',
    color: '#1890ff',
  },
  hybrid_cloud: {
    icon: <CloudOutlined />,
    i18nKey: 'pages.tasks.taskType.hybrid_cloud',
    defaultText: '混合云',
    color: '#722ed1',
  },
};

const TaskItem = styled.div<{ isSelected?: boolean; isRunning?: boolean }>`
  padding: 12px;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease;
  background: var(--bg-secondary);
  border-radius: 12px;
  margin: 4px 0;
  border: 1px solid ${props => props.isSelected ? 'rgba(59, 130, 246, 0.4)' : 'rgba(255, 255, 255, 0.06)'};
  position: relative;
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    height: 100%;
    width: 3px;
    background: ${props => props.isRunning ? '#1890FF' : 'transparent'};
  }

  &:hover {
    background: var(--bg-tertiary);
    border-color: ${props => props.isSelected ? 'rgba(59, 130, 246, 0.5)' : 'rgba(255, 255, 255, 0.1)'};

    .task-actions {
      opacity: 1;
    }
  }

  &.selected {
    background: linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(51, 65, 85, 0.5) 100%);
    border: 1px solid rgba(59, 130, 246, 0.4);
    box-shadow: 0 2px 10px rgba(59, 130, 246, 0.1);

    &::before {
      width: 3px;
      background: linear-gradient(180deg, rgba(59, 130, 246, 0.85) 0%, rgba(96, 165, 250, 0.6) 100%);
    }
  }
`;

const TaskHeader = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 10px;
`;

const TaskIconWrapper = styled.div<{ gradient?: string; status?: string; isRunning?: boolean }>`
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
  position: relative;
  background: ${props => {
    if (props.gradient) return props.gradient;
    switch (props.status) {
      case 'WORKING':
      case 'running':
        return 'linear-gradient(135deg, #1890FF 0%, #40a9ff 100%)';
      case 'COMPLETED':
      case 'ready':
        return 'linear-gradient(135deg, #52C41A 0%, #73d13d 100%)';
      case 'CANCELED':
      case 'FAILED':
        return 'linear-gradient(135deg, #FF4D4F 0%, #ff7875 100%)';
      case 'INPUT_REQUIRED':
        return 'linear-gradient(135deg, #FA8C16 0%, #ffa940 100%)';
      case 'SUBMITTED':
      case 'pending':
        return 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
      default:
        return 'linear-gradient(135deg, #722ed1 0%, #9254de 100%)';
    }
  }};
  color: white;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  ${props => props.isRunning && css`
    animation: ${pulseAnimation} 2s ease-in-out infinite;
  `}

  &::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: 12px;
    padding: 1px;
    background: linear-gradient(135deg, rgba(255, 255, 255, 0.4), rgba(255, 255, 255, 0.1));
    -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
    -webkit-mask-composite: xor;
    mask-composite: exclude;
  }
  
  &:hover {
    transform: scale(1.08);
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);
  }
`;

const TaskMeta = styled.div`
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
  margin-left: 12px;
  min-width: 0;
`;

const TaskTitleRow = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
`;

const TaskTitle = styled.span`
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
`;

const TaskTags = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
`;

const StyledTag = styled(Tag, {
  shouldForwardProp: (prop) => !['$bgColor', '$borderColor', '$color'].includes(prop as string)
})<{ $bgColor?: string; $borderColor?: string; $color?: string }>`
  border-radius: 6px;
  font-size: 12px;
  padding: 2px 8px;
  margin: 0;
  border: 1px solid ${props => props.$borderColor || 'transparent'};
  background: ${props => props.$bgColor || 'transparent'};
  color: ${props => props.$color || 'inherit'};
  transition: all 0.2s ease;
  
  &:hover {
    transform: scale(1.02);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  }
`;

const TaskStats = styled.div`
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  flex-wrap: wrap;
`;

const StatItem = styled('div', {
  shouldForwardProp: (prop) => prop !== '$highlight'
})<{ $highlight?: boolean }>`
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: ${props => props.$highlight ? 'var(--primary-color)' : 'var(--text-secondary)'};
  transition: all 0.2s ease;

  .anticon {
    font-size: 14px;
  }

  &:hover {
    color: var(--text-primary);
  }
`;

const ProgressWrapper = styled.div`
  margin: 8px 0;
  animation: ${scaleInAnimation} 0.3s ease-out;
`;

const ActionMenuWrapper = styled.div`
  opacity: 0;
  transition: opacity 0.2s ease;
`;

const TaskTypeBadge = styled('div', {
  shouldForwardProp: (prop) => prop !== '$color'
})<{ $color?: string }>`
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: ${props => props.$color || 'var(--text-secondary)'};
  background: ${props => props.$color ? props.$color + '15' : 'transparent'};
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
`;

const PriorityIndicator = styled('div', {
  shouldForwardProp: (prop) => prop !== '$level'
})<{ $level: number }>`
  width: 4px;
  height: 16px;
  border-radius: 2px;
  background: ${props => {
    switch (props.$level) {
      case 5: return '#cf1322';
      case 4: return '#d46b08';
      case 3: return '#d48806';
      case 2: return '#096dd9';
      case 1: return '#8c8c8c';
      default: return 'transparent';
    }
  }};
`;

interface TaskCardProps {
  task: Task;
  isSelected: boolean;
  onSelect: (task: Task) => void;
  onAction?: (action: string, task: Task) => void;
  viewMode?: 'list' | 'grid';
  searchHighlight?: string;
}

// Helper function to highlight search text
const highlightSearchText = (text: string, highlight: string): React.ReactNode => {
  if (!highlight || !text) return text;
  
  const regex = new RegExp(`(${highlight.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
  const parts = text.split(regex);
  
  return parts.map((part, index) =>
    regex.test(part) ? <mark key={index} className="highlight">{part}</mark> : part
  );
};

// Grid View specific styled components
const GridCardWrapper = styled.div<{ $isSelected?: boolean; $isRunning?: boolean }>`
  background: ${props => props.$isSelected
    ? 'linear-gradient(135deg, rgba(24, 144, 255, 0.10) 0%, rgba(51, 65, 85, 0.5) 100%)'
    : 'rgba(255, 255, 255, 0.025)'};
  border: 1px solid ${props => props.$isSelected
    ? 'rgba(24, 144, 255, 0.4)'
    : props.$isRunning
      ? 'rgba(24, 144, 255, 0.4)'
      : 'rgba(255, 255, 255, 0.08)'};
  border-radius: 14px;
  padding: 0;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease;
  position: relative;
  overflow: visible;

  &:hover {
    background: ${props => props.$isSelected
      ? 'linear-gradient(135deg, rgba(24, 144, 255, 0.14) 0%, rgba(51, 65, 85, 0.55) 100%)'
      : 'rgba(255, 255, 255, 0.045)'};
    border-color: ${props => props.$isSelected || props.$isRunning
      ? 'rgba(24, 144, 255, 0.55)'
      : 'rgba(255, 255, 255, 0.14)'};
  }
`;

// Grid card header bar
const GridCardHeaderBar = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 14px 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
`;

const GridHeaderLeft = styled.div`
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
`;

const GridStatusIcon = styled.div<{ $color: string }>`
  width: 34px;
  height: 34px;
  border-radius: 9px;
  background: ${props => props.$color};
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: 0 2px 8px ${props => props.$color}35;

  .anticon {
    font-size: 16px;
    color: white;
  }
`;

const GridHeaderInfo = styled.div`
  min-width: 0;
  flex: 1;
  max-width: calc(100% - 44px);
`;

const GridTaskTitle = styled.div`
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.35;
`;

// Grid card body
const GridCardBody = styled.div`
  padding: 10px 14px 8px;
`;

const GridMetaRow = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 8px;
`;

const GridStatusBadge = styled.div<{ $color: string; $bgColor: string }>`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 500;
  background: ${props => props.$bgColor};
  color: ${props => props.$color};
  border: 1px solid ${props => props.$color}30;

  .anticon {
    font-size: 11px;
  }
`;

const GridPriorityBadge = styled.div<{ $color: string; $bgColor: string; $borderColor: string }>`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 500;
  background: ${props => props.$bgColor};
  color: ${props => props.$color};
  border: 1px solid ${props => props.$borderColor};
`;

const GridTypeBadge = styled.div<{ $color: string }>`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 500;
  background: ${props => props.$color}15;
  color: ${props => props.$color};
  border: 1px solid ${props => props.$color}30;
`;

const GridTriggerBadges = styled.div`
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
`;

const GridTriggerBadge = styled.div<{ $color: string; $bgColor: string }>`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 7px;
  border-radius: 4px;
  font-size: 11px;
  background: ${props => props.$bgColor};
  color: ${props => props.$color};

  .anticon {
    font-size: 10px;
  }
`;

// Grid card footer
const GridCardFooter = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.04);
`;

const GridFooterMeta = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
`;

const GridFooterMetaItem = styled.div`
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-muted);

  .anticon {
    font-size: 11px;
    color: var(--text-muted);
  }
`;

const GridActionButtons = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
`;

const GridActionBtn = styled(Button, {
  shouldForwardProp: (prop) => !['$variant'].includes(prop as string)
})<{ $variant?: 'primary' | 'secondary' | 'ghost' }>`
  height: 28px !important;
  padding: 0 10px !important;
  border-radius: 6px !important;
  font-size: 12px !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 4px !important;
  transition: all 0.2s ease !important;

  ${props => props.$variant === 'primary' && css`
    background: linear-gradient(135deg, #1890FF 0%, #096dd9 100%) !important;
    border: none !important;
    color: white !important;
    box-shadow: 0 2px 8px rgba(24, 144, 255, 0.3) !important;

    &:hover {
      background: linear-gradient(135deg, #40a9ff 0%, #1890FF 100%) !important;
      box-shadow: 0 4px 12px rgba(24, 144, 255, 0.4) !important;
      transform: translateY(-1px);
    }

    &:disabled {
      background: rgba(255, 255, 255, 0.1) !important;
      color: rgba(255, 255, 255, 0.4) !important;
      box-shadow: none !important;
    }
  `}

  ${props => (props.$variant === 'secondary' || !props.$variant) && css`
    background: rgba(255, 255, 255, 0.06) !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    color: var(--text-secondary) !important;

    &:hover {
      background: rgba(255, 255, 255, 0.1) !important;
      border-color: rgba(255, 255, 255, 0.2) !important;
      color: var(--text-primary) !important;
    }
  `}

  ${props => props.$variant === 'ghost' && css`
    background: transparent !important;
    border: none !important;
    color: var(--text-muted) !important;
    padding: 0 6px !important;

    &:hover {
      color: var(--text-primary) !important;
      background: rgba(255, 255, 255, 0.05) !important;
    }
  `}

  .anticon {
    font-size: 12px;
  }
`;

// Drag handle for list items
const DragHandle = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  margin-right: 8px;
  color: var(--text-muted);
  cursor: grab;
  opacity: 0.4;
  transition: opacity 0.2s ease;
  flex-shrink: 0;

  &:hover {
    opacity: 1;
    color: var(--text-secondary);
  }

  &:active {
    cursor: grabbing;
  }
`;

export const TaskCard: React.FC<TaskCardProps> = ({
  task,
  isSelected,
  onSelect,
  onAction,
  viewMode = 'list',
  searchHighlight,
}) => {
  const { t } = useTranslation();

  // Get status
  const status = task.state?.top || task.status || 'unknown';
  const statusKey = status.toLowerCase();
  const baseStatusConfig = STATUS_BASE_CONFIG[statusKey as keyof typeof STATUS_BASE_CONFIG] || STATUS_BASE_CONFIG.unknown;
  const statusConfig = {
    ...baseStatusConfig,
    text: t(`pages.tasks.status.${baseStatusConfig.key}`, baseStatusConfig.defaultText),
  };
  const isRunning = statusConfig.pulse;

  // Get priority
  const priority = (task.priority || 'none').toUpperCase();
  const basePriorityConfig = PRIORITY_CONFIG[priority as keyof typeof PRIORITY_CONFIG] || PRIORITY_CONFIG.none;
  const priorityText = t(`pages.tasks.priority.${priority}`, basePriorityConfig.defaultText);

  // Get trigger types
  const rawTrigger = task.trigger;
  const triggerList: string[] = Array.isArray(rawTrigger)
    ? rawTrigger
    : (typeof rawTrigger === 'string' && rawTrigger
        ? rawTrigger.split(',').map(s => s.trim()).filter(Boolean)
        : ['auto']);

  const triggerConfigs = triggerList.map((trig) => {
    const finalConfig = TRIGGER_CONFIG[trig] || {
      icon: <ThunderboltOutlined />,
      i18nKey: `pages.tasks.trigger.${trig}`,
      defaultText: trig,
      color: '#8c8c8c',
      bgColor: '#fafafa',
    };
    return {
      ...finalConfig,
      key: trig,
      text: t(finalConfig.i18nKey, finalConfig.defaultText),
    };
  });

  // Get task type
  const taskType = task.task_type || task.metadata?.task_type || 'local';
  const taskTypeConfig = TASK_TYPE_CONFIG[taskType as keyof typeof TASK_TYPE_CONFIG] || TASK_TYPE_CONFIG.local;

  // Format last run time
  const lastRunTime = task.last_run_datetime
    ? dayjs(task.last_run_datetime).fromNow()
    : t('pages.tasks.notRun', '未运行');

  // Calculate progress
  const rawProgress = (task as any).progress ?? task.metadata?.progress ?? task.state?.progress ?? task.metadata?.progress_percent;
  const normalizedProgress = typeof rawProgress === 'number'
    ? rawProgress
    : typeof rawProgress === 'string'
      ? Number(rawProgress)
      : NaN;
  const hasRealProgress = Number.isFinite(normalizedProgress) && normalizedProgress >= 0;
  const progress = hasRealProgress
    ? Math.max(0, Math.min(100, normalizedProgress))
    : (status === 'COMPLETED' || status === 'ready' ? 100 : 0);
  const shouldShowProgress = isRunning && hasRealProgress;

  // Get run count
  const runCount = task.metadata?.run_count || 0;

  // Highlighted title
  const displayTitle = task.name || t('pages.tasks.untitledTask', '未命名任务');
  const highlightedTitle = searchHighlight ? highlightSearchText(displayTitle, searchHighlight) : displayTitle;

  // Dropdown menu items
  const menuItems: MenuProps['items'] = [
    {
      key: 'view',
      icon: <EyeOutlined />,
      label: t('pages.tasks.actions.view', '查看详情'),
    },
    {
      key: 'run',
      icon: <PlayCircleOutlined />,
      label: t('pages.tasks.actions.run', '立即运行'),
      disabled: isRunning,
    },
    { type: 'divider' },
    {
      key: 'edit',
      icon: <EditOutlined />,
      label: t('common.edit', '编辑'),
    },
    {
      key: 'duplicate',
      icon: <CopyOutlined />,
      label: t('pages.tasks.actions.duplicate', '复制'),
    },
    { type: 'divider' },
    {
      key: 'delete',
      icon: <DeleteOutlined />,
      label: t('common.delete', '删除'),
      danger: true,
    },
  ];

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    if (onAction) {
      onAction(key, task);
    }
  };

  // Grid View
  if (viewMode === 'grid') {
    return (
      <GridCardWrapper
        className={isSelected ? 'selected' : ''}
        onClick={() => onSelect(task)}
        $isSelected={isSelected}
        $isRunning={isRunning}
      >
        {/* Header Bar */}
        <GridCardHeaderBar>
          <GridHeaderLeft>
            <GridStatusIcon $color={statusConfig.color}>
              {statusConfig.icon}
            </GridStatusIcon>
            <GridHeaderInfo>
              <GridTaskTitle title={displayTitle}>
                {highlightedTitle}
              </GridTaskTitle>
            </GridHeaderInfo>
          </GridHeaderLeft>

          {/* Action Menu */}
          <Dropdown
            menu={{ items: menuItems, onClick: handleMenuClick }}
            trigger={['click']}
            placement="bottomRight"
          >
            <Button
              type="text"
              size="small"
              icon={<MoreOutlined />}
              onClick={(e: React.MouseEvent) => e.stopPropagation()}
              style={{ color: 'var(--text-muted)', padding: '4px' }}
            />
          </Dropdown>
        </GridCardHeaderBar>

        {/* Body */}
        <GridCardBody>
          {/* Status + Priority + Type badges */}
          <GridMetaRow>
            <GridStatusBadge $color={statusConfig.color} $bgColor={statusConfig.bgColor}>
              {statusConfig.icon}
              {statusConfig.text}
            </GridStatusBadge>

            {priority !== 'NONE' && priority !== 'none' && (
              <GridPriorityBadge
                $color={basePriorityConfig.color}
                $bgColor={basePriorityConfig.bgColor}
                $borderColor={basePriorityConfig.borderColor}
              >
                {priorityText}
              </GridPriorityBadge>
            )}

            <GridTypeBadge $color={taskTypeConfig.color}>
              {taskTypeConfig.icon}
              {t(taskTypeConfig.i18nKey, taskTypeConfig.defaultText)}
            </GridTypeBadge>
          </GridMetaRow>

          {/* Trigger badges */}
          {triggerConfigs.length > 0 && (
            <GridTriggerBadges>
              {triggerConfigs.map((cfg) => (
                <GridTriggerBadge
                  key={cfg.key}
                  $color={cfg.color}
                  $bgColor={cfg.bgColor}
                >
                  {cfg.icon}
                  {t(cfg.i18nKey, cfg.defaultText)}
                </GridTriggerBadge>
              ))}
            </GridTriggerBadges>
          )}
        </GridCardBody>

        {/* Footer */}
        <GridCardFooter>
          <GridFooterMeta>
            {task.last_run_datetime && (
              <GridFooterMetaItem>
                <ClockCircleOutlined />
                <span>{lastRunTime}</span>
              </GridFooterMetaItem>
            )}
            {runCount > 0 && (
              <GridFooterMetaItem>
                <SyncOutlined />
                <span>{t('pages.tasks.runCount', { count: runCount, defaultValue: `${runCount} 次运行` })}</span>
              </GridFooterMetaItem>
            )}
            {!task.last_run_datetime && runCount === 0 && (
              <GridFooterMetaItem>
                <ClockCircleOutlined />
                <span>{t('pages.tasks.notRun', '未运行过')}</span>
              </GridFooterMetaItem>
            )}
          </GridFooterMeta>

          <GridActionButtons onClick={(e: React.MouseEvent) => e.stopPropagation()}>
            <Tooltip title={t('common.edit', '编辑')}>
              <GridActionBtn
                $variant="secondary"
                size="small"
                icon={<EditOutlined />}
                onClick={() => onAction?.('edit', task)}
              />
            </Tooltip>
            <Tooltip title={isRunning ? t('pages.tasks.status.running', '运行中') : t('pages.tasks.actions.run', '运行')}>
              <GridActionBtn
                $variant="primary"
                size="small"
                icon={<PlayCircleOutlined />}
                onClick={() => onAction?.('run', task)}
                disabled={isRunning}
              />
            </Tooltip>
          </GridActionButtons>
        </GridCardFooter>

        {/* Progress Bar (only when running) */}
        {shouldShowProgress && (
          <div style={{ padding: '0 14px 12px' }}>
            <Progress
              percent={progress}
              size="small"
              strokeColor={{
                '0%': statusConfig.color,
                '100%': '#52C41A',
              }}
              trailColor="rgba(255, 255, 255, 0.1)"
              format={(p) => `${Math.round(p || 0)}%`}
            />
          </div>
        )}
      </GridCardWrapper>
    );
  }

  // List View (default)
  return (
    <TaskItem
      className={isSelected ? 'selected' : ''}
      onClick={() => onSelect(task)}
      isRunning={isRunning}
    >
      <TaskHeader>
        {/* Drag Handle */}
        <DragHandle>
          <DragOutlined />
        </DragHandle>
        
        <Space align="start" style={{ flex: 1 }}>
          {/* Status Icon */}
          <TaskIconWrapper status={status} gradient={statusConfig.gradient} isRunning={isRunning}>
            {statusConfig.icon}
          </TaskIconWrapper>

          {/* Task Info */}
          <TaskMeta>
            <TaskTitleRow>
              <TaskTitle title={displayTitle}>
                {highlightedTitle}
              </TaskTitle>
            </TaskTitleRow>

            {/* Tags Row */}
            <TaskTags>
              {/* Status Tag */}
              <StyledTag
                $bgColor={statusConfig.bgColor}
                $borderColor={statusConfig.color + '30'}
                $color={statusConfig.color}
                icon={statusConfig.icon}
              >
                {statusConfig.text}
              </StyledTag>

              {/* Priority Tag */}
              {priority !== 'NONE' && (
                <StyledTag
                  $bgColor={basePriorityConfig.bgColor}
                  $borderColor={basePriorityConfig.borderColor}
                  $color={basePriorityConfig.color}
                >
                  <Space size={4}>
                    <PriorityIndicator $level={basePriorityConfig.level} />
                    {basePriorityConfig.emoji} {priorityText}
                  </Space>
                </StyledTag>
              )}

              {/* Task Type Badge */}
              <TaskTypeBadge $color={taskTypeConfig.color}>
                {taskTypeConfig.icon} {taskTypeConfig.defaultText}
              </TaskTypeBadge>
            </TaskTags>
          </TaskMeta>
        </Space>

        {/* Action Menu */}
        <ActionMenuWrapper className="task-actions">
          <Dropdown
            menu={{ items: menuItems, onClick: handleMenuClick }}
            trigger={['click']}
            placement="bottomRight"
          >
            <Tooltip title={t('pages.tasks.actions.more', '更多操作')}>
              <Badge dot={isRunning} status="processing" offset={[-4, 4]}>
                <Button
                  type="text"
                  size="small"
                  icon={<MoreOutlined />}
                  onClick={(e: React.MouseEvent) => e.stopPropagation()}
                  style={{ color: 'var(--text-secondary)' }}
                />
              </Badge>
            </Tooltip>
          </Dropdown>
        </ActionMenuWrapper>
      </TaskHeader>

      {/* Progress Bar (only when running) */}
      {shouldShowProgress && (
        <ProgressWrapper key="progress">
          <Progress
            percent={progress}
            size="small"
            strokeColor={{
              '0%': statusConfig.color,
              '100%': '#52C41A',
            }}
            trailColor="rgba(255, 255, 255, 0.1)"
            format={(percent) => (
              <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                {Math.round(percent || 0)}%
              </span>
            )}
          />
        </ProgressWrapper>
      )}

      {/* Statistics Row */}
      <TaskStats>
        {/* Trigger Types */}
        {triggerConfigs.slice(0, 3).map((tc) => (
          <StyledTag
            key={tc.key}
            $bgColor={tc.bgColor}
            $borderColor={tc.color + '30'}
            $color={tc.color}
            icon={tc.icon}
          >
            {tc.text}
          </StyledTag>
        ))}
        {triggerConfigs.length > 3 && (
          <Tooltip title={triggerConfigs.slice(3).map(t => t.text).join(', ')}>
            <Tag style={{ margin: 0, cursor: 'pointer' }}>
              +{triggerConfigs.length - 3}
            </Tag>
          </Tooltip>
        )}

        {/* Divider */}
        <div style={{ flex: 1 }} />

        {/* Last Run Time */}
        <Tooltip title={task.last_run_datetime ? dayjs(task.last_run_datetime).format('YYYY-MM-DD HH:mm:ss') : ''}>
          <StatItem $highlight={isRunning}>
            <ClockCircleOutlined />
            <span>{lastRunTime}</span>
          </StatItem>
        </Tooltip>

        {/* Run Count */}
        {runCount > 0 && (
          <Tooltip title={t('pages.tasks.totalRuns', '总运行次数')}>
            <StatItem>
              <SyncOutlined />
              <span>{runCount}</span>
            </StatItem>
          </Tooltip>
        )}

        {/* Quick View Arrow */}
        <Tooltip title={t('pages.tasks.clickToView', '点击查看详情')}>
          <RightOutlined style={{ color: 'var(--text-muted)', fontSize: 12 }} />
        </Tooltip>
      </TaskStats>
    </TaskItem>
  );
};
