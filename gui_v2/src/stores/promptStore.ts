import { create } from 'zustand';
import { IPCAPI, type APIResponse } from '../services/ipc/api';
import type { Prompt } from '../pages/Prompts/types';

interface PromptStoreState {
  prompts: Prompt[];
  loading: boolean;
  error: string | null;
  fetched: boolean;
  fetch: (username: string, force?: boolean) => Promise<void>;
  save: (username: string, prompt: Prompt) => Promise<Prompt | null>;
  remove: (username: string, id: string) => Promise<boolean>;
  clone: (username: string, prompt: Prompt) => Promise<Prompt | null>;
}

export const usePromptStore = create<PromptStoreState>((set, get) => ({
  prompts: [],
  loading: false,
  error: null,
  fetched: false,
  fetch: async (username: string, force = false) => {
    console.log(`[promptStore] fetch called: username='${username}', force=${force}, loading=${get().loading}`);
    if (get().loading && !force) {
      console.log('[promptStore] Skipping fetch - already loading');
      return;
    }
    set({ loading: true, error: null });
    try {
      // Use getPrompts which routes through GraphQL getAllMine.prompts for web app
      console.log('[promptStore] Calling IPCAPI.getPrompts...');
      const res: APIResponse<Prompt[] | { prompts: Prompt[] }> = await IPCAPI.getInstance().getPrompts(username);
      console.log('[promptStore] getPrompts response:', JSON.stringify(res, null, 2));
      if (!res.success) throw new Error(res.error?.message || 'Failed to fetch prompts');
      // Handle both formats: direct array (from resultPath extraction) or { prompts: [...] }
      const rawPrompts = Array.isArray(res.data) 
        ? res.data 
        : (res.data as { prompts: Prompt[] })?.prompts ?? [];
      console.log(`[promptStore] rawPrompts count: ${rawPrompts.length}`);
      if (rawPrompts.length > 0) {
        console.log('[promptStore] First raw prompt:', JSON.stringify(rawPrompts[0], null, 2));
      }
      
      // Transform GraphQL format to frontend format
      // GraphQL returns: { id, owner, prompt: { title, sections, ... }, version }
      // Frontend expects: { id, title, sections, ... }
      // Note: AWSJSON fields may come as strings that need parsing
      const incoming = rawPrompts.map((p: any) => {
        let nested = p.prompt;
        // AWSJSON may be a string that needs parsing
        if (typeof nested === 'string') {
          try {
            nested = JSON.parse(nested);
          } catch (e) {
            console.warn('[promptStore] Failed to parse prompt AWSJSON:', e);
            nested = null;
          }
        }
        // If prompt has nested 'prompt' field (GraphQL format), flatten it
        if (nested && typeof nested === 'object') {
          const { prompt: _, ...rest } = p;
          return {
            ...rest,
            ...nested,
            // Ensure id is preserved from top level
            id: rest.id || nested.id,
            owner: rest.owner || nested.owner
          };
        }
        // Already flat format (desktop app or already transformed)
        return p;
      });
      
      console.log(`[promptStore] Processed ${incoming.length} prompts`);
      set({ prompts: incoming, loading: false, fetched: true });
    } catch (e: any) {
      console.error('[promptStore] Fetch error:', e);
      set({ loading: false, error: e?.message || 'Unknown error' });
    }
  },
  save: async (username: string, prompt: Prompt) => {
    if (prompt.readOnly) {
      return null;
    }
    try {
      // Use savePrompt which routes through GraphQL addPrompts mutation
      const res: APIResponse<any> = await IPCAPI.getInstance().savePrompt(username, prompt);
      if (!res.success) throw new Error(res.error?.message || 'Failed to save');
      // The saved prompt - use the input prompt since mutation returns { id, success, error }
      const saved = { ...prompt, readOnly: false, source: 'my_prompts' as const };
      set((state) => {
        const exists = state.prompts.some(p => p.id === saved.id);
        const prompts = exists
          ? state.prompts.map(p => (p.id === saved.id ? saved : p))
          : [saved, ...state.prompts];
        return { prompts } as Partial<PromptStoreState>;
      });
      return saved;
    } catch (e) {
      console.error('[promptStore] Save failed:', e);
      return null;
    }
  },
  remove: async (username: string, id: string) => {
    try {
      // Use deletePrompt which routes through GraphQL removePrompts mutation
      const res: APIResponse<any> = await IPCAPI.getInstance().deletePrompt(username, id);
      if (!res.success) throw new Error(res.error?.message || 'Failed to delete');
      set((state) => ({ prompts: state.prompts.filter(p => p.id !== id) }));
      return true;
    } catch (e) {
      console.error('[promptStore] Delete failed:', e);
      return false;
    }
  },
  clone: async (username: string, prompt: Prompt) => {
    const baseTitle = prompt.title || prompt.topic || 'Prompt';
    const copyId = `pr-${Math.floor(Math.random() * 1_000_000)}`;
    const copyTitle = `${baseTitle}${baseTitle.endsWith('_copy') ? '' : '_copy'}`;
    const clonePayload: Prompt = {
      ...prompt,
      id: copyId,
      title: copyTitle,
      readOnly: false,
      source: 'my_prompts',
    };
    delete (clonePayload as any).lastModified;

    return get().save(username, clonePayload);
  },
}));
