import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Space, Switch, Typography, message } from 'antd';
import { get_ipc_api } from '@/services/ipc_api';
import { isDesktopPlatform } from '@/config/platform';

interface UnattendedState {
  enabled: boolean;
  logon_task: boolean;
  watchdog_running: boolean;
  /** Whether a watchdog can run at all here (false in dev / CI). */
  watchdog_available?: boolean;
  error?: string;
}

/** Unattended mode: eCan starts at Windows logon and restarts itself if it crashes or hangs. */
export const UnattendedSetting: React.FC = () => {
  const { t } = useTranslation();
  const [state, setState] = useState<UnattendedState | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    const res = await get_ipc_api().getUnattended<UnattendedState>();
    if (res?.success && res.data) setState(res.data);
  }, []);

  useEffect(() => { if (isDesktopPlatform()) load(); }, [load]);

  if (!isDesktopPlatform() || !state) return null;

  const onChange = async (enabled: boolean) => {
    setSaving(true);
    try {
      const res = await get_ipc_api().setUnattended<UnattendedState>(enabled);
      if (res?.success && res.data) {
        setState(res.data);
        if (res.data.error) message.warning(t('pages.settings.unattended_task_failed', { error: res.data.error }));
      } else {
        message.error(t('pages.settings.unattended_save_failed'));
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <Space direction="vertical" size={4} style={{ width: '100%', marginBottom: 12 }}>
      <Space>
        <Switch size="small" checked={state.enabled} loading={saving} onChange={onChange} />
        <Typography.Text strong>{t('pages.settings.unattended_mode')}</Typography.Text>
      </Space>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {t('pages.settings.unattended_mode_desc')}
      </Typography.Text>
      {state.enabled && !state.logon_task && (
        <Alert type="warning" showIcon style={{ fontSize: 12 }} message={t('pages.settings.unattended_no_logon_task')} />
      )}
      {state.enabled && state.watchdog_available === false && (
        <Alert type="warning" showIcon style={{ fontSize: 12 }} message={t('pages.settings.unattended_watchdog_unavailable')} />
      )}
    </Space>
  );
};
