/**
 * ReadinessStrip — per-agent readiness dots driven by the backend's
 * [AGENT-STATUS] ledger (utils/agent_status.py), delivered through
 * get_all_agents_runtime_status as `readiness`.
 *
 * Five dots: Chrome attach, site tab, DOM monitor, DOM elements, detection
 * path. Hover shows the raw values. Renders nothing until the backend has
 * reported at least one key for this agent, so cards of idle agents stay
 * unchanged.
 */
import React from 'react';
import { Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';

export type Readiness = Record<string, string | number | null | undefined>;

type Level = 'ok' | 'warn' | 'bad' | 'unknown';

const COLORS: Record<Level, string> = {
  ok: '#22c55e',
  warn: '#f59e0b',
  bad: '#ef4444',
  unknown: 'rgba(148,163,184,0.45)',
};

function chromeLevel(r: Readiness): Level {
  switch (r.chrome) {
    case 'attached_existing': return 'ok';
    case 'auto_started':
    case 'auto_starting': return 'warn';   // eCan's own blank Chrome — site login may be missing
    case 'unreachable': return 'bad';
    default: return 'unknown';
  }
}
function siteTabLevel(r: Readiness): Level {
  if (r.site_tab === 'found') return 'ok';
  if (r.site_tab === 'missing') return 'bad';
  return 'unknown';
}
function monitorLevel(r: Readiness): Level {
  if (r.monitor === 'running') {
    if (r.monitor_hb === 'page_mismatch' || r.monitor_hb === 'cdp_error') return 'bad';
    if (r.monitor_hb === 'no_match' || r.monitor_hb === 'empty') return 'warn';
    return 'ok';
  }
  if (r.monitor === 'stopped') return 'bad';
  return 'unknown';
}
function domLevel(r: Readiness): Level {
  if (typeof r.dom_items === 'number') return r.dom_items > 0 ? 'ok' : 'warn';
  return 'unknown';
}
function detectionLevel(r: Readiness): Level {
  if (r.detection === 'ws' || r.detection === 'dom') return 'ok';
  return 'unknown';
}

export const ReadinessStrip: React.FC<{ readiness?: Readiness | null }> = ({ readiness }) => {
  const { t } = useTranslation();
  if (!readiness || Object.keys(readiness).length === 0) return null;
  const r = readiness;
  const dots: Array<{ key: string; level: Level; label: string; detail: string }> = [
    { key: 'chrome', level: chromeLevel(r), label: t('pages.agents.readiness_chrome', 'Chrome'),
      detail: `${r.chrome ?? '?'}${r.chrome_port ? ` :${r.chrome_port}` : ''}` },
    { key: 'site_tab', level: siteTabLevel(r), label: t('pages.agents.readiness_site_tab', 'Site tab'),
      detail: `${r.site_tab ?? '?'}${r.site_tab_url ? ` ${r.site_tab_url}` : ''}` },
    { key: 'monitor', level: monitorLevel(r), label: t('pages.agents.readiness_monitor', 'Monitor'),
      detail: `${r.monitor ?? '?'}${r.monitor_label ? ` ${r.monitor_label}` : ''}${r.monitor_hb ? ` hb=${r.monitor_hb}` : ''}` },
    { key: 'dom', level: domLevel(r), label: t('pages.agents.readiness_dom', 'DOM'),
      detail: `items=${r.dom_items ?? '?'}${r.dom_roots != null ? ` roots=${r.dom_roots}` : ''}${r.dom_last_items_at ? ` last=${r.dom_last_items_at}` : ''}` },
    { key: 'detection', level: detectionLevel(r), label: t('pages.agents.readiness_detection', 'Detection'),
      detail: `${r.detection ?? '?'}` },
  ];
  const updated = r.updated_at ? `${t('pages.agents.readiness_updated', 'updated')} ${r.updated_at}` : '';
  return (
    <div
      onClick={(e) => e.stopPropagation()}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 5, marginLeft: 6, flexShrink: 0 }}
      aria-label={t('pages.agents.readiness', 'Readiness')}
    >
      {dots.map((d) => (
        <Tooltip key={d.key} title={<span style={{ fontSize: 12 }}>{d.label}: {d.detail}{updated ? <><br />{updated}</> : null}</span>}>
          <span
            style={{
              width: 7, height: 7, borderRadius: '50%', display: 'inline-block',
              background: COLORS[d.level], boxShadow: d.level === 'bad' ? `0 0 4px ${COLORS.bad}` : undefined,
            }}
          />
        </Tooltip>
      ))}
    </div>
  );
};

export default ReadinessStrip;
