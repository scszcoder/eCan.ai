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
import { userStorageManager } from './storage/UserStorageManager';
import { useAgentStore } from '../stores/agentStore';

class OrgDataSyncService {
    private isInitialized = false;
    private eventHandler: ((data: any) => Promise<void>) | null = null;
    private retryCount = 0;
    private readonly maxRetries = 5;
    private readonly retryDelayMs = 1500;
    private isSyncing = false;

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
        
        // Listen for agent status updates from backend
        eventBus.on('agents-status-update', this.handleAgentsStatusUpdate.bind(this));
        
        // Listen for home agents updates from backend
        eventBus.on('home-agents-update', this.handleHomeAgentsUpdate.bind(this));
        
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
        eventBus.off('agents-status-update', this.handleAgentsStatusUpdate.bind(this));
        eventBus.off('home-agents-update', this.handleHomeAgentsUpdate.bind(this));
        this.eventHandler = null;
        this.isInitialized = false;
        
        logger.info('[OrgDataSyncService] ✅ Service cleaned up, event listener removed');
    }

    /**
     * Process org-agents-update Event
     *
     * WebSocket push from backend is itself the "system ready" signal —
     * the backend only emits update_org_agents after `_notify_initialization_complete`
     * runs (gui/MainGUI.py:1297). Trusting it removes the 10s waitForSystemReady
     * blocking that delayed login by ~40s in the Aug-20 trace.
     */
    private async handleOrgAgentsUpdate(data: any): Promise<void> {
        logger.info('[OrgDataSyncService] 📥 Received org-agents-update event', data);

        this.retryCount = 0;
        // No waitForSystemReady here — the WebSocket push implies the backend
        // IPC handlers and MainWindow are ready (see MainGUI._notify_initialization_complete).
        await this.fetchAllOrgAgents();
    }

    /**
     * Wait for system to be fully ready before fetching data.
     *
     * Two callers, two timeout regimes:
     * - Proactive path (component mount): default 3s, fixed-interval poll.
     * - SYSTEM_NOT_READY retry path: explicit 60s with exponential backoff
     *   so we retry the moment `fully_ready` flips, not on a fixed clock.
     */
    private async waitForSystemReady(
        timeoutMs: number = 3000,
        useBackoff: boolean = false
    ): Promise<boolean> {
        const startTime = Date.now();
        let currentInterval = 500;
        const minInterval = 500;
        const maxInterval = 4000;

        while (Date.now() - startTime < timeoutMs) {
            try {
                const api = get_ipc_api();
                if (!api) {
                    await new Promise(resolve => setTimeout(resolve, currentInterval));
                    continue;
                }

                const response = await api.getInitializationProgress();
                if (response?.success && response.data) {
                    const progress = response.data;
                    if (progress.sync_init_complete || progress.fully_ready) {
                        logger.info('[OrgDataSyncService] ✅ System is ready for data sync', progress);
                        return true;
                    }
                    logger.debug('[OrgDataSyncService] ⏳ Waiting for system to be ready...', progress);
                }
            } catch (error) {
                logger.debug('[OrgDataSyncService] Error checking system readiness:', error);
            }

            if (useBackoff) {
                currentInterval = Math.min(currentInterval * 2, maxInterval);
            }
            await new Promise(resolve => setTimeout(resolve, Math.min(currentInterval, maxInterval)));
            // Reset for next iteration's first step
            if (useBackoff && currentInterval > maxInterval) {
                currentInterval = minInterval;
            }
        }

        logger.warn('[OrgDataSyncService] ⚠️ System ready timeout, proceeding anyway');
        return false;
    }

    /**
     * Fetch org data with retry logic for backend initialization delays.
     * Used by WebSocket-driven path (no waitForSystemReady).
     */
    private async fetchAllOrgAgents(): Promise<void> {
        if (this.isSyncing) {
            logger.debug('[OrgDataSyncService] ⏳ Sync already in progress, skipping');
            return;
        }
        this.isSyncing = true;

        try {
            const username = useUserStore.getState().username;
            if (!username) {
                logger.warn('[OrgDataSyncService] ⚠️ No username available, skipping data sync');
                return;
            }

            // Fast-exit when no token is present: the backend will return
            // TOKEN_REQUIRED, api-router will silently redirect to /login,
            // and there's nothing for us to sync. Retrying here only delays
            // the redirect and accumulates error noise.
            if (!userStorageManager.getToken()) {
                logger.warn(
                    '[OrgDataSyncService] ⚠️ No auth token available, skipping data sync ' +
                    '(LoginCN autologin will install a token on success)'
                );
                return;
            }

            let companyName = '';
            try {
                companyName = (localStorage.getItem('org_company_filter') || '').trim();
            } catch {
                companyName = '';
            }

            while (this.retryCount < this.maxRetries) {
                // Re-check token at the top of each retry: if it disappeared
                // mid-loop (e.g. another tab called removeToken()), bail out
                // instead of firing 5 doomed requests.
                if (!userStorageManager.getToken()) {
                    logger.warn(
                        '[OrgDataSyncService] ⚠️ Token cleared during retry loop, aborting'
                    );
                    return;
                }
                try {
                    logger.info(`[OrgDataSyncService] 🔄 Fetching org data (attempt ${this.retryCount + 1}/${this.maxRetries})...`);

                    const response = await get_ipc_api().getAllOrgAgents(username, companyName);

                    if (response?.success && response.data) {
                        const orgStore = useOrgStore.getState();
                        orgStore.setAllOrgAgents(response.data);
                        logger.info('[OrgDataSyncService] ✅ orgStore updated');

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
                        return;
                    }

                    const errorCode = (response as any)?.error?.code;
                    if (errorCode === 'SYSTEM_NOT_READY') {
                        logger.warn(`[OrgDataSyncService] ⚠️ System not ready (attempt ${this.retryCount + 1}/${this.maxRetries}), waiting for fully_ready...`);
                        this.retryCount++;
                        // Give up early if we've burned through the retry budget.
                        if (this.retryCount >= this.maxRetries) {
                            logger.error(
                                `[OrgDataSyncService] ❌ Backend never became ready after ${this.maxRetries} attempts`
                            );
                            break;
                        }
                        // Poll get_initialization_progress for fully_ready instead of
                        // a blind sleep. Backend is currently still building
                        // MainWindow (DB / agent build / lightrag) — sleep-then-
                        // retry just adds latency on top. Watching fully_ready lets
                        // us retry the moment the system flips to ready.
                        const ready = await this.waitForSystemReady(60000, true);
                        if (ready) {
                            // Loop back to the top — don't increment retryCount again
                            // so we don't double-charge against the budget.
                            this.retryCount--;
                            continue;
                        }
                        continue;
                    }

                    logger.warn(`[OrgDataSyncService] ⚠️ Attempt ${this.retryCount + 1} failed:`, response?.error);
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
        } finally {
            this.isSyncing = false;
        }
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

    /**
     * Handle agents-status-update event from backend
     */
    private async handleAgentsStatusUpdate(data: any): Promise<void> {
        logger.info('[OrgDataSyncService] 📥 Received agents-status-update event', data);
        // Trigger data sync to refresh agent status
        await this.handleOrgAgentsUpdate({ source: 'agents-status-update', ...data });
    }

    /**
     * Handle home-agents-update event from backend
     */
    private async handleHomeAgentsUpdate(data: any): Promise<void> {
        logger.info('[OrgDataSyncService] 📥 Received home-agents-update event', data);
        // Trigger data sync to refresh home agents
        await this.handleOrgAgentsUpdate({ source: 'home-agents-update', ...data });
    }
}

// Export单例实例
export const orgDataSyncService = new OrgDataSyncService();
