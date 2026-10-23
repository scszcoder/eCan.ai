import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Space, Switch, Typography, message } from 'antd';
import { get_ipc_api } from '@/services/ipc_api';
import type { APIResponse } from '@/services/ipc/api';
import { isDesktopPlatform } from '@/config/platform';

interface UnattendedState {
  enabled: boolean;
  logon_task: boolean;
  watchdog_running: boolean;
  /** Whether a watchdog can run at all here (false in dev without the opt-in). */
  watchdog_available?: boolean;
  /** True when eCan runs from the source tree rather than a packaged build. */
  dev_mode?: boolean;
  /** The user's opt-in for running a watchdog against the source tree. */
  allow_in_dev?: boolean;
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

  const apply = (res: APIResponse<UnattendedState> | null | undefined) => {
    if (res?.success && res.data) {
      setState(res.data);
      if (res.data.error) message.warning(t('pages.settings.unattended_task_failed', { error: res.data.error }));
    } else {
      message.error(t('pages.settings.unattended_save_failed'));
    }
  };

  const onChange = async (enabled: boolean) => {
    setSaving(true);
    try {
      apply(await get_ipc_api().setUnattended<UnattendedState>(enabled));
    } finally {
      setSaving(false);
    }
  };

  const onDevChange = async (allowInDev: boolean) => {
    setSaving(true);
    try {
      // Always send both: the dev opt-in is meaningless without the feature
      // itself, so they move together.
      apply(await get_ipc_api().setUnattended<UnattendedState>(state.enabled, allowInDev));
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
        <Alert
          type="warning"
          showIcon
          style={{ fontSize: 12 }}
          message={state.dev_mode
            ? t('pages.settings.unattended_watchdog_off_in_dev')
            : t('pages.settings.unattended_watchdog_unavailable')}
        />
      )}
      {state.dev_mode && (
        <Space size={8} style={{ marginTop: 4 }}>
          <Switch
            size="small"
            checked={!!state.allow_in_dev}
            disabled={!state.enabled}
            loading={saving}
            onChange={onDevChange}
          />
          <Typography.Text style={{ fontSize: 12 }}>
            {t('pages.settings.unattended_allow_in_dev')}
          </Typography.Text>
        </Space>
      )}
    </Space>
  );
};
