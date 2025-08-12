// stores/taskStore.ts
import { create } from 'zustand';

interface PersonalityState {
  personalityname: string | null;
  setPersonalityname: (personalityname: string) => void;
}

export const usePersonalityStore = create<PersonalityState>((set) => ({
  personalityname: null,
  setPersonalityname: (personalityname) => set({ personalityname }),
}));
