import { Avatar, List, Space, Tag, Typography, theme } from 'antd';
import { CodeOutlined, OrderedListOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styled from 'styled-components';
import React from 'react';
import { Task } from '../types';

const { Text } = Typography;

const TaskItem = styled.div<{
  $isActive: boolean;
  $activeBg: string;
  $hoverBg: string;
  $borderRadius: number;
}>`
  padding: 12px;
  margin: 4px 8px;
  border-radius: ${(props) => props.$borderRadius}px;
  cursor: pointer;
  background-color: ${(props) => (props.$isActive ? props.$activeBg : 'transparent')};
  &:hover {
    background-color: ${(props) => props.$hoverBg};
  }
`;

const getStatusColor = (state: string) => {
  if (state === 'ready') return 'green';
  if (state === 'running') return 'blue';
  return 'default';
};

interface TaskListProps {
  tasks: Task[];
  onSelectItem: (task: Task) => void;
  isSelected: (task: Task) => boolean;
}

export const TaskList: React.FC<TaskListProps> = ({ tasks, onSelectItem, isSelected }) => {
  const { t } = useTranslation();
  const { token } = theme.useToken();

  return (
    <List
      dataSource={tasks}
      renderItem={(task) => (
        <TaskItem
          onClick={() => onSelectItem(task)}
          $isActive={isSelected(task)}
          $activeBg={token.colorPrimaryBg}
          $hoverBg={token.colorBgTextHover}
          $borderRadius={token.borderRadiusLG}
        >
          <Space direction="vertical" style={{ width: '100%' }}>
            <Space>
              <Avatar icon={<OrderedListOutlined />} />
              <Text strong>{t('pages.tasks.skill.' + task.skill, task.skill)}</Text>
            </Space>
            <Space>
              <Tag color={getStatusColor(task.state.top)}>{t('pages.tasks.states.' + task.state.top, task.state.top)}</Tag>
              <Tag icon={<CodeOutlined />}>
                {t('pages.tasks.trigger.' + task.trigger, task.trigger)}
              </Tag>
              <Tag>
                {t('pages.tasks.priority.' + task.priority, task.priority)}
              </Tag>
            </Space>
          </Space>
        </TaskItem>
      )}
    />
  );
}; 