import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { Agent } from '@/pages/Agents/types';
import { Task } from '@/pages/Tasks/types';
import { KnowledgeEntry as Knowledge } from '@/pages/Knowledge/types';
import { Skill } from '@/pages/Skills/types';
import { Tool } from '@/pages/Tools/types';
import { Vehicle } from '@/pages/Vehicles/types';
import { Settings } from '@/pages/Settings/types';
import { Chat } from '@/pages/Chat/types/chat';
import appData from './app_data.json';

export interface AppData {
  agents: Agent[];
  tasks: Task[];
  knowledges: Knowledge[];
  skills: Skill[];
  tools: Tool[];
  vehicles: Vehicle[];
  settings: Settings | null;
  chats: Chat[];
  isLoading: boolean;
  error: string | null;
  initialized: boolean;
  agentsLastFetched: number | null; // 记录最后获取agents数据的时间戳
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setAgents: (agents: Agent[]) => void;
  setTasks: (tasks: Task[]) => void;
  setSkills: (skills: Skill[]) => void;
  setKnowledges: (knowledges: Knowledge[]) => void;
  setTools: (tools: Tool[]) => void;
  setVehicles: (vehicles: Vehicle[]) => void;
  setSettings: (settings: Settings) => void;
  // Chat actions
  setChats: (chats: Chat[]) => void;
  myTwinAgent: () => Agent | null;
  setInitialized: (v: boolean) => void;
  getAgentById: (id: string) => Agent | null;
  shouldFetchAgents: () => boolean; // 判断是否需要重新获取agents数据
}

const useAppDataStore = create<AppData>()(
  persist(
    (set, get) => ({
      agents: appData.agents as Agent[],
      tasks: appData.tasks as Task[],
      knowledges: appData.knowledges as Knowledge[],
      skills: appData.skills as any as Skill[],
      tools: appData.tools as any as Tool[],
      vehicles: appData.vehicles as any as Vehicle[],
      settings: appData.settings as any as Settings,
      chats: [],
      isLoading: false,
      error: null,
      initialized: false,
      agentsLastFetched: null, // Initialize agentsLastFetched
      setLoading: (loading) => set({ isLoading: loading }),
      setError: (error) => set({ error }),
      setAgents: (agents) => set({ agents, agentsLastFetched: Date.now() }),
      setTasks: (tasks) => set({ tasks }),
      setSkills: (skills) => set({ skills }),
      setKnowledges: (knowledges) => set({ knowledges }),
      setTools: (tools) => set({ tools }),
      setVehicles: (vehicles) => set({ vehicles }),
      setSettings: (settings) => set({ settings }),

      // Chat actions implementation
      setChats: (chats) => set({ chats }),
      myTwinAgent: () => {
        const agents = get().agents;
        return agents.find(a => a.card?.name === 'My Twin Agent') || null;
      },
      setInitialized: (v) => set({ initialized: v }),
      getAgentById: (id) => {
        const agents = get().agents;
        return agents.find(a => a.card?.id === id) || null;
      },
      shouldFetchAgents: () => {
        const lastFetched = get().agentsLastFetched;
        if (!lastFetched) return true; // No data fetched yet
        const now = Date.now();
        const diff = now - lastFetched;
        // Re-fetch agents every 5 minutes
        return diff > 5 * 60 * 1000;
      },
    }),
    {
      name: 'system-storage',
    }
  )
);

export { useAppDataStore }; 