import { create } from 'zustand';

interface RunningNodeState {
  runningNodeId: string | null;
  setRunningNodeId: (nodeId: string | null) => void;
}

export const useRunningNodeStore = create<RunningNodeState>((set) => ({
  runningNodeId: null,
  setRunningNodeId: (nodeId) => set({ runningNodeId: nodeId }),
}));
