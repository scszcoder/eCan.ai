/**
 * Pods — the cloud half of the vehicle page.
 *
 * A machine below is something we discovered; a pod is something the customer
 * creates and pays for. The list shows both halves of a pod's truth side by
 * side: what was asked for (replicas, lifecycle, capabilities) and what the
 * fleet reports (status, last heartbeat). They are never merged, because a
 * customer who raises replicas needs to watch it converge.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Empty, Popconfirm, Space, Spin, Tag, Tooltip, Typography, message } from 'antd';
import { PlusOutlined, ReloadOutlined, DeleteOutlined, EditOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { IPCAPI } from '@/services/ipc/api';
import { isDedicatedCapability } from '@/types/domain/placement';
import { estimatePodCost, type Pod, type PodLimits } from '@/types/domain/pod';
import * as podService from '@/services/pods/podService';
import { logger } from '@/utils/logger';
import PodFormModal from './PodFormModal';

const { Text } = Typography;

/**
 * The page's list card styles `.ant-card-body` as a DESCENDANT selector, so its
 * rules — `flex: 1 1 0`, `min-height: 0`, `overflow-y: auto`, `max-height: 100%`,
 * `padding: 0 !important` — also land on THIS card's body, which is nested
 * inside it. A body carrying those can collapse to a sliver of clipped text
 * instead of sizing to its content. Take them back for our own card only.
 */
const Panel = styled.div`
  .ant-card-body {
    flex: 0 0 auto;
    min-height: auto;
    max-height: none;
    overflow: visible;
    display: block;
    padding: 12px !important;
  }
`;

/** One pod as the fleet reports it (server `fleet_status`). */
interface FleetVehicle {
  id: string;
  /** Which pool spawned it, when one did. A hand-rolled Deployment has none. */
  poolId?: string | null;
  name: string;
  status: string;
  live: boolean;
  secondsSinceHeartbeat: number | null;
  inFlight: number;
  capabilities: string[];
}

interface FleetQueue {
  queued: number;
  running: number;
  oldestQueuedSeconds: number;
  maxQueuedSeconds: number;
}

interface FleetStatus {
  vehicles: FleetVehicle[];
  liveVehicles: number;
  hasLivePod: boolean;
  queue: FleetQueue;
  staleAfterSeconds?: number;
}

function ago(seconds: number | null | undefined): string {
  if (seconds == null) return 'never';
  const s = Math.max(0, Math.round(seconds));
  if (s < 90) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 90) return `${m}m ago`;
  return `${Math.round(m / 60)}h ago`;
}

function heartbeatLabel(pod: Pod): string {
  if (!pod.last_heartbeat) return 'never seen';
  const seen = new Date(pod.last_heartbeat).getTime();
  if (Number.isNaN(seen)) return String(pod.last_heartbeat);
  return ago((Date.now() - seen) / 1000);
}

const PodsPanel: React.FC = () => {
  const [pods, setPods] = useState<Pod[]>([]);
  const [fleet, setFleet] = useState<FleetStatus | null>(null);
  const [limits, setLimits] = useState<PodLimits | null>(null);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Pod | null>(null);
  // Pods live only in the cloud, so a failed load is not an empty list. Showing
  // the empty state here would tell a customer they have no pods while they are
  // paying for one, and invite them to create a second.
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await podService.getPods();
      if (resp?.success && resp.data) {
        setPods(resp.data.pods || []);
        setLimits(resp.data.limits || null);
        setLoadError(null);
      } else {
        logger.warn('[PodsPanel] failed to load pods:', resp?.error);
        setLoadError(resp?.error?.message || 'Could not load pods.');
      }
    } catch (e) {
      logger.warn('[PodsPanel] failed to load pods:', e);
      setLoadError(e instanceof Error ? e.message : 'Could not load pods.');
    } finally {
      setLoading(false);
    }

    // Desired state came from the rows above; this is what the fleet actually
    // reports. Kept separate on purpose — and non-fatal, because a pod list
    // that cannot reach the control plane should still show what was asked for.
    try {
      const resp = await IPCAPI.getInstance().getFleetStatus<any>();
      setFleet(resp?.success && resp.data ? (resp.data as FleetStatus) : null);
    } catch (e) {
      logger.warn('[PodsPanel] fleet status unavailable:', e);
      setFleet(null);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleSubmit = async (values: Record<string, any>) => {
    const resp = await podService.savePod(values);
    if (resp?.success) {
      message.success(values.id ? 'Pod updated' : 'Pod created');
      setModalOpen(false);
      setEditing(null);
      load();
    } else {
      // The server owns the limits; surface its refusal rather than guessing.
      message.error(resp?.error?.message || 'Failed to save pod');
    }
  };

  const handleDelete = async (pod: Pod) => {
    const resp = await podService.deletePod(pod.id);
    if (resp?.success) {
      message.success('Pod deleted');
      load();
    } else {
      message.error(resp?.error?.message || 'Failed to delete pod');
    }
  };

  // Indexed by BOTH ids. A pod card is a POOL (`pod_2acc…`), while the fleet
  // reports the running instance (`pod-2acc…-<replicaset>-<suffix>`), so keying
  // only by vehicle id makes a live pod render "not registered" — understating
  // convergence, which misleads exactly as much as overstating it.
  const fleetById = new Map<string, FleetVehicle>(
    (fleet?.vehicles || []).flatMap((v) => {
      const entries: [string, FleetVehicle][] = [[v.id, v]];
      if (v.poolId) entries.push([v.poolId, v]);
      return entries;
    }),
  );

  // A turn queued far past the server's own ceiling is the customer's problem
  // before it is anybody else's: otherwise they see slow replies with no cause.
  const queueIsBacklogged = Boolean(
    fleet &&
      fleet.queue.maxQueuedSeconds > 0 &&
      fleet.queue.oldestQueuedSeconds > fleet.queue.maxQueuedSeconds / 2,
  );

  const totalMonthly = pods.reduce((sum, pod) => {
    const cost =
      pod.cost ||
      estimatePodCost(
        pod.cpu_cores || 0,
        pod.memory_gb || 0,
        pod.lifecycle,
        pod.desired_replicas,
      );
    return sum + (cost.monthly_cny || 0);
  }, 0);

  return (
    <Panel>
    <Card
      size="small"
      title={
        <Space wrap>
          <span>Pods</span>
          {limits && (
            <Text type="secondary" style={{ fontWeight: 400 }}>
              {limits.used_pods} of {limits.max_pods} · about ¥{totalMonthly.toFixed(0)}/month
            </Text>
          )}
          {fleet && (
            <Text
              type={queueIsBacklogged ? 'danger' : 'secondary'}
              style={{ fontWeight: 400 }}
            >
              queue {fleet.queue.queued} waiting · {fleet.queue.running} running
              {fleet.queue.queued > 0
                ? ` · oldest ${ago(fleet.queue.oldestQueuedSeconds)}`
                : ''}
            </Text>
          )}
        </Space>
      }
      extra={
        <Space>
          <Tooltip title="Refresh">
            <Button size="small" icon={<ReloadOutlined />} onClick={load} />
          </Tooltip>
          <Button
            size="small"
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setEditing(null);
              setModalOpen(true);
            }}
          >
            Create pod
          </Button>
        </Space>
      }
      style={{ marginBottom: 12 }}
    >
      <Spin spinning={loading}>
        {loadError ? (
          <Alert
            type="warning"
            showIcon
            message="Could not load your pods"
            description={loadError}
            action={
              <Button size="small" onClick={load}>
                Retry
              </Button>
            }
          />
        ) : pods.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="No pods. Agents run on this machine until you create one."
          />
        ) : (
          // Bounded: the panel does not shrink (see Vehicles.tsx), so without a
          // ceiling a long pod list would push the vehicle list off the page.
          <Space
            direction="vertical"
            size={8}
            style={{ width: '100%', maxHeight: '38vh', overflowY: 'auto' }}
          >
            {pods.map((pod) => {
              const cost =
                pod.cost ||
                estimatePodCost(
                  pod.cpu_cores || 0,
                  pod.memory_gb || 0,
                  pod.lifecycle,
                  pod.desired_replicas,
                );
              return (
                <Card key={pod.id} size="small" bodyStyle={{ padding: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                    <div style={{ minWidth: 0 }}>
                      <Space size={6} wrap>
                        <Text strong>{pod.name}</Text>
                        {/* The fleet's `live`, never `status`: a dead pod keeps
                            status='online' until the reaper notices it, which is
                            minutes of showing a machine that is gone. */}
                        {!fleet ? (
                          <Tooltip title="The fleet view is unavailable; this is the last stored state.">
                            <Tag>{pod.status || 'offline'} (unconfirmed)</Tag>
                          </Tooltip>
                        ) : !fleetById.has(pod.id) ? (
                          <Tooltip title="This pod has never registered with the fleet.">
                            <Tag>not registered</Tag>
                          </Tooltip>
                        ) : fleetById.get(pod.id)!.live ? (
                          <Tag color="green">live</Tag>
                        ) : (
                          <Tooltip
                            title={`Reported ${fleetById.get(pod.id)!.status}, but last heartbeat was ${ago(fleetById.get(pod.id)!.secondsSinceHeartbeat)}.`}
                          >
                            <Tag color="red">not live</Tag>
                          </Tooltip>
                        )}
                        <Text type="secondary">
                          {fleetById.has(pod.id)
                            ? ago(fleetById.get(pod.id)!.secondsSinceHeartbeat)
                            : heartbeatLabel(pod)}
                        </Text>
                        {(fleetById.get(pod.id)?.inFlight ?? 0) > 0 && (
                          <Tag color="blue">{fleetById.get(pod.id)!.inFlight} in flight</Tag>
                        )}
                      </Space>
                      <div style={{ marginTop: 6 }}>
                        <Space size={6} wrap>
                          <Tag>{pod.cpu_cores} vCPU · {pod.memory_gb} GiB</Tag>
                          <Tag color={pod.lifecycle === 'always_on' ? 'blue' : 'default'}>
                            {pod.lifecycle === 'always_on' ? 'always on' : 'on demand'}
                          </Tag>
                          <Tag>×{pod.desired_replicas} wanted</Tag>
                          {pod.lifecycle === 'on_demand' && pod.idle_shutdown_minutes ? (
                            <Tag>idle {pod.idle_shutdown_minutes}m</Tag>
                          ) : null}
                        </Space>
                      </div>
                      {pod.capabilities?.length > 0 && (
                        <div style={{ marginTop: 6 }}>
                          <Space size={4} wrap>
                            {pod.capabilities.map((cap) => (
                              <Tag key={cap} color={isDedicatedCapability(cap) ? 'purple' : 'cyan'}>
                                {cap}
                              </Tag>
                            ))}
                          </Space>
                        </div>
                      )}
                      <div style={{ marginTop: 6 }}>
                        <Text type="secondary">
                          {cost.monthly_is_ceiling ? 'up to ' : 'about '}
                          ¥{cost.monthly_cny.toFixed(0)}/month
                        </Text>
                      </div>
                    </div>
                    <Space>
                      <Tooltip title="Edit">
                        <Button
                          size="small"
                          icon={<EditOutlined />}
                          onClick={() => {
                            setEditing(pod);
                            setModalOpen(true);
                          }}
                        />
                      </Tooltip>
                      <Popconfirm
                        title="Delete this pod?"
                        description="Work it is running finishes; queued turns move to another pod."
                        onConfirm={() => handleDelete(pod)}
                      >
                        <Button size="small" danger icon={<DeleteOutlined />} />
                      </Popconfirm>
                    </Space>
                  </div>
                </Card>
              );
            })}
          </Space>
        )}
      </Spin>

      <PodFormModal
        open={modalOpen}
        pod={editing}
        limits={limits}
        onCancel={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        onSubmit={handleSubmit}
      />
    </Card>
    </Panel>
  );
};

export default PodsPanel;
