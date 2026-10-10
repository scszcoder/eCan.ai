import React, { useEffect, useState } from 'react';
import { App, Badge, Button, Popover, Tooltip, Typography } from 'antd';
import { CloudDownloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '../../services/ipc_api';
import { useSubscriptionUpdateStore, type SubscriptionUpdate } from '../../stores/subscriptionUpdateStore';

const { Text } = Typography;

/**
 * Header update icon: subscribed skills (and their prompts) with a newer
 * author version that could not be applied automatically because a task is
 * using the skill. Shown only while there is something to update.
 */
const SubscriptionUpdates: React.FC = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const items = useSubscriptionUpdateStore((s) => s.items);
  const applied = useSubscriptionUpdateStore((s) => s.applied);
  const setItems = useSubscriptionUpdateStore((s) => s.setItems);
  const clearApplied = useSubscriptionUpdateStore((s) => s.clearApplied);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  // A check may have finished before this header mounted.
  useEffect(() => {
    get_ipc_api().executeRequest<{ items: SubscriptionUpdate[] }>('subscription_updates.list', {})
      .then((res) => { if (res?.success && res.data?.items) setItems(res.data.items); })
      .catch(() => { /* no reminder until the next push */ });
  }, [setItems]);

  // Updates applied in the background (idle skills): say so once.
  useEffect(() => {
    if (!applied.length) return;
    message.success(t('subscriptionUpdates.autoApplied',
      { defaultValue: 'Updated to the author\'s latest: {{names}}', names: applied.map((a) => a.name).join(', ') }));
    clearApplied();
  }, [applied, clearApplied, message, t]);

  const apply = async (skillIds?: string[]) => {
    setBusy(skillIds ? skillIds[0] : '__all__');
    try {
      const res = await get_ipc_api().executeRequest<{ results: any[]; items: SubscriptionUpdate[] }>(
        'subscription_updates.apply', skillIds ? { skill_ids: skillIds } : {}, 300_000);
      const results = res?.data?.results || [];
      const failed = results.filter((r: any) => !r.ok);
      if (res?.success && !failed.length) {
        message.success(t('subscriptionUpdates.done', 'Updated'));
      } else {
        message.error(t('subscriptionUpdates.failed', { defaultValue: 'Update failed: {{names}}',
          names: failed.map((r: any) => `${r.name} (${r.error || ''})`).join(', ') || res?.error?.message || '' }));
      }
      if (res?.data?.items) setItems(res.data.items);
    } catch (e) {
      message.error(String(e));
    } finally {
      setBusy(null);
    }
  };

  if (!items.length) return null;

  const content = (
    <div style={{ width: 340, maxHeight: 380, overflow: 'auto' }}>
      {items.map((it) => (
        <div key={it.skill_id} data-testid={`sub-update-${it.skill_id}`}
          style={{ display: 'flex', alignItems: 'flex-start', gap: 8, padding: '8px 0', borderBottom: '1px solid rgba(128,128,128,0.15)' }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <Text strong>{it.name}</Text>
            <div style={{ fontSize: 12, opacity: 0.75 }}>
              {it.skill_newer ? t('subscriptionUpdates.newSkill', 'New skill version') : null}
              {it.skill_newer && it.prompts.length ? ' · ' : null}
              {it.prompts.length ? t('subscriptionUpdates.newPrompts', { defaultValue: '{{n}} prompt(s) changed', n: it.prompts.length }) : null}
            </div>
            {(it.busy || it.error) && (
              <div style={{ fontSize: 12, opacity: 0.6 }}>
                {it.error
                  ? t('subscriptionUpdates.error', { defaultValue: 'Last try failed: {{e}}', e: it.error })
                  : t('subscriptionUpdates.inUse', { defaultValue: 'In use ({{why}}) — updates when idle', why: it.busy })}
              </div>
            )}
          </div>
          <Button size="small" loading={busy === it.skill_id} disabled={!!busy && busy !== it.skill_id}
            onClick={() => apply([it.skill_id])}>
            {t('subscriptionUpdates.update', 'Update')}
          </Button>
        </div>
      ))}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: 8 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {t('subscriptionUpdates.hint', 'Running tasks switch to the new version.')}
        </Text>
        {items.length > 1 && (
          <Button type="primary" size="small" loading={busy === '__all__'} disabled={!!busy && busy !== '__all__'}
            onClick={() => apply()}>
            {t('subscriptionUpdates.updateAll', 'Update all')}
          </Button>
        )}
      </div>
    </div>
  );

  return (
    <Popover content={content} title={t('subscriptionUpdates.title', 'Updates for subscribed skills')}
      trigger="click" open={open} onOpenChange={setOpen} placement="bottomRight">
      <Tooltip title={open ? '' : t('subscriptionUpdates.tooltip', 'Subscribed skills have updates')}>
        <Badge count={items.length} overflowCount={99} size="small" offset={[-6, 6]}>
          <Button type="text" data-testid="sub-updates-icon" icon={<CloudDownloadOutlined />} style={{ fontSize: '18px' }} />
        </Badge>
      </Tooltip>
    </Popover>
  );
};

export default SubscriptionUpdates;
