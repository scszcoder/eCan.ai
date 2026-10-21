import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, App, Button, Card, Col, Empty, Input, Row, Segmented, Space, Spin, Tag, Typography } from 'antd';
import { BranchesOutlined, FileTextOutlined, SaveOutlined, UndoOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { ksApi, KSPoliciesView } from '@/services/ipc/ksApi';
import { policyChanges } from './policyDoc';
import { POLICY_TEMPLATE_ZH } from './policyTemplate';

const { Text } = Typography;
const { TextArea } = Input;

const DEFAULT_SCOPE = '__merchant__';

/**
 * Store policies: one text box per topic, its example (or, for a store, the
 * default it inherits) shown as the box's placeholder; one Save writes every
 * changed section. The section list on the right jumps to a section. The
 * merchant default is written once; a store holds only what differs (an empty
 * section = use the default).
 *
 * (It was one markdown document with the examples in <!-- --> comments: a
 * seller who typed over the example saved nothing, and the section list
 * could not be clicked.)
 */
const PoliciesPanel: React.FC<{ onChanged: () => void }> = ({ onChanged }) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const k = (key: string, o?: Record<string, unknown>): string => String(t(`pages.knowledge.ks.policies.${key}`, o as any));
  const [view, setView] = useState<KSPoliciesView | null>(null);
  const [scope, setScope] = useState<string>(DEFAULT_SCOPE);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const boxes = useRef<Record<string, HTMLDivElement | null>>({});

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

  if (!view) return <Spin />;

  const textOf = (topic: string) => drafts[topic] ?? (own[topic]?.text || '');
  const texts: Record<string, string> = {};
  view.topics.forEach(({ value }) => { texts[value] = textOf(value).trim(); });
  const changes = policyChanges(texts, own);
  const dirty = changes.save.length + changes.remove.length > 0;

  const hintOf = (topic: string): string => {
    if (!isDefault && !own[topic]) {
      const inherited = view.defaults[topic]?.text;
      return inherited ? `${k('usingDefault')}${inherited}` : k('overridePlaceholder');
    }
    return String(t(`pages.knowledge.ks.policies.hints.${topic}`, { defaultValue: k('defaultPlaceholder') }));
  };

  const switchScope = (v: string) => {
    if (dirty) {
      message.warning(k('unsavedSwitch'));
      return;
    }
    setDrafts({});
    setScope(v);
  };

  // The standard template fills only EMPTY sections of the merchant default, as
  // unsaved edits: the seller reviews and edits it, then saves -- nothing they
  // wrote is overwritten and nothing goes live unseen.
  const loadTemplate = () => {
    const fill: Record<string, string> = {};
    view.topics.forEach(({ value }) => {
      const tpl = POLICY_TEMPLATE_ZH[value];
      if (tpl && !textOf(value).trim()) fill[value] = tpl;
    });
    const n = Object.keys(fill).length;
    if (!n) {
      message.info(k('templateNothingEmpty'));
      return;
    }
    setDrafts(d => ({ ...d, ...fill }));
    message.success(k('templateLoaded', { count: n }));
  };

  const jumpTo = (topic: string) => {
    const el = boxes.current[topic];
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    el.querySelector('textarea')?.focus({ preventScroll: true });
  };

  const save = async () => {
    const { save: toSave, remove } = changes;
    if (!toSave.length && !remove.length) {
      message.info(k('nothingChanged'));
      setDrafts({});
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
      setDrafts({});
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
    const filled = !!texts[topic];
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
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            {view.topics.map(({ value, label }) => (
              <div key={value} ref={el => { boxes.current[value] = el; }} style={{ scrollMarginTop: 12 }}>
                <Card size="small" title={label} extra={statusTag(value)}>
                  <TextArea
                    data-testid={`policy-${value}`}
                    value={textOf(value)}
                    placeholder={hintOf(value)}
                    onChange={e => {
                      const v = e.target.value;
                      setDrafts(d => ({ ...d, [value]: v }));
                    }}
                    autoSize={{ minRows: 3, maxRows: 12 }}
                  />
                </Card>
              </div>
            ))}
          </Space>
          <Space style={{ marginTop: 12 }}>
            <Button type="primary" icon={<SaveOutlined />} disabled={!dirty} loading={saving} onClick={save}
                    data-testid="policy-save">{k('save')}</Button>
            <Button icon={<UndoOutlined />} disabled={!dirty || saving} onClick={() => setDrafts({})}>{k('discard')}</Button>
            {isDefault && (
              <Button icon={<FileTextOutlined />} disabled={saving} onClick={loadTemplate}
                      data-testid="policy-load-template">{k('loadTemplate')}</Button>
            )}
            {dirty && <Text type="warning">{k('unsaved')}</Text>}
          </Space>
        </Col>
        <Col xs={24} lg={7}>
          <Card size="small" title={k('sections')} style={{ position: 'sticky', top: 0 }}>
            {view.topics.map(({ value, label }) => (
              <div key={value} role="button" tabIndex={0} data-testid={`policy-jump-${value}`}
                   onClick={() => jumpTo(value)}
                   onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') jumpTo(value); }}
                   style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0', cursor: 'pointer' }}>
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
