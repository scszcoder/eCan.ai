import React from 'react';
import { Tag, Progress, Space } from 'antd';
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
} from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { Task } from '../types';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import 'dayjs/locale/zh-cn';

dayjs.extend(relativeTime);
dayjs.locale('zh-cn');

// 状态配置 - 基础配置（包含默认文本作为后备）
const STATUS_BASE_CONFIG = {
  SUBMITTED: {
    gradient: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: '#667eea',
    icon: <ClockCircleOutlined />,
    key: 'SUBMITTED',
    defaultText: '已提交'
  },
  WORKING: {
    gradient: 'linear-gradient(135deg, #1890FF 0%, #096dd9 100%)',
    color: '#1890FF',
    icon: <SyncOutlined spin />,
    key: 'WORKING',
    defaultText: '运行中'
  },
  INPUT_REQUIRED: {
    gradient: 'linear-gradient(135deg, #FA8C16 0%, #d46b08 100%)',
    color: '#FA8C16',
    icon: <ExclamationCircleOutlined />,
    key: 'INPUT_REQUIRED',
    defaultText: '等待输入'
  },
  COMPLETED: {
    gradient: 'linear-gradient(135deg, #52C41A 0%, #389e0d 100%)',
    color: '#52C41A',
    icon: <CheckCircleOutlined />,
    key: 'COMPLETED',
    defaultText: '已完成'
  },
  CANCELED: {
    gradient: 'linear-gradient(135deg, #FF4D4F 0%, #cf1322 100%)',
    color: '#FF4D4F',
    icon: <StopOutlined />,
    key: 'CANCELED',
    defaultText: '已取消'
  },
  ready: {
    gradient: 'linear-gradient(135deg, #52C41A 0%, #389e0d 100%)',
    color: '#52C41A',
    icon: <CheckCircleOutlined />,
    key: 'ready',
    defaultText: '就绪'
  },
  running: {
    gradient: 'linear-gradient(135deg, #1890FF 0%, #096dd9 100%)',
    color: '#1890FF',
    icon: <SyncOutlined spin />,
    key: 'running',
    defaultText: '运行中'
  },
  unknown: {
    gradient: 'linear-gradient(135deg, #8C8C8C 0%, #595959 100%)',
    color: '#8C8C8C',
    icon: <ClockCircleOutlined />,
    key: 'unknown',
    defaultText: '未知'
  },
};

// 优先级配置 - 使用更丰富的颜色
const PRIORITY_CONFIG = {
  ASAP: {
    color: 'red',
    emoji: '⚡',
    defaultText: '立即',
    style: { background: '#fff1f0', borderColor: '#ffa39e', color: '#cf1322' }
  },
  URGENT: {
    color: 'orange',
    emoji: '🔥',
    defaultText: '紧急',
    style: { background: '#fff7e6', borderColor: '#ffd591', color: '#d46b08' }
  },
  HIGH: {
    color: 'gold',
    emoji: '⬆️',
    defaultText: '高',
    style: { background: '#fffbe6', borderColor: '#ffe58f', color: '#d48806' }
  },
  MID: {
    color: 'blue',
    emoji: '➡️',
    defaultText: '中',
    style: { background: '#e6f7ff', borderColor: '#91d5ff', color: '#096dd9' }
  },
  LOW: {
    color: 'default',
    emoji: '⬇️',
    defaultText: '低',
    style: { background: '#fafafa', borderColor: '#d9d9d9', color: '#595959' }
  },
  none: {
    color: 'default',
    emoji: '',
    defaultText: '无',
    style: { background: '#fafafa', borderColor: '#d9d9d9', color: '#8c8c8c' }
  },
};

// 触发方式配置 - 使用更丰富的颜色
const TRIGGER_CONFIG = {
  schedule: {
    icon: <CalendarOutlined />,
    defaultText: '定时',
    color: '#722ed1',
    style: { background: '#f9f0ff', borderColor: '#d3adf7', color: '#722ed1' }
  },
  'human chat': {
    icon: <MessageOutlined />,
    defaultText: '聊天',
    color: '#13c2c2',
    style: { background: '#e6fffb', borderColor: '#87e8de', color: '#13c2c2' }
  },
  'agent message': {
    icon: <RobotOutlined />,
    defaultText: '消息',
    color: '#1890ff',
    style: { background: '#e6f7ff', borderColor: '#91d5ff', color: '#1890ff' }
  },
  chat_queue: {
    icon: <MessageOutlined />,
    defaultText: '聊天队列',
    color: '#13c2c2',
    style: { background: '#e6fffb', borderColor: '#87e8de', color: '#13c2c2' }
  },
  a2a_queue: {
    icon: <RobotOutlined />,
    defaultText: '消息队列',
    color: '#1890ff',
    style: { background: '#e6f7ff', borderColor: '#91d5ff', color: '#1890ff' }
  },
  manual: {
    icon: <ThunderboltOutlined />,
    defaultText: '手动',
    color: '#fa8c16',
    style: { background: '#fff7e6', borderColor: '#ffd591', color: '#fa8c16' }
  },
  interaction: {
    icon: <MessageOutlined />,
    defaultText: '交互',
    color: '#52c41a',
    style: { background: '#f6ffed', borderColor: '#b7eb8f', color: '#52c41a' }
  },
  message: {
    icon: <MessageOutlined />,
    defaultText: '消息',
    color: '#1890ff',
    style: { background: '#e6f7ff', borderColor: '#91d5ff', color: '#1890ff' }
  },
};

const TaskItem = styled.div`
    padding: 8px;
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    background: var(--bg-secondary);
    border-radius: 12px;
    margin: 4px 0;
    border: 2px solid transparent;
    position: relative;
    overflow: hidden;

    &::before {
        content: '';
        position: absolute;
        left: 0;
        top: 0;
        height: 100%;
        width: 4px;
        background: transparent;
        transition: all 0.3s ease;
    }

    &:hover {
        background: var(--bg-tertiary);
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);

        &::before {
            width: 3px;
            background: var(--primary-color);
        }
    }

    &.selected {
        background: linear-gradient(135deg, rgba(24, 144, 255, 0.15) 0%, rgba(24, 144, 255, 0.05) 100%);
        border: 2px solid var(--primary-color);

        &::before {
            background: var(--primary-color);
        }

        &:hover {
            background: linear-gradient(135deg, rgba(24, 144, 255, 0.2) 0%, rgba(24, 144, 255, 0.08) 100%);

            &::before {
                width: 4px;
            }
        }
    }
`;

const TaskHeader = styled.div`
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
`;

const TaskIcon = styled.div<{ gradient?: string }>`
    width: 40px;
    height: 40px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    color: white;
    background: ${props => props.gradient || 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'};
    flex-shrink: 0;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
`;

const TaskMeta = styled.div`
    display: flex;
    flex-direction: column;
    gap: 6px;
    flex: 1;
    margin-left: 12px;
`;

const TaskTitle = styled.div`
    font-size: 15px;
    font-weight: 600;
    color: var(--text-primary);
    display: block;
    margin-bottom: 4px;
`;

const TaskStats = styled.div`
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid var(--border-color);
`;

const StatItem = styled.div`
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    color: var(--text-secondary);

    .anticon {
        font-size: 14px;
    }
`;

interface TaskCardProps {
  task: Task;
  isSelected: boolean;
  onSelect: (task: Task) => void;
}

export const TaskCard: React.FC<TaskCardProps> = ({
  task,
  isSelected,
  onSelect,
}) => {
  const { t } = useTranslation();

  // 获取任务状态 - 使用国际化文本
  const status = task.state?.top || task.status || 'unknown';
  const baseStatusConfig = STATUS_BASE_CONFIG[status as keyof typeof STATUS_BASE_CONFIG] || STATUS_BASE_CONFIG.unknown;
  const statusConfig = {
    ...baseStatusConfig,
    text: t(`pages.tasks.status.${baseStatusConfig.key}`, baseStatusConfig.defaultText),
  };

  // 获取优先级 - 使用国际化文本
  const priority = task.priority || 'none';
  const basePriorityConfig = PRIORITY_CONFIG[priority as keyof typeof PRIORITY_CONFIG] || PRIORITY_CONFIG.none;
  const priorityText = t(`pages.tasks.priority.${priority}`, basePriorityConfig.defaultText);
  const priorityConfig = {
    ...basePriorityConfig,
    text: basePriorityConfig.emoji ? `${basePriorityConfig.emoji} ${priorityText}` : priorityText,
  };

  // 获取触发方式 - 使用国际化文本
  const trigger = task.trigger || 'manual';
  const baseTriggerConfig = TRIGGER_CONFIG[trigger as keyof typeof TRIGGER_CONFIG];

  // 如果找不到配置，使用默认配置
  const finalTriggerConfig = baseTriggerConfig || {
    icon: <ThunderboltOutlined />,
    defaultText: trigger,
    color: '#8c8c8c',
    style: { background: '#fafafa', borderColor: '#d9d9d9', color: '#8c8c8c' }
  };

  const triggerConfig = {
    ...finalTriggerConfig,
    text: t(`pages.tasks.trigger.${trigger}`, finalTriggerConfig.defaultText),
  };

  // 格式化最后运行时间
  const lastRunTime = task.last_run_datetime
    ? dayjs(task.last_run_datetime).fromNow()
    : t('pages.tasks.notRun', '未运行');

  // 计算进度（如果任务正在运行）
  const isRunning = status === 'WORKING' || status === 'running';
  const progress = isRunning ? 60 : 0; // TODO: 从实际数据获取

  // Task operations are handled in TaskDetail component

  return (
    <TaskItem
      className={isSelected ? 'selected' : ''}
      onClick={() => onSelect(task)}
    >
      <TaskHeader>
        <Space align="start" style={{ flex: 1 }}>
          {/* 状态图标 */}
          <TaskIcon gradient={statusConfig.gradient}>
            {statusConfig.icon}
          </TaskIcon>

          {/* 任务信息 */}
          <TaskMeta>
            <TaskTitle>{task.name || t('pages.tasks.untitledTask', '未命名任务')}</TaskTitle>
            <Space size={6} wrap>
              <Tag
                icon={statusConfig.icon}
                style={{
                  borderRadius: 4,
                  fontWeight: 500,
                }}
              >
                {statusConfig.text}
              </Tag>
              <Tag
                style={{
                  ...priorityConfig.style,
                  borderRadius: 4,
                  fontWeight: 500,
                }}
              >
                {priorityConfig.text}
              </Tag>
            </Space>
          </TaskMeta>
        </Space>
      </TaskHeader>

      {/* 进度条（仅运行中显示） */}
      {isRunning && (
        <div style={{ marginBottom: 8 }}>
          <Progress
            percent={progress}
            size="small"
            strokeColor={{
              '0%': statusConfig.color,
              '100%': '#52C41A',
            }}
          />
        </div>
      )}

      {/* 统计信息 */}
      <TaskStats>
        <Tag
          icon={triggerConfig.icon}
          style={{
            ...triggerConfig.style,
            borderRadius: 4,
            fontWeight: 500,
            margin: 0,
          }}
        >
          {triggerConfig.text}
        </Tag>
        <StatItem>
          <ClockCircleOutlined />
          <span>{lastRunTime}</span>
        </StatItem>
      </TaskStats>
    </TaskItem>
  );
};

