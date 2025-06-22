// stores/agentStore.ts
import { create } from 'zustand';

interface AgentState {
  agentname: string | null;
  setAgentname: (agentname: string) => void;
}

export const useAgentStore = create<AgentState>((set) => ({
  agentname: null,
  setAgentname: (agentname) => set({ agentname }),
}));
