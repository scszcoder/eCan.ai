/**
 * Store for persisting node H-flip states across selections/deselections
 */
import { create } from 'zustand';

interface NodeFlipState {
  flippedNodes: Set<string>; // node IDs that are H-flipped
  // Monotonic counter for any flip state change; useful for triggering side effects
  version: number;
  setFlipped: (nodeId: string, flipped: boolean) => void;
  isFlipped: (nodeId: string) => boolean;
  busyNodes: Set<string>; // nodes currently toggling to guard double triggers
  setBusy: (nodeId: string, busy: boolean) => void;
  isBusy: (nodeId: string) => boolean;
  clear: () => void;
}

export const useNodeFlipStore = create<NodeFlipState>((set, get) => ({
  flippedNodes: new Set<string>(),
  busyNodes: new Set<string>(),
  version: 0,
  
  setFlipped: (nodeId: string, flipped: boolean) => {
    set((state) => {
      const newSet = new Set(state.flippedNodes);
      const before = newSet.has(nodeId);
      if (flipped) {
        newSet.add(nodeId);
      } else {
        newSet.delete(nodeId);
      }
      const changed = before !== flipped;
      return {
        flippedNodes: newSet,
        version: changed ? state.version + 1 : state.version,
      };
    });
  },
  
  isFlipped: (nodeId: string) => get().flippedNodes.has(nodeId),
  
  setBusy: (nodeId: string, busy: boolean) => {
    set((state) => {
      const newSet = new Set(state.busyNodes);
      if (busy) newSet.add(nodeId); else newSet.delete(nodeId);
      return { busyNodes: newSet };
    });
  },

  isBusy: (nodeId: string) => get().busyNodes.has(nodeId),

  clear: () => {
    set({ flippedNodes: new Set(), busyNodes: new Set(), version: 0 });
  },
}));
