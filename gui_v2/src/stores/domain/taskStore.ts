/**
 * Task Store
 * Task data management store
 * 
 * Uses standardized store pattern with complete CRUD functionality
 */

import { createExtendedResourceStore } from '../base/createBaseStore';
import { BaseStoreState, CACHE_DURATION } from '../base/types';
import { Task, TaskStatus } from '../../types/domain/task';
import { TaskAPI } from '../../services/api/taskApi';

/**
 * Task Store extended interface
 * Adds task-specific query methods on top of the base store
 */
export interface TaskStoreState extends BaseStoreState<Task> {
  // Extended query methods
  getTasksByAgent: (agentId: string) => Task[];
  getTasksByStatus: (status: TaskStatus) => Task[];
  getPendingTasks: () => Task[];
  getCompletedTasks: () => Task[];
  
  // Extended operation methods
  createTask: (username: string, task: Task) => Promise<void>;
  updateTaskStatus: (username: string, taskId: string, status: TaskStatus) => Promise<void>;
  deleteTask: (username: string, taskId: string) => Promise<void>;
}

/**
 * Task Store
 * 
 * @example
 * ```typescript
 * const { items: tasks, loading, fetchItems } = useTaskStore();
 * 
 * // Get tasks
 * await fetchItems(username);
 * 
 * // Query tasks for specific agent
 * const agentTasks = useTaskStore.getState().getTasksByAgent(agentId);
 * 
 * // Create new task
 * await useTaskStore.getState().createTask(username, newTask);
 * ```
 */
export const useTaskStore = createExtendedResourceStore<Task, TaskStoreState>(
  {
    name: 'task',
    persist: false,  // 关闭持久化，避免数据不一致
    cacheDuration: CACHE_DURATION.MEDIUM,
  },
  new TaskAPI(),
  (baseState, set, get) => ({
    ...baseState,
    
    // Extended query methods
    getTasksByAgent: (agentId: string) => {
      const items = get().items;
      return items.filter(task => task.agentId === agentId);
    },
    
    getTasksByStatus: (status: TaskStatus) => {
      const items = get().items;
      return items.filter(task => task.status === status);
    },
    
    getPendingTasks: () => {
      const items = get().items;
      return items.filter(task => task.status === TaskStatus.PENDING);
    },
    
    getCompletedTasks: () => {
      const items = get().items;
      return items.filter(task => task.status === TaskStatus.COMPLETED);
    },
    
    // Extended operation methods
    createTask: async (username: string, task: Task) => {
      set({ loading: true, error: null });
      
      try {
        const api = new TaskAPI();
        const response = await api.create(username, task);
        
        if (response.success && response.data) {
          // Add to local state
          get().addItem(response.data);
          set({ loading: false });
        } else {
          throw new Error(response.error?.message || 'Failed to create task');
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        set({ error: errorMessage, loading: false });
        throw error;
      }
    },
    
    updateTaskStatus: async (username: string, taskId: string, status: TaskStatus) => {
      set({ loading: true, error: null });
      
      try {
        const api = new TaskAPI();
        const response = await api.update(username, taskId, { status });
        
        if (response.success && response.data) {
          // Update local state
          get().updateItem(taskId, { status });
          set({ loading: false });
        } else {
          throw new Error(response.error?.message || 'Failed to update task status');
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        set({ error: errorMessage, loading: false });
        throw error;
      }
    },
    
    deleteTask: async (username: string, taskId: string) => {
      set({ loading: true, error: null });
      
      try {
        const api = new TaskAPI();
        const response = await api.delete(username, taskId);
        
        if (response.success) {
          // Remove from local state
          get().removeItem(taskId);
          set({ loading: false });
        } else {
          throw new Error(response.error?.message || 'Failed to delete task');
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        set({ error: errorMessage, loading: false });
        throw error;
      }
    },
  })
);

