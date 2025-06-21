import { Avatar, List, Space, Tag, Typography } from 'antd';
import { CodeOutlined, OrderedListOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styled from 'styled-components';
import React from 'react';
import { Task } from '../types';

const { Text } = Typography;

const TaskItem = styled.div<{ $isActive: boolean }>`
  padding: 12px;
  border-bottom: 1px solid #eee;
  cursor: pointer;
  background-color: ${(props) => (props.$isActive ? '#e6f7ff' : 'transparent')};
  &:hover {
    background-color: #f5f5f5;
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

  return (
    <List
      dataSource={tasks}
      renderItem={(task) => (
        <TaskItem onClick={() => onSelectItem(task)} $isActive={isSelected(task)}>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Space>
              <Avatar icon={<OrderedListOutlined />} />
              <Text strong>{task.skill}</Text>
            </Space>
            <Space>
              <Tag color={getStatusColor(task.state.top)}>{task.state.top}</Tag>
              <Tag icon={<CodeOutlined />}>
                {t('pages.tasks.trigger')}: {task.trigger}
              </Tag>
              <Tag>
                {t('pages.tasks.priority')}: {task.priority}
              </Tag>
            </Space>
          </Space>
        </TaskItem>
      )}
    />
  );
}; 