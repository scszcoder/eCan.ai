/**
 * OrgDataSyncService - 组织DataSyncService
 * 
 * 职责：
 * 1. ListenBackend的 org-agents-update Event
 * 2. 自动Get最新的组织和 Agent Data
 * 3. Update orgStore 和 agentStore
 * 4. 确保无论User在哪个Page，Data都能保持Sync
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
    private retryCount = 0;
    private readonly maxRetries = 3;
    private readonly retryDelayMs = 2000;

    /**
     * InitializeService，Register全局EventListen器
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
     * CleanupService，RemoveEventListen器
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
     * Process org-agents-update Event
     */
    private async handleOrgAgentsUpdate(data: any): Promise<void> {
        logger.info('[OrgDataSyncService] 📥 Received org-agents-update event', data);
        
        this.retryCount = 0;
        await this.fetchWithRetry();
    }

    /**
     * Fetch org data with retry logic for backend initialization delays
     */
    private async fetchWithRetry(): Promise<void> {
        const username = useUserStore.getState().username;
        if (!username) {
            logger.warn('[OrgDataSyncService] ⚠️ No username available, skipping data sync');
            return;
        }

        let companyName = '';
        try {
            companyName = (localStorage.getItem('org_company_filter') || '').trim();
        } catch {
            companyName = '';
        }

        while (this.retryCount < this.maxRetries) {
            try {
                logger.info(`[OrgDataSyncService] 🔄 Fetching org data (attempt ${this.retryCount + 1}/${this.maxRetries})...`);

                const response = await get_ipc_api().getAllOrgAgents(username, companyName);
                
                if (response.success && response.data) {
                    // Update orgStore
                    const orgStore = useOrgStore.getState();
                    orgStore.setAllOrgAgents(response.data);
                    logger.info('[OrgDataSyncService] ✅ orgStore updated');

                    // Extract all agents and update agentStore
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
                    return;  // Success - exit retry loop
                }

                logger.warn(`[OrgDataSyncService] ⚠️ Attempt ${this.retryCount + 1} failed:`, response.error);
            } catch (error) {
                logger.error(`[OrgDataSyncService] ❌ Attempt ${this.retryCount + 1} error:`, error);
            }

            this.retryCount++;
            if (this.retryCount < this.maxRetries) {
                logger.info(`[OrgDataSyncService] ⏳ Retrying in ${this.retryDelayMs}ms...`);
                await new Promise(resolve => setTimeout(resolve, this.retryDelayMs));
            }
        }

        logger.error(`[OrgDataSyncService] ❌ Failed after ${this.maxRetries} attempts`);
    }

    /**
     * Recursive提取树形结构中的All agents
     */
    private extractAllAgents(node: any): any[] {
        let allAgents: any[] = [];

        // AddWhen前节点的 agents
        if (node.agents && Array.isArray(node.agents)) {
            allAgents = allAgents.concat(node.agents);
        }

        // RecursiveProcess子节点
        if (node.children && Array.isArray(node.children)) {
            node.children.forEach((child: any) => {
                allAgents = allAgents.concat(this.extractAllAgents(child));
            });
        }

        return allAgents;
    }

    /**
     * 将Backend agent DataMap为Frontend store 格式
     * Backend已经返回正确的格式（Include card 对象），直接返回
     */
    private mapAgentsForStore(agents: any[]): any[] {
        return agents;
    }

    /**
     * 手动TriggerDataSync（Used forTest或强制Refresh）
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
     * GetServiceStatus
     */
    getStatus(): { initialized: boolean; hasEventHandler: boolean } {
        return {
            initialized: this.isInitialized,
            hasEventHandler: this.eventHandler !== null,
        };
    }
}

// Export单例实例
export const orgDataSyncService = new OrgDataSyncService();
