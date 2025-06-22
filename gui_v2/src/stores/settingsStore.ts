// stores/settingsStore.ts
import { create } from 'zustand';

interface SettingsState {
  settingsname: string | null;
  setSettingsname: (settingsname: string) => void;
}

export const useSettingsStore = create<SettingsState>((set) => ({
  settingsname: null,
  setSettingsname: (settingsname) => set({ settingsname }),
}));
