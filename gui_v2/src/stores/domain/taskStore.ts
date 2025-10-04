/**
 * Task Store
 * 任务数据管理 Store
 * 
 * 使用标准化的 store 模式，提供完整的 CRUD 功能
 */

import { createExtendedResourceStore } from '../base/createBaseStore';
import { BaseStoreState, CACHE_DURATION } from '../base/types';
import { Task, TaskStatus } from '../../types/domain/task';
import { TaskAPI } from '../../services/api/taskApi';

/**
 * Task Store 扩展接口
 * 在基础 store 之上添加任务特定的查询方法
 */
export interface TaskStoreState extends BaseStoreState<Task> {
  // 扩展查询方法
  getTasksByAgent: (agentId: string) => Task[];
  getTasksByStatus: (status: TaskStatus) => Task[];
  getPendingTasks: () => Task[];
  getCompletedTasks: () => Task[];
  
  // 扩展操作方法
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
 * // 获取任务
 * await fetchItems(username);
 * 
 * // 查询特定 agent 的任务
 * const agentTasks = useTaskStore.getState().getTasksByAgent(agentId);
 * 
 * // 创建新任务
 * await useTaskStore.getState().createTask(username, newTask);
 * ```
 */
export const useTaskStore = createExtendedResourceStore<Task, TaskStoreState>(
  {
    name: 'task',
    persist: true,
    cacheDuration: CACHE_DURATION.MEDIUM,
  },
  new TaskAPI(),
  (baseState, set, get) => ({
    ...baseState,
    
    // 扩展查询方法
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
    
    // 扩展操作方法
    createTask: async (username: string, task: Task) => {
      set({ loading: true, error: null });
      
      try {
        const api = new TaskAPI();
        const response = await api.create(username, task);
        
        if (response.success && response.data) {
          // 添加到本地状态
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
          // 更新本地状态
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
          // 从本地状态移除
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

