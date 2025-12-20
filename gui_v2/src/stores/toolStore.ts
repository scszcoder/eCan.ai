// stores/toolStore.ts
import { create } from 'zustand';
import { IPCAPI, APIResponse } from '../services/ipc';
import { Tool } from '../pages/Tools/types';

// Re-export Tool type for convenience
export type { Tool };

interface ToolStoreState {
  tools: Tool[];
  loading: boolean;
  error: string | null;
  lastFetched: number | null;
  fetchTools: (username: string) => Promise<void>;
  forceRefresh: (username: string) => Promise<void>;
  clearTools: () => void;
}

export const useToolStore = create<ToolStoreState>((set, get) => ({
  tools: [],
  loading: false,
  error: null,
  lastFetched: null,
  fetchTools: async (username: string) => {
    // Check cache
    const { lastFetched } = get();
    const now = Date.now();
    const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes

    if (lastFetched && now - lastFetched < CACHE_DURATION) {
      return; // Use cached data
    }

    set({ loading: true, error: null });
    try {
      const response: APIResponse<{ tools: Tool[] }> = await IPCAPI.getInstance().getTools(username, []);
      if (response && response.success && response.data && Array.isArray(response.data.tools)) {
        const incoming = response.data.tools;
        set({ tools: incoming, loading: false, lastFetched: Date.now() });
      } else {
        throw new Error(response?.error?.message || 'Failed to fetch tools');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'An unknown error occurred';
      set({ error: errorMessage, loading: false });
    }
  },
  forceRefresh: async (username: string) => {
    set({ lastFetched: null });
    await get().fetchTools(username);
  },
  clearTools: () => {
    set({ tools: [], loading: false, error: null, lastFetched: null });
  },
}));