// stores/toolStore.ts
import { create } from 'zustand';
import { IPCAPI, APIResponse } from '../services/ipc';

// This should match the Tool type used in the Tools page
export interface Tool {
  id: string;
  name: string;
  description: string;
  // Add other properties from your actual Tool type
}

interface ToolStoreState {
  tools: Tool[];
  loading: boolean;
  error: string | null;
  fetchTools: (username: string) => Promise<void>;
}

export const useToolStore = create<ToolStoreState>((set) => ({
  tools: [],
  loading: false,
  error: null,
  fetchTools: async (username: string) => {
    set({ loading: true, error: null });
    try {
      const response: APIResponse<{ tools: Tool[] }> = await IPCAPI.getInstance().getTools(username, []);
      if (response && response.success && response.data && response.data.tools) {
        set({ tools: response.data.tools, loading: false });
      } else {
        throw new Error(response.error?.message || 'Failed to fetch tools');
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'An unknown error occurred';
      set({ error: errorMessage, loading: false });
    }
  },
}));