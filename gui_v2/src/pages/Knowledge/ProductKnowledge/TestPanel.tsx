import React, { useEffect, useState } from 'react';
import {
  Alert, App, Button, Card, Col, Descriptions, Empty, Input, List, Progress, Row, Select, Space, Tag, Tooltip, Typography,
} from 'antd';
import { SendOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { ksApi, KSOverview, KSProduct, KSSearchResult } from '@/services/ipc/ksApi';

const { Text, Paragraph } = Typography;

const TIER_COLOR = ['green', 'cyan', 'blue', 'purple'];

const EXAMPLES = ['这件是什么材质的', '身高170穿什么码', '可以七天无理由退货吗', '多久发货，用什么快递', '会缩水吗'];

/** "Ask as a buyer": shows exactly what the Q&A agent would receive. */
const TestPanel: React.FC<{ overview: KSOverview | null }> = ({ overview }) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const k = (key: string, o?: Record<string, unknown>): string => String(t(`pages.knowledge.ks.test.${key}`, o as any));
  const stores = overview?.stores || [];

  const [storeId, setStoreId] = useState<string>();
  const [productId, setProductId] = useState<string>();
  const [itemId, setItemId] = useState('');
  const [query, setQuery] = useState('');
  const [products, setProducts] = useState<KSProduct[]>([]);
  const [result, setResult] = useState<KSSearchResult | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    ksApi.listProducts({ store_id: storeId, limit: 200 }).then(r => setProducts(r.items)).catch(() => setProducts([]));
  }, [storeId]);

  const ask = async (q?: string) => {
    const text = (q ?? query).trim();
    if (!text) return;
    setQuery(text);
    setLoading(true);
    try {
      setResult(await ksApi.search({ query: text, store_id: storeId, product_id: productId, platform_item_id: itemId || undefined }));
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  const timingStages = result ? Object.entries(result.timings_ms).filter(([s]) => s !== 'total') : [];
  const total = result?.timings_ms.total || 0;

  return (
    <Row gutter={16}>
      <Col xs={24} xl={9}>
        <Card size="small" title={k('scope')}>
          <Paragraph type="secondary" style={{ fontSize: 12 }}>{k('scopeHint')}</Paragraph>
          <Text type="secondary">{k('store')}</Text>
          <Select allowClear style={{ width: '100%', marginBottom: 8 }} value={storeId} placeholder={k('anyStore')}
                  options={stores.map(s => ({ value: s.id, label: s.name }))}
                  onChange={v => { setStoreId(v); setProductId(undefined); }} />
          <Text type="secondary">{k('product')}</Text>
          <Select allowClear showSearch optionFilterProp="label" style={{ width: '100%', marginBottom: 8 }}
                  value={productId} placeholder={k('noProduct')}
                  options={products.map(p => ({ value: p.id, label: `${p.title} (${p.code})` }))}
                  onChange={v => { setProductId(v); if (v) setItemId(''); }} />
          <Text type="secondary">{k('itemId')}</Text>
          <Input value={itemId} disabled={!!productId} placeholder={k('itemIdPlaceholder')} onChange={e => setItemId(e.target.value)}
                 style={{ marginBottom: 12 }} />
          <Input.TextArea rows={3} value={query} placeholder={k('questionPlaceholder')} onChange={e => setQuery(e.target.value)}
                          onPressEnter={e => { if (!e.shiftKey) { e.preventDefault(); ask(); } }} />
          <Button type="primary" icon={<SendOutlined />} loading={loading} block style={{ marginTop: 8 }} onClick={() => ask()}>
            {k('ask')}
          </Button>
          <div style={{ marginTop: 12 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>{k('examples')}</Text>
            <div><Space size={[4, 4]} wrap>
              {EXAMPLES.map(ex => <Tag key={ex} style={{ cursor: 'pointer' }} onClick={() => ask(ex)}>{ex}</Tag>)}
            </Space></div>
          </div>
        </Card>
      </Col>

      <Col xs={24} xl={15}>
        {!result ? <Card size="small"><Empty description={k('empty')} /></Card> : (
          <>
            <Card size="small" style={{ marginBottom: 12 }}>
              <Space wrap style={{ width: '100%', justifyContent: 'space-between' }}>
                <Space wrap>
                  <Tag color={TIER_COLOR[result.tier]} icon={<ThunderboltOutlined />}>{k(`tier${result.tier}`)}</Tag>
                  {result.product ? <Text>{k('resolved')}: <Text strong>{result.product.title}</Text></Text>
                    : <Text type="secondary">{k('noProductResolved')}</Text>}
                </Space>
                <Space>
                  <Text type="secondary">{k('confidence')}</Text>
                  <Progress type="circle" size={44} percent={Math.round(result.confidence * 100)}
                            status={result.should_answer ? 'success' : 'exception'} />
                </Space>
              </Space>
              {!result.should_answer && (
                <Alert style={{ marginTop: 8 }} type="warning" showIcon message={k('noKnowledge')} description={k('noKnowledgeHint')} />
              )}
              <div style={{ marginTop: 8 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>{k('timing', { ms: total })}</Text>
                <div style={{ display: 'flex', height: 8, borderRadius: 4, overflow: 'hidden', marginTop: 4, background: '#f0f0f0' }}>
                  {timingStages.map(([stage, ms], i) => (
                    <Tooltip key={stage} title={`${k(`stage.${stage}`, { defaultValue: stage })}: ${ms} ms`}>
                      <div style={{ width: `${total ? (ms / total) * 100 : 0}%`, background: ['#52c41a', '#13c2c2', '#1677ff', '#722ed1', '#fa8c16'][i % 5] }} />
                    </Tooltip>
                  ))}
                </div>
              </div>
            </Card>

            {result.facts.length > 0 && (
              <Card size="small" title={k('facts')} style={{ marginBottom: 12 }}>
                <Descriptions size="small" column={1} bordered>
                  {result.facts.map((f, i) => <Descriptions.Item key={i} label={f.key}>{f.value}</Descriptions.Item>)}
                </Descriptions>
              </Card>
            )}
            {result.faq.length > 0 && (
              <Card size="small" title={k('faq')} style={{ marginBottom: 12 }}>
                <List size="small" dataSource={result.faq} renderItem={f => (
                  <List.Item extra={<Tag>{f.score.toFixed(2)}</Tag>}>
                    <List.Item.Meta title={f.question} description={f.answer} />
                  </List.Item>
                )} />
              </Card>
            )}
            {result.policies.length > 0 && (
              <Card size="small" title={k('policies')} style={{ marginBottom: 12 }}>
                {result.policies.map(p => (
                  <div key={p.id} style={{ marginBottom: 6 }}>
                    <Tag color={p.inherited ? 'blue' : 'orange'}>{p.inherited ? k('merchantRule') : k('storeRule')}</Tag>
                    <Text>{p.text}</Text>
                  </div>
                ))}
              </Card>
            )}
            {result.candidates.length > 0 && (
              <Card size="small" title={k('candidates')} style={{ marginBottom: 12 }}>
                <Space wrap>{result.candidates.map(c => <Tag key={c.id} color="purple">{c.title} · {c.score.toFixed(2)}</Tag>)}</Space>
              </Card>
            )}
            {result.chunks.length > 0 && (
              <Card size="small" title={k('sources')} style={{ marginBottom: 12 }}>
                <List size="small" dataSource={result.chunks} renderItem={c => (
                  <List.Item extra={<Tag>{c.score.toFixed(2)}</Tag>}>
                    <Space direction="vertical" size={0}>
                      <Text style={{ fontSize: 12 }}>{c.text}</Text>
                      <Space size={4}>
                        <Tag style={{ fontSize: 11 }}>{k(`docType.${c.doc_type}`, { defaultValue: c.doc_type })}</Tag>
                        {c.matched_terms.map(term => <Tag key={term} color="gold" style={{ fontSize: 11 }}>{term}</Tag>)}
                      </Space>
                    </Space>
                  </List.Item>
                )} />
              </Card>
            )}
            <Card size="small" title={k('context')}>
              <Paragraph type="secondary" style={{ fontSize: 12 }}>{k('contextHint')}</Paragraph>
              <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, margin: 0 }}>{result.context || '—'}</pre>
            </Card>
          </>
        )}
      </Col>
    </Row>
  );
};

export default TestPanel;
