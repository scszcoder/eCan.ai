import React, { useCallback, useEffect, useState } from 'react';
import { Alert, App, Button, Card, Col, Empty, Input, Popconfirm, Row, Segmented, Space, Spin, Tag, Typography } from 'antd';
import { BranchesOutlined, DeleteOutlined, SaveOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { ksApi, KSPoliciesView } from '@/services/ipc/ksApi';

const { Text } = Typography;
const { TextArea } = Input;

const DEFAULT_SCOPE = '__merchant__';

/**
 * Store policies: one merchant-wide default per topic, plus per-store
 * overrides that only need to state what is different. Each topic shows
 * which text a store actually uses.
 */
const PoliciesPanel: React.FC<{ onChanged: () => void }> = ({ onChanged }) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const k = (key: string, o?: Record<string, unknown>): string => String(t(`pages.knowledge.ks.policies.${key}`, o as any));
  const [view, setView] = useState<KSPoliciesView | null>(null);
  const [scope, setScope] = useState<string>(DEFAULT_SCOPE);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setView(await ksApi.getPolicies());
    } catch (e: any) {
      message.error(e.message);
    }
  }, [message]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setDrafts({}); }, [scope]);

  if (!view) return <Spin />;

  const isDefault = scope === DEFAULT_SCOPE;
  const overrides = isDefault ? {} : view.overrides[scope] || {};
  const current = (topic: string) => (isDefault ? view.defaults[topic] : overrides[topic]);

  const save = async (topic: string) => {
    const text = (drafts[topic] ?? current(topic)?.text ?? '').trim();
    if (!text) {
      message.warning(k('textRequired'));
      return;
    }
    setSaving(topic);
    try {
      await ksApi.savePolicy({ topic, text, store_id: isDefault ? null : scope });
      message.success(k('saved'));
      setDrafts(d => { const n = { ...d }; delete n[topic]; return n; });
      await load();
      onChanged();
    } catch (e: any) {
      message.error(e.message);
    } finally {
      setSaving(null);
    }
  };

  const remove = async (id: string) => {
    await ksApi.deletePolicy(id);
    await load();
    onChanged();
  };

  return (
    <div>
      <Alert type="info" showIcon style={{ marginBottom: 12 }} message={k('intro')} />
      <Segmented
        style={{ marginBottom: 16 }}
        value={scope}
        onChange={v => setScope(String(v))}
        options={[
          { value: DEFAULT_SCOPE, label: k('merchantDefault') },
          ...view.stores.map(s => ({
            value: s.id,
            label: <Space size={4}>{s.name}{Object.keys(view.overrides[s.id] || {}).length > 0 && <Tag color="orange" style={{ marginInlineEnd: 0 }}>{Object.keys(view.overrides[s.id]).length}</Tag>}</Space>,
          })),
        ]}
      />
      {view.stores.length === 0 && !isDefault && <Empty description={k('noStores')} />}
      <Row gutter={[16, 16]}>
        {view.topics.map(({ value: topic, label }) => {
          const own = current(topic);
          const inherited = !isDefault && !own ? view.defaults[topic] : undefined;
          const text = drafts[topic] ?? own?.text ?? '';
          const dirty = drafts[topic] !== undefined && drafts[topic] !== (own?.text ?? '');
          return (
            <Col xs={24} lg={12} key={topic}>
              <Card
                size="small"
                title={<Space>{label}
                  {isDefault ? (own ? <Tag color="green">{k('set')}</Tag> : <Tag>{k('notSet')}</Tag>)
                    : own ? <Tag color="orange" icon={<BranchesOutlined />}>{k('overridden')}</Tag>
                      : inherited ? <Tag color="blue">{k('inherits')}</Tag> : <Tag>{k('notSet')}</Tag>}
                </Space>}
                extra={
                  <Space>
                    {own && (
                      <Popconfirm title={isDefault ? k('deleteDefaultConfirm') : k('deleteOverrideConfirm')} onConfirm={() => remove(own.id)}>
                        <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                      </Popconfirm>
                    )}
                    <Button size="small" type="primary" icon={<SaveOutlined />} disabled={!dirty} loading={saving === topic}
                            onClick={() => save(topic)}>{k('save')}</Button>
                  </Space>
                }
              >
                {inherited && !own && drafts[topic] === undefined && (
                  <div style={{ marginBottom: 8 }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>{k('usingDefault')}</Text>
                    <div style={{ background: 'rgba(22,119,255,0.06)', padding: 8, borderRadius: 6, marginTop: 4 }}>
                      <Text style={{ fontSize: 12 }}>{inherited.text}</Text>
                    </div>
                  </div>
                )}
                <TextArea
                  rows={4}
                  value={text}
                  placeholder={isDefault ? k('defaultPlaceholder') : k('overridePlaceholder')}
                  onChange={e => setDrafts(d => ({ ...d, [topic]: e.target.value }))}
                />
              </Card>
            </Col>
          );
        })}
      </Row>
    </div>
  );
};

export default PoliciesPanel;
