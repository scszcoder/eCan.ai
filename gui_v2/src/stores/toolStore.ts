// stores/toolStore.ts
import { create } from 'zustand';
import { IPCAPI, APIResponse } from '../services/ipc';

// This should match the Tool type used in the Tools page
export interface Tool {
  id: string;
  name: string;
  description: string;
  inputSchema?: any;
  outputSchema?: any;
  // Add other properties from your actual Tool type
}

interface ToolStoreState {
  tools: Tool[];
  loading: boolean;
  error: string | null;
  fetchTools: (username: string) => Promise<void>;
  clearTools: () => void;
}

export const useToolStore = create<ToolStoreState>((set, get) => ({
  tools: [],
  loading: false,
  error: null,
  fetchTools: async (username: string) => {
    set({ loading: true, error: null });
    try {
      const response: APIResponse<{ tools: Tool[] }> = await IPCAPI.getInstance().getTools(username, []);
      if (response && response.success && response.data && Array.isArray(response.data.tools)) {
        const incoming = response.data.tools;
        console.log('[TOOLS_SCHEMA][STORE] fetched tools count =', incoming.length);
        // Debug a sample to ensure schemas exist
        if (incoming.length > 0) {
          const sample = incoming[0] as any;
          console.log('[TOOLS_SCHEMA][STORE] sample tool keys:', Object.keys(sample));
          console.log('[TOOLS_SCHEMA][STORE] sample inputSchema:', sample?.inputSchema);
        }
        // Avoid overwriting with empty list if we already have data (race protection)
        const current = get().tools || [];
        if (incoming.length === 0 && current.length > 0) {
          console.warn('[TOOLS_SCHEMA][STORE] Incoming tools is empty; preserving existing tools to avoid losing schemas');
          set({ loading: false });
          return;
        }
        set({ tools: incoming, loading: false });
        try {
          console.log('[TOOLS_SCHEMA][STORE] tools set in store, count =', incoming.length);
          if (incoming.length > 0) {
            console.log('[TOOLS_SCHEMA][STORE] first tool inputSchema after set:', (incoming[0] as any)?.inputSchema);
          }
        } catch {}
      } else {
        throw new Error(response?.error?.message || 'Failed to fetch tools');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'An unknown error occurred';
      set({ error: errorMessage, loading: false });
    }
  },
  clearTools: () => {
    set({ tools: [], loading: false, error: null });
  },
}));