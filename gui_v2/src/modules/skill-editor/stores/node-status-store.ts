import { create } from 'zustand';

export type EndStatus = 'completed' | 'failed' | null;

interface NodeStatusState {
  endNodeId: string | null;
  endStatus: EndStatus;
  setEndStatus: (nodeId: string | null, status: EndStatus) => void;
  clear: () => void;
}

export const useNodeStatusStore = create<NodeStatusState>((set) => ({
  endNodeId: null,
  endStatus: null,
  setEndStatus: (nodeId, status) => set({ endNodeId: nodeId, endStatus: status }),
  clear: () => set({ endNodeId: null, endStatus: null }),
}));
