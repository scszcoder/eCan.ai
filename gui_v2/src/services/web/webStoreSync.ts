import { IPCAPI } from '../ipc/api';
import { useAgentStore } from '../../stores/agentStore';
import { useTaskStore } from '../../stores/domain/taskStore';
import { useSkillStore } from '../../stores/domain/skillStore';
import { useToolStore } from '../../stores/toolStore';
import { useKnowledgeStore } from '../../stores/domain/knowledgeStore';
import { usePromptStore } from '../../stores/promptStore';
import { useOrgStore } from '../../stores/orgStore';
import { useVehicleStore } from '../../stores/domain/vehicleStore';
import { useAccountStore } from '../../stores/accountStore';

/**
 * Response type for getAll API call
 */
export interface GetAllMineResponse {
  agents?: any[];
  tasks?: any[];
  skills?: any[];
  tools?: any[];
  knowledges?: any[];
  prompts?: any[];
  orgs?: any;
  vehicles?: any[];
  accountInfo?: any;
}

export const hydrateStoresFromAllMine = (allMine: GetAllMineResponse) => {
  if (Array.isArray(allMine.agents)) {
    useAgentStore.getState().setAgents(allMine.agents as any);
  }
  if (Array.isArray(allMine.tasks)) {
    useTaskStore.getState().setItems(allMine.tasks as any);
  }
  if (Array.isArray(allMine.skills)) {
    useSkillStore.getState().setItems(allMine.skills as any);
  }
  if (Array.isArray(allMine.tools)) {
    useToolStore.setState({ tools: allMine.tools as any, lastFetched: Date.now(), loading: false, error: null });
  }
  if (Array.isArray(allMine.knowledges)) {
    useKnowledgeStore.getState().setItems(allMine.knowledges as any);
  }
  if (Array.isArray(allMine.prompts)) {
    // Transform GraphQL format to frontend format
    // GraphQL returns: { id, owner, prompt: { title, sections, ... }, version }
    // Frontend expects: { id, title, sections, ... }
    // Note: AWSJSON fields may come as strings that need parsing
    const transformedPrompts = allMine.prompts.map((p: any) => {
      let nested = p.prompt;
      // AWSJSON may be a string that needs parsing
      if (typeof nested === 'string') {
        try {
          nested = JSON.parse(nested);
        } catch (e) {
          console.warn('[webStoreSync] Failed to parse prompt AWSJSON:', e);
          nested = null;
        }
      }
      if (nested && typeof nested === 'object') {
        const { prompt: _, ...rest } = p;
        return {
          ...rest,
          ...nested,
          id: rest.id || nested.id,
          owner: rest.owner || nested.owner
        };
      }
      return p;
    });
    console.log('[webStoreSync] Transformed prompts:', transformedPrompts.slice(0, 2));
    usePromptStore.setState({ prompts: transformedPrompts as any, fetched: true, loading: false, error: null });
  }
  if (allMine.orgs) {
    useOrgStore.getState().setAllOrgAgents({ orgs: allMine.orgs as any, message: 'ok' });
  }
  if (Array.isArray(allMine.vehicles)) {
    useVehicleStore.getState().setItems(allMine.vehicles as any);
  }
  if (allMine.accountInfo) {
    useAccountStore.getState().setAccountData(allMine.accountInfo as any);
  }
};

export const refreshAllMineStores = async (username: string): Promise<GetAllMineResponse> => {
  try {
    const ipcApi = IPCAPI.getInstance();
    const response = await ipcApi.getAll<GetAllMineResponse>(username);
    
    if (response.success && response.data) {
      hydrateStoresFromAllMine(response.data);
      console.log('[webStoreSync] Successfully refreshed all stores');
      return response.data;
    } else {
      console.error('[webStoreSync] Failed to get all data:', response.error);
      // Return empty data structure on failure
      const emptyData: GetAllMineResponse = {
        agents: [],
        tasks: [],
        skills: [],
        tools: [],
        knowledges: [],
        prompts: [],
        orgs: [],
        vehicles: [],
        accountInfo: null
      } as GetAllMineResponse;
      return emptyData;
    }
  } catch (error) {
    console.error('[webStoreSync] Error refreshing stores:', error);
    throw error;
  }
};