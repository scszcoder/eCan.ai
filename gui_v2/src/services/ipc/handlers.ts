/**
 * IPC 处理器
 * 实现了与 Python 后端通信的请求处理器
 */
import { IPCRequest, IPCResponse } from './types';
import { updateDashboard } from '../../pages/Dashboard';
import { logger } from '../../utils/logger';

// 处理器类型定义
type Handler = (request: IPCRequest) => Promise<unknown>;
type HandlerMap = Record<string, Handler>;

// 配置存储
const config = new Map<string, unknown>();

// 参数验证函数
function validateParams(request: IPCRequest, requiredParams: string[]): void {
    const params = request.params as Record<string, unknown> | undefined;
    if (!params) {
        throw new Error(`Missing parameters: ${requiredParams.join(', ')}`);
    }

    const missingParams = requiredParams.filter(param => !(param in params));
    if (missingParams.length > 0) {
        throw new Error(`Missing required parameters: ${missingParams.join(', ')}`);
    }
}

// 处理器类
export class IPCHandlers {
    private handlers: HandlerMap = {};

    constructor() {
        // 注册所有处理器
        this.registerHandler('get_config', this.getConfig);
        this.registerHandler('set_config', this.setConfig);
        this.registerHandler('notify_event', this.notifyEvent);
        this.registerHandler('refresh_dashboard', this.refreshDashboard);
        this.registerHandler('update_agents', this.updateAgents);
        this.registerHandler('update_skills', this.updateSkills);
        this.registerHandler('update_tasks', this.updateTasks);
        this.registerHandler('update_knowledges', this.updateKnowledges);
        this.registerHandler('update_settings', this.updateSettings);
    }

    private registerHandler(method: string, handler: Handler): void {
        this.handlers[method] = handler;
    }

    getHandlers(): HandlerMap {
        return this.handlers;
    }

    async getConfig(request: IPCRequest): Promise<unknown> {
        validateParams(request, ['key']);
        const { key } = request.params as { key: string };
        if (!config.has(key)) {
            throw new Error(`Config not found for key: ${key}`);
        }
        return config.get(key);
    }

    async setConfig(request: IPCRequest): Promise<unknown> {
        validateParams(request, ['key', 'value']);
        const { key, value } = request.params as { key: string; value: unknown };
        config.set(key, value);
        return { success: true };
    }

    async notifyEvent(request: IPCRequest): Promise<unknown> {
        validateParams(request, ['event']);
        const { event, data } = request.params as { event: string; data?: unknown };
        // TODO: 实现事件处理逻辑
        return { event, processed: true };
    }

    async refreshDashboard(request: IPCRequest): Promise<unknown> {
        try {
            const { params } = request;
            if (!params || typeof params !== 'object') {
                throw new Error('Invalid parameters');
            }

            // 验证参数
            const requiredFields = ['overview', 'statistics', 'recentActivities', 'quickActions'] as const;
            const stats = params as { [K in typeof requiredFields[number]]: number };
            for (const field of requiredFields) {
                if (typeof stats[field] !== 'number') {
                    throw new Error(`Invalid field type: ${field} must be a number`);
                }
            }

            // 更新仪表盘数据
            updateDashboard(stats);
            return { refreshed: true };
        } catch (error) {
            logger.error('Error in refresh_dashboard handler:', error);
            throw error;
        }
    }


    async updateAgents(request: IPCRequest): Promise<unknown> {
        try {
            const { params } = request;
            if (!params || typeof params !== 'object') {
                throw new Error('Invalid parameters');
            }

            // 验证参数
            const requiredFields = ['overview', 'statistics', 'recentActivities', 'quickActions'] as const;
            const updatedAgents = params as { [K in typeof requiredFields[number]]: number };
            for (const field of requiredFields) {
                if (typeof stats[field] !== 'number') {
                    throw new Error(`Invalid field type: ${field} must be a number`);
                }
            }

            // 更新仪表盘数据
            updateAgentsGUI(updatedAgents);
            return { refreshed: true };
        } catch (error) {
            logger.error('Error in refresh_dashboard handler:', error);
            throw error;
        }
    }


    async updateSkills(request: IPCRequest): Promise<unknown> {
        try {
            const { params } = request;
            if (!params || typeof params !== 'object') {
                throw new Error('Invalid parameters');
            }

            // 验证参数
            const requiredFields = ['overview', 'statistics', 'recentActivities', 'quickActions'] as const;
            const stats = params as { [K in typeof requiredFields[number]]: number };
            for (const field of requiredFields) {
                if (typeof stats[field] !== 'number') {
                    throw new Error(`Invalid field type: ${field} must be a number`);
                }
            }

            // 更新仪表盘数据
            updateDashboard(stats);
            return { refreshed: true };
        } catch (error) {
            logger.error('Error in refresh_dashboard handler:', error);
            throw error;
        }
    }


    async updateTasks(request: IPCRequest): Promise<unknown> {
        try {
            const { params } = request;
            if (!params || typeof params !== 'object') {
                throw new Error('Invalid parameters');
            }

            // 验证参数
            const requiredFields = ['overview', 'statistics', 'recentActivities', 'quickActions'] as const;
            const stats = params as { [K in typeof requiredFields[number]]: number };
            for (const field of requiredFields) {
                if (typeof stats[field] !== 'number') {
                    throw new Error(`Invalid field type: ${field} must be a number`);
                }
            }

            // 更新仪表盘数据
            updateDashboard(stats);
            return { refreshed: true };
        } catch (error) {
            logger.error('Error in refresh_dashboard handler:', error);
            throw error;
        }
    }


    async updateSettings(request: IPCRequest): Promise<unknown> {
        try {
            const { params } = request;
            if (!params || typeof params !== 'object') {
                throw new Error('Invalid parameters');
            }

            // 验证参数
            const requiredFields = ['overview', 'statistics', 'recentActivities', 'quickActions'] as const;
            const stats = params as { [K in typeof requiredFields[number]]: number };
            for (const field of requiredFields) {
                if (typeof stats[field] !== 'number') {
                    throw new Error(`Invalid field type: ${field} must be a number`);
                }
            }

            // 更新仪表盘数据
            updateDashboard(stats);
            return { refreshed: true };
        } catch (error) {
            logger.error('Error in refresh_dashboard handler:', error);
            throw error;
        }
    }


    async updateKnowledges(request: IPCRequest): Promise<unknown> {
        try {
            const { params } = request;
            if (!params || typeof params !== 'object') {
                throw new Error('Invalid parameters');
            }

            // 验证参数
            const requiredFields = ['overview', 'statistics', 'recentActivities', 'quickActions'] as const;
            const stats = params as { [K in typeof requiredFields[number]]: number };
            for (const field of requiredFields) {
                if (typeof stats[field] !== 'number') {
                    throw new Error(`Invalid field type: ${field} must be a number`);
                }
            }

            // 更新仪表盘数据
            updateDashboard(stats);
            return { refreshed: true };
        } catch (error) {
            logger.error('Error in refresh_dashboard handler:', error);
            throw error;
        }
    }



}

// 创建处理器实例
const ipcHandlers = new IPCHandlers();

// 导出处理器映射
export const getHandlers = () => ipcHandlers.getHandlers();