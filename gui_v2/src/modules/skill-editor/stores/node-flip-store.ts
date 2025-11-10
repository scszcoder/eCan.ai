/**
 * Store for persisting node H-flip states across selections/deselections
 */
import { create } from 'zustand';

interface NodeFlipState {
  flippedNodes: Set<string>; // node IDs that are H-flipped
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
  
  setFlipped: (nodeId: string, flipped: boolean) => {
    console.log('[NodeFlipStore] setFlipped called:', { nodeId, flipped });
    console.trace('[NodeFlipStore] Stack trace:');
    set((state) => {
      const newSet = new Set(state.flippedNodes);
      if (flipped) {
        newSet.add(nodeId);
        console.log('[NodeFlipStore] Added node to flipped set:', nodeId);
      } else {
        newSet.delete(nodeId);
        console.log('[NodeFlipStore] Removed node from flipped set:', nodeId);
      }
      return { flippedNodes: newSet };
    });
  },
  
  isFlipped: (nodeId: string) => {
    const result = get().flippedNodes.has(nodeId);
    return result;
  },
  
  setBusy: (nodeId: string, busy: boolean) => {
    console.log('[NodeFlipStore] setBusy called:', { nodeId, busy });
    set((state) => {
      const newSet = new Set(state.busyNodes);
      if (busy) newSet.add(nodeId); else newSet.delete(nodeId);
      return { busyNodes: newSet } as any;
    });
  },
  isBusy: (nodeId: string) => {
    return get().busyNodes.has(nodeId);
  },
  
  clear: () => {
    console.log('[NodeFlipStore] CLEAR called - all flip states reset');
    set({ flippedNodes: new Set(), busyNodes: new Set() } as any);
  },
}));
