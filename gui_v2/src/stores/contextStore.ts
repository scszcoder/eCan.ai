/**
 * Context Store
 * Manages chat contexts for the context panel
 */
import { create } from 'zustand';
import type { ChatContext } from '@/pages/Chat/types/context';

interface ContextStore {
  contexts: ChatContext[];
  searchQuery: string;
  setContexts: (contexts: ChatContext[]) => void;
  addContext: (context: ChatContext) => void;
  updateContext: (uid: string, updates: Partial<ChatContext>) => void;
  deleteContext: (uid: string) => void;
  setSearchQuery: (query: string) => void;
  getFilteredContexts: () => ChatContext[];
}

export const useContextStore = create<ContextStore>((set, get) => ({
  contexts: [],
  searchQuery: '',

  setContexts: (contexts) => set({ contexts }),

  addContext: (context) =>
    set((state) => ({
      contexts: [context, ...state.contexts],
    })),

  updateContext: (uid, updates) =>
    set((state) => ({
      contexts: state.contexts.map((ctx) =>
        ctx.uid === uid ? { ...ctx, ...updates } : ctx
      ),
    })),

  deleteContext: (uid) =>
    set((state) => ({
      contexts: state.contexts.filter((ctx) => ctx.uid !== uid),
    })),

  setSearchQuery: (query) => set({ searchQuery: query }),

  getFilteredContexts: () => {
    const { contexts, searchQuery } = get();
    if (!searchQuery.trim()) {
      return contexts.filter((ctx) => !ctx.isArchived);
    }
    const query = searchQuery.toLowerCase();
    return contexts.filter(
      (ctx) =>
        !ctx.isArchived &&
        (ctx.title.toLowerCase().includes(query) ||
          ctx.mostRecentMessage.toLowerCase().includes(query))
    );
  },
}));
