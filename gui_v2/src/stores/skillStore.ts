// stores/skillStore.ts
import { create } from 'zustand';

interface SkillState {
  skillname: string | null;
  setSkillname: (skillname: string) => void;
}

export const useSkillStore = create<SkillState>((set) => ({
  skillname: null,
  setSkillname: (skillname) => set({ skillname }),
}));
