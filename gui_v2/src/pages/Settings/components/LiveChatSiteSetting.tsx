import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Select, Space, Typography, message } from 'antd';
import { get_ipc_api } from '@/services/ipc_api';

interface SiteOption {
  value: string;
  label_zh: string;
  label_en: string;
}

interface SiteState {
  site: string;
  running_site: string;
  restart_needed: boolean;
  options: SiteOption[];
}

/** Which live-chat platform (飞鸽 / 拼多多) this machine serves. Saved to run.env; applies after restart. */
export const LiveChatSiteSetting: React.FC = () => {
  const { t, i18n } = useTranslation();
  const [state, setState] = useState<SiteState | null>(null);
  const [saving, setSaving] = useState(false);
  const zh = (i18n.language || '').startsWith('zh');

  const load = useCallback(async () => {
    const res = await get_ipc_api().getLiveChatSite<SiteState>();
    if (res?.success && res.data) setState(res.data);
  }, []);

  useEffect(() => { load(); }, [load]);

  const onChange = async (site: string) => {
    setSaving(true);
    try {
      const res = await get_ipc_api().setLiveChatSite<SiteState>(site);
      if (res?.success && res.data) {
        setState(res.data);
      } else {
        message.error(res?.error?.message || t('pages.settings.live_chat_site_save_failed', 'Could not save'));
      }
    } finally {
      setSaving(false);
    }
  };

  if (!state) return null;
  return (
    <Space direction="vertical" size={6} style={{ width: '100%', marginBottom: 8 }}>
      <Space>
        <Typography.Text>{t('pages.settings.live_chat_site', 'Live-chat platform')}</Typography.Text>
        <Select
          size="small"
          style={{ minWidth: 180 }}
          value={state.site}
          loading={saving}
          onChange={onChange}
          options={state.options.map((o) => ({ value: o.value, label: zh ? o.label_zh : o.label_en }))}
        />
      </Space>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {t('pages.settings.live_chat_site_hint',
          'One platform per machine for now. Fast Deploy sets this for you.')}
      </Typography.Text>
      {state.restart_needed && (
        <Alert
          type="warning"
          showIcon
          message={t('pages.settings.live_chat_site_restart', 'Restart eCan to apply the new platform.')}
        />
      )}
    </Space>
  );
};

export default LiveChatSiteSetting;
