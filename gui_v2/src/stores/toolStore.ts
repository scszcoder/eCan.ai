// stores/toolStore.ts
import { create } from 'zustand';

interface ToolState {
  toolname: string | null;
  setToolname: (toolname: string) => void;
}

export const useToolStore = create<ToolState>((set) => ({
  toolname: null,
  setToolname: (toolname) => set({ toolname }),
}));