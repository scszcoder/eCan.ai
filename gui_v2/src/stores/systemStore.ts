import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { Agent } from '@/pages/Agents/types';
import { Task } from '@/pages/Tasks/types';
import { Knowledge } from '@/pages/Knowledge/types';
import { Skill } from '@/pages/Skills/types';
import { Tool } from '@/pages/Tools/types';
import { Vehicle } from '@/pages/Vehicles/types';
import { Settings } from '@/pages/Settings/types';
import { Chat } from '@/pages/Chat/types/chat';
import systemData from './system_data.json';

export interface SystemState {
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
}

const useSystemStore = create<SystemState>()(
  persist(
    (set, get) => ({
      agents: systemData.agents as Agent[],
      tasks: systemData.tasks as Task[],
      knowledges: systemData.knowledges as Knowledge[],
      skills: systemData.skills as any as Skill[],
      tools: systemData.tools as any as Tool[],
      vehicles: systemData.vehicles as any as Vehicle[],
      settings: systemData.settings as any as Settings,
      chats: [],
      isLoading: false,
      error: null,
      setLoading: (loading) => set({ isLoading: loading }),
      setError: (error) => set({ error }),
      setAgents: (agents) => set({ agents }),
      setTasks: (tasks) => set({ tasks }),
      setSkills: (skills) => set({ skills }),
      setKnowledges: (knowledges) => set({ knowledges }),
      setTools: (tools) => set({ tools }),
      setVehicles: (vehicles) => set({ vehicles }),
      setSettings: (settings) => set({ settings }),

      // Chat actions implementation
      setChats: (chats) => set({ chats }),
    }),
    {
      name: 'system-storage',
    }
  )
);

export { useSystemStore }; 