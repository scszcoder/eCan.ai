/**
 * IPC 处理器
 * 实现了与 Python 后端通信的请求处理器
 */
import { IPCRequest, IPCResponse } from './types';
import { updateDashboard } from '../../pages/Dashboard/Dashboard';
import { updateSkillsGUI } from '../../pages/Skills/Skills';
import { updateTasksGUI } from '../../pages/Tasks/Tasks';
import { updateAgentsGUI } from '../../pages/Agents/types';
import { updateKnowledgeGUI } from '../../pages/Knowledge/types';
import { updateSettingsGUI } from '../../pages/Settings/Settings';
import { logger } from '../../utils/logger';
import { useChatStore } from '../../pages/Chat/hooks/useChatStore';
import { Message } from '../../pages/Chat/types/chat';

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
                if (typeof updatedAgents[field] !== 'number') {
                    throw new Error(`Invalid field type: ${field} must be a number`);
                }
            }

            // 更新代理数据
            updateAgentsGUI(updatedAgents);
            return { refreshed: true };
        } catch (error) {
            logger.error('Error in update_agents handler:', error);
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
            updateSkillsGUI(stats);
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
            updateTasksGUI(stats);
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
            updateSettingsGUI(stats);
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

            // 验证参数 - 期望接收知识库数据数组
            if (!Array.isArray(params)) {
                throw new Error('Invalid parameters: expected Knowledge[] array');
            }

            // 验证每个知识库项目的结构
            for (const knowledge of params) {
                if (typeof knowledge !== 'object' || !knowledge) {
                    throw new Error('Invalid knowledge item: must be an object');
                }
                
                const requiredFields = ['id', 'name', 'type', 'status', 'battery', 'location', 'lastMaintenance', 'totalDistance'];
                for (const field of requiredFields) {
                    if (!(field in knowledge)) {
                        throw new Error(`Invalid knowledge item: missing required field '${field}'`);
                    }
                }
            }

            // 更新知识库数据
            updateKnowledgeGUI(params);
            return { refreshed: true };
        } catch (error) {
            logger.error('Error in update_knowledge handler:', error);
            throw error;
        }
    }

    async updateChats(request: IPCRequest): Promise<{ success: boolean }> {
        try {
            const { params } = request;
            console.log('Received request with params:', params);
            // Validate params
            if (!params || typeof params !== 'object' || !('chats' in params)) {
                throw new Error('Invalid parameters: expected { chats: IncomingMessage[] }');
            }

            const { chats } = params;
            console.log('Received request with chats:', chats);

            if (!Array.isArray(chats)) {
                throw new Error('Invalid parameters: "chats" must be an array');
            }

            // Process each incoming message
            for (const incomingMsg of chats) {
                try {
                    // Convert to the Message type expected by the UI
                    const message: Message = {
                        id: incomingMsg.id,
                        session_id: incomingMsg.session_id,
                        content: incomingMsg.content,
                        sender: incomingMsg.sender,
                        tx_timestamp: incomingMsg.tx_time,
                        rx_timestamp: new Date().toISOString(), // Set received time to now
                        read_timestamp: null,
                        status: 'delivered', // or 'sent' depending on your flow
                        is_edited: false,
                        is_retracted: false
                    };

                    // Check if we need to create a new chat or update existing one
                    const chatInfo = {
                        id: incomingMsg.chat_id,
                        name: `Chat ${incomingMsg.chat_id}`, // You might want to fetch the actual name
                        type: incomingMsg.is_group ? 'group' : 'agent' as const,
                        status: 'online' as const,
                        last_message: message.content,
                        last_message_time: new Date().toLocaleTimeString(),
                        last_session_time: new Date(message.tx_timestamp).toLocaleDateString(),
                        unread_count: 0, // Will be updated by the UI logic
                        is_group: incomingMsg.is_group,
                        members: [message.sender, ...incomingMsg.recipients].filter(Boolean),
                        messages: [message] // The Chat component will merge messages
                    };
                    console.log("chatInfo:", chatInfo);
                    console.log("message:", message);
                    // Update the UI using the new method
                    useChatStore.getState().updateChatsGUI({
                        chat: chatInfo,
                        message
                    });
                } catch (error) {
                    console.error('Error processing chat message:', error, incomingMsg);
                    // Continue processing other messages even if one fails
                }
            }

            return { success: true };
        } catch (error) {
            console.error('Error in updateChats handler:', error);
            return { success: false, error: error.message };
        }
    }


    async updateAll(request: IPCRequest): Promise<{ success: boolean }> {
        try {
            const { params } = request;
            console.log('Received request with params:', params);
            // Validate params
            if (!params || typeof params !== 'object' || !('chats' in params)) {
                throw new Error('Invalid parameters: expected { chats: IncomingMessage[] }');
            }

            const { chats } = params;
            console.log('Received request with chats:', chats);

            if (!Array.isArray(chats)) {
                throw new Error('Invalid parameters: "chats" must be an array');
            }

            // Process each incoming message
            for (const incomingMsg of chats) {
                try {
                    // Convert to the Message type expected by the UI
                    const message: Message = {
                        id: incomingMsg.id,
                        session_id: incomingMsg.session_id,
                        content: incomingMsg.content,
                        sender: incomingMsg.sender,
                        tx_timestamp: incomingMsg.tx_time,
                        rx_timestamp: new Date().toISOString(), // Set received time to now
                        read_timestamp: null,
                        status: 'delivered', // or 'sent' depending on your flow
                        is_edited: false,
                        is_retracted: false
                    };

                    // Check if we need to create a new chat or update existing one
                    const chatInfo = {
                        id: incomingMsg.chat_id,
                        name: `Chat ${incomingMsg.chat_id}`, // You might want to fetch the actual name
                        type: incomingMsg.is_group ? 'group' : 'agent' as const,
                        status: 'online' as const,
                        last_message: message.content,
                        last_message_time: new Date().toLocaleTimeString(),
                        last_session_time: new Date(message.tx_timestamp).toLocaleDateString(),
                        unread_count: 0, // Will be updated by the UI logic
                        is_group: incomingMsg.is_group,
                        members: [message.sender, ...incomingMsg.recipients].filter(Boolean),
                        messages: [message] // The Chat component will merge messages
                    };
                    console.log("chatInfo:", chatInfo);
                    console.log("message:", message);
                    // Update the UI using the new method
                    useChatStore.getState().updateChatsGUI({
                        chat: chatInfo,
                        message
                    });
                } catch (error) {
                    console.error('Error processing chat message:', error, incomingMsg);
                    // Continue processing other messages even if one fails
                }
            }

            return { success: true };
        } catch (error) {
            console.error('Error in updateChats handler:', error);
            return { success: false, error: error.message };
        }
    }
}

// 创建处理器实例
const ipcHandlers = new IPCHandlers();

// 导出处理器映射
export const getHandlers = () => ipcHandlers.getHandlers();