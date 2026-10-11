// Knowledge Service (ks.*) IPC client — product knowledge for e-commerce Q&A.
import { get_ipc_api } from '@/services/ipc_api';

export interface KSStore {
  id: string;
  tenant_id: string;
  name: string;
  platform: string;
  platform_store_id: string;
  ecan_store_id: string;
  product_count?: number;
  policy_overrides?: number;
}

export interface KSListing {
  id?: string;
  store_id: string;
  platform_item_id: string;
  title_override?: string;
}

export interface KSSizeChart {
  headers?: string[];
  rows?: string[][];
}

export interface KSProduct {
  id?: string;
  code: string;
  title: string;
  category: string;
  brand: string;
  attributes: Record<string, string>;
  variants: Record<string, string>[];
  size_chart: KSSizeChart;
  selling_points: string[];
  description: string;
  care: string;
  faq: { q: string; a: string }[];
  images: string[];
  source?: string;
  listings?: KSListing[];
  updated_at?: string;
  chunk_count?: number;
  doc_count?: number;
  documents?: { id: string; filename: string; doc_type: string; chunk_count: number; created_at: string }[];
}

export interface KSJob {
  id: string;
  kind: string;
  title: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  stage: string;
  progress: number;
  done: number;
  total: number;
  message: string;
  errors: string[];
  result: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface KSImportReport {
  rows_total: number;
  products: number;
  variants: number;
  listings: number;
  skipped: { row: number; reason: string }[];
  skipped_count: number;
  warnings: string[];
  warning_count: number;
  errors: string[];
  ignored_columns: string[];
}

export interface KSPendingImport {
  id: string;
  path: string;
  file_name: string;
  store_id: string;
  source: string;
  note: string;
  rows: number;
  created_at: number;
}

export interface KSCatalogPreview {
  path: string;
  filename: string;
  headers: string[];
  mapping: Record<string, string>;
  fields: { value: string; label: string }[];
  rows_preview: Record<string, string>[];
  report: KSImportReport;
  products_preview: KSProduct[];
  stores_in_file: string[];
}

export interface KSOverview {
  tenant: { id: string; name: string; kind: string };
  kbs: { id: string; name: string; plane: string; kind: string; index_profile: string; sensitivity: string }[];
  stores: KSStore[];
  stats: { products: number; stores: number; policies: number; documents: number; chunks: number; faqs: number };
  categories: { category: string; count: number }[];
  embedder: { id: string; is_fallback: boolean; needs_reindex: boolean; stale_embedders: string[] };
  jobs: KSJob[];
}

export interface KSPolicy {
  id: string;
  store_id: string | null;
  topic: string;
  title: string;
  text: string;
  updated_at: string;
  inherited?: boolean;
}

export interface KSPoliciesView {
  topics: { value: string; label: string }[];
  defaults: Record<string, KSPolicy>;
  overrides: Record<string, Record<string, KSPolicy>>;
  stores: KSStore[];
}

export interface KSSearchResult {
  query: string;
  tier: 0 | 1 | 2 | 3;
  store: KSStore | null;
  product: { id: string; code: string; title: string; category: string; brand: string } | null;
  facts: { key: string; value: string; source: string }[];
  policies: KSPolicy[];
  faq: { question: string; answer: string; score: number; product_id: string }[];
  chunks: { text: string; doc_type: string; product_id: string | null; score: number; keyword_score: number; matched_terms: string[] }[];
  candidates: { id: string; title: string; code: string; score: number }[];
  timings_ms: Record<string, number>;
  confidence: number;
  should_answer: boolean;
  reason: string;
  context: string;
}

export interface KSDraft {
  path: string;
  filename: string;
  draft: KSProduct;
  stats: { chars: number; tables: number; attributes: number; faq: number; has_size_chart: boolean };
  text_preview: string;
}

export interface KSConnection {
  id: string;
  name: string;
  plane: 'private' | 'public';
  base_url: string;
  tenant_id: string;
  auth: 'app' | 'local';
  enabled: boolean;
  verify_tls: boolean;
  send_queries: boolean;
  signed_in?: boolean;
}

export interface KSConnectionTest {
  ok: boolean;
  steps: { step: string; ok: boolean; detail: string; ms?: number; tenants?: { id: string; name: string; role: string }[] }[];
}

export interface KSMember {
  id: string;
  email: string;
  user_id: string;
  display_name: string;
  role: 'owner' | 'admin' | 'editor' | 'viewer';
  status: 'active' | 'invited' | 'disabled';
  groups?: string[];
}

export interface KSAccessView {
  tenant: { id: string; name: string; email_domain?: string };
  members: KSMember[];
  groups: { id: string; name: string; description: string; member_ids: string[] }[];
  grants: { id: string; kb_id: string; principal_type: string; principal_id: string; permission: string }[];
  kbs: { id: string; name: string; plane: string; sensitivity: string; kind: string }[];
  stores: KSStore[];
  me: { user_id: string; email: string };
}

export interface KSRouterResult extends KSSearchResult {
  plane: string;
  sensitivity: string;
  source?: string;
  planes: { source: string; plane: string; confidence: number; should_answer: boolean; tier: number }[];
  plane_errors: { source: string; plane: string; error: string }[];
  router_ms: number;
}

export interface KSLanStatus {
  role: string;
  enabled: boolean;
  port: number;
  running: boolean;
  error: string;
  addresses: string[];
  devices: { id: string; name: string; ip: string; paired_at: number; last_seen: number }[];
  source: { mode: 'local' | 'commander'; url: string; commander: string; paired: boolean };
}

async function call<T>(method: string, params: Record<string, any> = {}, timeout?: number): Promise<T> {
  const resp = await get_ipc_api().executeRequest<T>(method, params, timeout);
  if (!resp.success) {
    throw new Error(resp.error?.message || `${method} failed`);
  }
  return resp.data as T;
}

export const ksApi = {
  overview: () => call<KSOverview>('ks.overview'),
  updateTenant: (name: string) => call('ks.updateTenant', { name }),
  saveStore: (store: Partial<KSStore>) => call<KSStore>('ks.saveStore', store),
  deleteStore: (id: string) => call('ks.deleteStore', { id }),

  listProducts: (p: { q?: string; category?: string; store_id?: string; offset?: number; limit?: number }) =>
    call<{ items: KSProduct[]; total: number }>('ks.listProducts', p),
  getProduct: (id: string) => call<KSProduct>('ks.getProduct', { id }),
  saveProduct: (product: KSProduct, attach_path?: string) =>
    call<KSProduct>('ks.saveProduct', { product, attach_path }, 120000),
  deleteProduct: (id: string) => call('ks.deleteProduct', { id }),

  previewCatalog: (path: string) => call<KSCatalogPreview>('ks.previewCatalog', { path }, 120000),
  recheckCatalog: (path: string, mapping: Record<string, string>) =>
    call<{ report: KSImportReport; products_preview: KSProduct[] }>('ks.recheckCatalog', { path, mapping }, 120000),
  importCatalog: (path: string, mapping: Record<string, string>, default_store_id?: string, pending_id?: string) =>
    call<KSJob>('ks.importCatalog', { path, mapping, default_store_id, ...(pending_id ? { pending_id } : {}) }),
  /** Catalog files an agent fetched (e.g. a store's product export), awaiting review. */
  listPendingImports: () => call<{ items: KSPendingImport[] }>('ks.listPendingImports', {}),
  dismissPendingImport: (id: string) => call<{ dismissed: boolean }>('ks.dismissPendingImport', { id }),

  writeCatalogTemplate: (dir: string) => call<{ path: string }>('ks.writeCatalogTemplate', { dir }),

  draftFromDocument: (path: string) => call<KSDraft>('ks.draftFromDocument', { path }, 120000),
  ingestProductFiles: (paths: string[], store_id?: string) => call<KSJob>('ks.ingestProductFiles', { paths, store_id }),
  attachDocument: (product_id: string, path: string) => call('ks.attachDocument', { product_id, path }, 120000),
  deleteDocument: (id: string) => call('ks.deleteDocument', { id }),

  getPolicies: () => call<KSPoliciesView>('ks.getPolicies'),
  savePolicy: (p: { topic: string; text: string; store_id?: string | null; title?: string }) =>
    call<KSPolicy>('ks.savePolicy', p),
  deletePolicy: (id: string) => call('ks.deletePolicy', { id }),

  search: (p: { query: string; store_id?: string; platform_item_id?: string; product_id?: string }) =>
    call<KSSearchResult>('ks.search', p, 60000),

  getJob: (id: string) => call<KSJob>('ks.getJob', { id }),
  listJobs: (limit = 30) => call<KSJob[]>('ks.listJobs', { limit }),
  cancelJob: (id: string) => call('ks.cancelJob', { id }),
  reindex: () => call<KSJob>('ks.reindex'),

  listAppStores: () => call<{ store_id: string; name: string; platform: string }[]>('ks.listAppStores'),
  syncAppStores: () => call<{ created: KSStore[] }>('ks.syncAppStores'),

  getEmbedder: () => call<{ mode: 'app' | 'openai'; base_url: string; model: string; verify_tls: boolean;
    has_api_key: boolean; active_id: string }>('ks.getEmbedder'),
  testEmbedder: (p: { base_url: string; model: string; api_key?: string; verify_tls?: boolean }) =>
    call<{ dim: number; ms: number; related: number; unrelated: number; separates: boolean; instruction: boolean }>(
      'ks.testEmbedder', p, 120000),
  setEmbedder: (p: { mode: 'app' | 'openai'; base_url?: string; model?: string; api_key?: string; verify_tls?: boolean }) =>
    call('ks.setEmbedder', p),

  lanStatus: () => call<KSLanStatus>('ks.lanStatus'),
  lanSetSharing: (enabled: boolean, port?: number) => call<KSLanStatus>('ks.lanSetSharing', { enabled, port }, 30000),
  lanNewCode: () => call<{ code: string; expires_in: number }>('ks.lanNewCode'),
  lanRevoke: (id: string) => call('ks.lanRevoke', { id }),
  lanDiscover: () => call<{ machine_name: string; host: string; url: string; sharing: boolean }[]>('ks.lanDiscover', {}, 30000),
  lanPair: (url: string, code: string, commander?: string) =>
    call<KSLanStatus['source']>('ks.lanPair', { url, code, commander }, 30000),
  lanSetSource: (mode: 'local' | 'commander') => call<KSLanStatus['source']>('ks.lanSetSource', { mode }),
  lanForget: () => call<KSLanStatus['source']>('ks.lanSetSource', { forget: true }),
  lanTestSource: () => call<{ ok: boolean; ms: number; detail: string }>('ks.lanTestSource', {}, 30000),

  listConnections: () => call<KSConnection[]>('ks.listConnections'),
  saveConnection: (c: Partial<KSConnection>) => call<KSConnection>('ks.saveConnection', c),
  deleteConnection: (id: string) => call('ks.deleteConnection', { id }),
  testConnection: (id: string) => call<KSConnectionTest>('ks.testConnection', { id }, 60000),
  loginConnection: (id: string, email: string, password: string) =>
    call<{ signed_in: boolean }>('ks.loginConnection', { id, email, password }, 60000),
  routerSearch: (p: { query: string; store_id?: string; platform_item_id?: string; product_id?: string }) =>
    call<KSRouterResult>('ks.routerSearch', p, 60000),

  /** Access admin on this computer (connection_id empty) or a connected server. */
  access: <T = any>(op: string, params: Record<string, any> = {}, connection_id?: string) =>
    call<T>('ks.access', { op, connection_id, ...params }, 60000),

  /** Native file picker (desktop). Returns absolute paths, or [] when cancelled. */
  pickFiles: async (extensions: string[], name: string, multiple = true): Promise<string[]> => {
    const resp = await get_ipc_api().executeRequest<any>('fs.selectFiles', {
      multiple,
      filters: [{ name, extensions }],
    }, 300000);
    if (!resp.success) throw new Error(resp.error?.message || 'file picker failed');
    return (resp.data?.paths as string[]) || [];
  },
  /** Native folder picker (desktop). Returns '' when cancelled. */
  pickFolder: async (): Promise<string> => {
    const resp = await get_ipc_api().executeRequest<any>('fs.selectDirectory', {}, 300000);
    if (!resp.success) throw new Error(resp.error?.message || 'folder picker failed');
    return (resp.data?.path as string) || '';
  },
};
