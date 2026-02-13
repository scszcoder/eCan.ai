import { create } from 'zustand';
import { apiRouter } from '../services/api/api-router';
import type { APIResponse } from '../services/ipc/api';
import { GRAPHQL_QUERIES, GRAPHQL_MUTATIONS } from '../services/api/api-config';
import type { Product } from '../pages/Products/types';

/**
 * Unpack product from GraphQL response.
 * The lambda packs non-schema fields into `attributes` AWSJSON.
 * For IPC, the data comes as-is.
 */
function unpackProduct(raw: any): Product {
  if (!raw || typeof raw !== 'object') return raw;
  // If attributes is a JSON string containing extra fields, merge them in
  if (typeof raw.attributes === 'string') {
    try {
      const extra = JSON.parse(raw.attributes);
      if (extra && typeof extra === 'object') {
        const { _filepath, _filename, ...rest } = extra;
        return { ...raw, ...rest, id: raw.id };
      }
    } catch { /* ignore parse error */ }
  }
  return raw;
}

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
      const res: APIResponse<any> = await apiRouter.execute(
        {
          method: 'get_products',
          graphql: {
            query: GRAPHQL_QUERIES.GET_PRODUCTS,
            resultPath: 'getProducts'
          }
        },
        { username }
      );
      if (res.success) {
        // IPC returns { products: Product[] }, GraphQL returns Product[] via resultPath
        const raw = Array.isArray(res.data) ? res.data : (res.data?.products ?? []);
        const list = raw.map(unpackProduct) as Product[];
        set({ products: list, loading: false, fetched: true });
      } else {
        throw new Error((res as any).error?.message || 'Failed to fetch products');
      }
    } catch (e: any) {
      set({ loading: false, error: e?.message || 'Unknown error' });
    }
  },
  save: async (username: string, product: Product) => {
    try {
      const exists = get().products.some(p => p.id === product.id);
      const mutation = exists ? GRAPHQL_MUTATIONS.UPDATE_PRODUCTS : GRAPHQL_MUTATIONS.ADD_PRODUCTS;
      const resultPath = exists ? 'updateProducts' : 'addProducts';
      const res: APIResponse<any> = await apiRouter.execute(
        {
          method: 'save_product',
          graphql: { mutation, resultPath }
        },
        { username, product, input: [product] }
      );
      if (!res.success) throw new Error((res as any).error?.message || 'Failed to save');
      // IPC returns { product: Product }, GraphQL returns [Product]
      const rawSaved = Array.isArray(res.data) ? res.data[0] : (res.data?.product ?? product);
      const saved = unpackProduct(rawSaved);
      set((state) => {
        const ex = state.products.some(p => p.id === saved.id);
        return { products: ex ? state.products.map(p => (p.id === saved.id ? saved : p)) : [saved, ...state.products] } as Partial<ProductStoreState>;
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
          method: 'delete_product',
          graphql: {
            mutation: GRAPHQL_MUTATIONS.REMOVE_PRODUCTS,
            resultPath: 'removeProducts'
          }
        },
        { username, id, ids: [id] }
      );
      if (!res.success) throw new Error((res as any).error?.message || 'Failed to delete');
      set((state) => ({ products: state.products.filter(p => p.id !== id) }));
      return true;
    } catch (e) {
      return false;
    }
  },
}));
