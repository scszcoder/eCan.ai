import { create } from 'zustand';
import { IPCAPI, type APIResponse } from '../services/ipc';
import type { Prompt } from '../pages/Prompts/types';

interface PromptStoreState {
  prompts: Prompt[];
  loading: boolean;
  error: string | null;
  fetched: boolean;
  fetch: (username: string, force?: boolean) => Promise<void>;
  save: (username: string, prompt: Prompt) => Promise<Prompt | null>;
  remove: (username: string, id: string) => Promise<boolean>;
  duplicate: (username: string, source: Prompt) => Promise<Prompt | null>;
}

export const usePromptStore = create<PromptStoreState>((set, get) => ({
  prompts: [],
  loading: false,
  error: null,
  fetched: false,
  fetch: async (username: string, force = false) => {
    if (get().loading && !force) return;
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
    if (prompt.readOnly) {
      return null;
    }
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
      const target = get().prompts.find((p) => p.id === id);
      if (target?.readOnly) {
        return false;
      }
      const res: APIResponse<any> = await IPCAPI.getInstance().executeRequest('delete_prompt', { username, id });
      if (!res.success) throw new Error(res.error?.message || 'Failed to delete');
      set((state) => ({ prompts: state.prompts.filter(p => p.id !== id) }));
      return true;
    } catch (e) {
      return false;
    }
  },
  duplicate: async (username: string, source: Prompt) => {
    const baseTitle = (source.title || source.topic || 'prompt').trim() || 'prompt';
    const title = `${baseTitle}_copy`;
    const topic = `${(source.topic || source.title || baseTitle).trim() || baseTitle}_copy`;
    const newId = `pr-${Date.now().toString(36)}-${Math.floor(Math.random() * 10000)}`;

    const cloneSection = (section: NonNullable<Prompt['systemSections']>[number]) => ({
      id: `${section.type}_${Math.random().toString(36).slice(2, 10)}`,
      type: section.type,
      items: [...(section.items || [])],
    });

    const clonePrompt: Prompt = {
      ...source,
      id: newId,
      title,
      topic,
      usageCount: 0,
      lastModified: undefined,
      readOnly: false,
      roleToneContext: source.roleToneContext || '',
      goals: [...(source.goals || [])],
      guidelines: [...(source.guidelines || [])],
      rules: [...(source.rules || [])],
      instructions: [...(source.instructions || [])],
      sysInputs: [...(source.sysInputs || [])],
      humanInputs: [...(source.humanInputs || [])],
      examples: [...(source.examples || [])],
      systemSections: (source.systemSections || []).map(cloneSection),
    };

    const saved = await get().save(username, clonePrompt);
    if (saved) {
      set((state) => ({ prompts: [saved, ...state.prompts.filter(p => p.id !== saved.id)] }));
    }
    return saved;
  },
}));
