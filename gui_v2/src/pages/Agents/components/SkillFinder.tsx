/**
 * SkillFinder — "find any agent with skill X across the fleet" widget.
 *
 * Backed by `discovery.list_skills` (autocomplete) + `discovery.find_agents`
 * (results). Lives at the top of the Agents page as a small AutoComplete +
 * results popover. Selecting an agent from results navigates to chat.
 *
 * Why a popover and not a full results page:
 *   The agent grid below is already the user's primary navigation. The
 *   skill finder is "I know what I want, jump to it" — overlay UX fits
 *   better than replacing the grid. Future Phase 6 could promote this
 *   to a proper fleet search page if usage warrants.
 */

import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { AutoComplete, Input, Popover, Empty, Tag, Tooltip, Spin } from 'antd';
import { SearchOutlined, DesktopOutlined, GlobalOutlined, CloudOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import {
  discoveryApi,
  type DiscoveredAgent,
  type DiscoveryTransport,
} from '../../../services/api/discoveryApi';
import { useDiscoveryStore } from '../../../stores/domain/discoveryStore';

interface Props {
  /** Max width of the input field. */
  maxWidth?: number;
  /** Optional className to position the widget in the parent layout. */
  className?: string;
  /** Optional inline style. */
  style?: React.CSSProperties;
}

function transportFor(a: DiscoveredAgent): DiscoveryTransport {
  const hasLan = !!a.lan_url;
  const hasWan = !!a.wan_relay_channel;
  if (hasLan && hasWan) return 'lan+wan';
  if (hasLan) return 'lan';
  if (hasWan) return 'wan';
  return 'none';
}

function transportIcon(t: DiscoveryTransport): React.ReactNode {
  if (t === 'lan' || t === 'lan+wan') return <GlobalOutlined />;
  if (t === 'wan') return <CloudOutlined />;
  return <DesktopOutlined />;
}

function transportColor(t: DiscoveryTransport): string {
  if (t === 'lan' || t === 'lan+wan') return 'blue';
  if (t === 'wan') return 'purple';
  return 'default';
}

export function SkillFinder({ maxWidth = 280, className, style }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  // Skill catalog comes from the discovery store snapshot (already polled
  // every 15 s on the Agents page) so we don't re-hit the IPC just to fill
  // the autocomplete.
  const agents = useDiscoveryStore(s => s.agents);
  const selfMachineId = useDiscoveryStore(s => s.selfMachineId);
  const lanActive = useDiscoveryStore(s => s.lanActive);
  const wanActive = useDiscoveryStore(s => s.wanActive);

  const skillOptions = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const a of agents) {
      for (const s of a.skills) {
        if (!s) continue;
        counts[s] = (counts[s] || 0) + 1;
      }
    }
    return Object.keys(counts)
      .sort((a, b) => counts[b] - counts[a] || a.localeCompare(b))
      .map(name => ({
        value: name,
        label: (
          <span>
            <span>{name}</span>
            <span style={{ float: 'right', opacity: 0.65 }}>×{counts[name]}</span>
          </span>
        ),
      }));
  }, [agents]);

  const [query, setQuery] = useState('');
  const [results, setResults] = useState<DiscoveredAgent[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const runSearch = useCallback(async (skill: string) => {
    const trimmed = (skill || '').trim();
    if (!trimmed) {
      setResults(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const r = await discoveryApi.findAgents({
        skill: trimmed,
        reachable: false,
        exclude_self: false,
        limit: 25,
      });
      if (r.success && r.data) {
        setResults(r.data.agents || []);
      } else {
        setError(r.error?.message || 'search failed');
        setResults([]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Debounce typing — wait 250 ms after last keystroke before hitting IPC.
  useEffect(() => {
    if (!query.trim()) {
      setResults(null);
      return;
    }
    const handle = setTimeout(() => {
      void runSearch(query);
    }, 250);
    return () => clearTimeout(handle);
  }, [query, runSearch]);

  const handleSelect = (value: string) => {
    setQuery(value);
    void runSearch(value);
    setOpen(true);
  };

  const handleAgentClick = (a: DiscoveredAgent) => {
    setOpen(false);
    navigate(`/chat?agentId=${encodeURIComponent(a.agent_id)}`);
  };

  const placeholder =
    t('pages.agents.findBySkillPlaceholder') ||
    'Find agent by skill (e.g. find_air_ticket)';

  const popoverContent = (
    <div style={{ minWidth: 320, maxWidth: 420 }}>
      <div style={{ marginBottom: 8, fontSize: 12, opacity: 0.7 }}>
        {t('pages.agents.discoveryStatus') || 'Discovery'}: LAN{' '}
        <Tag color={lanActive ? 'green' : 'default'} style={{ margin: 0 }}>
          {lanActive ? 'on' : 'off'}
        </Tag>{' '}
        WAN{' '}
        <Tag color={wanActive ? 'green' : 'default'} style={{ margin: 0 }}>
          {wanActive ? 'on' : 'off'}
        </Tag>
      </div>
      {loading ? (
        <div style={{ padding: 16, textAlign: 'center' }}>
          <Spin size="small" />
        </div>
      ) : error ? (
        <div style={{ color: '#ff7875', fontSize: 12 }}>{error}</div>
      ) : !results || results.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            query.trim()
              ? t('pages.agents.noSkillMatch') || 'No agents offer this skill on the fleet right now.'
              : t('pages.agents.skillFinderHint') || 'Start typing a skill name.'
          }
        />
      ) : (
        <div style={{ maxHeight: 320, overflowY: 'auto' }}>
          {results.map(a => {
            const tport = transportFor(a);
            const isLocal = !!selfMachineId && a.machine_id === selfMachineId;
            return (
              <div
                key={a.agent_id}
                onClick={() => handleAgentClick(a)}
                style={{
                  padding: '8px 10px',
                  borderBottom: '1px solid rgba(255,255,255,0.06)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {a.name || a.agent_id}
                  </div>
                  <div style={{ fontSize: 11, opacity: 0.6, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {a.role || ' '}
                  </div>
                </div>
                <Tooltip title={isLocal ? 'this PC' : a.machine_id.slice(0, 12)}>
                  <Tag
                    color={isLocal ? 'green' : transportColor(tport)}
                    icon={isLocal ? <DesktopOutlined /> : transportIcon(tport)}
                    style={{ margin: 0, fontSize: 11 }}
                  >
                    {isLocal
                      ? t('pages.agents.hostLocal') || 'this PC'
                      : tport.toUpperCase()}
                  </Tag>
                </Tooltip>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );

  return (
    <Popover
      content={popoverContent}
      trigger="click"
      open={open}
      onOpenChange={setOpen}
      placement="bottomLeft"
      title={t('pages.agents.findBySkillTitle') || 'Find agent by skill'}
    >
      <div className={className} style={{ maxWidth, width: '100%', ...style }}>
        <AutoComplete
          options={query.trim() ? skillOptions.filter(o => o.value.toLowerCase().includes(query.toLowerCase())) : skillOptions.slice(0, 20)}
          value={query}
          onChange={setQuery}
          onSelect={handleSelect}
          onFocus={() => setOpen(true)}
          style={{ width: '100%' }}
        >
          <Input
            allowClear
            prefix={<SearchOutlined style={{ opacity: 0.6 }} />}
            placeholder={placeholder}
          />
        </AutoComplete>
      </div>
    </Popover>
  );
}

export default SkillFinder;
