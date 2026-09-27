import React, { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Badge, Button, Card, Empty, Space, Tag, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useFleetFeedStore } from '@/stores/fleetFeedStore';
import { sendFleetCommand, startFleetFeed, stopFleetFeed } from '@/services/web/fleetFeed';
import MachineActivity, { FLEET_STALE_MS } from '@/components/Fleet/MachineActivity';

/** The account's machines and what their agents are doing, live from the cloud. */
const FleetMonitor: React.FC = () => {
  const { t } = useTranslation();
  const { connection, connectionDetail, machines } = useFleetFeedStore();

  useEffect(() => {
    startFleetFeed();
    return () => stopFleetFeed();
  }, []);

  const list = useMemo(
    () => Object.values(machines).sort((a, b) => (a.machine.name || '').localeCompare(b.machine.name || '')),
    [machines],
  );

  const status = {
    live: { type: 'success', text: t('pages.fleet.live', 'Live') },
    connecting: { type: 'info', text: t('pages.fleet.connecting', 'Connecting…') },
    reconnecting: { type: 'warning', text: t('pages.fleet.reconnecting', 'Reconnecting…') },
    error: { type: 'error', text: t('pages.fleet.error', 'The cloud refused the connection') },
    unconfigured: { type: 'warning', text: t('pages.fleet.unconfigured', 'Not available here') },
    idle: { type: 'info', text: '' },
  }[connection] as { type: 'success' | 'info' | 'warning' | 'error'; text: string };

  return (
    <div style={{ padding: 16, height: '100%', overflowY: 'auto' }}>
      <Space style={{ marginBottom: 12 }} wrap>
        <Typography.Title level={4} style={{ margin: 0 }}>{t('pages.fleet.title', 'Fleet monitor')}</Typography.Title>
        <Button size="small" icon={<ReloadOutlined />} onClick={() => sendFleetCommand('snapshot')}>
          {t('pages.fleet.refresh', 'Refresh')}
        </Button>
      </Space>
      {status.text && connection !== 'live' && (
        <Alert type={status.type} showIcon style={{ marginBottom: 12 }}
          message={status.text} description={connectionDetail || undefined} />
      )}
      {list.length === 0 ? (
        <Empty description={t('pages.fleet.empty',
          'No machine has reported yet. Machines report once a minute while eCan runs on them.')} />
      ) : list.map((m) => {
        const live = Date.now() - m.lastSeen < FLEET_STALE_MS;
        return (
          <Card key={m.machine.id || m.machine.name} size="small" style={{ marginBottom: 12 }}
            title={
              <Space wrap>
                <Badge status={live ? 'success' : 'default'} />
                <span>{m.machine.name || m.machine.id}</span>
                {m.machine.role && <Tag>{m.machine.role}</Tag>}
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {t('pages.fleet.lastSeen', 'last seen')} {m.lastSeen ? new Date(m.lastSeen).toLocaleTimeString() : '—'}
                </Typography.Text>
              </Space>
            }>
            <MachineActivity machineId={m.machine.id || m.machine.name} />
          </Card>
        );
      })}
    </div>
  );
};

export default FleetMonitor;
