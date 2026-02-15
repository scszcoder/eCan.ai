import { create } from 'zustand';
import { apiRouter } from '../services/api/api-router';
import type { APIResponse } from '../services/ipc/api';
import { GRAPHQL_QUERIES, GRAPHQL_MUTATIONS } from '../services/api/api-config';
import type { Warehouse } from '../pages/Warehouses/types';

/**
 * Unpack warehouse from GraphQL response.
 * The lambda packs non-schema fields into `notes` as JSON.
 * For IPC, the data comes as-is.
 */
function unpackWarehouse(raw: any): Warehouse {
  if (!raw || typeof raw !== 'object') return raw;
  // If notes looks like JSON with extra fields, merge them in
  if (typeof raw.notes === 'string' && raw.notes.startsWith('{')) {
    try {
      const extra = JSON.parse(raw.notes);
      if (extra && typeof extra === 'object') {
        const { _filepath, _filename, ...rest } = extra;
        return { ...raw, ...rest, id: raw.id, notes: undefined };
      }
    } catch { /* not JSON, keep as-is */ }
  }
  return raw;
}

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
      const res: APIResponse<any> = await apiRouter.execute(
        {
          method: 'get_warehouses',
          graphql: {
            query: GRAPHQL_QUERIES.GET_WAREHOUSES,
            resultPath: 'getWarehouses'
          }
        },
        { username }
      );
      if (res.success) {
        // IPC returns { warehouses: Warehouse[] }, GraphQL returns Warehouse[] via resultPath
        const raw = Array.isArray(res.data) ? res.data : (res.data?.warehouses ?? []);
        const list = raw.map(unpackWarehouse) as Warehouse[];
        set({ warehouses: list, loading: false, fetched: true });
      } else {
        throw new Error((res as any).error?.message || 'Failed to fetch warehouses');
      }
    } catch (e: any) {
      set({ loading: false, error: e?.message || 'Unknown error' });
    }
  },
  save: async (username: string, warehouse: Warehouse) => {
    try {
      const exists = get().warehouses.some(w => w.id === warehouse.id);
      const mutation = exists ? GRAPHQL_MUTATIONS.UPDATE_WAREHOUSES : GRAPHQL_MUTATIONS.ADD_WAREHOUSES;
      const resultPath = exists ? 'UpdateWarehouses' : 'addWareHouses';
      const res: APIResponse<any> = await apiRouter.execute(
        {
          method: 'save_warehouse',
          graphql: { mutation, resultPath }
        },
        { username, warehouse, input: [warehouse] }
      );
      if (!res.success) throw new Error((res as any).error?.message || 'Failed to save');
      // IPC returns { warehouse: Warehouse }, GraphQL returns [Warehouse]
      const rawSaved = Array.isArray(res.data) ? res.data[0] : (res.data?.warehouse ?? warehouse);
      const saved = unpackWarehouse(rawSaved);
      set((state) => {
        const ex = state.warehouses.some(w => w.id === saved.id);
        return {
          warehouses: ex ? state.warehouses.map(w => (w.id === saved.id ? saved : w)) : [saved, ...state.warehouses],
        } as Partial<WarehouseStoreState>;
      });
      return saved;
    } catch (e) {
      return null;
    }
  },
  remove: async (username: string, id: string) => {
    try {
      const res: APIResponse<any> = await apiRouter.execute(
        {
          method: 'delete_warehouse',
          graphql: {
            mutation: GRAPHQL_MUTATIONS.REMOVE_WAREHOUSES,
            resultPath: 'RemoveWareHouses'
          }
        },
        { username, id, ids: [id] }
      );
      if (!res.success) throw new Error((res as any).error?.message || 'Failed to delete');
      set((state) => ({ warehouses: state.warehouses.filter(w => w.id !== id) }));
      return true;
    } catch (e) {
      return false;
    }
  },
}));
