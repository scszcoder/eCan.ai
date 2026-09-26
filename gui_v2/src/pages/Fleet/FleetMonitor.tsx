import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Badge, Button, Card, Empty, Select, Space, Tag, Typography, theme } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useFleetFeedStore, FleetMachineState, FleetEvent } from '@/stores/fleetFeedStore';
import { sendFleetCommand, startFleetFeed } from '@/services/web/fleetFeed';

const STALE_MS = 150_000;   // two missed 60 s snapshots

const time = (ts: number) => new Date(ts).toLocaleTimeString();

function eventLine(ev: FleetEvent, t: (k: string, d: string) => string): string {
  if (ev.kind === 'task') {
    const err = ev.error ? ` — ${String(ev.error)}` : '';
    return `${t('pages.fleet.task', 'Task')} ${String(ev.task || '')}: ${String(ev.status || '')}${err}`;
  }
  if (ev.kind === 'agent_status') {
    const { kind, ts, agent_id, agent_name, updated_at, ...rest } = ev as Record<string, unknown>;
    void kind; void ts; void updated_at;
    const fields = Object.entries(rest).map(([k, v]) => `${k}=${String(v)}`).join(' ');
    return `${String(agent_name || agent_id || '')}: ${fields}`;
  }
  return JSON.stringify(ev);
}

const MachineCard: React.FC<{ m: FleetMachineState }> = ({ m }) => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const [ttl, setTtl] = useState(300);
  const logRef = useRef<HTMLDivElement>(null);
  const live = Date.now() - m.lastSeen < STALE_MS;

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [m.logs.length]);

  return (
    <Card
      size="small"
      style={{ marginBottom: 12 }}
      title={
        <Space wrap>
          <Badge status={live ? 'success' : 'default'} />
          <span>{m.machine.name || m.machine.id}</span>
          {m.machine.role && <Tag>{m.machine.role}</Tag>}
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {t('pages.fleet.lastSeen', 'last seen')} {m.lastSeen ? time(m.lastSeen) : '—'}
          </Typography.Text>
        </Space>
      }
      extra={
        m.logTail ? (
          <Button size="small" onClick={() => sendFleetCommand('log_stop', m.machine.id)}>
            {t('pages.fleet.stopLog', 'Stop log')}
          </Button>
        ) : (
          <Space size={4}>
            <Select size="small" value={ttl} onChange={setTtl} style={{ width: 90 }}
              options={[{ value: 300, label: '5 min' }, { value: 900, label: '15 min' }, { value: 1800, label: '30 min' }]} />
            <Button size="small" type="primary" onClick={() => sendFleetCommand('log_start', m.machine.id, { ttl_s: ttl })}>
              {t('pages.fleet.startLog', 'Live log')}
            </Button>
          </Space>
        )
      }
    >
      <Space wrap style={{ marginBottom: 8 }}>
        {m.agents.length === 0 && <Typography.Text type="secondary">{t('pages.fleet.noAgents', 'No agents reported yet')}</Typography.Text>}
        {m.agents.map((a) => (
          <Tag key={a.id} color={a.running ? 'green' : 'default'}>
            {a.name} {a.running ? '●' : '○'}
          </Tag>
        ))}
      </Space>

      <Typography.Text strong style={{ fontSize: 12 }}>{t('pages.fleet.events', 'Recent activity')}</Typography.Text>
      <div style={{ maxHeight: 180, overflowY: 'auto', fontSize: 12, fontFamily: 'monospace', marginTop: 4 }}>
        {m.events.length === 0 && <Typography.Text type="secondary">—</Typography.Text>}
        {[...m.events].reverse().slice(0, 100).map((ev, i) => (
          <div key={`${ev.ts}-${i}`} style={{ color: ev.status === 'failed' ? token.colorError : undefined }}>
            {time(ev.ts)} {eventLine(ev, t)}
          </div>
        ))}
      </div>

      {(m.logTail || m.logs.length > 0) && (
        <>
          <Typography.Text strong style={{ fontSize: 12, display: 'block', marginTop: 8 }}>
            {t('pages.fleet.log', 'Live log')}{m.logDropped ? ` (${m.logDropped} ${t('pages.fleet.dropped', 'lines skipped')})` : ''}
          </Typography.Text>
          <div ref={logRef} style={{
            maxHeight: 320, overflowY: 'auto', fontSize: 11, fontFamily: 'monospace', whiteSpace: 'pre-wrap',
            background: token.colorFillTertiary, padding: 8, borderRadius: 6, marginTop: 4,
          }}>
            {m.logs.map((l, i) => (
              <div key={`${l.ts}-${i}`} style={{ color: l.level === 'ERROR' ? token.colorError : l.level === 'WARNING' ? token.colorWarning : undefined }}>
                {time(l.ts)} {String(l.text || '')}
              </div>
            ))}
          </div>
        </>
      )}
    </Card>
  );
};

/** The account's machines and what their agents are doing, live from the cloud. */
const FleetMonitor: React.FC = () => {
  const { t } = useTranslation();
  const { connection, connectionDetail, machines } = useFleetFeedStore();

  useEffect(() => { startFleetFeed(); }, []);

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
      ) : list.map((m) => <MachineCard key={m.machine.id || m.machine.name} m={m} />)}
    </div>
  );
};

export default FleetMonitor;
