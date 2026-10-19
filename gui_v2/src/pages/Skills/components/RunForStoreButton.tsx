import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App, Button, Modal, Radio, Space, Typography, Empty, Spin } from 'antd';
import { ShopOutlined } from '@ant-design/icons';
import { IPCAPI } from '@/services/ipc/api';

interface StoreHost {
  store_id: string;
  store_name: string;
  agent_name: string;
}

interface RunResult {
  task_name: string;
  agent_name: string;
  store_name: string;
  already_queued: boolean;
}

/**
 * 为店铺运行一次: run a store-scoped skill (e.g. 抖店商品导出) once for one store.
 * The run goes to the agent already running that store, as a one-off background
 * task removed when it finishes -- the same handler as `ecan skills run-for-store`.
 */
export const RunForStoreButton: React.FC<{ skill: string; style?: React.CSSProperties }> = ({ skill, style }) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [stores, setStores] = useState<StoreHost[]>([]);
  const [picked, setPicked] = useState<string>('');

  const show = async () => {
    setOpen(true);
    setLoading(true);
    try {
      const res = await IPCAPI.getInstance().getSkillStoreHosts<{ stores: StoreHost[] }>();
      const list = (res?.success && res.data?.stores) || [];
      setStores(list);
      setPicked(list.length === 1 ? list[0].store_id : '');
    } finally {
      setLoading(false);
    }
  };

  const run = async () => {
    if (!picked) return;
    setRunning(true);
    try {
      const res = await IPCAPI.getInstance().runSkillForStore<RunResult>(skill, picked);
      if (res?.success && res.data) {
        const d = res.data;
        message.success(d.already_queued
          ? t('pages.skills.runForStore.already', { store: d.store_name, agent: d.agent_name })
          : t('pages.skills.runForStore.queued', { store: d.store_name, agent: d.agent_name }), 8);
        setOpen(false);
      } else {
        message.error(String((res as any)?.error?.message || t('pages.skills.runForStore.failed')));
      }
    } finally {
      setRunning(false);
    }
  };

  return (
    <>
      <Button icon={<ShopOutlined />} onClick={show} style={style}>
        {t('pages.skills.runForStore.button')}
      </Button>
      <Modal
        open={open}
        title={t('pages.skills.runForStore.title')}
        onCancel={() => setOpen(false)}
        onOk={run}
        okText={t('pages.skills.runForStore.ok')}
        okButtonProps={{ disabled: !picked, loading: running }}
      >
        <Typography.Paragraph type="secondary">{t('pages.skills.runForStore.explain')}</Typography.Paragraph>
        {loading ? <Spin /> : stores.length === 0 ? (
          <Empty description={t('pages.skills.runForStore.noStores')} />
        ) : (
          <Radio.Group value={picked} onChange={(e) => setPicked(e.target.value)}>
            <Space direction="vertical">
              {stores.map((s) => (
                <Radio key={s.store_id} value={s.store_id}>
                  {s.store_name} <Typography.Text type="secondary">· {s.agent_name}</Typography.Text>
                </Radio>
              ))}
            </Space>
          </Radio.Group>
        )}
      </Modal>
    </>
  );
};
