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
import { Button, Card, Empty, Popconfirm, Space, Spin, Tag, Tooltip, Typography, message } from 'antd';
import { PlusOutlined, ReloadOutlined, DeleteOutlined, EditOutlined } from '@ant-design/icons';
import { IPCAPI } from '@/services/ipc/api';
import { isDedicatedCapability } from '@/types/domain/placement';
import { estimatePodCost, type Pod, type PodLimits } from '@/types/domain/pod';
import { logger } from '@/utils/logger';
import PodFormModal from './PodFormModal';

const { Text } = Typography;

function statusColor(status?: string): string {
  switch ((status || '').toLowerCase()) {
    case 'online':
      return 'green';
    case 'busy':
      return 'blue';
    case 'maintenance':
      return 'orange';
    default:
      return 'default';
  }
}

function heartbeatLabel(pod: Pod): string {
  if (!pod.last_heartbeat) return 'never seen';
  const seen = new Date(pod.last_heartbeat).getTime();
  if (Number.isNaN(seen)) return String(pod.last_heartbeat);
  const seconds = Math.max(0, Math.round((Date.now() - seen) / 1000));
  if (seconds < 90) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) return `${minutes}m ago`;
  return `${Math.round(minutes / 60)}h ago`;
}

const PodsPanel: React.FC = () => {
  const [pods, setPods] = useState<Pod[]>([]);
  const [limits, setLimits] = useState<PodLimits | null>(null);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Pod | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await IPCAPI.getInstance().getPods<any>();
      if (resp?.success && resp.data) {
        setPods(resp.data.pods || []);
        setLimits(resp.data.limits || null);
      } else {
        logger.warn('[PodsPanel] failed to load pods:', resp?.error);
      }
    } catch (e) {
      logger.warn('[PodsPanel] failed to load pods:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleSubmit = async (values: Record<string, any>) => {
    const resp = await IPCAPI.getInstance().savePod<any>(values);
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
    const resp = await IPCAPI.getInstance().deletePod<any>(pod.id);
    if (resp?.success) {
      message.success('Pod deleted');
      load();
    } else {
      message.error(resp?.error?.message || 'Failed to delete pod');
    }
  };

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
    <Card
      size="small"
      title={
        <Space>
          <span>Pods</span>
          {limits && (
            <Text type="secondary" style={{ fontWeight: 400 }}>
              {limits.used_pods} of {limits.max_pods} · about ¥{totalMonthly.toFixed(0)}/month
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
        {pods.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="No pods. Agents run on this machine until you create one."
          />
        ) : (
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
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
                        {/* Observed, not desired: what the fleet reports today */}
                        <Tag color={statusColor(pod.status)}>{pod.status || 'offline'}</Tag>
                        <Text type="secondary">{heartbeatLabel(pod)}</Text>
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
  );
};

export default PodsPanel;
