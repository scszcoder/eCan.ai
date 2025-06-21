import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { Agent } from '@/pages/Agents/types';
import { Task } from '@/pages/Tasks/types';
import { Knowledge } from '@/pages/Knowledge/types';
import { Skill } from '@/pages/Skills/types';
import systemData from './system_data.json';

export interface SystemState {
  agents: Agent[];
  tasks: Task[];
  knowledges: Knowledge[];
  skills: Skill[];
  isLoading: boolean;
  error: string | null;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setAgents: (agents: Agent[]) => void;
  setTasks: (tasks: Task[]) => void;
  setSkills: (skills: Skill[]) => void;
  setKnowledges: (knowledges: Knowledge[]) => void;
}

const useSystemStore = create<SystemState>()(
  persist(
    (set) => ({
      agents: systemData.agents as Agent[],
      tasks: systemData.tasks as Task[],
      knowledges: systemData.knowledges as Knowledge[],
      skills: systemData.skills as any as Skill[],
      isLoading: false,
      error: null,
      setLoading: (loading) => set({ isLoading: loading }),
      setError: (error) => set({ error }),
      setAgents: (agents) => set({ agents }),
      setTasks: (tasks) => set({ tasks }),
      setSkills: (skills) => set({ skills }),
      setKnowledges: (knowledges) => set({ knowledges }),
    }),
    {
      name: 'system-storage',
    }
  )
);

export { useSystemStore }; 