/**
 * OrgDataSyncService - 组织数据同步服务
 * 
 * 职责：
 * 1. 监听后端的 org-agents-update 事件
 * 2. 自动获取最新的组织和 Agent 数据
 * 3. 更新 orgStore 和 agentStore
 * 4. 确保无论用户在哪个页面，数据都能保持同步
 */

import { eventBus } from '../utils/eventBus';
import { logger } from '../utils/logger';
import { get_ipc_api } from './ipc_api';
import { useUserStore } from '../stores/userStore';
import { useOrgStore } from '../stores/orgStore';
import { useAgentStore } from '../stores/agentStore';

class OrgDataSyncService {
    private isInitialized = false;
    private eventHandler: ((data: any) => Promise<void>) | null = null;

    /**
     * 初始化服务，注册全局事件监听器
     */
    initialize(): void {
        if (this.isInitialized) {
            logger.warn('[OrgDataSyncService] Service already initialized');
            return;
        }

        this.eventHandler = this.handleOrgAgentsUpdate.bind(this);
        eventBus.on('org-agents-update', this.eventHandler);
        
        this.isInitialized = true;
        logger.info('[OrgDataSyncService] ✅ Service initialized, global event listener registered');
    }

    /**
     * 清理服务，移除事件监听器
     */
    cleanup(): void {
        if (!this.isInitialized || !this.eventHandler) {
            return;
        }

        eventBus.off('org-agents-update', this.eventHandler);
        this.eventHandler = null;
        this.isInitialized = false;
        
        logger.info('[OrgDataSyncService] ✅ Service cleaned up, event listener removed');
    }

    /**
     * 处理 org-agents-update 事件
     */
    private async handleOrgAgentsUpdate(data: any): Promise<void> {
        logger.info('[OrgDataSyncService] 📥 Received org-agents-update event', data);
        
        try {
            // 获取当前用户
            const username = useUserStore.getState().username;
            if (!username) {
                logger.warn('[OrgDataSyncService] ⚠️ No username available, skipping data sync');
                return;
            }

            logger.info(`[OrgDataSyncService] 🔄 Fetching latest org data for user: ${username}`);

            // 调用 API 获取最新数据
            const response = await get_ipc_api().getAllOrgAgents(username);
            
            if (!response.success || !response.data) {
                logger.error('[OrgDataSyncService] ❌ Failed to fetch org data:', response.error);
                return;
            }

            // 更新 orgStore
            const orgStore = useOrgStore.getState();
            orgStore.setAllOrgAgents(response.data);
            logger.info('[OrgDataSyncService] ✅ orgStore updated');

            // 提取所有 agents 并更新 agentStore
            const allAgents = this.extractAllAgents(response.data.orgs);
            
            if (allAgents.length > 0) {
                const mappedAgents = this.mapAgentsForStore(allAgents);
                const agentStore = useAgentStore.getState();
                agentStore.setAgents(mappedAgents);
                logger.info(`[OrgDataSyncService] ✅ agentStore updated with ${allAgents.length} agents`);
            } else {
                logger.info('[OrgDataSyncService] ℹ️ No agents found in the updated data');
            }

            logger.info('[OrgDataSyncService] 🎉 Data sync completed successfully');
        } catch (error) {
            logger.error('[OrgDataSyncService] ❌ Error during data sync:', error);
        }
    }

    /**
     * 递归提取树形结构中的所有 agents
     */
    private extractAllAgents(node: any): any[] {
        let allAgents: any[] = [];

        // 添加当前节点的 agents
        if (node.agents && Array.isArray(node.agents)) {
            allAgents = allAgents.concat(node.agents);
        }

        // 递归处理子节点
        if (node.children && Array.isArray(node.children)) {
            node.children.forEach((child: any) => {
                allAgents = allAgents.concat(this.extractAllAgents(child));
            });
        }

        return allAgents;
    }

    /**
     * 将后端 agent 数据映射为前端 store 格式
     */
    private mapAgentsForStore(agents: any[]): any[] {
        return agents.map((agent: any) => ({
            card: {
                id: agent.id,
                name: agent.name,
                description: agent.description || '',
                url: '',
                provider: null,
                version: '1.0.0',
                documentationUrl: null,
                capabilities: {
                    streaming: false,
                    pushNotifications: false,
                    stateTransitionHistory: false,
                },
                authentication: null,
                defaultInputModes: [],
                defaultOutputModes: [],
            },
            supervisors: [],
            subordinates: [],
            peers: [],
            rank: 'member' as const,
            organizations: agent.org_id ? [String(agent.org_id)] : [],
            job_description: agent.description || '',
            personalities: [],
        }));
    }

    /**
     * 手动触发数据同步（用于测试或强制刷新）
     */
    async triggerSync(): Promise<void> {
        if (!this.isInitialized) {
            logger.warn('[OrgDataSyncService] Service not initialized');
            return;
        }

        logger.info('[OrgDataSyncService] 🔄 Manual sync triggered');
        await this.handleOrgAgentsUpdate({ source: 'manual_trigger' });
    }

    /**
     * 获取服务状态
     */
    getStatus(): { initialized: boolean; hasEventHandler: boolean } {
        return {
            initialized: this.isInitialized,
            hasEventHandler: this.eventHandler !== null,
        };
    }
}

// 导出单例实例
export const orgDataSyncService = new OrgDataSyncService();
