// stores/titleStore.ts
import { create } from 'zustand';

interface TitleState {
  titlename: string | null;
  setTitlename: (titlename: string) => void;
}

export const useTitleStore = create<TitleState>((set) => ({
  titlename: null,
  setTitlename: (titlename) => set({ titlename }),
}));
