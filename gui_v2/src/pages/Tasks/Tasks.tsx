import { Button, Typography, Space, message } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import React, { useCallback, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';

import DetailLayout from '@/components/Layout/DetailLayout';
import { TaskList } from './components/TaskList';
import { TaskDetail } from './components/TaskDetail';
import { useTasks } from './hooks/useTasks';
import { Task } from './types';
import { get_ipc_api } from '@/services/ipc_api';
import { useUserStore } from '@/stores/userStore';

const { Text } = Typography;

const Tasks: React.FC = () => {
  const { t } = useTranslation();
  const { tasks, selectedTask, selectItem, isSelected, loading, handleRefresh } = useTasks();
  const [isAddingNew, setIsAddingNew] = React.useState(false);
  const username = useUserStore((state) => state.username);
  const [searchParams, setSearchParams] = useSearchParams();

  // Handle taskId from URL parameter
  useEffect(() => {
    const taskId = searchParams.get('taskId');
    if (taskId && tasks.length > 0) {
      const task = tasks.find(t => t.id === taskId);
      if (task) {
        selectItem(task);
        // Clear the URL parameter after selecting
        setSearchParams({});
      }
    }
  }, [searchParams, tasks, selectItem, setSearchParams]);

  const listTitle = (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <Text strong>{t('pages.tasks.title')}</Text>
      <Space>
        <Button
          shape="circle"
          icon={<ReloadOutlined />}
          onClick={handleRefresh}
          loading={loading}
          title={t('pages.tasks.refresh')}
        />
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            setIsAddingNew(true);
          }}
          title={t('pages.tasks.add')}
        />
      </Space>
    </div>
  );

  const handleTaskSave = () => {
    setIsAddingNew(false);
    handleRefresh();
  };

  // 运行任务
  const handleRunTask = useCallback(async (task: Task) => {
    if (!username) {
      message.error('用户未登录');
      return;
    }

    try {
      const api = get_ipc_api();
      const response = await api.runTask(username, task.id);
      if (response?.success) {
        message.success('任务已开始运行');
        handleRefresh();
      } else {
        message.error('运行任务失败');
      }
    } catch (error) {
      console.error('Failed to run task:', error);
      message.error('运行任务失败');
    }
  }, [username, handleRefresh]);

  // 暂停任务
  const handlePauseTask = useCallback(async (task: Task) => {
    if (!username) {
      message.error('用户未登录');
      return;
    }

    try {
      const api = get_ipc_api();
      const response = await api.pauseTask(username, task.id);
      if (response?.success) {
        message.success('任务已暂停');
        handleRefresh();
      } else {
        message.error('暂停任务失败');
      }
    } catch (error) {
      console.error('Failed to pause task:', error);
      message.error('暂停任务失败');
    }
  }, [username, handleRefresh]);

  // 取消任务
  const handleCancelTask = useCallback(async (task: Task) => {
    if (!username) {
      message.error('用户未登录');
      return;
    }

    try {
      const api = get_ipc_api();
      const response = await api.cancelTask(username, task.id);
      if (response?.success) {
        message.success('任务已取消');
        handleRefresh();
      } else {
        message.error('取消任务失败');
      }
    } catch (error) {
      console.error('Failed to cancel task:', error);
      message.error('取消任务失败');
    }
  }, [username, handleRefresh]);



  return (
    <DetailLayout
      listTitle={listTitle}
      detailsTitle={t('pages.tasks.details')}
      listContent={
        <TaskList
          tasks={tasks}
          loading={loading}
          onSelectItem={selectItem}
          isSelected={isSelected}
          onRun={handleRunTask}
          onPause={handlePauseTask}
          onCancel={handleCancelTask}
        />
      }
      detailsContent={
        selectedTask || isAddingNew ? (
          <TaskDetail
            task={isAddingNew ? null : selectedTask}
            isNew={isAddingNew}
            onSave={handleTaskSave}
            onCancel={() => setIsAddingNew(false)}
          />
        ) : null
      }
    />
  );
};

export default Tasks;