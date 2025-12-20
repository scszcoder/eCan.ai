import { create } from 'zustand';

interface RuntimeStateEntry {
  nodeId: string;
  status?: string;
  state: any; // normalized runtime state object
  updatedAt: number;
}

interface RuntimeStateStore {
  byNodeId: Record<string, RuntimeStateEntry>;
  setNodeRuntimeState: (nodeId: string, state: any, status?: string) => void;
  getNodeRuntimeState: (nodeId: string) => RuntimeStateEntry | undefined;
  clearNode: (nodeId: string) => void;
  clearAll: () => void;
}

export const useRuntimeStateStore = create<RuntimeStateStore>((set, get) => ({
  byNodeId: {},
  setNodeRuntimeState: (nodeId, state, status) => {
    const entry: RuntimeStateEntry = {
      nodeId,
      status,
      state,
      updatedAt: Date.now(),
    };
    set((s) => ({ byNodeId: { ...s.byNodeId, [nodeId]: entry } }));
  },
  getNodeRuntimeState: (nodeId) => get().byNodeId[nodeId],
  clearNode: (nodeId) => set((s) => {
    const { [nodeId]: _, ...rest } = s.byNodeId;
    return { byNodeId: rest } as any;
  }),
  clearAll: () => set({ byNodeId: {} }),
}));
