// stores/knowledgeStore.ts
import { create } from 'zustand';

interface KnowledgeState {
  knowledgename: string | null;
  setKnowledgename: (knowledgename: string) => void;
}

export const useKnowledgeStore = create<KnowledgeState>((set) => ({
  knowledgename: null,
  setKnowledgename: (knowledgename) => set({ knowledgename }),
}));
