import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { App } from 'antd';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, params?: Record<string, any>) =>
      params && Object.keys(params).length && !('defaultValue' in params) ? `${key}:${JSON.stringify(params)}` : key,
  }),
}));

jest.mock('@/utils/eventBus', () => ({ eventBus: { on: jest.fn(), off: jest.fn(), emit: jest.fn() } }));

const overview = {
  tenant: { id: 't1', name: '我的店铺', kind: 'merchant' },
  kbs: [{ id: 'kb1', name: '商品知识库', plane: 'local', kind: 'catalog', index_profile: 'vector', sensitivity: 'internal' }],
  stores: [{ id: 's1', tenant_id: 't1', name: '天猫店', platform: 'tmall', platform_store_id: '', ecan_store_id: '', product_count: 2, policy_overrides: 1 }],
  stats: { products: 0, stores: 1, policies: 0, documents: 0, chunks: 0, faqs: 0 },
  categories: [],
  embedder: { id: 'hashing-ngram-v1:512', is_fallback: true, needs_reindex: true, stale_embedders: ['old'] },
  jobs: [],
};

const searchResult = {
  query: '材质', tier: 0, store: overview.stores[0],
  product: { id: 'p1', code: 'TS-001', title: '纯棉T恤', category: '', brand: '' },
  facts: [{ key: '材质', value: '100%棉', source: 'attribute' }],
  policies: [], faq: [], chunks: [], candidates: [],
  timings_ms: { scope: 1, tier0_facts: 1, embed_query: 2, search: 3, total: 7 },
  confidence: 0.9, should_answer: true, reason: '', context: '[商品] 纯棉T恤',
};

const ksApi = {
  overview: jest.fn().mockResolvedValue(overview),
  listProducts: jest.fn().mockResolvedValue({ items: [], total: 0 }),
  listJobs: jest.fn().mockResolvedValue([]),
  getPolicies: jest.fn().mockResolvedValue({ topics: [{ value: 'returns', label: '退换货' }], defaults: {}, overrides: {}, stores: overview.stores }),
  search: jest.fn().mockResolvedValue(searchResult),
  reindex: jest.fn().mockResolvedValue({ id: 'j1', kind: 'reindex', title: '重新建立索引', status: 'running', stage: 'embed', progress: 0.5, done: 5, total: 10, message: '', errors: [], result: {}, created_at: '', updated_at: '' }),
  getJob: jest.fn(),
  pickFiles: jest.fn().mockResolvedValue(['C:/x/catalog.csv']),
  previewCatalog: jest.fn().mockResolvedValue({
    path: 'C:/x/catalog.csv', filename: 'catalog.csv', headers: ['宝贝标题', '一口价'],
    mapping: { '宝贝标题': 'title', '一口价': 'price' },
    fields: [{ value: 'title', label: 'Title' }, { value: 'price', label: 'Price' }],
    rows_preview: [{ '宝贝标题': '纯棉T恤', '一口价': '59' }],
    report: { rows_total: 1, products: 1, variants: 0, listings: 0, skipped: [], skipped_count: 0, warnings: [], warning_count: 0, errors: [], ignored_columns: ['一口价'] },
    products_preview: [], stores_in_file: [],
  }),
  listConnections: jest.fn().mockResolvedValue([{ id: 'c1', name: '公司服务器', plane: 'private', base_url: 'http://10.0.0.5:8790',
    tenant_id: 'tn_1', auth: 'local', enabled: true, verify_tls: true, send_queries: true, signed_in: false }]),
  testConnection: jest.fn().mockResolvedValue({ ok: true, steps: [
    { step: 'reach', ok: true, detail: 'plane=private', ms: 12 }, { step: 'identity', ok: true, detail: 'fae@corp.cn' },
    { step: 'tenant', ok: true, detail: '设计公司 (owner)' }] }),
  access: jest.fn().mockImplementation((op: string) => Promise.resolve(op === 'audit' ? [] : {
    tenant: { id: 'tn_1', name: '设计公司' },
    members: [{ id: 'm1', email: 'fae@corp.cn', user_id: 'fae', display_name: '', role: 'owner', status: 'active' }],
    groups: [], grants: [], stores: [], me: { user_id: 'fae', email: 'fae@corp.cn' },
    kbs: [{ id: 'kb1', name: '产品资料', plane: 'private', sensitivity: 'confidential', kind: 'catalog' }],
  })),
};

jest.mock('@/services/ipc/ksApi', () => ({ ksApi }));

import ProductKnowledgeTab from '../../pages/Knowledge/ProductKnowledge';

const renderTab = () => render(<App><ProductKnowledgeTab /></App>);

describe('ProductKnowledgeTab', () => {
  beforeAll(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: (q: string) => ({ matches: false, media: q, onchange: null, addListener: jest.fn(), removeListener: jest.fn(),
        addEventListener: jest.fn(), removeEventListener: jest.fn(), dispatchEvent: jest.fn() }),
    });
  });

  it('shows stats, onboarding, stores and the re-index warning', async () => {
    renderTab();
    expect(await screen.findByText('天猫店')).toBeInTheDocument();
    expect(screen.getByText('pages.knowledge.ks.gettingStarted')).toBeInTheDocument();
    expect(screen.getByText('pages.knowledge.ks.reindexNeeded')).toBeInTheDocument();
    fireEvent.click(screen.getByText('pages.knowledge.ks.reindex'));
    await waitFor(() => expect(ksApi.reindex).toHaveBeenCalled());
    expect(await screen.findByText('重新建立索引')).toBeInTheDocument();  // job progress card
  });

  it('walks the import wizard to the column mapping step', async () => {
    renderTab();
    await screen.findByText('天猫店');
    fireEvent.click(screen.getByText('pages.knowledge.ks.tabs.import'));
    fireEvent.click(await screen.findByText('pages.knowledge.ks.import.chooseFile'));
    expect(await screen.findByText('catalog.csv')).toBeInTheDocument();
    expect(screen.getByText('宝贝标题')).toBeInTheDocument();
    expect(ksApi.previewCatalog).toHaveBeenCalledWith('C:/x/catalog.csv');
  });

  it('lists servers, shows sign-in state and runs a step-by-step connection test', async () => {
    renderTab();
    await screen.findByText('天猫店');
    fireEvent.click(screen.getByText('pages.knowledge.ks.tabs.servers'));
    expect(await screen.findByText('公司服务器')).toBeInTheDocument();
    expect(screen.getByText('pages.knowledge.ks.connections.notSignedIn')).toBeInTheDocument();
    fireEvent.click(screen.getByText('pages.knowledge.ks.connections.test'));
    expect(await screen.findByText('pages.knowledge.ks.connections.ready')).toBeInTheDocument();
    expect(screen.getByText(/设计公司 \(owner\)/)).toBeInTheDocument();
  });

  it('shows members and the confidential warning in access management', async () => {
    renderTab();
    await screen.findByText('天猫店');
    fireEvent.click(screen.getByText('pages.knowledge.ks.tabs.access'));
    expect(await screen.findByText('pages.knowledge.ks.access.confidentialHint')).toBeInTheDocument();
    expect(screen.getAllByText('fae@corp.cn').length).toBeGreaterThan(0);
  });

  it('asks a buyer question and shows tier, facts and context', async () => {
    renderTab();
    await screen.findByText('天猫店');
    fireEvent.click(screen.getByText('pages.knowledge.ks.tabs.test'));
    fireEvent.click(await screen.findByText('这件是什么材质的'));
    expect(await screen.findByText('pages.knowledge.ks.test.tier0')).toBeInTheDocument();
    expect(screen.getByText('100%棉')).toBeInTheDocument();
    expect(screen.getByText('[商品] 纯棉T恤')).toBeInTheDocument();
  });
});
