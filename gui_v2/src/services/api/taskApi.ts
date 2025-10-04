/**
 * Task API Service
 * 任务相关的 API 调用封装
 */

import { createIPCAPI } from '../ipc/api';
import type { IPCAPI } from '../ipc/api';
import { ResourceAPI, APIResponse } from '../../stores/base/types';
import { Task, CreateTaskInput, UpdateTaskInput } from '../../types/domain/task';
import { logger } from '../../utils/logger';

/**
 * Task API 服务类
 * 实现 ResourceAPI 接口，提供标准化的 CRUD 操作
 */
export class TaskAPI implements ResourceAPI<Task> {
  private _api?: IPCAPI;

  private get api(): IPCAPI {
    if (!this._api) {
      this._api = createIPCAPI();
    }
    return this._api;
  }

  /**
   * 获取所有任务
   */
  async getAll(username: string, agentId?: string): Promise<APIResponse<Task[]>> {
    try {
      logger.debug('[TaskAPI] Fetching all tasks for user:', username);
      
      const response = await this.api.getTasks(username, agentId ? [agentId] : []);
      
      if (response && response.success && response.data) {
        // 处理不同的响应格式
        let tasks: Task[] = [];
        
        if (Array.isArray(response.data)) {
          tasks = response.data;
        } else if (response.data && typeof response.data === 'object' && 'tasks' in response.data) {
          tasks = (response.data as any).tasks || [];
        }
        
        logger.debug('[TaskAPI] Successfully fetched tasks:', tasks.length);
        
        return {
          success: true,
          data: tasks,
        };
      } else {
        throw new Error(response.error?.message || 'Failed to fetch tasks');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      logger.error('[TaskAPI] Error fetching tasks:', errorMessage);
      
      return {
        success: false,
        error: {
          code: 'FETCH_TASKS_ERROR',
          message: errorMessage,
        },
      };
    }
  }

  /**
   * 根据 ID 获取单个任务
   */
  async getById(username: string, id: string): Promise<APIResponse<Task>> {
    try {
      logger.debug('[TaskAPI] Fetching task by ID:', id);
      
      // 目前后端可能没有单独的 getTaskById 接口，先通过 getAll 然后过滤
      const allTasksResponse = await this.getAll(username);
      
      if (allTasksResponse.success && allTasksResponse.data) {
        const task = allTasksResponse.data.find(t => t.id === id);
        
        if (task) {
          return {
            success: true,
            data: task,
          };
        } else {
          throw new Error(`Task not found: ${id}`);
        }
      } else {
        throw new Error(allTasksResponse.error?.message || 'Failed to fetch task');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      logger.error('[TaskAPI] Error fetching task by ID:', errorMessage);
      
      return {
        success: false,
        error: {
          code: 'FETCH_TASK_ERROR',
          message: errorMessage,
        },
      };
    }
  }

  /**
   * 创建新任务
   */
  async create(username: string, task: Task): Promise<APIResponse<Task>> {
    try {
      logger.debug('[TaskAPI] Creating new task:', task.name);
      
      const response = await this.api.newTasks(username, [task]);
      
      if (response && response.success) {
        logger.debug('[TaskAPI] Successfully created task');
        
        return {
          success: true,
          data: task,
        };
      } else {
        throw new Error(response.error?.message || 'Failed to create task');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      logger.error('[TaskAPI] Error creating task:', errorMessage);
      
      return {
        success: false,
        error: {
          code: 'CREATE_TASK_ERROR',
          message: errorMessage,
        },
      };
    }
  }

  /**
   * 更新任务
   */
  async update(username: string, id: string, updates: Partial<Task>): Promise<APIResponse<Task>> {
    try {
      logger.debug('[TaskAPI] Updating task:', id);
      
      // 先获取完整的任务数据
      const taskResponse = await this.getById(username, id);
      
      if (!taskResponse.success || !taskResponse.data) {
        throw new Error('Task not found');
      }
      
      const updatedTask = { ...taskResponse.data, ...updates };
      
      const response = await this.api.saveTasks(username, [updatedTask]);
      
      if (response && response.success) {
        logger.debug('[TaskAPI] Successfully updated task');
        
        return {
          success: true,
          data: updatedTask,
        };
      } else {
        throw new Error(response.error?.message || 'Failed to update task');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      logger.error('[TaskAPI] Error updating task:', errorMessage);
      
      return {
        success: false,
        error: {
          code: 'UPDATE_TASK_ERROR',
          message: errorMessage,
        },
      };
    }
  }

  /**
   * 删除任务
   */
  async delete(username: string, id: string): Promise<APIResponse<void>> {
    try {
      logger.debug('[TaskAPI] Deleting task:', id);
      
      const response = await this.api.deleteTask(username, id);
      
      if (response && response.success) {
        logger.debug('[TaskAPI] Successfully deleted task');
        
        return {
          success: true,
        };
      } else {
        throw new Error(response.error?.message || 'Failed to delete task');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      logger.error('[TaskAPI] Error deleting task:', errorMessage);
      
      return {
        success: false,
        error: {
          code: 'DELETE_TASK_ERROR',
          message: errorMessage,
        },
      };
    }
  }
}

// 导出单例实例
export const taskApi = new TaskAPI();

