import React, { useState } from 'react';
import { Button, Card, Checkbox, Col, Empty, Input, Row, Select, Space, Tooltip, Typography } from 'antd';
import { DeleteOutlined, PlusOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { KSListing, KSProduct, KSStore } from '@/services/ipc/ksApi';

const { Text } = Typography;
const { TextArea } = Input;

export const emptyProduct = (): KSProduct => ({
  code: '', title: '', category: '', brand: '', attributes: {}, variants: [], size_chart: {},
  selling_points: [], description: '', care: '', faq: [], images: [], listings: [],
});

interface Props {
  value: KSProduct;
  onChange: (next: KSProduct) => void;
  stores: KSStore[];
  categories?: string[];
}

const Section: React.FC<{ title: string; hint?: string; extra?: React.ReactNode; children: React.ReactNode }> = ({ title, hint, extra, children }) => (
  <Card
    size="small"
    style={{ marginBottom: 12 }}
    title={<Space>{title}{hint && <Tooltip title={hint}><QuestionCircleOutlined style={{ color: '#999' }} /></Tooltip>}</Space>}
    extra={extra}
  >
    {children}
  </Card>
);

/** Editable canonical product record (used for new, edit and document drafts). */
const ProductEditor: React.FC<Props> = ({ value, onChange, stores, categories = [] }) => {
  const { t } = useTranslation();
  const k = (key: string): string => String(t(`pages.knowledge.ks.editor.${key}`));
  const set = (patch: Partial<KSProduct>) => onChange({ ...value, ...patch });

  // ---- attributes as ordered rows ------------------------------------------
  // Rows live in local state so half-typed rows (empty or duplicate keys)
  // survive; the parent remounts the editor (key=product id) to reset them.
  const [attrRows, setRows] = useState<[string, string][]>(() => Object.entries(value.attributes || {}));
  const setAttrRows = (rows: [string, string][]) => {
    setRows(rows);
    const obj: Record<string, string> = {};
    rows.forEach(([key, v]) => { if (key.trim()) obj[key.trim()] = v; });
    set({ attributes: obj });
  };

  // ---- listings ----------------------------------------------------------------
  const listings: KSListing[] = value.listings || [];
  const listingFor = (storeId: string) => listings.find(l => l.store_id === storeId);
  const toggleStore = (storeId: string, on: boolean) => {
    set({ listings: on ? [...listings, { store_id: storeId, platform_item_id: '' }] : listings.filter(l => l.store_id !== storeId) });
  };
  const setItemId = (storeId: string, itemId: string) => {
    set({ listings: listings.map(l => (l.store_id === storeId ? { ...l, platform_item_id: itemId.trim() } : l)) });
  };

  // ---- size chart --------------------------------------------------------------
  const headers = value.size_chart?.headers || [];
  const rows = value.size_chart?.rows || [];
  const setChart = (h: string[], r: string[][]) => set({ size_chart: h.length ? { headers: h, rows: r } : {} });

  return (
    <div>
      <Section title={k('basic')}>
        <Row gutter={12}>
          <Col span={16}>
            <Text type="secondary">{k('title')} *</Text>
            <Input value={value.title} status={value.title ? undefined : 'error'} placeholder={k('titlePlaceholder')}
                   onChange={e => set({ title: e.target.value })} />
          </Col>
          <Col span={8}>
            <Text type="secondary">{k('code')}</Text>
            <Input value={value.code} placeholder={k('codePlaceholder')} onChange={e => set({ code: e.target.value })} />
          </Col>
        </Row>
        <Row gutter={12} style={{ marginTop: 8 }}>
          <Col span={12}>
            <Text type="secondary">{k('category')}</Text>
            <Select
              style={{ width: '100%' }} showSearch allowClear value={value.category || undefined}
              placeholder={k('categoryPlaceholder')}
              options={[...new Set([value.category, ...categories].filter(Boolean))].map(c => ({ value: c, label: c }))}
              onSearch={() => undefined}
              onChange={v => set({ category: v || '' })}
              dropdownRender={menu => (
                <>
                  {menu}
                  <Input size="small" style={{ margin: 4, width: 'calc(100% - 8px)' }} placeholder={k('newCategory')}
                         onPressEnter={e => set({ category: (e.target as HTMLInputElement).value.trim() })} />
                </>
              )}
            />
          </Col>
          <Col span={12}>
            <Text type="secondary">{k('brand')}</Text>
            <Input value={value.brand} onChange={e => set({ brand: e.target.value })} />
          </Col>
        </Row>
      </Section>

      <Section title={k('stores')} hint={k('storesHint')}>
        {stores.length === 0 ? <Text type="secondary">{k('noStores')}</Text> : stores.map(s => {
          const l = listingFor(s.id);
          return (
            <Row key={s.id} gutter={8} align="middle" style={{ marginBottom: 6 }}>
              <Col span={10}><Checkbox checked={!!l} onChange={e => toggleStore(s.id, e.target.checked)}>{s.name}</Checkbox></Col>
              <Col span={14}>
                <Input size="small" disabled={!l} value={l?.platform_item_id} placeholder={k('itemIdPlaceholder')}
                       onChange={e => setItemId(s.id, e.target.value)} />
              </Col>
            </Row>
          );
        })}
      </Section>

      <Section
        title={k('attributes')} hint={k('attributesHint')}
        extra={<Button size="small" icon={<PlusOutlined />} onClick={() => setAttrRows([...attrRows, ['', '']])}>{k('add')}</Button>}
      >
        {attrRows.length === 0 && <Text type="secondary">{k('attributesEmpty')}</Text>}
        {attrRows.map(([key, v], i) => (
          <Row key={i} gutter={8} style={{ marginBottom: 6 }}>
            <Col span={8}>
              <Input size="small" value={key} placeholder={k('attrKey')}
                     onChange={e => setAttrRows(attrRows.map((r, j) => (j === i ? [e.target.value, r[1]] : r)))} />
            </Col>
            <Col span={14}>
              <Input size="small" value={v} placeholder={k('attrValue')}
                     onChange={e => setAttrRows(attrRows.map((r, j) => (j === i ? [r[0], e.target.value] : r)))} />
            </Col>
            <Col span={2}>
              <Button size="small" type="text" danger icon={<DeleteOutlined />} onClick={() => setAttrRows(attrRows.filter((_, j) => j !== i))} />
            </Col>
          </Row>
        ))}
      </Section>

      <Section title={k('sellingPoints')}>
        <Select mode="tags" style={{ width: '100%' }} value={value.selling_points} tokenSeparators={['\n', '；', ';']}
                placeholder={k('sellingPointsPlaceholder')} onChange={v => set({ selling_points: v })} open={false} />
      </Section>

      <Section
        title={k('faq')} hint={k('faqHint')}
        extra={<Button size="small" icon={<PlusOutlined />} onClick={() => set({ faq: [...value.faq, { q: '', a: '' }] })}>{k('add')}</Button>}
      >
        {value.faq.length === 0 && <Text type="secondary">{k('faqEmpty')}</Text>}
        {value.faq.map((qa, i) => (
          <Row key={i} gutter={8} style={{ marginBottom: 6 }}>
            <Col span={9}>
              <Input size="small" value={qa.q} placeholder={k('question')}
                     onChange={e => set({ faq: value.faq.map((x, j) => (j === i ? { ...x, q: e.target.value } : x)) })} />
            </Col>
            <Col span={13}>
              <Input size="small" value={qa.a} placeholder={k('answer')}
                     onChange={e => set({ faq: value.faq.map((x, j) => (j === i ? { ...x, a: e.target.value } : x)) })} />
            </Col>
            <Col span={2}>
              <Button size="small" type="text" danger icon={<DeleteOutlined />} onClick={() => set({ faq: value.faq.filter((_, j) => j !== i) })} />
            </Col>
          </Row>
        ))}
      </Section>

      <Section
        title={k('sizeChart')} hint={k('sizeChartHint')}
        extra={
          <Space>
            <Button size="small" onClick={() => setChart(headers.length ? [...headers, ''] : [k('sizeColumn'), ''], rows.map(r => [...r, '']))}>{k('addColumn')}</Button>
            <Button size="small" disabled={!headers.length} onClick={() => setChart(headers, [...rows, headers.map(() => '')])}>{k('addRow')}</Button>
          </Space>
        }
      >
        {headers.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={k('sizeChartEmpty')} /> : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  {headers.map((h, ci) => (
                    <th key={ci} style={{ padding: 2 }}>
                      <Input size="small" value={h} style={{ width: 90, fontWeight: 600 }}
                             onChange={e => setChart(headers.map((x, j) => (j === ci ? e.target.value : x)), rows)} />
                    </th>
                  ))}
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((r, ri) => (
                  <tr key={ri}>
                    {headers.map((_, ci) => (
                      <td key={ci} style={{ padding: 2 }}>
                        <Input size="small" value={r[ci] || ''} style={{ width: 90 }}
                               onChange={e => setChart(headers, rows.map((row, j) => (j === ri ? headers.map((__, c) => (c === ci ? e.target.value : row[c] || '')) : row)))} />
                      </td>
                    ))}
                    <td>
                      <Button size="small" type="text" danger icon={<DeleteOutlined />} onClick={() => setChart(headers, rows.filter((_, j) => j !== ri))} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {value.variants.length > 0 && (
        <Section title={`${k('variants')} (${value.variants.length})`}>
          <Space wrap>
            {value.variants.map((v, i) => (
              <Text key={i} code>{Object.entries(v).map(([a, b]) => `${a}:${b}`).join(' ')}</Text>
            ))}
          </Space>
        </Section>
      )}

      <Section title={k('description')}>
        <TextArea rows={5} value={value.description} onChange={e => set({ description: e.target.value })} placeholder={k('descriptionPlaceholder')} />
        <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>{k('care')}</Text>
        <TextArea rows={2} value={value.care} onChange={e => set({ care: e.target.value })} />
      </Section>
    </div>
  );
};

export default ProductEditor;
