import React, { useEffect, useState } from 'react';
import { Tag, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '@/services/ipc_api';

interface PoolMember {
  id: string;
  name: string;
  active: boolean;
  running: boolean;
  load: number;
  last_turn: number | null;
}

interface PoolView {
  settings: { min: number; max: number; idle_minutes: number };
  members: PoolMember[];
  scaling: boolean;
  active_count: number;
  wait_p50_s: number;
  wait_p90_s: number;
  turns_last_hour: number;
  expected_turns_this_hour: number | null;
}

const POLL_MS = 5000;

/** The Q&A pool a front-desk agent dispatches to (agent_pool.py); nothing for other agents. */
const AgentPoolPanel: React.FC<{ agentId?: string }> = ({ agentId }) => {
  const { t } = useTranslation();
  const k = (key: string, def: string, o?: any): string =>
    String(t(`pages.agents.pool.${key}`, { defaultValue: def, ...(o || {}) }));
  const [pool, setPool] = useState<PoolView | null>(null);

  useEffect(() => {
    if (!agentId) return undefined;
    let alive = true;
    const load = async () => {
      const api = get_ipc_api();
      if (!api) return;
      try {
        const res = await api.executeRequest<{ pool: PoolView | null }>('get_agent_pool', { agent_id: agentId });
        if (alive && res?.success) setPool(res.data?.pool || null);
      } catch {
        /* next poll */
      }
    };
    load();
    const timer = setInterval(load, POLL_MS);
    return () => { alive = false; clearInterval(timer); };
  }, [agentId]);

  if (!pool) return null;
  const s = pool.settings;
  return (
    <div data-testid="agent-pool-panel" style={{
      margin: '0 0 12px', padding: '8px 10px', borderRadius: 6,
      background: 'rgba(59, 130, 246, 0.06)', border: '1px solid rgba(59, 130, 246, 0.18)',
    }}>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
        {k('title', 'Q&A pool')}{' '}
        <span style={{ fontWeight: 400, opacity: 0.75 }}>
          {k('summary', '{{active}} of {{total}} answering (min {{min}}, max {{max}})',
            { active: pool.active_count, total: pool.members.length, min: s.min, max: s.max })}
        </span>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 6 }}>
        {pool.members.map((m) => (
          <Tooltip key={m.id} title={!m.running ? k('notRunning', 'Not running on this computer')
            : m.active ? k('activeTip', 'Answering; {{n}} turn(s) queued or running', { n: m.load })
              : k('parkedTip', 'Parked: gets no new customers, finishes what it has')}>
            <Tag data-testid={`pool-member-${m.id}`} color={!m.running ? 'default' : m.active ? 'blue' : undefined}
              style={{ margin: 0, opacity: m.active ? 1 : 0.6 }}>
              {m.name}{m.load > 0 ? ` · ${m.load}` : ''}
            </Tag>
          </Tooltip>
        ))}
      </div>
      <div style={{ fontSize: 12, opacity: 0.7 }}>
        {k('stats', 'Wait p50 {{p50}}s · p90 {{p90}}s · {{turns}} turn(s) in the last hour',
          { p50: pool.wait_p50_s, p90: pool.wait_p90_s, turns: pool.turns_last_hour })}
        {pool.expected_turns_this_hour != null
          ? ` · ${k('expected', 'usually {{n}} this hour', { n: Math.round(pool.expected_turns_this_hour) })}` : ''}
        {!pool.scaling ? ` · ${k('fixed', 'scaling off')}` : ''}
      </div>
    </div>
  );
};

export default AgentPoolPanel;
