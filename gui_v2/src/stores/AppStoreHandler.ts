import { useSystemStore } from './systemStore';
import { Agent } from '../pages/Agents/types';
import { Task } from '../pages/Tasks/types';
import { Skill } from '../pages/Skills/types';
import { Knowledge } from '../pages/Knowledge/types';
import { Chat } from '../pages/Chat/types/chat';
import { Tool } from '../pages/Tools/types';
import { Vehicle } from '../pages/Vehicles/types';
import { Settings } from '../pages/Settings/types';
import { logger } from '../utils/logger';

// 定义从 API 返回的 systemData 的结构
interface SystemData {
    agents?: Agent[];
    tasks?: Task[];
    skills?: Skill[];
    knowledges?: Knowledge[];
    chats?: Chat[];
    tools?: Tool[];
    vehicles?: Vehicle[];
    settings?: Settings;
}

/**
 * AppStoreHandler
 * 统一处理从后端API获取的系统数据，并更新 Zustand store。
 */
export class AppStoreHandler {
    /**
     * 更新 store 中的系统数据。
     * 此方法会逐一检查数据对象中的每个字段，并调用对应的 setter 更新 store。
     * @param data - 从 API 返回的 SystemData 对象。
     */
    public static updateStore(data: SystemData): void {
        if (!data) {
            logger.error('AppStoreHandler received null or undefined data.');
            return;
        }

        console.debug('AppStoreHandler: Updating store with new data.', data);

        const { 
            setAgents, 
            setTasks, 
            setSkills, 
            setKnowledges, 
            setChats,
            setTools,
            setVehicles,
            setSettings
        } = useSystemStore.getState();

        if (data.agents && Array.isArray(data.agents)) {
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
        
        logger.info('AppStoreHandler: Store update complete.');
    }
} 