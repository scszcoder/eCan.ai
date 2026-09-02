import { useUserStore } from '@/stores/userStore';
import { useOrgStore } from '@/stores/orgStore';
import { useAgentStore } from '@/stores/agentStore';
import { get_ipc_api } from '@/services/ipc_api';
import { logger } from '@/utils/logger';
import { extractAllAgents } from './orgTreeUtils';
import { mapOrgAgentToAgent } from './agentMappers';

/**
 * Re-fetch orgs + agents from the backend and populate BOTH stores.
 *
 * Standalone (non-hook) so it can be called from anywhere that changes the
 * agent set outside the normal page fetch: Fast Deploy success, the header
 * refresh button, post-delete convergence. Before this existed, generated
 * agents only appeared after re-login (2026-09-02 customer report) — the
 * panel never refreshed and the refresh button discarded its response.
 */
export async function refreshOrgAgents(usernameArg?: string): Promise<boolean> {
    const username = usernameArg || useUserStore.getState().username;
    if (!username) return false;
    try {
        const response = await get_ipc_api().getAllOrgAgents<any>(username);
        if (response?.success && response.data) {
            useOrgStore.getState().setAllOrgAgents(response.data);
            const allAgents = extractAllAgents(response.data.orgs || []);
            useAgentStore.getState().setAgents(
                allAgents.map((agent: any) =>
                    mapOrgAgentToAgent(agent, agent.org_id || undefined))
            );
            logger.info(`[refreshOrgAgents] refreshed ${allAgents.length} agents`);
            return true;
        }
        logger.warn('[refreshOrgAgents] fetch failed:', response?.error?.message);
        return false;
    } catch (e) {
        logger.error('[refreshOrgAgents] error:', e);
        return false;
    }
}
