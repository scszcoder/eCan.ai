import { create } from 'zustand';
import { IPCAPI, type APIResponse } from '../services/ipc';
import type { Prompt } from '../pages/Prompts/types';

interface PromptStoreState {
  prompts: Prompt[];
  loading: boolean;
  error: string | null;
  fetched: boolean;
  fetch: (username: string) => Promise<void>;
  save: (username: string, prompt: Prompt) => Promise<Prompt | null>;
  remove: (username: string, id: string) => Promise<boolean>;
}

export const usePromptStore = create<PromptStoreState>((set, get) => ({
  prompts: [],
  loading: false,
  error: null,
  fetched: false,
  fetch: async (username: string) => {
    if (get().loading) return;
    set({ loading: true, error: null });
    try {
      const res: APIResponse<{ prompts: Prompt[] }> = await IPCAPI.getInstance().executeRequest('get_prompts', { username });
      if (res.success) {
        const list = (res.data?.prompts ?? []) as Prompt[];
        set({ prompts: list, loading: false, fetched: true });
      } else {
        throw new Error(res.error?.message || 'Failed to fetch prompts');
      }
    } catch (e: any) {
      set({ loading: false, error: e?.message || 'Unknown error' });
    }
  },
  save: async (username: string, prompt: Prompt) => {
    try {
      const res: APIResponse<{ prompt: Prompt }> = await IPCAPI.getInstance().executeRequest('save_prompt', { username, prompt });
      if (!res.success) throw new Error(res.error?.message || 'Failed to save');
      const saved = res.data?.prompt ?? prompt;
      set((state) => {
        const exists = state.prompts.some(p => p.id === saved.id);
        return {
          prompts: exists ? state.prompts.map(p => (p.id === saved.id ? saved : p)) : [saved, ...state.prompts],
        } as Partial<PromptStoreState>;
      });
      return saved;
    } catch (e) {
      return null;
    }
  },
  remove: async (username: string, id: string) => {
    try {
      const res: APIResponse<any> = await IPCAPI.getInstance().executeRequest('delete_prompt', { username, id });
      if (!res.success) throw new Error(res.error?.message || 'Failed to delete');
      set((state) => ({ prompts: state.prompts.filter(p => p.id !== id) }));
      return true;
    } catch (e) {
      return false;
    }
  },
}));
