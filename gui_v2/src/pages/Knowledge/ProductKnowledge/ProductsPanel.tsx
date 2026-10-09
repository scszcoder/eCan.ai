import React, { useCallback, useEffect, useState } from 'react';
import { App, Button, Drawer, Empty, Input, Popconfirm, Select, Space, Table, Tag, Tooltip, Typography } from 'antd';
import { DeleteOutlined, EditOutlined, FileAddOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { ksApi, KSOverview, KSProduct } from '@/services/ipc/ksApi';
import ProductEditor, { emptyProduct } from './ProductEditor';

const { Text } = Typography;

const DOC_EXTS = ['pdf', 'docx', 'txt', 'md'];

interface Props {
  overview: KSOverview | null;
  onChanged: () => void;
  /** Open the editor with this product (e.g. a document draft) when set. */
  draft?: { product: KSProduct; attachPath?: string } | null;
  onDraftConsumed?: () => void;
}

const ProductsPanel: React.FC<Props> = ({ overview, onChanged, draft, onDraftConsumed }) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const k = (key: string, opts?: Record<string, unknown>): string => String(t(`pages.knowledge.ks.products.${key}`, opts as any));
  const stores = overview?.stores || [];
  const categories = (overview?.categories || []).map(c => c.category).filter(Boolean);

  const [q, setQ] = useState('');
  const [category, setCategory] = useState<string>();
  const [storeId, setStoreId] = useState<string>();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [data, setData] = useState<{ items: KSProduct[]; total: number }>({ items: [], total: 0 });
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState<KSProduct | null>(null);
  const [attachPath, setAttachPath] = useState<string>();
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await ksApi.listProducts({ q, category, store_id: storeId, offset: (page - 1) * pageSize, limit: pageSize }));
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }, [q, category, storeId, page, pageSize, message]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (draft) {
      setEditing(draft.product);
      setAttachPath(draft.attachPath);
      onDraftConsumed?.();
    }
  }, [draft, onDraftConsumed]);

  const openEdit = async (id?: string) => {
    setAttachPath(undefined);
    if (!id) {
      setEditing(emptyProduct());
      return;
    }
    try {
      setEditing(await ksApi.getProduct(id));
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const save = async () => {
    if (!editing) return;
    if (!editing.title.trim()) {
      message.warning(k('titleRequired'));
      return;
    }
    setSaving(true);
    try {
      await ksApi.saveProduct(editing, attachPath);
      message.success(k('saved'));
      setEditing(null);
      setAttachPath(undefined);
      load();
      onChanged();
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  const attachDoc = async () => {
    if (!editing?.id) return;
    const paths = await ksApi.pickFiles(DOC_EXTS, k('docFiles'), false);
    if (!paths.length) return;
    const hide = message.loading(k('attaching'), 0);
    try {
      await ksApi.attachDocument(editing.id, paths[0]);
      setEditing(await ksApi.getProduct(editing.id));
      message.success(k('attached'));
    } catch (e: any) {
      message.error(e.message);
    } finally {
      hide();
    }
  };

  const storeName = (id: string) => stores.find(s => s.id === id)?.name || id;

  const columns = [
    {
      title: k('colTitle'), dataIndex: 'title', key: 'title', ellipsis: true,
      render: (_: any, p: KSProduct) => (
        <Space direction="vertical" size={0}>
          <a onClick={() => openEdit(p.id)}>{p.title}</a>
          <Text type="secondary" style={{ fontSize: 12 }}>{p.code}{p.brand ? ` · ${p.brand}` : ''}</Text>
        </Space>
      ),
    },
    { title: k('colCategory'), dataIndex: 'category', key: 'category', width: 140, render: (c: string) => c ? <Tag>{c}</Tag> : '—' },
    {
      title: k('colStores'), key: 'stores', width: 220,
      render: (_: any, p: KSProduct) => (p.listings || []).length === 0
        ? <Tooltip title={k('noListingHint')}><Tag color="warning">{k('noListing')}</Tag></Tooltip>
        : <Space size={[4, 4]} wrap>{(p.listings || []).map(l => (
          <Tooltip key={l.store_id} title={l.platform_item_id ? `${k('itemId')}: ${l.platform_item_id}` : k('noItemId')}>
            <Tag color={l.platform_item_id ? 'blue' : 'default'}>{storeName(l.store_id)}</Tag>
          </Tooltip>
        ))}</Space>,
    },
    {
      title: k('colKnowledge'), key: 'knowledge', width: 180,
      render: (_: any, p: KSProduct) => (
        <Space size={4} wrap>
          <Tag>{k('attrCount', { count: Object.keys(p.attributes || {}).length })}</Tag>
          <Tag color={p.faq?.length ? 'green' : 'default'}>FAQ {p.faq?.length || 0}</Tag>
          {p.size_chart?.rows?.length ? <Tag color="purple">{k('sizeChart')}</Tag> : null}
          {p.doc_count ? <Tag color="cyan">{k('docCount', { count: p.doc_count })}</Tag> : null}
        </Space>
      ),
    },
    {
      title: '', key: 'actions', width: 90,
      render: (_: any, p: KSProduct) => (
        <Space>
          <Button size="small" type="text" icon={<EditOutlined />} onClick={() => openEdit(p.id)} />
          <Popconfirm title={k('deleteConfirm', { title: p.title })} okButtonProps={{ danger: true }}
                      onConfirm={async () => { await ksApi.deleteProduct(p.id!); load(); onChanged(); }}>
            <Button size="small" type="text" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Space wrap style={{ marginBottom: 12 }}>
        <Input.Search allowClear placeholder={k('searchPlaceholder')} style={{ width: 260 }}
                      onSearch={v => { setPage(1); setQ(v.trim()); }} />
        <Select allowClear placeholder={k('allStores')} style={{ width: 180 }} value={storeId}
                options={stores.map(s => ({ value: s.id, label: s.name }))} onChange={v => { setPage(1); setStoreId(v); }} />
        <Select allowClear placeholder={k('allCategories')} style={{ width: 180 }} value={category}
                options={categories.map(c => ({ value: c, label: c }))} onChange={v => { setPage(1); setCategory(v); }} />
        <Button icon={<ReloadOutlined />} onClick={load} />
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openEdit()}>{k('new')}</Button>
      </Space>

      <Table
        rowKey="id" size="middle" loading={loading} columns={columns as any} dataSource={data.items}
        locale={{ emptyText: <Empty description={k('empty')} /> }}
        pagination={{
          current: page, pageSize, total: data.total, showSizeChanger: true,
          showTotal: total => k('total', { count: total }),
          onChange: (p, s) => { setPage(p); setPageSize(s); },
        }}
      />

      <Drawer
        width={760} open={!!editing} destroyOnClose
        title={editing?.id ? k('edit') : attachPath ? k('reviewDraft') : k('new')}
        onClose={() => { setEditing(null); setAttachPath(undefined); }}
        extra={
          <Space>
            {editing?.id && <Button icon={<FileAddOutlined />} onClick={attachDoc}>{k('attachDoc')}</Button>}
            <Button type="primary" loading={saving} onClick={save}>{k('save')}</Button>
          </Space>
        }
      >
        {attachPath && <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>{k('draftFrom', { file: attachPath.split(/[\\/]/).pop() })}</Text>}
        {editing && (
          <ProductEditor key={editing.id || attachPath || 'new'} value={editing} onChange={setEditing}
                         stores={stores} categories={categories} />
        )}
        {editing?.documents && editing.documents.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <Text strong>{k('documents')}</Text>
            {editing.documents.map(d => (
              <div key={d.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                <Text>{d.filename} <Text type="secondary">· {k('chunkCount', { count: d.chunk_count })}</Text></Text>
                <Popconfirm title={k('deleteDocConfirm')} onConfirm={async () => {
                  await ksApi.deleteDocument(d.id);
                  setEditing(await ksApi.getProduct(editing.id!));
                }}>
                  <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              </div>
            ))}
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default ProductsPanel;
