/**
 * IPC 处理器
 * 实现了与 Python 后端通信的请求处理器
 */
import { IPCRequest } from './types';
import { useAppDataStore } from '../../stores/appDataStore';
import { useAgentStore } from '../../stores/agentStore';
import { eventBus } from '@/utils/eventBus';
import { useRunningNodeStore } from '@/modules/skill-editor/stores/running-node-store';
import { useAvatarSceneStore } from '../../stores/avatarSceneStore';
import { AvatarEventType } from '../avatarEventType';
import { logger } from '@/utils/logger';
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
        this.registerHandler('update_org_agents', this.updateOrgAgents);
        this.registerHandler('get_config', this.getConfig);
        this.registerHandler('set_config', this.setConfig);
        this.registerHandler('notify_event', this.notifyEvent);
        this.registerHandler('update_agents', this.updateAgents);
        this.registerHandler('update_agents_scenes', this.updateAgentsScenes);
        this.registerHandler('update_skills', this.updateSkills);
        this.registerHandler('update_tasks', this.updateTasks);
        this.registerHandler('update_knowledge', this.updateKnowledges);
        this.registerHandler('update_settings', this.updateSettings);
        this.registerHandler('update_chats', this.updateChats);
        // this.registerHandler('update_tools', this.updateTools);
        // this.registerHandler('update_vehicles', this.updateVehicles);
        this.registerHandler('push_chat_message', this.pushChatMessage);
        this.registerHandler('update_skill_run_stat', this.updateSkillRunStat);
        this.registerHandler('update_tasks_stat', this.updateTasksStat);
        this.registerHandler('push_chat_notification', this.pushChatNotification);
        this.registerHandler('update_all', this.updateAll);
        this.registerHandler('update_screens', this.updateScreens);
        this.registerHandler('trigger_scene_event', this.triggerSceneEvent);
    }

    private registerHandler(method: string, handler: Handler): void {
        this.handlers[method] = handler;
    }

    getHandlers(): HandlerMap {
        return this.handlers;
    }

    async updateOrgAgents(request: IPCRequest): Promise<unknown> {
        logger.info('Received update_org_agents request:', request.params);
        
        // 简单发送事件，让 agents 组件自己决定如何处理
        eventBus.emit('org-agents-update', {
            timestamp: Date.now(),
            source: 'backend_notification',
            data: request.params
        });
        
        return { 
            success: true,
            timestamp: Date.now()
        };
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
        const agents = request.params as any;
        
        // 只更新专用的 agentStore，移除重复更新
        useAgentStore.getState().setAgents(agents);
        
        logger.info('Updated agentStore with agents:', agents?.length || 0);
        return { refreshed: true };
    }

    async updateAgentsScenes(request: IPCRequest): Promise<unknown> {
        logger.info('Received update_agents_scenes request:', request.params);
        const agents = request.params as any;
        
        // 只更新专用的 agentStore，移除重复更新
        useAgentStore.getState().setAgents(agents);
        
        logger.info('Updated agentStore with agents scenes:', agents?.length || 0);
        return { refreshed: true };
    }

    async updateSkills(request: IPCRequest): Promise<unknown> {
        logger.info('Received update_skills request:', request.params);
        const skills = request.params as any;
        
        // 使用专用的 skillStore（如果存在）
        // 暂时保留 appDataStore 直到所有组件迁移完成
        useAppDataStore.getState().setSkills(skills);
        
        logger.info('Updated skills:', skills?.length || 0);
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

    async pushChatMessage(request: IPCRequest): Promise<{ success: boolean }> {
        // logger.info('Received pushChatMessage request:', request.params);
        eventBus.emit('chat:newMessage', request.params);
        return { success: true };
    }

    async pushChatNotification(request: IPCRequest): Promise<{ success: boolean }> {
        let { chatId, content, isRead, timestamp, uid } = request.params as { chatId: string, content: any, isRead: boolean, timestamp: string, uid: string };
        if (!chatId || !content) {
            throw new Error('pushChatNotification: chatId and notification are required');
        }
        // 自动解析字符串 JSON
        if (typeof content === 'string') {
            try {
                content = JSON.parse(content);
            } catch (e) {
                throw new Error('pushChatNotification: content is string but not valid JSON');
            }
        }
        eventBus.emit('chat:newNotification', { chatId, content, isRead, timestamp, uid });
        return { success: true };
    }


    async updateSkillRunStat(request: IPCRequest): Promise<{ success: boolean }> {
        // logger.info('Received updateSkillRunStat request:', request.params);
        const { current_node, status } = request.params as { current_node?: string, status?: string };

        // Update the running node if the backend provides a specific node ID.
        if (typeof current_node === 'string' && current_node.length > 0) {
            useRunningNodeStore.getState().setRunningNodeId(current_node);
        }

        // Clear the running node if the skill has completed or failed.
        if (status === 'completed' || status === 'failed') {
            useRunningNodeStore.getState().setRunningNodeId(null);
        }

        eventBus.emit('chat:latestSkillRunStat', request.params);
        return { success: true };
    }

    async updateTasksStat(request: IPCRequest): Promise<{ success: boolean }> {
        // logger.info('Received updateTasksStat request:', request.params);
        eventBus.emit('chat:newMessage', request.params);
        return { success: true };
    }

    async updateScreens(request: IPCRequest): Promise<{ success: boolean }> {
        logger.info('Received update_screens request:', request.params);
        
        try {
            const screensData = request.params as any;
            
            // Update the avatar scene store with the new screens data
            if (screensData && screensData.agents) {
                const sceneStore = useAvatarSceneStore.getState();
                
                // Process each agent's scenes
                Object.entries(screensData.agents).forEach(([agentId, agentData]: [string, any]) => {
                    if (agentData && agentData.scenes) {
                        sceneStore.setAgentScenes(agentId, agentData.scenes);
                    }
                });
                
                logger.info(`Updated screens for ${Object.keys(screensData.agents).length} agents`);
            }
            
            return { success: true };
        } catch (error) {
            logger.error('Error updating screens:', error);
            throw new Error(`Failed to update screens: ${error instanceof Error ? error.message : 'Unknown error'}`);
        }
    }

    async triggerSceneEvent(request: IPCRequest): Promise<{ success: boolean }> {
        logger.info('Received trigger_scene_event request:', request.params);
        
        try {
            validateParams(request, ['agentId', 'eventType']);
            const { agentId, eventType, eventData } = request.params as {
                agentId: string;
                eventType: string;
                eventData?: any;
            };
            
            // Get the avatar event manager instance and trigger the event
            const eventManager = AvatarEventManager.getInstance();
            eventManager.emitEvent(agentId, eventType, eventData || {});
            
            logger.info(`Triggered scene event '${eventType}' for agent '${agentId}'`);
            return { success: true };
        } catch (error) {
            logger.error('Error triggering scene event:', error);
            throw new Error(`Failed to trigger scene event: ${error instanceof Error ? error.message : 'Unknown error'}`);
        }
    }

}

export const getHandlers = () => {
    const ipcHandlers = new IPCHandlers();
    return ipcHandlers.getHandlers();
};