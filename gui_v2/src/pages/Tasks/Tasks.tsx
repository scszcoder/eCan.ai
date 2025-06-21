import { Button, Spin, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import React from 'react';

import DetailLayout from '@/components/Layout/DetailLayout';
import { TaskList } from './components/TaskList';
import { TaskDetail } from './components/TaskDetail';
import { useTasks } from './hooks/useTasks';
import { Task } from './types';

const { Text } = Typography;

export const tasksEventBus = {
  listeners: new Set<(data: Task[]) => void>(),
  subscribe(listener: (data: Task[]) => void) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  },
  emit(data: Task[]) {
    this.listeners.forEach((listener) => listener(data));
  },
};

export const updateTasksGUI = (data: Task[]) => {
  tasksEventBus.emit(data);
};

const Tasks: React.FC = () => {
  const { t } = useTranslation();
  const { tasks, selectedTask, selectItem, isSelected, loading, handleRefresh } = useTasks();

  const listTitle = (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <Text strong>{t('pages.tasks.title')}</Text>
      <Button
        shape="circle"
        icon={<ReloadOutlined />}
        onClick={handleRefresh}
        loading={loading}
        title={t('pages.tasks.refresh')}
      />
    </div>
  );

  return (
    <DetailLayout
      listTitle={listTitle}
      detailsTitle={t('pages.tasks.details')}
      listContent={
        <Spin spinning={loading}>
          <TaskList tasks={tasks} onSelectItem={selectItem} isSelected={isSelected} />
        </Spin>
      }
      detailsContent={<TaskDetail task={selectedTask} />}
    />
  );
};

export default Tasks;