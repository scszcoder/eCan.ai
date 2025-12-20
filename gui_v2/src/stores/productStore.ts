import { create } from 'zustand';
import { IPCAPI, type APIResponse } from '../services/ipc';
import type { Product } from '../pages/Products/types';

interface ProductStoreState {
  products: Product[];
  loading: boolean;
  error: string | null;
  fetched: boolean;
  fetch: (username: string) => Promise<void>;
  save: (username: string, product: Product) => Promise<Product | null>;
  remove: (username: string, id: string) => Promise<boolean>;
}

export const useProductStore = create<ProductStoreState>((set, get) => ({
  products: [],
  loading: false,
  error: null,
  fetched: false,
  fetch: async (username: string) => {
    if (get().loading) return;
    set({ loading: true, error: null });
    try {
      const res: APIResponse<{ products: Product[] }> = await IPCAPI.getInstance().executeRequest('get_products', { username });
      if (res.success) {
        const list = (res.data?.products ?? []) as Product[];
        set({ products: list, loading: false, fetched: true });
      } else {
        throw new Error(res.error?.message || 'Failed to fetch products');
      }
    } catch (e: any) {
      set({ loading: false, error: e?.message || 'Unknown error' });
    }
  },
  save: async (username: string, product: Product) => {
    try {
      const res: APIResponse<{ product: Product }> = await IPCAPI.getInstance().executeRequest('save_product', { username, product });
      if (!res.success) throw new Error(res.error?.message || 'Failed to save');
      const saved = res.data?.product ?? product;
      set((state) => {
        const exists = state.products.some(p => p.id === saved.id);
        return { products: exists ? state.products.map(p => (p.id === saved.id ? saved : p)) : [saved, ...state.products] } as Partial<ProductStoreState>;
      });
      return saved;
    } catch (e) {
      return null;
    }
  },
  remove: async (username: string, id: string) => {
    try {
      const res: APIResponse<any> = await IPCAPI.getInstance().executeRequest('delete_product', { username, id });
      if (!res.success) throw new Error(res.error?.message || 'Failed to delete');
      set((state) => ({ products: state.products.filter(p => p.id !== id) }));
      return true;
    } catch (e) {
      return false;
    }
  },
}));
