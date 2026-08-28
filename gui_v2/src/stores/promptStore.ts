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
    const state = get();
    if (state.loading && !force) {
      console.debug('[promptStore] Fetch already in progress, skipping duplicate request');
      return;
    }
    if (state.fetched && !force) {
      console.log('[promptStore] Prompts already fetched, skipping duplicate request (use force=true to reload)');
      return;
    }
    set({ loading: true, error: null });
    try {
      const res: APIResponse<Prompt[] | { prompts: Prompt[] }> = await IPCAPI.getInstance().getPrompts(username);
      if (!res.success) throw new Error(res.error?.message || 'Failed to fetch prompts');
      // Handle both formats: direct array (from resultPath extraction) or { prompts: [...] }
      const rawPrompts = Array.isArray(res.data) 
        ? res.data 
        : (res.data as { prompts: Prompt[] })?.prompts ?? [];
      
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
            // Not JSON-parsable — preserve the raw string for preview display
            console.warn('[promptStore] Failed to parse prompt AWSJSON:', e);
            const { prompt: _, ...rest } = p;
            return {
              ...rest,
              id: rest.id || p.id,
              owner: rest.owner,
              title: rest.title || rest.id || 'Untitled',
              topic: rest.topic || '',
              usageCount: rest.usageCount || 0,
              sections: [],
              userSections: [],
              humanInputs: [],
              rawContent: nested, // the original non-JSON string
              readOnly: true,
            };
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
      
      // Deduplicate prompts by ID to prevent rendering duplicates
      const uniquePrompts = incoming.reduce((acc: Prompt[], current: Prompt) => {
        const exists = acc.find(p => p.id === current.id);
        if (!exists) {
          acc.push(current);
        } else {
          console.warn(`[promptStore] Duplicate prompt ID detected: ${current.id}, skipping duplicate`);
        }
        return acc;
      }, []);

      // Keep public and skill-shared prompts visible, but never editable by a
      // different owner. The backend has already applied access controls.
      const normalise = (s: string) => (s || '').trim().toLowerCase();
      const visiblePrompts = uniquePrompts.map((p: any) => {
        const pOwner = normalise(p.owner);
        const isOwned = !pOwner || pOwner === normalise(username);
        const src = normalise(p.source);
        const isLocalLibraryPrompt = src === 'my_prompts' || src === 'sample_prompts';
        if (isOwned || isLocalLibraryPrompt) return p;
        return { ...p, source: src || 'public_prompts', readOnly: true };
      });
      
      console.log(`[promptStore] Loaded ${visiblePrompts.length} prompts (${incoming.length - uniquePrompts.length} duplicates)`);
      
      set({ prompts: visiblePrompts, loading: false, fetched: true });
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
