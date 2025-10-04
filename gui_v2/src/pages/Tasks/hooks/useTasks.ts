import { useState, useEffect, useCallback } from 'react';
import { useDetailView } from '@/hooks/useDetailView';
import { useTaskStore } from '@/stores';
import { useUserStore } from '@/stores/userStore';
import { Task } from '../types';
import { logger } from '../../../utils/logger';
import { message } from 'antd';

export const useTasks = () => {
  // 使用新的 taskStore
  const tasks = useTaskStore((state) => state.items);
  const isLoading = useTaskStore((state) => state.loading);
  const error = useTaskStore((state) => state.error);
  const fetchItems = useTaskStore((state) => state.fetchItems);

  const username = useUserStore((state) => state.username);

  const {
    selectedItem: selectedTask,
    selectItem,
    isSelected,
  } = useDetailView<Task>(tasks, (task) => task.id);

  const [loading, setLoading] = useState(false);

  const fetchTasks = useCallback(async () => {
    if (!username) {
      logger.warn('[useTasks] Username is not available');
      return;
    }

    setLoading(true);
    try {
      logger.info('[useTasks] Fetching tasks for user:', username);
      await fetchItems(username);
      logger.info('[useTasks] Successfully fetched tasks:', tasks.length);
    } catch (error) {
      logger.error('[useTasks] Error fetching tasks:', error);
      message.error('Failed to fetch tasks');
    } finally {
      setLoading(false);
    }
  }, [username, fetchItems, tasks.length]);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  // 显示错误信息
  useEffect(() => {
    if (error) {
      message.error(error);
    }
  }, [error]);

  const handleRefresh = () => {
    fetchTasks();
  };

  return {
    tasks,
    selectedTask,
    selectItem,
    isSelected,
    loading: loading || isLoading,
    handleRefresh,
  };
};