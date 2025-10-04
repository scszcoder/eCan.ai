import { useAppDataStore } from './appDataStore';
import { useAgentStore } from './agentStore';
import { logger } from '../utils/logger';

/**
 * AppDataStoreHandler
 * 统一处理从后端API获取的系统数据，并更新 Zustand store。
 */
export class AppDataStoreHandler {
    /**
     * 更新 store 中的系统数据。
     * 此方法会逐一检查数据对象中的每个字段，并调用对应的 setter 更新 store。
     * @param data - 从 API 返回的 SystemData 对象。
     */
    public static updateStore(data: any): void {
        if (!data) {
            logger.error('AppDataStoreHandler received null or undefined data.');
            return;
        }

        console.debug('AppDataStoreHandler: Updating store with new data.', data);

        const { 
            setTasks, 
            setSkills, 
            setKnowledges, 
            setChats,
            setTools,
            setVehicles,
            setSettings
        } = useAppDataStore.getState();

        // 使用专用的 agentStore 处理 agents 数据
        if (data.agents && Array.isArray(data.agents)) {
            const { setAgents } = useAgentStore.getState();
            setAgents(data.agents);
        }
        if (data.tasks && Array.isArray(data.tasks)) {
            setTasks(data.tasks);
        }
        if (data.skills && Array.isArray(data.skills)) {
            setSkills(data.skills);
        }
        if (data.knowledges && Array.isArray(data.knowledges)) {
            setKnowledges(data.knowledges);
        }
        if (data.chats && Array.isArray(data.chats)) {
            setChats(data.chats);
        }
        if (data.tools && Array.isArray(data.tools)) {
            setTools(data.tools);
        }
        if (data.vehicles && Array.isArray(data.vehicles)) {
            setVehicles(data.vehicles);
        }
        if (data.settings) {
            setSettings(data.settings);
        }
        
        logger.info('AppDataStoreHandler: Store update complete.');
        // 标记全局数据已初始化
        useAppDataStore.getState().setInitialized(true);
        if (typeof window !== 'undefined' && (window as any).onAppDataInitialized) {
            (window as any).onAppDataInitialized();
        }
    }
} 