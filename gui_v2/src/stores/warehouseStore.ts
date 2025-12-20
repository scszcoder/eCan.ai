import { create } from 'zustand';
import { IPCAPI, type APIResponse } from '../services/ipc';
import type { Warehouse } from '../pages/Warehouses/types';

interface WarehouseStoreState {
  warehouses: Warehouse[];
  loading: boolean;
  error: string | null;
  fetched: boolean;
  fetch: (username: string) => Promise<void>;
  save: (username: string, warehouse: Warehouse) => Promise<Warehouse | null>;
  remove: (username: string, id: string) => Promise<boolean>;
}

export const useWarehouseStore = create<WarehouseStoreState>((set, get) => ({
  warehouses: [],
  loading: false,
  error: null,
  fetched: false,
  fetch: async (username: string) => {
    if (get().loading) return;
    set({ loading: true, error: null });
    try {
      const res: APIResponse<{ warehouses: Warehouse[] }> = await IPCAPI.getInstance().executeRequest('get_warehouses', { username });
      if (res.success) {
        const list = (res.data?.warehouses ?? []) as Warehouse[];
        set({ warehouses: list, loading: false, fetched: true });
      } else {
        throw new Error(res.error?.message || 'Failed to fetch warehouses');
      }
    } catch (e: any) {
      set({ loading: false, error: e?.message || 'Unknown error' });
    }
  },
  save: async (username: string, warehouse: Warehouse) => {
    try {
      const res: APIResponse<{ warehouse: Warehouse }> = await IPCAPI.getInstance().executeRequest('save_warehouse', { username, warehouse });
      if (!res.success) throw new Error(res.error?.message || 'Failed to save');
      const saved = res.data?.warehouse ?? warehouse;
      set((state) => {
        const exists = state.warehouses.some(w => w.id === saved.id);
        return {
          warehouses: exists ? state.warehouses.map(w => (w.id === saved.id ? saved : w)) : [saved, ...state.warehouses],
        } as Partial<WarehouseStoreState>;
      });
      return saved;
    } catch (e) {
      return null;
    }
  },
  remove: async (username: string, id: string) => {
    try {
      const res: APIResponse<any> = await IPCAPI.getInstance().executeRequest('delete_warehouse', { username, id });
      if (!res.success) throw new Error(res.error?.message || 'Failed to delete');
      set((state) => ({ warehouses: state.warehouses.filter(w => w.id !== id) }));
      return true;
    } catch (e) {
      return false;
    }
  },
}));
