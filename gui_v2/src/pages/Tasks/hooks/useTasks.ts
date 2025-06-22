import { useState, useEffect, useCallback } from 'react';
import { useDetailView } from '@/hooks/useDetailView';
import { useAppDataStore } from '@/stores/appDataStore';
import { Task } from '../types';
import { APIResponse } from '../../../services/ipc/api';
import { logger } from '../../../utils/logger';
import { get_ipc_api } from '@/services/ipc_api';

export const useTasks = () => {
  const storeTasks = useAppDataStore((state) => state.tasks);
  const setTasks = useAppDataStore((state) => state.setTasks);

  const {
    items: tasks,
    setItems,
    selectedItem: selectedTask,
    selectItem,
    isSelected,
  } = useDetailView<Task>([], (task) => task.id);

  const [loading, setLoading] = useState(false);

  const fetchTasks = useCallback(async () => {
    setLoading(true);
    try {
      const api = get_ipc_api();
      const loginInfoResponse = await api.getLastLoginInfo<{ last_login: { username: string } }>();

      if (loginInfoResponse.success && loginInfoResponse.data?.last_login.username) {
        const username = loginInfoResponse.data.last_login.username;
        const response: APIResponse<{ tasks: Task[] }> = await api.getTasks(username, []);
        if (response.success && response.data) {
          console.log('[Tasks] Fetched tasks:', response.data);
          setTasks(response.data.tasks);
        } else {
          logger.error('Failed to fetch tasks:', response.error);
        }
      } else {
        logger.error('Failed to get user login info:', loginInfoResponse.error);
      }
    } catch (error) {
      logger.error('An error occurred while fetching tasks:', error);
    } finally {
      setLoading(false);
    }
  }, [setTasks]);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  useEffect(() => {
    if (Array.isArray(storeTasks)) {
      setItems(storeTasks);
    }
  }, [storeTasks, setItems]);

  const handleRefresh = () => {
    fetchTasks();
  };

  return {
    tasks,
    selectedTask,
    selectItem,
    isSelected,
    loading,
    handleRefresh,
  };
}; 