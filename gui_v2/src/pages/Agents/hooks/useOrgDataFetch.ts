import { useEffect, useCallback } from 'react';
import { useUserStore } from '@/stores/userStore';
import { useOrgStore } from '@/stores/orgStore';
import { useAgentStore } from '@/stores/agentStore';
import { logger } from '@/utils/logger';
import { get_ipc_api } from '@/services/ipc_api';
import { GetAllOrgAgentsResponse } from '../../Orgs/types';
import { extractAllAgents } from '../utils/orgTreeUtils';
import { mapOrgAgentToAgent } from '../utils/agentMappers';

/**
 * 组织DataGet的Custom Hook
 * 负责从BackendGet组织和 Agent Data
 */
export function useOrgDataFetch() {
  const username = useUserStore((state) => state.username);
  const {
    setAllOrgAgents,
    setLoading,
    setError,
    shouldFetchData,
  } = useOrgStore();
  const setAgents = useAgentStore((state) => state.setAgents);

  // Get组织结构Data
  const fetchOrgStructure = useCallback(async () => {
    if (!username || !shouldFetchData()) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      logger.info('[OrgNavigator] Fetching organization structure...');
      const response = await get_ipc_api().getAllOrgAgents<GetAllOrgAgentsResponse>(username);

      if (response.success && response.data) {
        setAllOrgAgents(response.data);

        // 提取All Agent 并Save到 agentStore
        const allAgents = extractAllAgents(response.data.orgs);

        if (allAgents.length > 0) {
          setAgents(
            allAgents.map((agent) =>
              mapOrgAgentToAgent(agent, agent.org_id || undefined)
            )
          );
          logger.info(`[OrgNavigator] Extracted and saved ${allAgents.length} agents to agentStore`);
        } else {
          logger.warn('[OrgNavigator] No agents found in organization structure');
        }
      } else {
        const errorMessage = response.error?.message || 'Failed to fetch organization structure';
        setError(errorMessage);
        logger.error('[OrgNavigator] Failed to fetch organization structure:', errorMessage);
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error occurred';
      setError(errorMessage);
      logger.error('[OrgNavigator] Error fetching organization structure:', errorMessage);
    } finally {
      setLoading(false);
    }
  }, [username, shouldFetchData, setLoading, setError, setAllOrgAgents, setAgents]);

  // 强制Refresh组织结构
  const forceRefreshOrgStructure = useCallback(async () => {
    if (!username) {
      return;
    }

    logger.info('[OrgNavigator] Force refreshing organization structure...');
    setLoading(true);
    setError(null);

    try {
      const response = await get_ipc_api().getAllOrgAgents<GetAllOrgAgentsResponse>(username);

      if (response.success && response.data) {
        setAllOrgAgents(response.data);

        const allAgents = extractAllAgents(response.data.orgs);

        if (allAgents.length > 0) {
          setAgents(
            allAgents.map((agent) =>
              mapOrgAgentToAgent(agent, agent.org_id || undefined)
            )
          );
          logger.info(`[OrgNavigator] Force refreshed and saved ${allAgents.length} agents to agentStore`);
        }

        logger.info('[OrgNavigator] Organization structure force refreshed successfully');
      } else {
        const errorMessage = response.error?.message || 'Failed to fetch organization structure';
        setError(errorMessage);
        logger.error('[OrgNavigator] Error in force refresh response:', errorMessage);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';
      setError(errorMessage);
      logger.error('[OrgNavigator] Error force refreshing organization structure:', errorMessage);
    } finally {
      setLoading(false);
    }
  }, [username, setAllOrgAgents, setLoading, setError, setAgents]);

  // 初始Load
  useEffect(() => {
    fetchOrgStructure();
  }, [fetchOrgStructure]);

  return {
    fetchOrgStructure,
    forceRefreshOrgStructure,
  };
}
