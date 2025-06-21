/**
 * IPC 处理器
 * 实现了与 Python 后端通信的请求处理器
 */
import { IPCRequest } from './types';
import { useAppDataStore } from '../../stores/appDataStore';
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
        this.registerHandler('get_config', this.getConfig);
        this.registerHandler('set_config', this.setConfig);
        this.registerHandler('notify_event', this.notifyEvent);
        this.registerHandler('update_agents', this.updateAgents);
        this.registerHandler('update_skills', this.updateSkills);
        this.registerHandler('update_tasks', this.updateTasks);
        this.registerHandler('update_knowledge', this.updateKnowledges);
        this.registerHandler('update_settings', this.updateSettings);
        this.registerHandler('update_chats', this.updateChats);
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
        logger.info('Notify event received:', { event, data });
        return { event, processed: true };
    }

    async updateAgents(request: IPCRequest): Promise<unknown> {
        logger.info('Received update_agents request:', request.params);
        useAppDataStore.getState().setAgents(request.params as any);
        return { refreshed: true };
    }

    async updateSkills(request: IPCRequest): Promise<unknown> {
        logger.info('Received update_skills request:', request.params);
        useAppDataStore.getState().setSkills(request.params as any);
        return { refreshed: true };
    }

    async updateTasks(request: IPCRequest): Promise<unknown> {
        logger.info('Received update_tasks request:', request.params);
        useAppDataStore.getState().setTasks(request.params as any);
        return { refreshed: true };
    }

    async updateSettings(request: IPCRequest): Promise<unknown> {
        logger.info('Received update_settings request:', request.params);
        return { refreshed: true };
    }

    async updateKnowledges(request: IPCRequest): Promise<unknown> {
        logger.info('Received update_knowledges request:', request.params);
        useAppDataStore.getState().setKnowledges(request.params as any);
        return { refreshed: true };
    }

    async updateChats(request: IPCRequest): Promise<{ success: boolean }> {
        logger.info('Received update_chats request:', request.params);
        return { success: true };
    }

    async updateAll(request: IPCRequest): Promise<{ success: boolean }> {
        logger.info('Received update_all request:', request.params);
        return { success: true };
    }
}

export const getHandlers = () => {
    const ipcHandlers = new IPCHandlers();
    return ipcHandlers.getHandlers();
};