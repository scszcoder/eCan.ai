// stores/taskStore.ts
import { create } from 'zustand';

interface RankState {
  rankname: string | null;
  setRankname: (rankname: string) => void;
}

export const useRankStore = create<RankState>((set) => ({
  rankname: null,
  setRankname: (rankname) => set({ rankname }),
}));
