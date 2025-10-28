/**
 * Agent Task API Service
 * Agent 任务Related to API 调用封装
 */

import { createIPCAPI } from '../ipc/api';
import type { IPCAPI } from '../ipc/api';
import { ResourceAPI, APIResponse } from '../../stores/base/types';
import { Task, CreateTaskInput, UpdateTaskInput } from '../../types/domain/task';
import { logger } from '../../utils/logger';

/**
 * Agent Task API Service类
 * Implementation ResourceAPI Interface，提供Standard化的 CRUD Operation
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
   * GetAll Agent 任务
   */
  async getAll(username: string, agentId?: string): Promise<APIResponse<Task[]>> {
    try {
      logger.debug('[TaskAPI] Fetching all agent tasks for user:', username);

      const response = await this.api.getAgentTasks(username, agentId ? [agentId] : []);

      if (response && response.success && response.data) {
        // Process不同的Response格式
        let tasks: Task[] = [];

        if (Array.isArray(response.data)) {
          tasks = response.data;
        } else if (response.data && typeof response.data === 'object' && 'tasks' in response.data) {
          tasks = (response.data as any).tasks || [];
        }

        logger.debug('[TaskAPI] Successfully fetched agent tasks:', tasks.length);

        return {
          success: true,
          data: tasks,
        };
      } else {
        throw new Error(response.error?.message || 'Failed to fetch agent tasks');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      logger.error('[TaskAPI] Error fetching agent tasks:', errorMessage);

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
   * 根据 ID Get单个 Agent 任务
   */
  async getById(username: string, id: string): Promise<APIResponse<Task>> {
    try {
      logger.debug('[TaskAPI] Fetching agent task by ID:', id);

      // 目前Backend可能没有单独的 getAgentTaskById Interface，先通过 getAll 然后Filter
      const allTasksResponse = await this.getAll(username);

      if (allTasksResponse.success && allTasksResponse.data) {
        const task = allTasksResponse.data.find(t => t.id === id);

        if (task) {
          return {
            success: true,
            data: task,
          };
        } else {
          throw new Error(`Agent task not found: ${id}`);
        }
      } else {
        throw new Error(allTasksResponse.error?.message || 'Failed to fetch agent task');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      logger.error('[TaskAPI] Error fetching agent task by ID:', errorMessage);

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
   * Create新 Agent 任务
   */
  async create(username: string, task: Task): Promise<APIResponse<Task>> {
    try {
      logger.debug('[TaskAPI] Creating new agent task:', task.name);

      const response = await this.api.newAgentTask(username, task);

      if (response && response.success) {
        logger.debug('[TaskAPI] Successfully created agent task');

        return {
          success: true,
          data: task,
        };
      } else {
        throw new Error(response.error?.message || 'Failed to create agent task');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      logger.error('[TaskAPI] Error creating agent task:', errorMessage);

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
   * Update Agent 任务
   */
  async update(username: string, id: string, updates: Partial<Task>): Promise<APIResponse<Task>> {
    try {
      logger.debug('[TaskAPI] Updating agent task:', id);

      // 先Get完整的任务Data
      const taskResponse = await this.getById(username, id);

      if (!taskResponse.success || !taskResponse.data) {
        throw new Error('Agent task not found');
      }

      const updatedTask = { ...taskResponse.data, ...updates };

      const response = await this.api.saveAgentTask(username, updatedTask);

      if (response && response.success) {
        logger.debug('[TaskAPI] Successfully updated agent task');

        return {
          success: true,
          data: updatedTask,
        };
      } else {
        throw new Error(response.error?.message || 'Failed to update agent task');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      logger.error('[TaskAPI] Error updating agent task:', errorMessage);

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
   * Delete Agent 任务
   */
  async delete(username: string, id: string): Promise<APIResponse<void>> {
    try {
      logger.debug('[TaskAPI] Deleting agent task:', id);

      const response = await this.api.deleteAgentTask(username, id);

      if (response && response.success) {
        logger.debug('[TaskAPI] Successfully deleted agent task');

        return {
          success: true,
        };
      } else {
        throw new Error(response.error?.message || 'Failed to delete agent task');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      logger.error('[TaskAPI] Error deleting agent task:', errorMessage);

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

// Export单例实例
export const taskApi = new TaskAPI();

