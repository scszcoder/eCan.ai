import { create } from 'zustand';
import { persist } from 'zustand/middleware';
// import { Agent } from '@/pages/Agents/types'; // 已迁移到 agentStore，不再需要
import { Task } from '@/pages/Tasks/types';
import { KnowledgeEntry as Knowledge } from '@/pages/Knowledge/types';
import { Skill } from '@/pages/Skills/types';
import { Tool } from '@/pages/Tools/types';
import { Vehicle } from '@/pages/Vehicles/types';
import { Settings } from '@/pages/Settings/types';
import { Chat } from '@/pages/Chat/types/chat';
import appData from './app_data.json';
// import { useAgentStore } from './agentStore'; // 不再需要，agents 已迁移

export interface AppData {
  // 移除 agents 数据，使用专用的 agentStore
  // agents: Agent[]; // 已迁移到 agentStore
  tasks: Task[];
  knowledges: Knowledge[];
  skills: Skill[];
  tools: Tool[];
  vehicles: Vehicle[];
  settings: Settings | null;
  chats: Chat[];
  
  // 全局状态
  isLoading: boolean;
  error: string | null;
  initialized: boolean;
  
  // 数据获取时间戳（保留非 agents 相关的）
  // agentsLastFetched: number | null; // 已迁移到 agentStore
  tasksLastFetched: number | null;
  skillsLastFetched: number | null;
  toolsLastFetched: number | null;
  vehiclesLastFetched: number | null;
  
  // 全局状态管理
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setInitialized: (v: boolean) => void;
  
  // 数据管理（保留非 agents 相关的）
  // setAgents: (agents: Agent[]) => void; // 已迁移到 agentStore
  setTasks: (tasks: Task[]) => void;
  setSkills: (skills: Skill[]) => void;
  setKnowledges: (knowledges: Knowledge[]) => void;
  setTools: (tools: Tool[]) => void;
  setVehicles: (vehicles: Vehicle[]) => void;
  setSettings: (settings: Settings) => void;
  
  // Chat actions
  setChats: (chats: Chat[]) => void;
  
  // 移除 agents 相关方法，使用 agentStore
  // myTwinAgent: () => Agent | null; // 使用 agentStore.getMyTwinAgent()
  // getAgentById: (id: string) => Agent | null; // 使用 agentStore.getAgentById()
  
  // 数据获取判断（保留非 agents 相关的）
  // shouldFetchAgents: () => boolean; // 已迁移到 agentStore
  shouldFetchTasks: () => boolean;
  shouldFetchSkills: () => boolean;
  shouldFetchTools: () => boolean;
  shouldFetchVehicles: () => boolean;
  shouldFetchData: (dataType: 'tasks' | 'skills' | 'tools' | 'vehicles') => boolean; // 移除 'agents'
}

const useAppDataStore = create<AppData>()(
  persist(
    (set, get) => ({
      // 移除 agents 相关数据，使用专用的 agentStore
      // agents: appData.agents as Agent[], // 已迁移到 agentStore
      tasks: appData.tasks as Task[],
      knowledges: appData.knowledges as Knowledge[],
      skills: appData.skills as any as Skill[],
      tools: appData.tools as any as Tool[],
      vehicles: appData.vehicles as any as Vehicle[],
      settings: appData.settings as any as Settings,
      chats: [],
      
      // 全局状态
      isLoading: false,
      error: null,
      initialized: false,
      
      // 数据获取时间戳（移除 agents 相关）
      // agentsLastFetched: null, // 已迁移到 agentStore
      tasksLastFetched: null,
      skillsLastFetched: null,
      toolsLastFetched: null,
      vehiclesLastFetched: null,
      
      // 全局状态管理
      setLoading: (loading) => set({ isLoading: loading }),
      setError: (error) => set({ error }),
      setInitialized: (v) => set({ initialized: v }),
      
      // 数据管理（移除 agents 相关）
      // setAgents: (agents) => set({ agents, agentsLastFetched: Date.now() }), // 已迁移到 agentStore
      setTasks: (tasks) => set({ tasks, tasksLastFetched: Date.now() }),
      setSkills: (skills) => set({ skills, skillsLastFetched: Date.now() }),
      setKnowledges: (knowledges) => set({ knowledges }),
      setTools: (tools) => set({ tools, toolsLastFetched: Date.now() }),
      setVehicles: (vehicles) => set({ vehicles, vehiclesLastFetched: Date.now() }),
      setSettings: (settings) => set({ settings }),

      // Chat actions implementation
      setChats: (chats) => set({ chats }),
      
      // 移除 agents 相关方法，使用 agentStore
      // myTwinAgent: () => { ... }, // 使用 agentStore.getMyTwinAgent()
      // getAgentById: (id) => { ... }, // 使用 agentStore.getAgentById()
      // shouldFetchAgents: () => { ... }, // 已迁移到 agentStore
      shouldFetchTasks: () => {
        const lastFetched = get().tasksLastFetched;
        if (!lastFetched) return true;
        const now = Date.now();
        const diff = now - lastFetched;
        return diff > 5 * 60 * 1000;
      },
      shouldFetchSkills: () => {
        const lastFetched = get().skillsLastFetched;
        if (!lastFetched) return true;
        const now = Date.now();
        const diff = now - lastFetched;
        return diff > 5 * 60 * 1000;
      },
      shouldFetchTools: () => {
        const lastFetched = get().toolsLastFetched;
        if (!lastFetched) return true;
        const now = Date.now();
        const diff = now - lastFetched;
        return diff > 5 * 60 * 1000;
      },
      shouldFetchVehicles: () => {
        const lastFetched = get().vehiclesLastFetched;
        if (!lastFetched) return true;
        const now = Date.now();
        const diff = now - lastFetched;
        return diff > 5 * 60 * 1000;
      },
      shouldFetchData: (dataType) => {
        const state = get();
        const lastFetchedKey = `${dataType}LastFetched` as keyof typeof state;
        const lastFetched = state[lastFetchedKey] as number | null;
        if (!lastFetched) return true;
        const now = Date.now();
        const diff = now - lastFetched;
        return diff > 5 * 60 * 1000;
      },
    }),
    {
      name: 'system-storage',
    }
  )
);

export { useAppDataStore }; 