import { create } from 'zustand';

interface DisplayRunningState {
  displayRunningNodeId: string | null;
  setDisplayRunningNodeId: (nodeId: string | null) => void;
  clear: () => void;
}

export const useDisplayRunningNodeStore = create<DisplayRunningState>((set) => ({
  displayRunningNodeId: null,
  setDisplayRunningNodeId: (nodeId) => set({ displayRunningNodeId: nodeId }),
  clear: () => set({ displayRunningNodeId: null }),
}));
