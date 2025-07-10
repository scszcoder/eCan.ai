import {
  ClockCircleOutlined,
  DeleteOutlined,
  OrderedListOutlined,
  PlayCircleOutlined,
  SettingOutlined,
  StopOutlined,
} from '@ant-design/icons';
import { Avatar, Button, Card, Descriptions, Space, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import React from 'react';
import { Task } from '../types';

const { Title, Text } = Typography;

const getStatusColor = (state: string) => {
  if (state === 'ready') return 'green';
  if (state === 'running') return 'blue';
  return 'default';
};

interface TaskDetailProps {
  task: Task | null;
}

export const TaskDetail: React.FC<TaskDetailProps> = ({ task }) => {
  const { t } = useTranslation();

  if (!task) {
    return <Text type="secondary">{t('pages.tasks.selectTask')}</Text>;
  }

  return (
    <div style={{ maxHeight: '100%', overflow: 'auto' }}>
      <Space direction="vertical" style={{ width: '100%' }} size="large">
        <Space align="start">
          <Avatar size={64} icon={<OrderedListOutlined />} />
          <div>
            <Title level={4} style={{ margin: 0 }}>
              {t('pages.tasks.skill.' + task.skill, task.skill)}
            </Title>
            <Text type="secondary">{t('pages.tasks.id', { id: task.id })}</Text>
          </div>
        </Space>

        <Descriptions bordered column={1} size="small">
          <Descriptions.Item label={t('pages.tasks.status')}>
            <Tag color={getStatusColor(task.state.top)}>{t('pages.tasks.states.' + task.state.top, task.state.top)}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t('pages.tasks.triggerLabel', '触发器')}>
            {t('pages.tasks.trigger.' + task.trigger, task.trigger)}
          </Descriptions.Item>
          <Descriptions.Item label={t('pages.tasks.priorityLabel', '优先级')}>
            {t('pages.tasks.priority.' + task.priority, task.priority)}
          </Descriptions.Item>
          <Descriptions.Item label={t('pages.tasks.lastRun')}>
            {task.last_run_datetime || t('common.never')}
          </Descriptions.Item>
        </Descriptions>

        <Card title={t('pages.tasks.scheduleDetails')}>
          <Descriptions bordered column={1} size="small">
            <Descriptions.Item label={t('pages.tasks.scheduleRepeatTypeLabel', '重复类型')}>
              {t('pages.tasks.schedule.repeatType.' + task.schedule.repeat_type, task.schedule.repeat_type)}
            </Descriptions.Item>
            <Descriptions.Item label={t('pages.tasks.scheduleRepeatUnitLabel', '重复单位')}>
              {t('pages.tasks.schedule.repeatUnit.' + task.schedule.repeat_unit, task.schedule.repeat_unit)} ({task.schedule.repeat_number})
            </Descriptions.Item>
            <Descriptions.Item label={t('pages.tasks.scheduleStartTimeLabel', '开始时间')}>
              {task.schedule.start_date_time}
            </Descriptions.Item>
            <Descriptions.Item label={t('pages.tasks.scheduleEndTimeLabel', '结束时间')}>
              {task.schedule.end_date_time}
            </Descriptions.Item>
            <Descriptions.Item label={t('pages.tasks.scheduleTimeoutLabel', '超时时间')}>
              {task.schedule.time_out}s
            </Descriptions.Item>
          </Descriptions>
        </Card>

        <Space>
          <Button type="primary" icon={<PlayCircleOutlined />}>
            {t('common.run')}
          </Button>
          <Button danger icon={<StopOutlined />}>
            {t('common.stop')}
          </Button>
          <Button icon={<SettingOutlined />}>{t('common.settings')}</Button>
          <Button danger icon={<DeleteOutlined />}>
            {t('common.delete')}
          </Button>
        </Space>
      </Space>
    </div>
  );
}; 