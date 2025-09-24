// stores/agentStore.ts
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { Agent } from '@/pages/Agents/types';
import { createIPCAPI } from '@/services/ipc/api';

interface AgentStoreState {
  agents: Agent[];
  loading: boolean;
  error: string | null;
  lastFetched: number | null;
  
  // Actions
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setAgents: (agents: Agent[]) => void;
  addAgent: (agent: Agent) => void;
  updateAgent: (id: string, updates: Partial<Agent>) => void;
  removeAgent: (id: string) => void;
  
  // Selectors
  getAgentById: (id: string) => Agent | null;
  getMyTwinAgent: () => Agent | null;
  getAgentsByRank: (rank: string) => Agent[];
  getAgentsByOrganization: (organization: string) => Agent[];
  
  // Data fetching
  fetchAgents: (username: string, skillIds?: string[]) => Promise<void>;
  shouldFetchAgents: () => boolean;
  
  // Agent management operations
  saveAgent: (username: string, agent: Agent) => Promise<void>;
  deleteAgent: (username: string, agentId: string) => Promise<void>;
  createAgent: (username: string, agent: Agent) => Promise<void>;
}

export const useAgentStore = create<AgentStoreState>()(
  persist(
    (set, get) => ({
      agents: [],
      loading: false,
      error: null,
      lastFetched: null,

      // Actions
      setLoading: (loading) => set({ loading }),
      setError: (error) => set({ error }),
      setAgents: (agents) => set({ agents, lastFetched: Date.now() }),
      
      addAgent: (agent) => set((state) => ({
        agents: [...state.agents, agent]
      })),
      
      updateAgent: (id, updates) => set((state) => ({
        agents: state.agents.map(agent => 
          agent.card?.id === id ? { ...agent, ...updates } : agent
        )
      })),
      
      removeAgent: (id) => set((state) => ({
        agents: state.agents.filter(agent => agent.card?.id !== id)
      })),

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
        return agents.filter(agent => agent.organizations?.includes(organization));
      },

      // Data fetching
      fetchAgents: async (username: string, skillIds: string[] = []) => {
        set({ loading: true, error: null });
        try {
          const api = createIPCAPI();
          const response = await api.getAgents(username, skillIds);
          
          if (response && response.success && response.data) {
            // Handle different response structures
            let agentsData: Agent[] = [];
            if (Array.isArray(response.data)) {
              agentsData = response.data;
            } else if (response.data.agents && Array.isArray(response.data.agents)) {
              agentsData = response.data.agents;
            }
            
            set({ 
              agents: agentsData, 
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
          const response = await api.saveAgents(username, [agent]);
          
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
          const response = await api.deleteAgent(username, agentId);
          
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
          const response = await api.newAgents(username, [agent]);
          
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
    }),
    {
      name: 'agent-storage',
      // Only persist the agents data, not loading states
      partialize: (state) => ({
        agents: state.agents,
        lastFetched: state.lastFetched,
      }),
    }
  )
);
