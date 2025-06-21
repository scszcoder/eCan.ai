import { useState, useEffect } from 'react';
import { useDetailView } from '@/hooks/useDetailView';
import { useSystemStore } from '@/stores/systemStore';
import { Task } from '../types';
import { tasksEventBus } from '../Tasks'; 

export const useTasks = () => {
  const storeTasks = useSystemStore((state) => state.tasks);

  const {
    items: tasks,
    setItems,
    selectedItem: selectedTask,
    selectItem,
    isSelected,
  } = useDetailView<Task>([], (task) => task.id);

  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (Array.isArray(storeTasks)) {
      setItems(storeTasks);
    }
  }, [storeTasks, setItems]);

  useEffect(() => {
    const unsubscribe = tasksEventBus.subscribe(setItems);
    return () => {
      unsubscribe();
    };
  }, [setItems]);

  const handleRefresh = () => {
    setLoading(true);
    // In a real app, you would call an API and then update the store.
    // The hook will then automatically receive the new initialTasks.
    setTimeout(() => {
      setLoading(false);
    }, 1000);
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