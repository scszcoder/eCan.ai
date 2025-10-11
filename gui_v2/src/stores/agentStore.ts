// stores/agentStore.ts
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { Agent } from '@/pages/Agents/types';
import { createIPCAPI } from '@/services/ipc/api';

// Define the expected response structure from the backend
interface AgentsResponse {
  agents?: Agent[];
}

interface AgentStoreState {
  agents: Agent[];
  items: Agent[]; // 别名，兼容标准接口
  loading: boolean;
  error: string | null;
  lastFetched: number | null;

  // Actions
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setAgents: (agents: Agent[]) => void;
  setItems: (items: Agent[]) => void; // 别名，兼容标准接口
  addAgent: (agent: Agent) => void;
  updateAgent: (id: string, updates: Partial<Agent>) => void;
  removeAgent: (id: string) => void;
  updateAgentOrganization: (agentId: string, orgId: string | null) => void;

  // Selectors
  getAgentById: (id: string) => Agent | null;
  getMyTwinAgent: () => Agent | null;
  getAgentsByRank: (rank: string) => Agent[];
  getAgentsByOrganization: (organization: string) => Agent[];

  // Data fetching
  fetchAgents: (username: string, skillIds?: string[]) => Promise<void>;
  shouldFetchAgents: () => boolean;

  // 兼容 SyncManager 的标准接口
  fetchItems: (username: string, ...args: any[]) => Promise<void>;
  shouldFetch: () => boolean;
  clearData: () => void;

  // Agent management operations
  saveAgent: (username: string, agent: Agent) => Promise<void>;
  deleteAgent: (username: string, agentId: string) => Promise<void>;
  createAgent: (username: string, agent: Agent) => Promise<void>;
}

export const useAgentStore = create<AgentStoreState>()(
  persist(
    (set, get) => ({
      agents: [],
      items: [], // 别名，兼容标准接口
      loading: false,
      error: null,
      lastFetched: null,

      // Actions
      setLoading: (loading) => set({ loading }),
      setError: (error) => set({ error }),
      setAgents: (agents) => set({ agents, items: agents, lastFetched: Date.now() }),
      setItems: (items) => set({ agents: items, items: items, lastFetched: Date.now() }), // 别名，兼容标准接口
      
      addAgent: (agent) => set((state) => {
        const newAgents = [...state.agents, agent];
        return { agents: newAgents, items: newAgents };
      }),
      
      updateAgent: (id, updates) => set((state) => {
        const newAgents = state.agents.map(agent => 
          agent.card?.id === id ? { ...agent, ...updates } : agent
        );
        return { agents: newAgents, items: newAgents };
      }),
      
      removeAgent: (id) => set((state) => {
        const newAgents = state.agents.filter(agent => {
          // 支持两种数据结构：agent.card?.id 或 agent.id
          const agentId = agent.card?.id || (agent as any).id;
          return agentId !== id;
        });
        return { agents: newAgents, items: newAgents };
      }),
      
      updateAgentOrganization: (agentId, orgId) => set((state) => {
        const newAgents = state.agents.map(agent => {
          if (agent.card?.id === agentId) {
            return {
              ...agent,
              orgIds: orgId ? [orgId] : []
            };
          }
          return agent;
        });
        return { agents: newAgents, items: newAgents };
      }),

      // Selectors
      getAgentById: (id) => {
        const agents = get().agents;
        return agents.find(agent => agent.card?.id === id) || null;
      },
      
      getMyTwinAgent: () => {
        const agents = get().agents;
        return agents.find(agent => agent.card?.name === 'My Twin Agent') || null;
      },
      
      getAgentsByRank: (rank) => {
        const agents = get().agents;
        return agents.filter(agent => agent.rank === rank);
      },
      
      getAgentsByOrganization: (organization) => {
        const agents = get().agents;
        return agents.filter(agent => agent.orgIds?.includes(organization));
      },

      // Data fetching
      fetchAgents: async (username: string, skillIds: string[] = []) => {
        set({ loading: true, error: null });
        try {
          const api = createIPCAPI();
          const response = await api.getAgents<AgentsResponse | Agent[]>(username, skillIds);
          
          if (response && response.success && response.data) {
            // Handle different response structures
            let agentsData: Agent[] = [];
            if (Array.isArray(response.data)) {
              agentsData = response.data;
            } else if (response.data && typeof response.data === 'object' && 'agents' in response.data && Array.isArray(response.data.agents)) {
              agentsData = response.data.agents;
            }
            
            set({ 
              agents: agentsData,
              items: agentsData,
              loading: false, 
              lastFetched: Date.now(),
              error: null 
            });
          } else {
            throw new Error(response.error?.message || 'Failed to fetch agents');
          }
        } catch (error) {
          const errorMessage = error instanceof Error ? error.message : 'An unknown error occurred';
          set({ error: errorMessage, loading: false });
        }
      },
      
      shouldFetchAgents: () => {
        const lastFetched = get().lastFetched;
        if (!lastFetched) return true; // No data fetched yet
        const now = Date.now();
        const diff = now - lastFetched;
        // Re-fetch agents every 5 minutes
        return diff > 5 * 60 * 1000;
      },

      // Agent management operations
      saveAgent: async (username: string, agent: Agent) => {
        set({ loading: true, error: null });
        try {
          const api = createIPCAPI();
          const response = await api.saveAgent(username, [agent]);
          
          if (response && response.success) {
            // Update the local state
            const existingAgent = get().getAgentById(agent.card?.id || '');
            if (existingAgent) {
              get().updateAgent(agent.card?.id || '', agent);
            } else {
              get().addAgent(agent);
            }
            set({ loading: false });
          } else {
            throw new Error(response.error?.message || 'Failed to save agent');
          }
        } catch (error) {
          const errorMessage = error instanceof Error ? error.message : 'An unknown error occurred';
          set({ error: errorMessage, loading: false });
          throw error;
        }
      },
      
      deleteAgent: async (username: string, agentId: string) => {
        set({ loading: true, error: null });
        try {
          const api = createIPCAPI();
          const response = await api.deleteAgent(username, [agentId]);
          
          if (response && response.success) {
            // Remove from local state
            get().removeAgent(agentId);
            set({ loading: false });
          } else {
            throw new Error(response.error?.message || 'Failed to delete agent');
          }
        } catch (error) {
          const errorMessage = error instanceof Error ? error.message : 'An unknown error occurred';
          set({ error: errorMessage, loading: false });
          throw error;
        }
      },
      
      createAgent: async (username: string, agent: Agent) => {
        set({ loading: true, error: null });
        try {
          const api = createIPCAPI();
          const response = await api.newAgent(username, [agent]);

          if (response && response.success) {
            // Add to local state
            get().addAgent(agent);
            set({ loading: false });
          } else {
            throw new Error(response.error?.message || 'Failed to create agent');
          }
        } catch (error) {
          const errorMessage = error instanceof Error ? error.message : 'An unknown error occurred';
          set({ error: errorMessage, loading: false });
          throw error;
        }
      },

      // 兼容 SyncManager 的标准接口（别名方法）
      fetchItems: async (username: string, ...args: any[]) => {
        return get().fetchAgents(username, args[0]);
      },

      shouldFetch: () => {
        return get().shouldFetchAgents();
      },

      clearData: () => {
        set({ agents: [], items: [], lastFetched: null, error: null });
      },
    }),
    {
      name: 'agent-storage',
      // Only persist the agents data, not loading states
      partialize: (state) => ({
        agents: state.agents,
        items: state.agents, // 持久化时同步 items
        lastFetched: state.lastFetched,
      }),
    }
  )
);
