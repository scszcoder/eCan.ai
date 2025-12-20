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
  const forceRefresh = useTaskStore((state) => state.forceRefresh);

  const username = useUserStore((state) => state.username);

  const {
    selectedItem: selectedTask,
    selectItem,
    isSelected,
  } = useDetailView<Task>(tasks, (task) => task.id);

  const [loading, setLoading] = useState(false);

  const fetchTasks = useCallback(async () => {
    if (!username) return;

    setLoading(true);
    try {
      await fetchItems(username);
    } catch (error) {
      logger.error('[useTasks] Error fetching tasks:', error);
      message.error('Failed to fetch tasks');
    } finally {
      setLoading(false);
    }
  }, [username, fetchItems]);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  // DisplayErrorInformation
  useEffect(() => {
    if (error) {
      message.error(error);
    }
  }, [error]);

  const handleRefresh = useCallback(async () => {
    if (!username) return;

    setLoading(true);
    try {
      await forceRefresh(username);
    } catch (error) {
      logger.error('[useTasks] Error refreshing tasks:', error);
      message.error('Failed to refresh tasks');
    } finally {
      setLoading(false);
    }
  }, [username, forceRefresh]);

  return {
    tasks,
    selectedTask,
    selectItem,
    isSelected,
    loading: loading || isLoading,
    handleRefresh,
  };
};