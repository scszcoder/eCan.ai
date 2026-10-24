import React, { useCallback, useEffect, useState } from 'react';
import { Alert, App, Button, Card, Empty, Input, Popconfirm, Select, Space, Spin, Tag, Typography } from 'antd';
import { DeleteOutlined, ReloadOutlined, SaveOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { ksApi, KSBuyerProfile, PROFILE_FIELDS } from '@/services/ipc/ksApi';

const { Text } = Typography;

/**
 * 顾客画像: what each buyer told customer service about the person the item is
 * for (who, age, size, budget...), read from the chat and used for
 * recommendations. Kept on this PC only, dropped after 30 days without contact.
 * The owner can correct a field (it is then never overwritten by the chat)
 * or delete one person or the whole buyer.
 */
const BuyerProfilesPanel: React.FC = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const k = (key: string, o?: Record<string, unknown>): string => String(t(`pages.knowledge.ks.buyers.${key}`, o as any));
  const [stores, setStores] = useState<{ store_id: string; name: string }[] | null>(null);
  const [store, setStore] = useState<string>('');
  const [items, setItems] = useState<KSBuyerProfile[] | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Record<string, string>>>({});

  useEffect(() => {
    ksApi.listAppStores().then(list => {
      setStores(list);
      if (list.length) setStore(s => s || list[0].store_id);
    }).catch(() => setStores([]));
  }, []);

  const load = useCallback(async () => {
    if (!store) return;
    try {
      setItems((await ksApi.listProfiles(store)).items);
      setDrafts({});
    } catch (e: any) {
      message.error(e.message);
    }
  }, [store, message]);

  useEffect(() => { load(); }, [load]);

  const keyOf = (cid: string, who: string) => `${cid}\u0000${who}`;
  const shown = (v: unknown) => (Array.isArray(v) ? v.join('、') : String(v ?? ''));

  const save = async (cid: string, who: string) => {
    const draft = drafts[keyOf(cid, who)] || {};
    const fields: Record<string, string | string[]> = {};
    Object.entries(draft).forEach(([f, v]) => {
      fields[f] = f === 'prefs' ? v.split(/[、,，\s]+/).filter(Boolean) : v.trim();
    });
    try {
      await ksApi.saveProfile({ store_id: store, customer_id: cid, recipient: who, fields });
      message.success(k('saved'));
      load();
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const remove = async (cid: string, who?: string) => {
    try {
      await ksApi.deleteProfile({ store_id: store, customer_id: cid, recipient: who || '' });
      load();
    } catch (e: any) {
      message.error(e.message);
    }
  };

  if (stores === null) return <Spin />;
  if (!stores.length) return <Empty description={k('noStores')} />;

  return (
    <div>
      <Alert type="info" showIcon style={{ marginBottom: 12 }} message={k('intro')} />
      <Space style={{ marginBottom: 12 }}>
        <Select style={{ minWidth: 240 }} value={store || undefined} onChange={setStore}
                options={stores.map(s => ({ value: s.store_id, label: s.name }))} />
        <Button icon={<ReloadOutlined />} onClick={load}>{k('refresh')}</Button>
      </Space>
      {items === null ? <Spin /> : !items.length ? <Empty description={k('empty')} /> : items.map(b => (
        <Card key={b.customer_id} size="small" style={{ marginBottom: 12 }}
              title={<Space><Text strong>{b.name || b.customer_id}</Text>
                <Text type="secondary">{k('lastContact', { at: new Date(b.last_contact * 1000).toLocaleString() })}</Text></Space>}
              extra={<Popconfirm title={k('deleteBuyerConfirm')} onConfirm={() => remove(b.customer_id)}>
                <Button size="small" danger icon={<DeleteOutlined />}>{k('deleteBuyer')}</Button></Popconfirm>}>
          {Object.entries(b.recipients).map(([who, rec]) => {
            const dk = keyOf(b.customer_id, who);
            const draft = drafts[dk] || {};
            return (
              <div key={who} style={{ marginBottom: 8 }}>
                <Space wrap style={{ marginBottom: 4 }}>
                  <Text strong>{who === '自己' ? k('self') : who === '未说明' ? k('unknownWho') : k('forWho', { who })}</Text>
                  {b.current === who && <Tag color="blue">{k('current')}</Tag>}
                  {rec.gift && <Tag color="magenta">{k('gift')}</Tag>}
                </Space>
                <Space wrap>
                  {PROFILE_FIELDS.map(f => (
                    <Input key={f} size="small" style={{ width: f === 'prefs' ? 220 : 130 }}
                           addonBefore={k(`fields.${f}`)}
                           suffix={(rec.owner_set || []).includes(f) ? <Tag style={{ marginInlineEnd: 0 }}>{k('ownerSet')}</Tag> : undefined}
                           value={draft[f] ?? shown(rec.fields[f])}
                           onChange={e => setDrafts({ ...drafts, [dk]: { ...draft, [f]: e.target.value } })} />
                  ))}
                  <Button size="small" type="primary" icon={<SaveOutlined />} disabled={!Object.keys(draft).length}
                          onClick={() => save(b.customer_id, who)}>{k('save')}</Button>
                  <Popconfirm title={k('deletePersonConfirm')} onConfirm={() => remove(b.customer_id, who)}>
                    <Button size="small" icon={<DeleteOutlined />}>{k('deletePerson')}</Button>
                  </Popconfirm>
                </Space>
              </div>
            );
          })}
        </Card>
      ))}
    </div>
  );
};

export default BuyerProfilesPanel;
