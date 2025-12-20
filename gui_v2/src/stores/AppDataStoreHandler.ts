import { useAppDataStore } from './appDataStore';
import {
  useAgentStore,
  useTaskStore,
  useSkillStore,
  useVehicleStore,
  useKnowledgeStore,
  useChatStore
} from './index';
import { logger } from '../utils/logger';

/**
 * AppDataStoreHandler
 * 统一Process从BackendAPIGet的SystemData，并Update Zustand store。
 *
 * Note：此类已Deprecated，建议使用 storeSyncManager 进行DataSync
 * @deprecated 使用 storeSyncManager 替代
 */
export class AppDataStoreHandler {
    /**
     * Update store 中的SystemData。
     * 此Method会逐一CheckData对象中的每个Field，并调用对应的 setter Update store。
     * @param data - 从 API 返回的 SystemData 对象。
     * @deprecated 使用 storeSyncManager.syncAll() 替代
     */
    public static updateStore(data: any): void {
        if (!data) {
            logger.error('AppDataStoreHandler received null or undefined data.');
            return;
        }

        console.debug('AppDataStoreHandler: Updating store with new data.', data);
        logger.warn('[AppDataStoreHandler] This class is deprecated. Please use storeSyncManager instead.');

        const { setSettings } = useAppDataStore.getState();

        // 使用专用的 domain stores ProcessData
        if (data.agents && Array.isArray(data.agents)) {
            const { setItems } = useAgentStore.getState();
            setItems(data.agents);
            logger.info('[AppDataStoreHandler] Updated agents in agentStore');
        }
        if (data.tasks && Array.isArray(data.tasks)) {
            const { setItems } = useTaskStore.getState();
            setItems(data.tasks);
            logger.info('[AppDataStoreHandler] Updated tasks in taskStore');
        }
        if (data.skills && Array.isArray(data.skills)) {
            const { setItems } = useSkillStore.getState();
            setItems(data.skills);
            logger.info('[AppDataStoreHandler] Updated skills in skillStore');
        }
        if (data.knowledges && Array.isArray(data.knowledges)) {
            const { setItems } = useKnowledgeStore.getState();
            setItems(data.knowledges);
            logger.info('[AppDataStoreHandler] Updated knowledges in knowledgeStore');
        }
        if (data.chats && Array.isArray(data.chats)) {
            const { setItems } = useChatStore.getState();
            setItems(data.chats);
            logger.info('[AppDataStoreHandler] Updated chats in chatStore');
        }
        if (data.tools && Array.isArray(data.tools)) {
            // toolStore 已Migration，不再通过 AppDataStoreHandler Update
            // 建议使用 storeSyncManager 或直接调用 toolStore.fetchTools()
            logger.warn('[AppDataStoreHandler] Tools update skipped. Use storeSyncManager or toolStore.fetchTools() instead.');
        }
        if (data.vehicles && Array.isArray(data.vehicles)) {
            const { setItems } = useVehicleStore.getState();
            setItems(data.vehicles);
            logger.info('[AppDataStoreHandler] Updated vehicles in vehicleStore');
        }
        if (data.settings) {
            setSettings(data.settings);
            logger.info('[AppDataStoreHandler] Updated settings in appDataStore');
        }

        logger.info('AppDataStoreHandler: Store update complete.');
        // 标记全局Data已Initialize
        useAppDataStore.getState().setInitialized(true);
        if (typeof window !== 'undefined' && (window as any).onAppDataInitialized) {
            (window as any).onAppDataInitialized();
        }
    }
}