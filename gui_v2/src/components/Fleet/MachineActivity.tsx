import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Select, Space, Switch, Tag, Typography, theme } from 'antd';
import { useFleetFeedStore, FleetEvent } from '@/stores/fleetFeedStore';
import { sendFleetCommand } from '@/services/web/fleetFeed';

export const FLEET_STALE_MS = 150_000;   // two missed 60 s snapshots

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

/** One machine's live activity: agents, recent events and the log tail controls. */
const MachineActivity: React.FC<{ machineId: string }> = ({ machineId }) => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const m = useFleetFeedStore((s) => s.machines[machineId]);
  const [ttl, setTtl] = useState(300);
  const [level, setLevel] = useState('INFO');
  const [follow, setFollow] = useState(true);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (follow && logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [m?.logs.length, follow]);

  if (!m) {
    return <Typography.Text type="secondary">{t('pages.fleet.waiting', 'Waiting for this machine to report…')}</Typography.Text>;
  }

  return (
    <div>
      <Space wrap style={{ marginBottom: 8 }}>
        {m.agents.length === 0 && <Typography.Text type="secondary">{t('pages.fleet.noAgents', 'No agents reported yet')}</Typography.Text>}
        {m.agents.map((a) => (
          <Tag key={a.id} color={a.running ? 'green' : 'default'}>
            {a.name} {a.running ? '●' : '○'}
          </Tag>
        ))}
      </Space>

      <Typography.Text strong style={{ fontSize: 12 }}>{t('pages.fleet.events', 'Recent activity')}</Typography.Text>
      <div style={{ maxHeight: 200, overflowY: 'auto', fontSize: 12, fontFamily: 'monospace', marginTop: 4 }}>
        {m.events.length === 0 && <Typography.Text type="secondary">—</Typography.Text>}
        {[...m.events].reverse().slice(0, 100).map((ev, i) => (
          <div key={`${ev.ts}-${i}`} style={{ color: ev.status === 'failed' ? token.colorError : undefined }}>
            {time(ev.ts)} {eventLine(ev, t)}
          </div>
        ))}
      </div>

      <Space wrap style={{ marginTop: 12 }}>
        <Typography.Text strong style={{ fontSize: 12 }}>
          {t('pages.fleet.log', 'Live log')}{m.logDropped ? ` (${m.logDropped} ${t('pages.fleet.dropped', 'lines skipped')})` : ''}
        </Typography.Text>
        {m.logTail ? (
          <Button size="small" onClick={() => sendFleetCommand('log_stop', machineId)}>
            {t('pages.fleet.stopLog', 'Stop log')}
          </Button>
        ) : (
          <>
            <Select size="small" value={level} onChange={setLevel} style={{ width: 100 }}
              options={['INFO', 'WARNING', 'ERROR'].map((l) => ({ value: l, label: l }))} />
            <Select size="small" value={ttl} onChange={setTtl} style={{ width: 90 }}
              options={[{ value: 300, label: '5 min' }, { value: 900, label: '15 min' }, { value: 1800, label: '30 min' }]} />
            <Button size="small" type="primary"
              onClick={() => sendFleetCommand('log_start', machineId, { ttl_s: ttl, level })}>
              {t('pages.fleet.startLog', 'Live log')}
            </Button>
          </>
        )}
        <Space size={4}>
          <Switch size="small" checked={follow} onChange={setFollow} />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>{t('pages.fleet.follow', 'Auto-scroll')}</Typography.Text>
        </Space>
      </Space>
      {(m.logTail || m.logs.length > 0) && (
        <div ref={logRef} style={{
          maxHeight: 360, overflowY: 'auto', fontSize: 11, fontFamily: 'monospace', whiteSpace: 'pre-wrap',
          background: token.colorFillTertiary, padding: 8, borderRadius: 6, marginTop: 6,
        }}>
          {m.logs.map((l, i) => (
            <div key={`${l.ts}-${i}`} style={{ color: l.level === 'ERROR' ? token.colorError : l.level === 'WARNING' ? token.colorWarning : undefined }}>
              {time(l.ts)} {String(l.text || '')}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default MachineActivity;
