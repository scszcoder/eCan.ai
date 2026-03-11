/**
 * Store for persisting node agentNote values across selections/deselections.
 * The flowgram Entity data system doesn't reliably preserve arbitrary properties
 * set via (node as any).data, so we use this external store as source of truth.
 */
import { create } from 'zustand';

interface NodeNoteState {
  notes: Map<string, string>; // nodeId -> agentNote text
  setNote: (nodeId: string, note: string) => void;
  getNote: (nodeId: string) => string;
  clear: () => void;
}

export const useNodeNoteStore = create<NodeNoteState>((set, get) => ({
  notes: new Map<string, string>(),

  setNote: (nodeId: string, note: string) => {
    set((state) => {
      const newMap = new Map(state.notes);
      if (note) {
        newMap.set(nodeId, note);
      } else {
        newMap.delete(nodeId);
      }
      return { notes: newMap };
    });
  },

  getNote: (nodeId: string) => get().notes.get(nodeId) || '',

  clear: () => {
    set({ notes: new Map() });
  },
}));
