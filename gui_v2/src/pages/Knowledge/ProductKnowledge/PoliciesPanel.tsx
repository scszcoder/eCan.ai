import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, App, Button, Card, Col, Empty, Input, Row, Segmented, Space, Spin, Tag, Typography } from 'antd';
import { BranchesOutlined, SaveOutlined, UndoOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { ksApi, KSPoliciesView } from '@/services/ipc/ksApi';
import { buildPolicyDoc, parsePolicyDoc, policyChanges } from './policyDoc';

const { Text } = Typography;
const { TextArea } = Input;

const DEFAULT_SCOPE = '__merchant__';

/**
 * Store policies as one markdown document per scope: a "## topic" section per
 * topic, with an example hint, that the user scrolls through and fills in;
 * one Save writes every changed section. The merchant default is written once;
 * a store's document holds only what differs (an empty section = use the
 * default, which its hint shows).
 */
const PoliciesPanel: React.FC<{ onChanged: () => void }> = ({ onChanged }) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const k = (key: string, o?: Record<string, unknown>): string => String(t(`pages.knowledge.ks.policies.${key}`, o as any));
  const [view, setView] = useState<KSPoliciesView | null>(null);
  const [scope, setScope] = useState<string>(DEFAULT_SCOPE);
  const [draft, setDraft] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      setView(await ksApi.getPolicies());
    } catch (e: any) {
      message.error(e.message);
    }
  }, [message]);

  useEffect(() => { load(); }, [load]);

  const isDefault = scope === DEFAULT_SCOPE;
  const own = useMemo(() => (view ? (isDefault ? view.defaults : view.overrides[scope] || {}) : {}), [view, isDefault, scope]);

  // The document as saved: own text per section; hints show an example or,
  // for a store, the default it inherits.
  const savedDoc = useMemo(() => {
    if (!view) return '';
    return buildPolicyDoc(view.topics, (topic) => own[topic]?.text || '', (topic) => {
      if (!isDefault && !own[topic]) {
        const inherited = view.defaults[topic]?.text;
        return inherited ? `${k('usingDefault')}${inherited}` : k('overridePlaceholder');
      }
      return String(t(`pages.knowledge.ks.policies.hints.${topic}`, { defaultValue: k('defaultPlaceholder') }));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, own, isDefault, t]);

  if (!view) return <Spin />;

  const doc = draft ?? savedDoc;
  const dirty = draft !== null && draft !== savedDoc;
  const parsed = parsePolicyDoc(doc, view.topics);

  const switchScope = (v: string) => {
    if (dirty) {
      message.warning(k('unsavedSwitch'));
      return;
    }
    setDraft(null);
    setScope(v);
  };

  const save = async () => {
    const { save: toSave, remove } = policyChanges(parsed, own);
    if (parsed.unknown.length) {
      message.warning(k('unknownSections', { names: parsed.unknown.join('、') }));
    }
    if (!toSave.length && !remove.length) {
      message.info(k('nothingChanged'));
      setDraft(null);
      return;
    }
    setSaving(true);
    try {
      for (const p of toSave) {
        await ksApi.savePolicy({ topic: p.topic, text: p.text, store_id: isDefault ? null : scope });
      }
      for (const r of remove) {
        await ksApi.deletePolicy(r.id);
      }
      message.success(k('savedCount', { saved: toSave.length, removed: remove.length }));
      setDraft(null);
      await load();
      onChanged();
    } catch (e: any) {
      message.error(e.message);
      await load();
    } finally {
      setSaving(false);
    }
  };

  const statusTag = (topic: string) => {
    const text = parsed.texts[topic];
    const filled = text !== undefined ? !!text : !!own[topic];
    if (isDefault) return filled ? <Tag color="green">{k('set')}</Tag> : <Tag>{k('notSet')}</Tag>;
    if (filled) return <Tag color="orange" icon={<BranchesOutlined />}>{k('overridden')}</Tag>;
    return view.defaults[topic] ? <Tag color="blue">{k('inherits')}</Tag> : <Tag>{k('notSet')}</Tag>;
  };

  return (
    <div>
      <Alert type="info" showIcon style={{ marginBottom: 12 }} message={k('intro')} description={k('docHint')} />
      <Segmented
        style={{ marginBottom: 16 }}
        value={scope}
        onChange={v => switchScope(String(v))}
        options={[
          { value: DEFAULT_SCOPE, label: k('merchantDefault') },
          ...view.stores.map(s => ({
            value: s.id,
            label: <Space size={4}>{s.name}{Object.keys(view.overrides[s.id] || {}).length > 0 && <Tag color="orange" style={{ marginInlineEnd: 0 }}>{Object.keys(view.overrides[s.id]).length}</Tag>}</Space>,
          })),
        ]}
      />
      {view.stores.length === 0 && !isDefault && <Empty description={k('noStores')} />}
      <Row gutter={16}>
        <Col xs={24} lg={17}>
          <TextArea
            data-testid="policy-doc"
            value={doc}
            onChange={e => setDraft(e.target.value)}
            autoSize={{ minRows: 22, maxRows: 40 }}
            spellCheck={false}
            style={{ fontFamily: 'Consolas, "Courier New", monospace', fontSize: 13, lineHeight: 1.6 }}
          />
          <Space style={{ marginTop: 12 }}>
            <Button type="primary" icon={<SaveOutlined />} disabled={!dirty} loading={saving} onClick={save}
                    data-testid="policy-save">{k('save')}</Button>
            <Button icon={<UndoOutlined />} disabled={!dirty || saving} onClick={() => setDraft(null)}>{k('discard')}</Button>
            {dirty && <Text type="warning">{k('unsaved')}</Text>}
          </Space>
        </Col>
        <Col xs={24} lg={7}>
          <Card size="small" title={k('sections')}>
            {view.topics.map(({ value, label }) => (
              <div key={value} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0' }}>
                <Text>{label}</Text>
                {statusTag(value)}
              </div>
            ))}
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default PoliciesPanel;
