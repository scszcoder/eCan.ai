/**
 * AgentHostTag — inline indicator showing which machine an agent runs on.
 *
 * Sources, in priority order:
 *   1. Discovery directory (zeroconf / cloud) — preferred because it knows
 *      both the machine NAME and the transport (LAN / WAN / local).
 *   2. Vehicle store (legacy) — falls back to the `vehicle_id` field on the
 *      agent record + name from `useVehicleStore`. Used when the agent
 *      isn't in the new discovery directory yet (Phase 4 migration window).
 *
 * Renders nothing if neither source has a hit (keeps the card uncluttered
 * when discovery is offline + no vehicle assigned).
 */

import React, { useMemo } from 'react';
import { Tag, Tooltip } from 'antd';
import { DesktopOutlined, GlobalOutlined, CloudOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

import { useDiscoveryStore } from '../../../stores/domain/discoveryStore';
import { useVehicleStore } from '../../../stores/domain/vehicleStore';

interface Props {
  /** Stable agent_id (= AgentCard.id from the backend). */
  agentId?: string | null;
  /** Optional legacy vehicle_id from the agent record, used as fallback. */
  vehicleId?: string | null;
  /** Optional compact mode (icon only, full name on hover). */
  compact?: boolean;
}

type Source = 'discovery-local' | 'discovery-lan' | 'discovery-wan' | 'vehicle' | 'none';

interface Resolved {
  source: Source;
  machineName: string;
  detail: string;   // hover detail (URL / channel / etc.)
  color: string;
  Icon: React.ComponentType<any>;
}

export function AgentHostTag({ agentId, vehicleId, compact }: Props) {
  const { t } = useTranslation();
  const discAgent = useDiscoveryStore(s => (agentId ? s.agentById[agentId] : undefined));
  const discNode = useDiscoveryStore(
    s => (discAgent ? s.nodeById[discAgent.machine_id] : undefined),
  );
  const selfMachineId = useDiscoveryStore(s => s.selfMachineId);

  const vehicles = useVehicleStore(s => s.items);

  const resolved = useMemo<Resolved | null>(() => {
    // ---- 1. Discovery directory (preferred) ----
    if (discAgent) {
      const isLocal = !!selfMachineId && discAgent.machine_id === selfMachineId;
      const hasLan = !!discAgent.lan_url;
      const hasWan = !!discAgent.wan_relay_channel;
      const machineName =
        discNode?.machine_name || (discAgent.machine_id || '').slice(0, 8) || 'unknown';

      if (isLocal) {
        return {
          source: 'discovery-local',
          machineName: t('pages.agents.hostLocal') || 'this machine',
          detail: machineName,
          color: 'green',
          Icon: DesktopOutlined,
        };
      }
      if (hasLan) {
        return {
          source: 'discovery-lan',
          machineName,
          detail: discAgent.lan_url || '',
          color: 'blue',
          Icon: GlobalOutlined,
        };
      }
      if (hasWan) {
        return {
          source: 'discovery-wan',
          machineName,
          detail: t('pages.agents.hostViaCloud') || 'via cloud relay',
          color: 'purple',
          Icon: CloudOutlined,
        };
      }
    }

    // ---- 2. Vehicle store (legacy fallback) ----
    if (vehicleId && vehicles && vehicles.length > 0) {
      const v: any = vehicles.find((x: any) => x.id === vehicleId);
      if (v) {
        const name = v.name || v.hostname || v.id;
        const isLocal =
          v.hostname === 'localhost' ||
          v.ip === '127.0.0.1' ||
          v.ip === '0.0.0.0' ||
          (v.name || '').includes('本机');
        return {
          source: 'vehicle',
          machineName: isLocal ? (t('pages.agents.hostLocal') || 'this machine') : name,
          detail: v.ip ? `${name} (${v.ip})` : name,
          color: isLocal ? 'green' : 'default',
          Icon: DesktopOutlined,
        };
      }
    }

    return null;
  }, [discAgent, discNode, selfMachineId, vehicleId, vehicles, t]);

  if (!resolved) return null;

  const { Icon, color, machineName, detail } = resolved;
  const hostLabel = t('pages.agents.hostPrefix') || '';
  const tooltip = (
    <>
      <div><strong>{machineName}</strong></div>
      {detail && detail !== machineName ? <div style={{ opacity: 0.75 }}>{detail}</div> : null}
    </>
  );

  return (
    <Tooltip title={tooltip}>
      <Tag
        color={color}
        icon={<Icon />}
        style={{
          margin: 0,
          fontSize: 11,
          lineHeight: '18px',
          padding: '0 6px',
          borderRadius: 4,
          flexShrink: 0,
        }}
      >
        {compact ? null : (
          <span style={{ maxWidth: 90, display: 'inline-block', overflow: 'hidden', textOverflow: 'ellipsis', verticalAlign: 'middle', whiteSpace: 'nowrap' }}>
            {hostLabel ? `${hostLabel} ${machineName}` : machineName}
          </span>
        )}
      </Tag>
    </Tooltip>
  );
}

export default AgentHostTag;
