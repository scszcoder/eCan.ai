import { create } from 'zustand';

interface RunningNodeState {
  runningNodeId: string | null;
  setRunningNodeId: (nodeId: string | null) => void;
}

export const useRunningNodeStore = create<RunningNodeState>((set) => ({
  runningNodeId: null,
  setRunningNodeId: (nodeId) => {
    console.log(`[RunningNodeStore] setRunningNodeId called with: '${nodeId}'`);
    set({ runningNodeId: nodeId });
  },
}));

// Subscribe to store changes for debugging
if (typeof window !== 'undefined') {
  useRunningNodeStore.subscribe((state) => {
    console.log(`[RunningNodeStore] State changed to: runningNodeId='${state.runningNodeId}'`);
  });
}
