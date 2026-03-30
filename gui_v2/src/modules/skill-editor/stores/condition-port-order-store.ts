import { create } from 'zustand';

interface ConditionPortOrderState {
  portOrders: Map<string, string[]>;
  setPortOrder: (nodeId: string, order: string[]) => void;
  getPortOrder: (nodeId: string) => string[] | undefined;
  clear: () => void;
}

export const useConditionPortOrderStore = create<ConditionPortOrderState>((set, get) => ({
  portOrders: new Map<string, string[]>(),

  setPortOrder: (nodeId: string, order: string[]) => {
    set((state) => {
      const current = state.portOrders.get(nodeId) ?? [];
      if (
        current.length === order.length &&
        current.every((value, index) => value === order[index])
      ) {
        return state;
      }
      const next = new Map(state.portOrders);
      if (order.length > 0) {
        next.set(nodeId, [...order]);
      } else {
        next.delete(nodeId);
      }
      return { portOrders: next };
    });
  },

  getPortOrder: (nodeId: string) => get().portOrders.get(nodeId),

  clear: () => set({ portOrders: new Map<string, string[]>() }),
}));
