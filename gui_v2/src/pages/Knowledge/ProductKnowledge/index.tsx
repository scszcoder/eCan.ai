import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert, App, Button, Card, Col, Empty, Input, List, Modal, Popconfirm, Row, Select, Space, Statistic, Tabs, Tag, Tooltip, Typography,
} from 'antd';
import {
  ApiOutlined, AppstoreOutlined, CloudUploadOutlined, DeleteOutlined, EditOutlined, ExperimentOutlined, FileProtectOutlined,
  HistoryOutlined, PlusOutlined, SafetyOutlined, ShopOutlined, SyncOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { ksApi, KSJob, KSLanStatus, KSOverview, KSProduct, KSStore } from '@/services/ipc/ksApi';
import ProductsPanel from './ProductsPanel';
import ImportPanel from './ImportPanel';
import PoliciesPanel from './PoliciesPanel';
import TestPanel from './TestPanel';
import ConnectionsPanel from './ConnectionsPanel';
import AccessPanel from './AccessPanel';
import JobProgress from './JobProgress';
import { useJob } from './useJob';

const { Text, Paragraph } = Typography;

const PLATFORMS = ['taobao', 'tmall', 'douyin', 'pdd', 'jd', 'other'];

type SubTab = 'overview' | 'products' | 'import' | 'policies' | 'test' | 'servers' | 'access' | 'jobs';

const StoreModal: React.FC<{ store: Partial<KSStore> | null; onClose: () => void; onSaved: () => void }> = ({ store, onClose, onSaved }) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const k = (key: string): string => String(t(`pages.knowledge.ks.stores.${key}`));
  const [value, setValue] = useState<Partial<KSStore>>({});
  const [appStores, setAppStores] = useState<{ store_id: string; name: string; platform: string }[]>([]);
  useEffect(() => { setValue(store || {}); }, [store]);
  useEffect(() => { if (store) ksApi.listAppStores().then(setAppStores).catch(() => setAppStores([])); }, [store]);
  const save = async () => {
    try {
      await ksApi.saveStore(value);
      onSaved();
      onClose();
    } catch (e: any) {
      message.error(e.message);
    }
  };
  return (
    <Modal open={!!store} title={value.id ? k('edit') : k('add')} onCancel={onClose} onOk={save} okText={k('save')}
           okButtonProps={{ disabled: !value.name?.trim() }} destroyOnClose>
      <Text type="secondary">{k('name')} *</Text>
      <Input value={value.name} onChange={e => setValue({ ...value, name: e.target.value })} style={{ marginBottom: 8 }} />
      <Text type="secondary">{k('platform')}</Text>
      <Select style={{ width: '100%', marginBottom: 8 }} value={value.platform || undefined}
              options={PLATFORMS.map(p => ({ value: p, label: t(`pages.knowledge.ks.platforms.${p}`) }))}
              onChange={v => setValue({ ...value, platform: v })} />
      <Text type="secondary">{k('ecanStoreId')}</Text>
      <Select
        style={{ width: '100%' }} allowClear showSearch optionFilterProp="label"
        value={value.ecan_store_id || undefined} placeholder={k('ecanStoreIdHint')}
        options={appStores.map(s => ({ value: s.store_id, label: `${s.name} · ${s.store_id}` }))}
        onChange={v => {
          const picked = appStores.find(s => s.store_id === v);
          setValue({ ...value, ecan_store_id: v || '', name: value.name || picked?.name, platform: value.platform || picked?.platform });
        }}
      />
    </Modal>
  );
};

const JobsList: React.FC<{ refreshKey: number }> = ({ refreshKey }) => {
  const { t } = useTranslation();
  const [jobs, setJobs] = useState<KSJob[]>([]);
  useEffect(() => {
    let alive = true;
    const load = () => ksApi.listJobs(30).then(j => alive && setJobs(j)).catch(() => undefined);
    load();
    const timer = setInterval(load, 2000);
    return () => { alive = false; clearInterval(timer); };
  }, [refreshKey]);
  if (!jobs.length) return <Empty description={t('pages.knowledge.ks.jobs.empty')} />;
  return (
    <List
      dataSource={jobs}
      renderItem={job => (
        <List.Item>
          <div style={{ width: '100%' }}>
            <JobProgress job={job} />
            <Text type="secondary" style={{ fontSize: 11 }}>{new Date(job.created_at).toLocaleString()}</Text>
          </div>
        </List.Item>
      )}
    />
  );
};

const ProductKnowledgeTab: React.FC = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const k = (key: string, o?: Record<string, unknown>): string => String(t(`pages.knowledge.ks.${key}`, o as any));
  const [overview, setOverview] = useState<KSOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<SubTab>('overview');
  const [editingStore, setEditingStore] = useState<Partial<KSStore> | null>(null);
  const [draft, setDraft] = useState<{ product: KSProduct; attachPath?: string } | null>(null);
  const [jobsKey, setJobsKey] = useState(0);
  const [lan, setLan] = useState<KSLanStatus | null>(null);
  const reindexJob = useJob(job => {
    if (job.status === 'succeeded') message.success(job.message);
    refresh();
  });

  const refresh = useCallback(async () => {
    ksApi.lanStatus().then(setLan).catch(() => setLan(null));
    try {
      setOverview(await ksApi.overview());
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const changed = () => { refresh(); setJobsKey(x => x + 1); };

  const stats = overview?.stats;
  const emb = overview?.embedder;

  const overviewPane = (
    <div>
      {emb?.needs_reindex && (
        <Alert
          type="warning" showIcon style={{ marginBottom: 12 }}
          message={k('reindexNeeded')}
          description={k('reindexNeededHint', { model: emb.id })}
          action={<Button size="small" type="primary" icon={<SyncOutlined />} disabled={reindexJob.running}
                          onClick={async () => reindexJob.track(await ksApi.reindex())}>{k('reindex')}</Button>}
        />
      )}
      {emb?.is_fallback && (
        <Alert type="info" showIcon style={{ marginBottom: 12 }} message={k('fallbackEmbedder')} description={k('fallbackEmbedderHint')} />
      )}
      {reindexJob.job && <Card size="small" style={{ marginBottom: 12 }}><JobProgress job={reindexJob.job} /></Card>}

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {[
          ['products', stats?.products], ['stores', stats?.stores], ['faqs', stats?.faqs],
          ['policies', stats?.policies], ['documents', stats?.documents], ['chunks', stats?.chunks],
        ].map(([key, val]) => (
          <Col xs={12} md={8} xl={4} key={key as string}>
            <Card size="small"><Statistic title={k(`stats.${key}`)} value={(val as number) ?? 0} /></Card>
          </Col>
        ))}
      </Row>

      {stats && stats.products === 0 && (
        <Card size="small" style={{ marginBottom: 16 }}>
          <Space direction="vertical">
            <Text strong>{k('gettingStarted')}</Text>
            <Text>1. {k('step1')}</Text>
            <Text>2. {k('step2')}</Text>
            <Text>3. {k('step3')}</Text>
            <Text>4. {k('step4')}</Text>
            <Space>
              <Button icon={<ShopOutlined />} onClick={() => setEditingStore({})}>{k('stores.add')}</Button>
              <Button type="primary" icon={<CloudUploadOutlined />} onClick={() => setTab('import')}>{k('goImport')}</Button>
            </Space>
          </Space>
        </Card>
      )}

      <Card
        size="small"
        title={<Space><ShopOutlined />{k('stores.title')}</Space>}
        extra={<Space>
          <Tooltip title={k('stores.syncAppHint')}>
            <Button size="small" icon={<SyncOutlined />} onClick={async () => {
              try {
                const r = await ksApi.syncAppStores();
                message.success(k('stores.syncDone', { count: r.created.length }));
                changed();
              } catch (e: any) { message.error(e.message); }
            }}>{k('stores.syncApp')}</Button>
          </Tooltip>
          <Button size="small" icon={<PlusOutlined />} onClick={() => setEditingStore({})}>{k('stores.add')}</Button>
        </Space>}
      >
        <Paragraph type="secondary" style={{ fontSize: 12 }}>{k('stores.hint')}</Paragraph>
        {(overview?.stores || []).length === 0 ? <Empty description={k('stores.empty')} /> : (
          <List
            dataSource={overview?.stores || []}
            renderItem={s => (
              <List.Item actions={[
                <Button key="e" size="small" type="text" icon={<EditOutlined />} onClick={() => setEditingStore(s)} />,
                <Popconfirm key="d" title={k('stores.deleteConfirm', { name: s.name })} okButtonProps={{ danger: true }}
                            onConfirm={async () => { await ksApi.deleteStore(s.id); changed(); }}>
                  <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                </Popconfirm>,
              ]}>
                <List.Item.Meta
                  title={<Space>{s.name}{s.platform && <Tag>{t(`pages.knowledge.ks.platforms.${s.platform}`, { defaultValue: s.platform })}</Tag>}</Space>}
                  description={<Space size={12}>
                    <Text type="secondary">{k('stores.products', { count: s.product_count || 0 })}</Text>
                    <Tooltip title={k('stores.overridesHint')}>
                      <Text type="secondary">{k('stores.overrides', { count: s.policy_overrides || 0 })}</Text>
                    </Tooltip>
                  </Space>}
                />
              </List.Item>
            )}
          />
        )}
      </Card>

      <Card size="small" style={{ marginTop: 16 }} title={k('kbTitle')}>
        {(overview?.kbs || []).map(kb => (
          <Space key={kb.id} wrap>
            <Text strong>{kb.name}</Text>
            <Tooltip title={k(`plane.${kb.plane}Hint`)}><Tag color={kb.plane === 'private' ? 'red' : kb.plane === 'public' ? 'blue' : 'green'}>{k(`plane.${kb.plane}`)}</Tag></Tooltip>
            <Tag>{k(`profile.${kb.index_profile}`, { defaultValue: kb.index_profile })}</Tag>
            <Text type="secondary" style={{ fontSize: 12 }}>{k('embedderLabel')}: {emb?.id}</Text>
          </Space>
        ))}
      </Card>
    </div>
  );

  if (error && !overview) {
    return <Alert type="error" showIcon message={k('loadFailed')} description={error}
                  action={<Button onClick={refresh}>{k('retry')}</Button>} style={{ margin: 24 }} />;
  }

  return (
    <div style={{ padding: '12px 24px' }}>
      {lan?.source.mode === 'commander' && (
        <Alert type="info" showIcon style={{ marginBottom: 8 }}
               message={k('lan.usingCommanderBanner', { name: lan.source.commander || lan.source.url })}
               description={k('lan.usingCommanderBannerHint')}
               action={<Button size="small" onClick={() => setTab('servers')}>{k('lan.manage')}</Button>} />
      )}
      <Tabs
        activeKey={tab}
        onChange={key => setTab(key as SubTab)}
        items={[
          { key: 'overview', label: <span><AppstoreOutlined /> {k('tabs.overview')}</span>, children: overviewPane },
          {
            key: 'products', label: <span><ShopOutlined /> {k('tabs.products')}</span>,
            children: <ProductsPanel overview={overview} onChanged={changed} draft={draft} onDraftConsumed={() => setDraft(null)} />,
          },
          {
            key: 'import', label: <span><CloudUploadOutlined /> {k('tabs.import')}</span>,
            children: <ImportPanel overview={overview} onChanged={changed}
                                   onReviewDraft={(product, attachPath) => { setDraft({ product, attachPath }); setTab('products'); }} />,
          },
          { key: 'policies', label: <span><FileProtectOutlined /> {k('tabs.policies')}</span>, children: <PoliciesPanel onChanged={changed} /> },
          { key: 'test', label: <span><ExperimentOutlined /> {k('tabs.test')}</span>, children: <TestPanel overview={overview} /> },
          { key: 'servers', label: <span><ApiOutlined /> {k('tabs.servers')}</span>, children: <ConnectionsPanel onChanged={changed} /> },
          { key: 'access', label: <span><SafetyOutlined /> {k('tabs.access')}</span>, children: <AccessPanel /> },
          { key: 'jobs', label: <span><HistoryOutlined /> {k('tabs.jobs')}</span>, children: <JobsList refreshKey={jobsKey} /> },
        ]}
      />
      <StoreModal store={editingStore} onClose={() => setEditingStore(null)} onSaved={changed} />
    </div>
  );
};

export default ProductKnowledgeTab;
